"""Acces au modele de langage, interchangeable via LLM_PROVIDER (anthropic, gemini, groq).

Toutes les generations de l'application demandent une sortie JSON.
"""
import asyncio
import logging

import anthropic
import httpx
from anthropic import AsyncAnthropic
from groq import AsyncGroq, GroqError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Modeles Anthropic pour lesquels le repli serveur automatique en cas de refus est disponible
_FALLBACK_PREFIXES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5")
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRY_STATUS = {429, 500, 502, 503}


class IAError(Exception):
    """Echec d'un appel IA (indisponible, quota, refus, reponse vide ou JSON invalide)."""


# --- Anthropic ---------------------------------------------------------------
# Si ANTHROPIC_API_KEY est vide, le SDK retrouve les identifiants dans l'environnement
_anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY or None)


async def _anthropic_complete(prompt: str, effort: str, max_tokens: int) -> str:
    model = settings.ANTHROPIC_MODEL
    extra = {}
    if model.startswith(_FALLBACK_PREFIXES):
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        response = await _anthropic.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            output_config={"effort": effort},
            messages=[{"role": "user", "content": prompt}],
            **extra,
        )
    except TypeError as e:
        # Le SDK leve TypeError quand aucun identifiant Anthropic n'est configure
        logger.error("Identifiants Anthropic manquants (ANTHROPIC_API_KEY): %s", e)
        raise IAError("Identifiants Anthropic manquants") from e
    except anthropic.APIError as e:
        logger.error("Erreur API Anthropic: %s", e)
        raise IAError(f"Erreur du fournisseur d'IA ({type(e).__name__})") from e
    if response.stop_reason == "refusal":
        raise IAError("Requete refusee par le modele")
    return "".join(b.text for b in response.content if b.type == "text")


# --- Groq (gratuit avec limites) ---------------------------------------------
_groq = AsyncGroq(api_key=settings.GROQ_API_KEY or "missing")


async def _groq_complete(prompt: str, max_tokens: int) -> str:
    if not settings.GROQ_API_KEY:
        logger.error("GROQ_API_KEY manquante")
        raise IAError("Cle Groq manquante")
    try:
        response = await _groq.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=max_tokens,
        )
    except GroqError as e:
        logger.error("Erreur API Groq: %s", e)
        raise IAError(f"Erreur du fournisseur d'IA ({type(e).__name__})") from e
    return response.choices[0].message.content or ""


# --- Google Gemini (palier gratuit AI Studio) --------------------------------
async def _gemini_complete(prompt: str, max_tokens: int) -> str:
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY manquante")
        raise IAError("Cle Gemini manquante")
    model = settings.GEMINI_MODEL
    generation = {
        "maxOutputTokens": max_tokens,
        "temperature": 0.4,
        "responseMimeType": "application/json",
    }
    if "2.5-flash" in model:
        # Sans raisonnement interne : plus rapide, et les tokens vont a la reponse
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": generation}
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY}

    async with httpx.AsyncClient(timeout=120) as client:
        for tentative in range(3):
            try:
                response = await client.post(_GEMINI_URL.format(model=model), json=body, headers=headers)
            except httpx.HTTPError as e:
                logger.error("Gemini injoignable: %s", e)
                raise IAError("Fournisseur d'IA injoignable") from e
            if response.status_code in _RETRY_STATUS and tentative < 2:
                await asyncio.sleep(2 * (tentative + 1))
                continue
            break

    if response.status_code != 200:
        logger.error("Erreur API Gemini %s: %s", response.status_code, response.text[:400])
        raise IAError(f"Erreur du fournisseur d'IA (HTTP {response.status_code})")
    data = response.json()
    candidats = data.get("candidates") or []
    if not candidats:
        raise IAError("Requete bloquee par le modele")
    parties = (candidats[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parties)


# --- Point d'entree ----------------------------------------------------------
async def complete(prompt: str, *, effort: str = "medium", max_tokens: int = 8000) -> str:
    provider = settings.LLM_PROVIDER
    if provider == "anthropic":
        texte = await _anthropic_complete(prompt, effort, max_tokens)
    elif provider == "gemini":
        texte = await _gemini_complete(prompt, max_tokens)
    elif provider == "groq":
        texte = await _groq_complete(prompt, max_tokens)
    else:
        raise IAError(f"Fournisseur LLM inconnu: {provider}")
    texte = texte.strip()
    if not texte:
        raise IAError("Reponse vide du modele")
    return texte
