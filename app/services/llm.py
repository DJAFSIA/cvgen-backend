"""Acces au modele de langage.

LLM_PROVIDERS definit une chaine de fournisseurs essayes dans l'ordre : si l'un est sans cle,
en panne ou a court de quota, le suivant prend le relais. On cumule ainsi plusieurs paliers
gratuits (Gemini, Groq, OpenRouter, Mistral), un modele local (Ollama) ou un fournisseur payant.

Toutes les generations de l'application demandent une sortie JSON.
"""
import asyncio
import logging

import anthropic
import httpx
from anthropic import AsyncAnthropic

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


# --- Fournisseurs compatibles OpenAI (Groq, OpenRouter, Mistral, Ollama) ----------
def _compat_config(provider: str) -> dict:
    c = settings
    return {
        "groq": {"url": "https://api.groq.com/openai/v1", "key": c.GROQ_API_KEY, "model": c.GROQ_MODEL,
                 # palier gratuit : quelques milliers de tokens par minute
                 "max_tokens": 4096},
        "openrouter": {"url": "https://openrouter.ai/api/v1", "key": c.OPENROUTER_API_KEY,
                       "model": c.OPENROUTER_MODEL, "fallbacks": c.openrouter_fallback_list, "max_tokens": 8000},
        "mistral": {"url": "https://api.mistral.ai/v1", "key": c.MISTRAL_API_KEY, "model": c.MISTRAL_MODEL, "max_tokens": 8000},
        "ollama": {"url": c.OLLAMA_URL.rstrip("/") + "/v1", "key": "ollama", "model": c.OLLAMA_MODEL,
                   "max_tokens": 8000, "timeout": 600},
    }[provider]


async def _compat_complete(provider: str, prompt: str, max_tokens: int) -> str:
    conf = _compat_config(provider)
    if not conf["key"]:
        raise IAError(f"Cle {provider} manquante")
    body = {
        "model": conf["model"],
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": min(max_tokens, conf["max_tokens"]),
    }
    if conf.get("fallbacks"):
        # OpenRouter essaie lui-meme les modeles suivants si le premier est indisponible
        body["models"] = [conf["model"], *conf["fallbacks"]]
    headers = {"Authorization": f"Bearer {conf['key']}"}
    if provider == "openrouter":
        headers.update({"HTTP-Referer": settings.FRONTEND_URL, "X-Title": "CVGen"})

    async with httpx.AsyncClient(timeout=conf.get("timeout", 120)) as client:
        for tentative in range(2):
            try:
                response = await client.post(f"{conf['url']}/chat/completions", json=body, headers=headers)
            except httpx.HTTPError as e:
                raise IAError(f"{provider} injoignable ({type(e).__name__})") from e
            if response.status_code in _RETRY_STATUS and tentative == 0:
                await asyncio.sleep(2)
                continue
            break
    if response.status_code != 200:
        logger.warning("Erreur API %s %s: %s", provider, response.status_code, response.text[:300])
        raise IAError(f"Erreur du fournisseur d'IA {provider} (HTTP {response.status_code})")
    choix = response.json().get("choices") or []
    if not choix:
        raise IAError(f"Reponse vide de {provider}")
    return (choix[0].get("message") or {}).get("content") or ""


# --- Google Gemini (palier gratuit AI Studio) --------------------------------
async def _gemini_une_tentative(client: httpx.AsyncClient, model: str, body: dict) -> httpx.Response:
    """Appelle un modele, avec une nouvelle tentative sur les erreurs temporaires."""
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY}
    for tentative in range(2):
        try:
            response = await client.post(_GEMINI_URL.format(model=model), json=body, headers=headers)
        except httpx.HTTPError as e:
            logger.error("Gemini injoignable: %s", e)
            raise IAError("Fournisseur d'IA injoignable") from e
        if response.status_code in _RETRY_STATUS and tentative == 0:
            await asyncio.sleep(2)
            continue
        return response
    return response


async def _gemini_complete(prompt: str, max_tokens: int) -> str:
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY manquante")
        raise IAError("Cle Gemini manquante")
    # Les modeles recents depensent une partie du budget de sortie en raisonnement interne
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens + 4000,
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }
    modeles = [settings.GEMINI_MODEL, *settings.gemini_fallback_list]

    async with httpx.AsyncClient(timeout=120) as client:
        for model in modeles:
            response = await _gemini_une_tentative(client, model, body)
            if response.status_code == 200:
                break
            logger.warning("Gemini %s: HTTP %s %s", model, response.status_code, response.text[:200])
            # Modele surcharge, retire ou quota atteint : on passe au suivant
            if response.status_code not in _RETRY_STATUS | {404}:
                break
        else:
            raise IAError(f"Erreur du fournisseur d'IA (HTTP {response.status_code})")

    if response.status_code != 200:
        logger.error("Erreur API Gemini %s: %s", response.status_code, response.text[:400])
        raise IAError(f"Erreur du fournisseur d'IA (HTTP {response.status_code})")
    candidats = response.json().get("candidates") or []
    if not candidats:
        raise IAError("Requete bloquee par le modele")
    parties = (candidats[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parties if not p.get("thought"))


# --- Point d'entree ----------------------------------------------------------
_COMPAT = ("groq", "openrouter", "mistral", "ollama")


async def _un_fournisseur(provider: str, prompt: str, effort: str, max_tokens: int) -> str:
    if provider == "anthropic":
        return await _anthropic_complete(prompt, effort, max_tokens)
    if provider == "gemini":
        return await _gemini_complete(prompt, max_tokens)
    if provider in _COMPAT:
        return await _compat_complete(provider, prompt, max_tokens)
    raise IAError(f"Fournisseur LLM inconnu: {provider}")


def _est_configure(provider: str) -> bool:
    """Les fournisseurs sans cle sont ignores sans bruit (Ollama et Anthropic se tentent toujours)."""
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY)
    if provider in ("groq", "openrouter", "mistral"):
        return bool(_compat_config(provider)["key"])
    return True


async def complete(prompt: str, *, effort: str = "medium", max_tokens: int = 8000) -> str:
    derniere_erreur = IAError("Aucun fournisseur d'IA configure (LLM_PROVIDERS)")
    for provider in settings.llm_provider_chain:
        if not _est_configure(provider):
            continue
        try:
            texte = (await _un_fournisseur(provider, prompt, effort, max_tokens)).strip()
        except IAError as e:
            logger.warning("Fournisseur %s indisponible (%s), passage au suivant", provider, e)
            derniere_erreur = e
            continue
        if texte:
            return texte
        derniere_erreur = IAError(f"Reponse vide de {provider}")
    logger.error("Tous les fournisseurs d'IA ont echoue: %s", derniere_erreur)
    raise derniere_erreur
