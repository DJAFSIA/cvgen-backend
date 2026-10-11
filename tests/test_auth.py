import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import app.routers.auth as auth
from app.core.config import settings
from conftest import code


@pytest.fixture
def emails(monkeypatch):
    envoyes = []

    async def faux_envoi(kind, to, lang, link):
        envoyes.append({"kind": kind, "to": to, "lang": lang, "token": parse_qs(urlparse(link).query)["token"][0]})

    monkeypatch.setattr(auth, "send_action_email", faux_envoi)
    return envoyes


def inscrire(client, email, mdp="FirstPass-7731", langue="fr"):
    return client.post("/auth/inscription", json={"nom": "T", "prenom": "U", "email": email, "mot_de_passe": mdp, "langue": langue})


def test_inscription_puis_verification(client, emails):
    email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    r = inscrire(client, email)
    assert r.status_code == 201 and r.json()["utilisateur"]["email_verifie"] is False
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert emails[-1]["kind"] == "verify" and emails[-1]["lang"] == "fr"

    # Les fonctions IA sont fermees tant que l'email n'est pas confirme
    r = client.post("/offre/extraire", json={"url": "http://169.254.169.254/"}, headers=h)
    assert r.status_code == 403 and code(r) == "email_not_verified"

    assert client.post("/auth/verify-email", json={"token": "x" * 20}).status_code == 400
    r = client.post("/auth/verify-email", json={"token": emails[-1]["token"]})
    assert r.status_code == 200 and r.json()["email_verifie"] is True

    # Ouvertes ensuite (puis l'URL interne est bloquee par la protection SSRF)
    r = client.post("/offre/extraire", json={"url": "http://169.254.169.254/"}, headers=h)
    assert r.status_code == 400 and code(r) == "scraping_failed"


def test_email_deja_utilise(client, emails):
    email = f"b-{uuid.uuid4().hex[:8]}@example.com"
    assert inscrire(client, email).status_code == 201
    r = inscrire(client, email)
    assert r.status_code == 400 and code(r) == "email_taken"


def test_mot_de_passe_trop_court(client):
    assert inscrire(client, f"c-{uuid.uuid4().hex[:8]}@example.com", mdp="123").status_code == 422


def test_jeton_d_action_refuse_comme_session(client, emails):
    inscrire(client, f"d-{uuid.uuid4().hex[:8]}@example.com")
    r = client.get("/auth/me", headers={"Authorization": "Bearer " + emails[-1]["token"]})
    assert r.status_code == 401


def test_mot_de_passe_oublie_et_reinitialisation(client, emails):
    email = f"e-{uuid.uuid4().hex[:8]}@example.com"
    inscrire(client, email, mdp="FirstPass-7731")
    nb = len(emails)

    # Compte inconnu : meme reponse, aucun email (pas d'enumeration des comptes)
    assert client.post("/auth/forgot-password", json={"email": "inconnu-zz@example.com"}).status_code == 202
    assert len(emails) == nb

    assert client.post("/auth/forgot-password", json={"email": email, "langue": "en"}).status_code == 202
    jeton = emails[-1]["token"]
    assert emails[-1]["kind"] == "reset" and emails[-1]["lang"] == "en"

    assert client.post("/auth/verify-email", json={"token": jeton}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": jeton, "mot_de_passe": "short"}).status_code == 422
    assert client.post("/auth/reset-password", json={"token": jeton, "mot_de_passe": "SecondPass-7731"}).status_code == 200
    # Lien a usage unique
    assert client.post("/auth/reset-password", json={"token": jeton, "mot_de_passe": "Third-Pass-999"}).status_code == 400
    assert client.post("/auth/login", json={"email": email, "mot_de_passe": "FirstPass-7731"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "mot_de_passe": "SecondPass-7731"}).status_code == 200


def test_force_brute_limitee(client):
    codes = [client.post("/auth/login", json={"email": "x@example.com", "mot_de_passe": "wrongpass1"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "client-test")
    vrai = httpx.AsyncClient

    def repondre(payload, status=200):
        monkeypatch.setattr(auth.httpx, "AsyncClient",
                            lambda **kw: vrai(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload)), **kw))
    return repondre


def test_google_creation_puis_reconnexion(client, google):
    email = f"g-{uuid.uuid4().hex[:8]}@example.com"
    info = {"aud": "client-test", "email": email, "email_verified": "true", "sub": "g-" + uuid.uuid4().hex, "given_name": "Gina"}
    google(info)
    r1 = client.post("/auth/google", json={"credential": "c" * 20})
    r2 = client.post("/auth/google", json={"credential": "c" * 20})
    assert r1.status_code == 200 and r1.json()["utilisateur"]["email_verifie"] is True
    assert r2.json()["utilisateur"]["id"] == r1.json()["utilisateur"]["id"]


@pytest.mark.parametrize("modif", [{"aud": "autre-client"}, {"email_verified": "false"}])
def test_google_refuse_jeton_douteux(client, google, modif):
    google({"aud": "client-test", "email": "x@example.com", "email_verified": "true", "sub": "g-1", **modif})
    assert client.post("/auth/google", json={"credential": "c" * 20}).status_code == 401
