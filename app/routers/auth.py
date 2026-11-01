import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import http_error
from app.core.rate_limit import (
    forgot_limiter, google_limiter, inscription_limiter, login_limiter, resend_limiter,
    reset_limiter, verify_limiter,
)
from app.core.security import (
    create_access_token, create_purpose_token, decode_purpose_token, get_current_user,
    hash_password, password_fingerprint, verify_password,
)
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur
from app.schemas.utilisateur import (
    ForgotPasswordRequest, GoogleLoginRequest, ResetPasswordRequest, Token, UtilisateurCreate,
    UtilisateurLogin, UtilisateurResponse, VerifyEmailRequest,
)
from app.services.mail_service import send_action_email

router = APIRouter()
logger = logging.getLogger(__name__)

VERIFY_PURPOSE = "verify_email"
RESET_PURPOSE = "reset_password"
GOOGLE_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"


def _lien(chemin: str, token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}{chemin}?token={quote(token)}"


def _envoyer_verification(background: BackgroundTasks, utilisateur: Utilisateur) -> None:
    token = create_purpose_token(str(utilisateur.id), VERIFY_PURPOSE, minutes=48 * 60, email=utilisateur.email)
    background.add_task(send_action_email, "verify", utilisateur.email, utilisateur.langue, _lien("/verify-email", token))


def _session(utilisateur: Utilisateur) -> Token:
    return Token(access_token=create_access_token({"sub": str(utilisateur.id)}), utilisateur=utilisateur)


