"""Plans, quotas mensuels et activation du plan Pro (Stripe ou Mobile Money)."""
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import http_error
from app.core.security import get_current_user
from app.models.facturation import Usage

TYPES_USAGE = ("generations", "analyses", "imports")
# Marge apres la date de renouvellement Stripe, le temps que le paiement aboutisse
GRACE_STRIPE = timedelta(days=2)


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def periode_courante() -> str:
    return maintenant().strftime("%Y-%m")


def limites(plan: str) -> dict:
    if plan == "pro":
        return {"generations": settings.PRO_GENERATIONS, "analyses": settings.PRO_ANALYSES, "imports": settings.PRO_IMPORTS}
    return {"generations": settings.FREE_GENERATIONS, "analyses": settings.FREE_ANALYSES, "imports": settings.FREE_IMPORTS}


def est_pro(utilisateur) -> bool:
    if utilisateur.plan != "pro":
        return False
    return utilisateur.plan_expire_le is None or utilisateur.plan_expire_le > maintenant()


def plan_effectif(utilisateur) -> str:
    return "pro" if est_pro(utilisateur) else "free"


def usage_courant(db: Session, utilisateur) -> Usage:
    periode = periode_courante()
    usage = db.query(Usage).filter(Usage.utilisateur_id == utilisateur.id, Usage.periode == periode).first()
    if usage:
        return usage
    try:
        usage = Usage(utilisateur_id=utilisateur.id, periode=periode, generations=0, analyses=0, imports=0)
        db.add(usage)
        db.commit()
    except IntegrityError:
        # Creation concurrente par une autre requete : on relit la ligne existante
        db.rollback()
        usage = db.query(Usage).filter(Usage.utilisateur_id == utilisateur.id, Usage.periode == periode).one()
    return usage


def verifier_quota(db: Session, utilisateur, type_usage: str) -> None:
    usage = usage_courant(db, utilisateur)
    plan = plan_effectif(utilisateur)
    if getattr(usage, type_usage) >= limites(plan)[type_usage]:
        raise http_error(
            402, "quota_exceeded",
            "Quota mensuel atteint pour votre plan. Passez au plan Pro pour continuer.",
        )


def consommer(db: Session, utilisateur, type_usage: str) -> None:
    """Incremente le compteur de facon atomique (pas de perte en cas de requetes paralleles)."""
    usage_courant(db, utilisateur)
    db.execute(
        update(Usage)
        .where(Usage.utilisateur_id == utilisateur.id, Usage.periode == periode_courante())
        .values({type_usage: getattr(Usage, type_usage) + 1})
    )
    db.commit()


def quota(type_usage: str):
    """Dependance FastAPI : refuse la requete (402) si le quota du mois est atteint."""
    assert type_usage in TYPES_USAGE

    def dependance(db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> None:
        verifier_quota(db, current_user, type_usage)
    return Depends(dependance)


def prolonger_pro(utilisateur, jours: int) -> None:
    """Paiement ponctuel (Mobile Money) : ajoute des jours a partir de la fin du plan en cours."""
    base = utilisateur.plan_expire_le if est_pro(utilisateur) and utilisateur.plan_expire_le else maintenant()
    utilisateur.plan = "pro"
    utilisateur.plan_expire_le = base + timedelta(days=jours)


def fin_de_periode_stripe(abonnement) -> datetime | None:
    """La date de fin de periode est sur les elements de l'abonnement dans les versions recentes de l'API."""
    fin = None
    try:
        elements = abonnement["items"]["data"]
        if elements:
            fin = elements[0].get("current_period_end")
    except (KeyError, TypeError):
        pass
    fin = fin or abonnement.get("current_period_end")
    return datetime.fromtimestamp(fin, tz=timezone.utc) if fin else None


def appliquer_abonnement_stripe(utilisateur, abonnement) -> None:
    statut = abonnement.get("status")
    fin = fin_de_periode_stripe(abonnement)
    if statut in ("active", "trialing", "past_due"):
        utilisateur.plan = "pro"
        utilisateur.stripe_subscription_id = abonnement.get("id")
        if fin:
            nouvelle_fin = fin + GRACE_STRIPE
            # Ne raccourcit jamais des jours deja payes en Mobile Money
            if not utilisateur.plan_expire_le or nouvelle_fin > utilisateur.plan_expire_le:
                utilisateur.plan_expire_le = nouvelle_fin
    else:
        # Abonnement termine : l'utilisateur garde le Pro jusqu'a la fin deja payee
        utilisateur.stripe_subscription_id = None
        if fin and (not utilisateur.plan_expire_le or utilisateur.plan_expire_le > fin):
            utilisateur.plan_expire_le = fin


def parse_prix(brut: str) -> dict:
    """'eur:799,usd:899' -> {'eur': 799, 'usd': 899}"""
    prix = {}
    for morceau in brut.split(","):
        if ":" in morceau:
            devise, montant = morceau.split(":", 1)
            prix[devise.strip()] = int(montant.strip())
    return prix
