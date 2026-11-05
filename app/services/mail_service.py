"""Envoi d'emails : en developpement le message est ecrit dans les logs (lien cliquable),
en production il part par l'API de Brevo (HTTPS) ou par SMTP.
L'offre gratuite de Render bloque les ports SMTP : seul l'envoi par API y fonctionne."""
import asyncio
import html
import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"

_TEXTES = {
    "fr": {
        "verify": {
            "subject": "Confirmez votre adresse email",
            "intro": "Bienvenue sur Apply ! Confirmez votre adresse email pour activer la génération de documents.",
            "button": "Confirmer mon email",
            "outro": "Ce lien est valable 48 heures. Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message.",
        },
        "reset": {
            "subject": "Réinitialisation de votre mot de passe",
            "intro": "Vous avez demandé à réinitialiser votre mot de passe Apply.",
            "button": "Choisir un nouveau mot de passe",
            "outro": "Ce lien est valable 1 heure et ne peut servir qu'une fois. Si vous n'avez rien demandé, ignorez ce message : votre mot de passe reste inchangé.",
        },
        "deleted": {
            "subject": "Votre compte Apply a été supprimé",
            "intro": "Votre compte Apply et les données associées (profil, offres, CV, lettres) ont été supprimés à votre demande. Tout abonnement par carte a été arrêté.",
            "outro": "Si vous n'êtes pas à l'origine de cette suppression, contactez-nous immédiatement{contact}.",
        },
    },
    "en": {
        "verify": {
            "subject": "Confirm your email address",
            "intro": "Welcome to Apply! Confirm your email address to enable document generation.",
            "button": "Confirm my email",
            "outro": "This link is valid for 48 hours. If you did not sign up, you can ignore this message.",
        },
        "reset": {
            "subject": "Reset your password",
            "intro": "You asked to reset your Apply password.",
            "button": "Choose a new password",
            "outro": "This link is valid for 1 hour and can only be used once. If you did not ask for this, ignore this message: your password is unchanged.",
        },
        "deleted": {
            "subject": "Your Apply account has been deleted",
            "intro": "Your Apply account and its data (profile, job offers, CVs, letters) have been deleted at your request. Any card subscription has been stopped.",
            "outro": "If you did not delete your account, contact us immediately{contact}.",
        },
    },
}


_STYLE_CORPS = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"
    "max-width:480px;margin:auto;color:#1d1d1f;line-height:1.5"
)


def _smtp_send(message: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def _message_smtp(to: str, subject: str, text: str, html_body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.MAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    if settings.SUPPORT_EMAIL:
        message["Reply-To"] = settings.SUPPORT_EMAIL
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")
    return message


async def _brevo_send(to: str, subject: str, text: str, html_body: str) -> None:
    nom, adresse = parseaddr(settings.MAIL_FROM)
    corps = {
        "sender": {"name": nom or "Apply", "email": adresse},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
        "htmlContent": html_body,
    }
    if settings.SUPPORT_EMAIL:
        corps["replyTo"] = {"email": settings.SUPPORT_EMAIL}
    async with httpx.AsyncClient(timeout=20) as client:
        reponse = await client.post(
            BREVO_URL, json=corps, headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"}
        )
    if reponse.status_code >= 400:
        # La reponse de Brevo dit quoi corriger : cle invalide, adresse IP non autorisee, expediteur non valide...
        raise RuntimeError(f"Brevo a refuse l'envoi ({reponse.status_code}) : {reponse.text[:300]}")


async def send_email(to: str, subject: str, text: str, html_body: str) -> None:
    """N'echoue jamais vers l'appelant : une erreur d'envoi est journalisee."""
    if settings.MAIL_BACKEND == "console":
        logger.info("\n=== EMAIL (mode console) ===\nA: %s\nObjet: %s\n\n%s\n============================", to, subject, text)
        return
    try:
        if settings.MAIL_BACKEND == "brevo":
            await _brevo_send(to, subject, text, html_body)
        else:
            await asyncio.to_thread(_smtp_send, _message_smtp(to, subject, text, html_body))
    except Exception:
        logger.exception("Echec de l'envoi de l'email a %s", to)


async def send_action_email(kind: str, to: str, lang: str, link: str) -> None:
    """kind: 'verify' | 'reset'."""
    t = _TEXTES.get(lang, _TEXTES["en"])[kind]
    text = f"{t['intro']}\n\n{t['button']} : {link}\n\n{t['outro']}\n"
    safe = html.escape(link, quote=True)
    html_body = (
        f'<div style="{_STYLE_CORPS}">'
        f"<p>{html.escape(t['intro'])}</p>"
        f'<p><a href="{safe}" style="display:inline-block;background:#0071e3;color:#fff;text-decoration:none;'
        f'padding:12px 22px;border-radius:980px;font-weight:500">{html.escape(t["button"])}</a></p>'
        f'<p style="color:#6e6e73;font-size:13px">{html.escape(t["outro"])}</p>'
        f'<p style="color:#6e6e73;font-size:12px;word-break:break-all">{safe}</p></div>'
    )
    await send_email(to, t["subject"], text, html_body)


async def send_notification_email(kind: str, to: str, lang: str) -> None:
    """Email d'information sans lien d'action (ex. 'deleted')."""
    t = _TEXTES.get(lang, _TEXTES["en"])[kind]
    contact = f" : {settings.SUPPORT_EMAIL}" if settings.SUPPORT_EMAIL else ""
    outro = t["outro"].format(contact=contact)
    text = f"{t['intro']}\n\n{outro}\n"
    html_body = (
        f'<div style="{_STYLE_CORPS}">'
        f"<p>{html.escape(t['intro'])}</p>"
        f'<p style="color:#6e6e73;font-size:13px">{html.escape(outro)}</p></div>'
    )
    await send_email(to, t["subject"], text, html_body)
