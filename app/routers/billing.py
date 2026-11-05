"""Abonnement Pro : cartes bancaires via Stripe (abonnement mensuel), MTN Mobile Money /
Orange Money via Flutterwave (pass de N jours paye en une fois).

Regle d'or : aucun acces n'est accorde sur la seule foi d'une redirection ou d'un webhook.
Chaque paiement est reverifie aupres du fournisseur, et la reference unique de la table
paiements empeche de crediter deux fois le meme paiement.
"""
import asyncio
import hmac
import logging
import uuid
from datetime import datetime, timezone

import httpx
import stripe
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import http_error
from app.core.rate_limit import payment_limiter
from app.core.security import get_current_user
from app.models.facturation import Paiement
from app.models.utilisateur import Utilisateur
from app.services import billing

router = APIRouter()
logger = logging.getLogger(__name__)

FLW_API = "https://api.flutterwave.com/v3"


# --- Etat de l'abonnement ----------------------------------------------------
def _offre_publique() -> dict:
    return {
        "limites": {"free": billing.limites("free"), "pro": billing.limites("pro")},
        "stripe": {
            "actif": bool(settings.STRIPE_SECRET_KEY),
            "prix": billing.parse_prix(settings.PRO_STRIPE_PRICES),
        },
        "mobile_money": {
            "actif": bool(settings.FLUTTERWAVE_SECRET_KEY),
            "prix": billing.parse_prix(settings.MOMO_PRICES),
            "jours": settings.MOMO_DAYS,
        },
    }


@router.get("/plans")
def plans():
    """Public : alimente la page de tarifs."""
    return _offre_publique()


@router.get("/me")
def mon_abonnement(db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user)):
    usage = billing.usage_courant(db, current_user)
    plan = billing.plan_effectif(current_user)
    return {
        "plan": plan,
        "expire_le": current_user.plan_expire_le if plan == "pro" else None,
        "renouvellement_auto": bool(current_user.stripe_subscription_id),
        "peut_gerer_carte": bool(current_user.stripe_customer_id and settings.STRIPE_SECRET_KEY),
        "usage": {t: getattr(usage, t) for t in billing.TYPES_USAGE},
        "limites": billing.limites(plan),
        **{"offre": _offre_publique()},
    }


# --- Stripe (cartes bancaires, abonnement mensuel) ----------------------------
def _stripe_actif() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise http_error(503, "payment_unavailable", "Paiement par carte non configure")


def _en_dict(objet):
    """Les objets du SDK Stripe (v13+) ne sont plus des dict : on travaille sur des dict simples."""
    return objet.to_dict() if hasattr(objet, "to_dict") else objet


async def _stripe(appel, *args, **kwargs):
    """Le SDK Stripe est synchrone : on l'execute hors de la boucle d'evenements."""
    try:
        return _en_dict(await asyncio.to_thread(appel, *args, api_key=settings.STRIPE_SECRET_KEY, **kwargs))
    except stripe.StripeError as e:
        logger.error("Erreur Stripe: %s", e)
        raise http_error(502, "payment_provider_error", "Le service de paiement a renvoye une erreur")


# "incomplete" exclu : un 3D Secure abandonne ne doit pas bloquer une nouvelle tentative
STATUTS_ACTIFS = ("active", "trialing", "past_due")


def _retirer_pro(utilisateur: Utilisateur, raison: str) -> None:
    """Remboursement total ou contestation bancaire : le Pro s'arrete immediatement."""
    logger.warning("Plan Pro retire a %s (%s)", utilisateur.id, raison)
    utilisateur.plan_expire_le = datetime.now(timezone.utc)


class StripeCheckoutRequest(BaseModel):
    devise: str = Field(default="eur", max_length=3)


