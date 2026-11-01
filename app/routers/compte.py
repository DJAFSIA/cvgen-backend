"""Compte : rectification (nom, langue), export des donnees, suppression definitive."""
import asyncio
import logging
from datetime import date
from typing import Literal, Optional

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import http_error
from app.core.rate_limit import compte_limiter, export_limiter, suppression_limiter
from app.core.security import get_current_user, verify_password
from app.models.utilisateur import Utilisateur
from app.schemas.utilisateur import UtilisateurResponse
from app.services import compte_service
from app.services.mail_service import send_notification_email

router = APIRouter()
logger = logging.getLogger(__name__)


class CompteUpdate(BaseModel):
    # Espaces retires AVANT la verification de longueur : "   " est refuse
    model_config = ConfigDict(str_strip_whitespace=True)

    prenom: Optional[str] = Field(default=None, min_length=1, max_length=100)
    nom: Optional[str] = Field(default=None, min_length=1, max_length=100)
    langue: Optional[Literal["en", "fr"]] = None


class SuppressionRequest(BaseModel):
    # Compte email : mot de passe actuel. Compte Google (sans mot de passe connu) : son adresse email.
    mot_de_passe: Optional[str] = Field(default=None, max_length=72)
    confirmation: Optional[str] = Field(default=None, max_length=255)


@router.patch("/", response_model=UtilisateurResponse, dependencies=[compte_limiter.by_user()])
def modifier_compte(data: CompteUpdate, db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user)):
    """Droit de rectification : prenom, nom, langue des emails."""
    for champ, valeur in data.model_dump(exclude_unset=True).items():
        if valeur is not None:
            setattr(current_user, champ, valeur)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/export", dependencies=[export_limiter.by_user()])
def exporter_donnees(db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user)):
    """Droits d'acces et a la portabilite : toutes les donnees du compte en JSON."""
    donnees = compte_service.exporter(db, current_user)
    nom_fichier = f"cvgen-export-{date.today().isoformat()}.json"
    return JSONResponse(
        content=jsonable_encoder(donnees),
        headers={"Content-Disposition": f'attachment; filename="{nom_fichier}"', "Cache-Control": "no-store"},
    )


async def _arreter_facturation_stripe(u: Utilisateur) -> None:
    """Supprime le client Stripe : tout abonnement en cours s'arrete immediatement et les moyens
    de paiement enregistres sont effaces (les factures restent chez Stripe pour la comptabilite).
    Si l'arret echoue, le compte n'est PAS supprime : la personne ne doit pas continuer a payer."""
    if not u.stripe_customer_id:
        return
    if not settings.STRIPE_SECRET_KEY:
        if u.stripe_subscription_id:
            raise http_error(503, "payment_unavailable", "Impossible d'arreter l'abonnement pour le moment, contactez le support.")
        return
    try:
        await asyncio.to_thread(stripe.Customer.delete, u.stripe_customer_id, api_key=settings.STRIPE_SECRET_KEY)
    except stripe.InvalidRequestError as e:
        if getattr(e, "code", None) != "resource_missing":  # deja supprime chez Stripe : rien a arreter
            logger.error("Suppression du client Stripe %s impossible: %s", u.stripe_customer_id, e)
            raise http_error(502, "payment_provider_error", "Le service de paiement a renvoye une erreur")
    except stripe.StripeError as e:
        logger.error("Suppression du client Stripe %s impossible: %s", u.stripe_customer_id, e)
        raise http_error(502, "payment_provider_error", "Le service de paiement a renvoye une erreur")


@router.post("/supprimer", dependencies=[suppression_limiter.by_user()])
async def supprimer_compte(
    data: SuppressionRequest, background: BackgroundTasks,
    db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user),
):
    """Droit a l'effacement : suppression definitive du compte et de son contenu."""
    if current_user.provider == "google":
        if (data.confirmation or "").strip().lower() != current_user.email.lower():
            raise http_error(400, "confirmation_invalid", "Saisissez votre adresse email pour confirmer")
    elif not data.mot_de_passe or not verify_password(data.mot_de_passe, current_user.mot_de_passe):
        raise http_error(400, "wrong_password", "Mot de passe incorrect")

    await _arreter_facturation_stripe(current_user)

    email, langue, uid = current_user.email, current_user.langue, current_user.id
    compte_service.supprimer(db, uid)
    logger.info("Compte %s supprime a la demande de son titulaire", uid)
    # Notification de securite : prevenir la personne si ce n'est pas elle qui a supprime le compte
    background.add_task(send_notification_email, "deleted", email, langue)
    return {"supprime": True}
