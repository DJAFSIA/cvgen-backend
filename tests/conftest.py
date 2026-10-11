"""Base de donnees de test jetable : creee au debut de la session, supprimee a la fin.

- En CI : TEST_DATABASE_URL pointe vers une base dediee (service PostgreSQL).
- En local : la base "<nom>_test" est creee sur le serveur de DATABASE_URL (.env).
Aucun appel reseau : Stripe, Flutterwave, Google et l'IA sont simules dans les tests.
"""
import os
import uuid
from urllib.parse import urlparse, urlunparse

import psycopg2
import pytest
from dotenv import dotenv_values


def _url_test() -> str:
    if os.getenv("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    base = os.getenv("DATABASE_URL") or dotenv_values(".env").get("DATABASE_URL")
    if not base:
        raise RuntimeError("Definissez TEST_DATABASE_URL ou DATABASE_URL pour lancer les tests")
    u = urlparse(base)
    return urlunparse(u._replace(path=f"{u.path}_test"))


TEST_URL = _url_test()

# Configuration figee AVANT l'import de l'application
os.environ.update({
    "DATABASE_URL": TEST_URL,
    "ENV": "development",
    "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789",
    "MAIL_BACKEND": "console",
    "LLM_PROVIDERS": "gemini",
    "GEMINI_API_KEY": "",
    "STRIPE_SECRET_KEY": "",
    "FLUTTERWAVE_SECRET_KEY": "",
    "GOOGLE_CLIENT_ID": "",
    "FREE_GENERATIONS": "3",
})


def _admin(url: str):
    u = urlparse(url)
    conn = psycopg2.connect(urlunparse(u._replace(path="/postgres")))
    conn.autocommit = True
    return conn, u.path.lstrip("/")


@pytest.fixture(scope="session", autouse=True)
def base_de_test():
    recreer = not os.getenv("TEST_DATABASE_URL")
    if recreer:
        conn, nom = _admin(TEST_URL)
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')
            cur.execute(f'CREATE DATABASE "{nom}"')
        conn.close()

    from alembic import command
    from alembic.config import Config
    command.upgrade(Config("alembic.ini"), "head")
    yield

    from app.core.database import engine
    engine.dispose()
    if recreer:
        conn, nom = _admin(TEST_URL)
        with conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')
        conn.close()


@pytest.fixture(autouse=True)
def limites_reinitialisees():
    """Les limiteurs de debit sont en memoire : on les vide entre les tests."""
    from app.core import rate_limit
    for objet in vars(rate_limit).values():
        if isinstance(objet, rate_limit.RateLimiter):
            objet._hits.clear()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture
def db():
    from app.core.database import SessionLocal
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def make_user(db):
    """Cree un utilisateur (avec profil) et renvoie (utilisateur, en-tetes d'authentification)."""
    from app.core.security import create_access_token
    from app.models.profil import Profil
    from app.models.utilisateur import Utilisateur

    def fabrique(verifie: bool = True, **champs):
        u = Utilisateur(
            nom=champs.pop("nom", "Test"), prenom="User", mot_de_passe="x",
            email=champs.pop("email", f"u-{uuid.uuid4().hex[:10]}@example.com"),
            email_verifie=verifie, **champs,
        )
        db.add(u)
        db.flush()
        db.add(Profil(utilisateur_id=u.id))
        db.commit()
        db.refresh(u)
        return u, {"Authorization": "Bearer " + create_access_token({"sub": str(u.id)})}

    return fabrique


def code(reponse) -> str | None:
    """Code d'erreur stable d'une reponse ({detail: {code}})."""
    detail = reponse.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None