@router.post("/stripe/checkout", dependencies=[payment_limiter.by_user()])
async def stripe_checkout(
    data: StripeCheckoutRequest, db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user),
):
    _stripe_actif()
    if current_user.stripe_subscription_id and billing.est_pro(current_user):
        raise http_error(409, "already_subscribed", "Vous avez deja un abonnement actif")
    prix = billing.parse_prix(settings.PRO_STRIPE_PRICES)
    devise = data.devise.lower()
    if not settings.STRIPE_PRICE_ID and devise not in prix:
        raise http_error(400, "currency_unsupported", "Devise non proposee")

    if current_user.stripe_customer_id:
        # Source de verite : Stripe (couvre un abonnement cree dans un autre onglet)
        existants = await _stripe(stripe.Subscription.list, customer=current_user.stripe_customer_id, status="all", limit=10)
        if any(a.get("status") in STATUTS_ACTIFS for a in existants.get("data", [])):
            raise http_error(409, "already_subscribed", "Vous avez deja un abonnement actif")
    else:
        client = await _stripe(
            stripe.Customer.create, email=current_user.email,
            name=f"{current_user.prenom} {current_user.nom}", metadata={"user_id": str(current_user.id)},
        )
        current_user.stripe_customer_id = client["id"]
        db.commit()

    ligne = (
        {"price": settings.STRIPE_PRICE_ID, "quantity": 1}
        if settings.STRIPE_PRICE_ID else
        {"quantity": 1, "price_data": {
            "currency": devise, "unit_amount": prix[devise],
            "recurring": {"interval": "month"}, "product_data": {"name": "Apply Pro"},
        }}
    )
    params = {
        "mode": "subscription",
        "customer": current_user.stripe_customer_id,
        "client_reference_id": str(current_user.id),
        "metadata": {"user_id": str(current_user.id)},
        "subscription_data": {"metadata": {"user_id": str(current_user.id)}},
        "line_items": [ligne],
        "allow_promotion_codes": True,
        "locale": "auto",
        "success_url": f"{settings.FRONTEND_URL}/abonnement?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.FRONTEND_URL}/abonnement?checkout=cancel",
    }
    if settings.STRIPE_AUTOMATIC_TAX:
        params["automatic_tax"] = {"enabled": True}
        params["customer_update"] = {"address": "auto", "name": "auto"}
    session = await _stripe(stripe.checkout.Session.create, **params)
    return {"url": session["url"]}


async def _activer_depuis_session(db: Session, session) -> Utilisateur | None:
    user_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
    utilisateur = db.query(Utilisateur).filter(Utilisateur.id == user_id).first() if user_id else None
    if not utilisateur or session.get("status") != "complete" or not session.get("subscription"):
        return None
    sub_id = session["subscription"] if isinstance(session["subscription"], str) else session["subscription"]["id"]
    abonnement = await _stripe(stripe.Subscription.retrieve, sub_id)
    utilisateur.stripe_customer_id = utilisateur.stripe_customer_id or session.get("customer")
    billing.appliquer_abonnement_stripe(utilisateur, abonnement)
    db.commit()
    return utilisateur


class StripeConfirmRequest(BaseModel):
    session_id: str = Field(min_length=5, max_length=255)


@router.post("/stripe/confirm", dependencies=[payment_limiter.by_user()])
async def stripe_confirm(
    data: StripeConfirmRequest, db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user),
):
    """Appele au retour du checkout : active le Pro sans attendre le webhook."""
    _stripe_actif()
    session = await _stripe(stripe.checkout.Session.retrieve, data.session_id)
    if session.get("client_reference_id") != str(current_user.id):
        raise http_error(404, "payment_not_found", "Paiement introuvable")
    await _activer_depuis_session(db, session)
    db.refresh(current_user)
    return {"plan": billing.plan_effectif(current_user), "expire_le": current_user.plan_expire_le}


@router.post("/stripe/portal", dependencies=[payment_limiter.by_user()])
async def stripe_portal(current_user: Utilisateur = Depends(get_current_user)):
    """Portail Stripe : changer de carte, telecharger les factures, resilier."""
    _stripe_actif()
    if not current_user.stripe_customer_id:
        raise http_error(404, "payment_not_found", "Aucun abonnement par carte")
    portail = await _stripe(
        stripe.billing_portal.Session.create,
        customer=current_user.stripe_customer_id, return_url=f"{settings.FRONTEND_URL}/abonnement",
    )
    return {"url": portail["url"]}