@router.post("/inscription", response_model=Token, status_code=201, dependencies=[inscription_limiter.by_ip()])
def inscription(data: UtilisateurCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not data.accepte_cgu:
        raise http_error(400, "terms_required", "Vous devez accepter les conditions d'utilisation")
    existant = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
    if existant:
        raise http_error(400, "email_taken", "Cet email est déjà utilisé")

    utilisateur = Utilisateur(
        nom=data.nom,
        prenom=data.prenom,
        email=data.email,
        mot_de_passe=hash_password(data.mot_de_passe),
        langue=data.langue,
        email_verifie=False,
        cgu_acceptees_le=datetime.now(timezone.utc),
        cgu_version=settings.CGU_VERSION,
    )
    db.add(utilisateur)
    db.flush()
    db.add(Profil(utilisateur_id=utilisateur.id))
    db.commit()
    db.refresh(utilisateur)

    _envoyer_verification(background, utilisateur)
    return _session(utilisateur)


@router.post("/login", response_model=Token, dependencies=[login_limiter.by_ip()])
def login(data: UtilisateurLogin, db: Session = Depends(get_db)):
    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
    if not utilisateur or not verify_password(data.mot_de_passe, utilisateur.mot_de_passe):
        raise http_error(401, "bad_credentials", "Email ou mot de passe incorrect")
    utilisateur.derniere_connexion = datetime.now(timezone.utc)
    db.commit()
    return _session(utilisateur)


@router.get("/me", response_model=UtilisateurResponse)
def me(current_user: Utilisateur = Depends(get_current_user)):
    return current_user


# --- Verification de l'email -------------------------------------------------
@router.post("/verify-email", response_model=UtilisateurResponse, dependencies=[verify_limiter.by_ip()])
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_purpose_token(data.token, VERIFY_PURPOSE)
    except JWTError:
        raise http_error(400, "invalid_link", "Lien invalide ou expiré")
    utilisateur = db.query(Utilisateur).filter(Utilisateur.id == payload["sub"]).first()
    # Le jeton est lie a l'adresse : si l'email a change depuis, il ne vaut plus rien
    if not utilisateur or payload.get("email") != utilisateur.email:
        raise http_error(400, "invalid_link", "Lien invalide ou expiré")
    if not utilisateur.email_verifie:
        utilisateur.email_verifie = True
        db.commit()
    return utilisateur


@router.post("/resend-verification", status_code=202, dependencies=[resend_limiter.by_user()])
def resend_verification(
    background: BackgroundTasks, current_user: Utilisateur = Depends(get_current_user),
):
    if not current_user.email_verifie:
        _envoyer_verification(background, current_user)
    return {"sent": not current_user.email_verifie}


# --- Mot de passe oublie -----------------------------------------------------
@router.post("/forgot-password", status_code=202, dependencies=[forgot_limiter.by_ip()])
def forgot_password(data: ForgotPasswordRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Reponse identique que le compte existe ou non (pas d'enumeration des emails)."""
    utilisateur = db.query(Utilisateur).filter(Utilisateur.email == data.email).first()
    if utilisateur:
        token = create_purpose_token(
            str(utilisateur.id), RESET_PURPOSE, minutes=60, pw=password_fingerprint(utilisateur.mot_de_passe),
        )
        lang = data.langue or utilisateur.langue
        background.add_task(send_action_email, "reset", utilisateur.email, lang, _lien("/reset-password", token))
    return {"sent": True}


@router.post("/reset-password", dependencies=[reset_limiter.by_ip()])
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_purpose_token(data.token, RESET_PURPOSE)
    except JWTError:
        raise http_error(400, "invalid_link", "Lien invalide ou expiré")
    utilisateur = db.query(Utilisateur).filter(Utilisateur.id == payload["sub"]).first()
    # Le jeton embarque une empreinte de l'ancien mot de passe : il ne sert qu'une seule fois
    if not utilisateur or payload.get("pw") != password_fingerprint(utilisateur.mot_de_passe):
        raise http_error(400, "invalid_link", "Lien invalide ou expiré")
    utilisateur.mot_de_passe = hash_password(data.mot_de_passe)
    # Recevoir ce lien prouve la possession de la boite mail
    utilisateur.email_verifie = True
    db.commit()
    return {"ok": True}


# --- Connexion avec Google ---------------------------------------------------
@router.post("/google", response_model=Token, dependencies=[google_limiter.by_ip()])
async def google_login(data: GoogleLoginRequest, db: Session = Depends(get_db)):
    if not settings.GOOGLE_CLIENT_ID:
        raise http_error(503, "google_disabled", "Connexion Google non configurée")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            reponse = await client.get(GOOGLE_TOKENINFO, params={"id_token": data.credential})
    except httpx.HTTPError:
        raise http_error(502, "google_unreachable", "Google est injoignable")
    if reponse.status_code != 200:
        raise http_error(401, "google_invalid", "Connexion Google refusée")
    info = reponse.json()
    if info.get("aud") != settings.GOOGLE_CLIENT_ID or str(info.get("email_verified")).lower() != "true":
        raise http_error(401, "google_invalid", "Connexion Google refusée")

    email, google_id = info.get("email"), info.get("sub")
    if not email or not google_id:
        raise http_error(401, "google_invalid", "Connexion Google refusée")

    utilisateur = db.query(Utilisateur).filter(Utilisateur.google_id == google_id).first()
    if not utilisateur:
        utilisateur = db.query(Utilisateur).filter(Utilisateur.email == email).first()
        if utilisateur:
            # Compte existant : Google a verifie l'adresse, on le rattache
            utilisateur.google_id = google_id
            utilisateur.email_verifie = True
        else:
            utilisateur = Utilisateur(
                nom=(info.get("family_name") or info.get("name") or "-")[:100],
                prenom=(info.get("given_name") or info.get("name") or "-")[:100],
                email=email,
                mot_de_passe=hash_password(secrets.token_urlsafe(32)),
                provider="google",
                google_id=google_id,
                email_verifie=True,
                langue=data.langue,
                # Le bouton Google est accompagne de la mention d'acceptation des conditions
                cgu_acceptees_le=datetime.now(timezone.utc),
                cgu_version=settings.CGU_VERSION,
            )
            db.add(utilisateur)
            db.flush()
            db.add(Profil(utilisateur_id=utilisateur.id))
    utilisateur.derniere_connexion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(utilisateur)
    return _session(utilisateur)
