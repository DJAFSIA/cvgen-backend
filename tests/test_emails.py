"""Envoi des emails par l'API de Brevo (l'offre gratuite de Render bloque SMTP) et garde-fou de production."""
import asyncio
import logging

import httpx
import pytest

from app.core.config import Settings, settings
from app.services import mail_service


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_BACKEND", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "cle-de-test")
    monkeypatch.setattr(settings, "MAIL_FROM", "Apply <contact@example.com>")
    monkeypatch.setattr(settings, "SUPPORT_EMAIL", "support@example.com")
    appels = {"recus": [], "statut": 201, "reponse": {"messageId": "<x@y>"}}

    async def faux_post(self, url, json=None, headers=None):
        appels["recus"].append({"url": url, "json": json, "headers": headers})
        return httpx.Response(appels["statut"], json=appels["reponse"])

    monkeypatch.setattr(httpx.AsyncClient, "post", faux_post)
    return appels


def test_envoi_par_l_api_brevo(brevo):
    asyncio.run(mail_service.send_action_email("verify", "amina@example.com", "fr", "https://site/verify?token=abc"))
    appel = brevo["recus"][0]
    assert appel["url"] == "https://api.brevo.com/v3/smtp/email"
    assert appel["headers"]["api-key"] == "cle-de-test"
    assert appel["json"]["sender"] == {"name": "Apply", "email": "contact@example.com"}
    assert appel["json"]["to"] == [{"email": "amina@example.com"}]
    assert appel["json"]["replyTo"] == {"email": "support@example.com"}
    assert appel["json"]["subject"] == "Confirmez votre adresse email"
    assert "https://site/verify?token=abc" in appel["json"]["textContent"]
    assert "https://site/verify?token=abc" in appel["json"]["htmlContent"]


def test_un_refus_de_brevo_est_journalise_sans_faire_echouer_l_appelant(brevo, caplog):
    brevo["statut"], brevo["reponse"] = 401, {"code": "unauthorized", "message": "unrecognised IP address"}
    with caplog.at_level(logging.ERROR, logger="app.services.mail_service"):
        asyncio.run(mail_service.send_notification_email("deleted", "amina@example.com", "fr"))
    assert "unrecognised IP address" in caplog.text


def _production(**reglages):
    base = {
        "ENV": "production",
        "DATABASE_URL": "postgresql://u:p@h/d",
        "SECRET_KEY": "a" * 40,
        "FRONTEND_URL": "https://site.example.com",
        "CORS_ORIGINS": "https://site.example.com",
        "MAIL_BACKEND": "brevo",
        "MAIL_FROM": "Apply <contact@example.com>",
        "BREVO_API_KEY": "cle",
    }
    return Settings(_env_file=None, **{**base, **reglages}).verifier_production()


def test_une_configuration_complete_est_acceptee():
    assert _production() == []


@pytest.mark.parametrize("reglages, attendu", [
    ({"MAIL_BACKEND": "console"}, "MAIL_BACKEND"),
    ({"BREVO_API_KEY": ""}, "BREVO_API_KEY"),
    ({"MAIL_BACKEND": "smtp", "SMTP_HOST": ""}, "SMTP_HOST"),
    ({"MAIL_FROM": "Apply <no-reply@localhost>"}, "MAIL_FROM"),
])
def test_un_envoi_d_email_mal_configure_bloque_le_demarrage(reglages, attendu):
    assert any(attendu in erreur for erreur in _production(**reglages))