def _abonnement_de_facture(facture) -> str | None:
    parent = facture.get("parent") or {}
    details = parent.get("subscription_details") or {}
    return details.get("subscription") or facture.get("subscription")


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise http_error(503, "payment_unavailable", "Webhook Stripe non configure")
    payload = await request.body()
    try:
        event = _en_dict(stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature"), settings.STRIPE_WEBHOOK_SECRET))
    except (ValueError, stripe.SignatureVerificationError):
        raise http_error(400, "invalid_signature", "Signature invalide")

    objet = event["data"]["object"]
    type_evt = event["type"]

    if type_evt == "checkout.session.completed":
        await _activer_depuis_session(db, objet)

    elif type_evt == "invoice.paid":
        utilisateur = db.query(Utilisateur).filter(Utilisateur.stripe_customer_id == objet.get("customer")).first()
        sub_id = _abonnement_de_facture(objet)
        if utilisateur and sub_id:
            if not db.query(Paiement).filter(Paiement.reference == objet["id"]).first():
                db.add(Paiement(
                    utilisateur_id=utilisateur.id, fournisseur="stripe", reference=objet["id"],
                    montant=objet.get("amount_paid") or 0, devise=(objet.get("currency") or "").upper()[:3],
                    statut="paid", paye_le=datetime.now(timezone.utc),
                ))
            billing.appliquer_abonnement_stripe(utilisateur, await _stripe(stripe.Subscription.retrieve, sub_id))
            db.commit()

    elif type_evt == "charge.refunded":
        # Remboursement total uniquement : un geste commercial partiel ne retire pas le Pro
        if objet.get("refunded"):
            utilisateur = db.query(Utilisateur).filter(Utilisateur.stripe_customer_id == objet.get("customer")).first()
            if utilisateur:
                _retirer_pro(utilisateur, f"remboursement {objet.get('id')}")
                db.commit()

    elif type_evt == "charge.dispute.created":
        charge = await _stripe(stripe.Charge.retrieve, objet.get("charge"))
        utilisateur = db.query(Utilisateur).filter(Utilisateur.stripe_customer_id == charge.get("customer")).first()
        if utilisateur:
            _retirer_pro(utilisateur, f"contestation {objet.get('id')}")
            db.commit()

    elif type_evt in ("customer.subscription.updated", "customer.subscription.deleted"):
        utilisateur = db.query(Utilisateur).filter(Utilisateur.stripe_customer_id == objet.get("customer")).first()
        if utilisateur:
            billing.appliquer_abonnement_stripe(utilisateur, objet)
            db.commit()

    return {"received": True}


# --- Flutterwave (MTN Mobile Money, Orange Money...) --------------------------
def _flw_actif() -> None:
    if not settings.FLUTTERWAVE_SECRET_KEY:
        raise http_error(503, "payment_unavailable", "Paiement Mobile Money non configure")


async def _flw(methode: str, chemin: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            reponse = await client.request(methode, f"{FLW_API}{chemin}", headers=headers, **kwargs)
    except httpx.HTTPError as e:
        logger.error("Flutterwave injoignable: %s", e)
        raise http_error(502, "payment_provider_error", "Le service de paiement est injoignable")
    corps = reponse.json() if reponse.headers.get("content-type", "").startswith("application/json") else {}
    if reponse.status_code >= 400 or corps.get("status") != "success":
        logger.error("Erreur Flutterwave %s %s: %s", reponse.status_code, chemin, str(corps)[:300])
        raise http_error(502, "payment_provider_error", "Le service de paiement a renvoye une erreur")
    return corps.get("data") or {}


class MomoCheckoutRequest(BaseModel):
    devise: str = Field(default="XAF", max_length=3)


@router.post("/momo/checkout", dependencies=[payment_limiter.by_user()])
async def momo_checkout(
    data: MomoCheckoutRequest, db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user),
):
    _flw_actif()
    prix = billing.parse_prix(settings.MOMO_PRICES)
    devise = data.devise.upper()
    if devise not in prix:
        raise http_error(400, "currency_unsupported", "Devise non proposee")

    tx_ref = f"apply-{uuid.uuid4().hex}"
    db.add(Paiement(
        utilisateur_id=current_user.id, fournisseur="flutterwave", reference=tx_ref,
        montant=prix[devise], devise=devise, statut="pending", jours=settings.MOMO_DAYS,
    ))
    db.commit()

    lien = await _flw("POST", "/payments", json={
        "tx_ref": tx_ref,
        "amount": prix[devise],
        "currency": devise,
        "redirect_url": f"{settings.FRONTEND_URL}/abonnement/mobile-money",
        "customer": {"email": current_user.email, "name": f"{current_user.prenom} {current_user.nom}"},
        "customizations": {"title": "Apply Pro", "description": f"Plan Pro - {settings.MOMO_DAYS} jours"},
        "meta": {"user_id": str(current_user.id)},
    })
    return {"url": lien.get("link")}


async def _crediter_flutterwave(db: Session, transaction_id: str) -> Paiement | None:
    """Verifie la transaction aupres de Flutterwave puis credite (une seule fois)."""
    transaction = await _flw("GET", f"/transactions/{transaction_id}/verify")
    tx_ref = transaction.get("tx_ref")
    paiement = (
        db.query(Paiement)
        .filter(Paiement.reference == tx_ref, Paiement.fournisseur == "flutterwave")
        .with_for_update()
        .first()
    )
    if not paiement:
        logger.warning("Transaction Flutterwave %s sans paiement connu (%s)", transaction_id, tx_ref)
        return None
    if paiement.statut == "paid":
        return paiement

    valide = (
        transaction.get("status") == "successful"
        and str(transaction.get("currency", "")).upper() == paiement.devise
        and float(transaction.get("amount") or 0) >= paiement.montant
    )
    paiement.details = {"transaction_id": transaction.get("id"), "status": transaction.get("status"),
                        "payment_type": transaction.get("payment_type")}
    if not valide:
        if transaction.get("status") in ("failed", "cancelled"):
            paiement.statut = "failed"
        db.commit()
        return paiement

    paiement.statut = "paid"
    paiement.paye_le = datetime.now(timezone.utc)
    utilisateur = (
        db.query(Utilisateur).filter(Utilisateur.id == paiement.utilisateur_id).first()
        if paiement.utilisateur_id else None
    )
    if utilisateur:
        billing.prolonger_pro(utilisateur, paiement.jours or settings.MOMO_DAYS)
    else:
        # Compte supprime entre le paiement et sa confirmation : rien a crediter
        logger.warning("Paiement %s confirme pour un compte supprime", paiement.reference)
    db.commit()
    return paiement


class MomoConfirmRequest(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=64)


@router.post("/momo/confirm", dependencies=[payment_limiter.by_user()])
async def momo_confirm(
    data: MomoConfirmRequest, db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user),
):
    """Appele au retour de la page de paiement Flutterwave."""
    _flw_actif()
    if not data.transaction_id.isdigit():
        raise http_error(400, "payment_not_found", "Paiement introuvable")
    paiement = await _crediter_flutterwave(db, data.transaction_id)
    if not paiement or paiement.utilisateur_id != current_user.id:
        raise http_error(404, "payment_not_found", "Paiement introuvable")
    db.refresh(current_user)
    return {
        "statut": paiement.statut,
        "plan": billing.plan_effectif(current_user),
        "expire_le": current_user.plan_expire_le,
    }


@router.post("/momo/webhook", include_in_schema=False)
async def momo_webhook(request: Request, db: Session = Depends(get_db)):
    """Filet de securite si l'utilisateur ferme la page avant la redirection."""
    attendu = settings.FLUTTERWAVE_WEBHOOK_HASH
    recu = request.headers.get("verif-hash") or ""
    if not attendu or not hmac.compare_digest(recu, attendu):
        raise http_error(401, "invalid_signature", "Signature invalide")
    corps = await request.json()
    transaction_id = str((corps.get("data") or {}).get("id") or "")
    if transaction_id.isdigit():
        await _crediter_flutterwave(db, transaction_id)
    return {"received": True}
