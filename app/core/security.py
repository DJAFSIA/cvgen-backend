import hashlib
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import http_error

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

http_bearer = HTTPBearer()

async def get_token(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> str:
    return credentials.credentials

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), db: Session = Depends(get_db)):
    from app.models.utilisateur import Utilisateur
    credentials_exception = http_error(401, "invalid_token", "Token invalide ou expiré")
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        # Un jeton d'action (verification d'email, reinitialisation) n'ouvre jamais une session
        if user_id is None or payload.get("purpose"):
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(Utilisateur).filter(Utilisateur.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def password_fingerprint(hashed_password: str) -> str:
    """Empreinte du mot de passe actuel : lie un jeton de reinitialisation a un seul usage."""
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()[:16]


def create_purpose_token(subject: str, purpose: str, minutes: int, **claims) -> str:
    payload = {"sub": subject, "purpose": purpose, **claims,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_purpose_token(token: str, purpose: str) -> dict:
    """Leve JWTError si le jeton est invalide, expire ou destine a un autre usage."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("purpose") != purpose or not payload.get("sub"):
        raise JWTError("mauvais usage du jeton")
    return payload


def get_verified_user(current_user=Depends(get_current_user)):
    """Les fonctions payantes (appels IA) exigent un email confirme : frein aux comptes jetables."""
    if settings.REQUIRE_EMAIL_VERIFICATION and not current_user.email_verifie:
        raise http_error(403, "email_not_verified", "Confirmez votre adresse email pour utiliser cette fonction.")
    return current_user
