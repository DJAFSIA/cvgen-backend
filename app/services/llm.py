"""Acces au modele de langage.

LLM_PROVIDERS definit une chaine de fournisseurs essayes dans l'ordre : si l'un est sans cle,
en panne ou a court de quota, le suivant prend le relais. On cumule ainsi plusieurs paliers
gratuits (Gemini, Groq, OpenRouter, Mistral), un modele local (Ollama) ou un fournisseur payant.

Toutes les generations de l'application demandent une sortie JSON.
"""
import asyncio
import logging
import time

import anthropic
import httpx
from anthropic import AsyncAnthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# Modeles Anthropic pour lesquels le repli serveur automatique en cas de refus est disponible
_FALLBACK_PREFIXES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5")
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_RETRY_STATUS = {429, 500, 502, 503}
# Secondes : reponse d'un modele, puis toute la chaine de modeles et de fournisseurs
DELAI_ESSAI = 45
DELAI_TOTAL = 150


class IAError(Exception):
    """Echec d'un appel IA (indisponible, quota, refus, reponse vide ou JSON invalide)."""

    def __init__(self, message: str, temporaire: bool = False):
        super().__init__(message)
        self.temporaire = temporaire  # saturation, coupure ou delai : un nouvel essai peut reussir


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


async def _compat_complete(provider: str, prompt: str, max_tokens: int, essai: float) -> str:
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
        headers.update({"HTTP-Referer": settings.FRONTEND_URL, "X-Title": "Apply"})

    async with httpx.AsyncClient(timeout=conf.get("timeout", essai)) as client:
        try:
            response = await client.post(f"{conf['url']}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as e:
            raise IAError(f"{provider} injoignable ({type(e).__name__})", temporaire=True) from e
    if response.status_code != 200:
        logger.warning("Erreur API %s %s: %s", provider, response.status_code, response.text[:300])
        raise IAError(
            f"Erreur du fournisseur d'IA {provider} (HTTP {response.status_code})",
            temporaire=response.status_code in _RETRY_STATUS,
        )
    choix = response.json().get("choices") or []
    if not choix:
        raise IAError(f"Reponse vide de {provider}")
    return (choix[0].get("message") or {}).get("content") or ""


# --- Google Gemini (palier gratuit AI Studio) --------------------------------
def _texte_gemini(response: httpx.Response) -> str:
    candidats = response.json().get("candidates") or []
    if not candidats:
        raise IAError("Requete bloquee par le modele")
    parties = (candidats[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parties if not p.get("thought"))


async def _gemini_complete(prompt: str, max_tokens: int, essai: float) -> str:
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
    headers = {"x-goog-api-key": settings.GEMINI_API_KEY}
    erreur = IAError("Aucun modele Gemini configure")

    async with httpx.AsyncClient(timeout=essai) as client:
        # Modele sature, muet, retire ou quota atteint : on passe tout de suite au suivant
        for model in [settings.GEMINI_MODEL, *settings.gemini_fallback_list]:
            try:
                response = await client.post(_GEMINI_URL.format(model=model), json=body, headers=headers)
            except httpx.HTTPError as e:
                logger.warning("Gemini %s injoignable (%s)", model, type(e).__name__)
                erreur = IAError("Fournisseur d'IA injoignable", temporaire=True)
                continue
            if response.status_code == 200:
                return _texte_gemini(response)
            logger.warning("Gemini %s: HTTP %s %s", model, response.status_code, response.text[:200])
            erreur = IAError(
                f"Erreur du fournisseur d'IA (HTTP {response.status_code})", temporaire=response.status_code in _RETRY_STATUS,
            )
            if response.status_code not in _RETRY_STATUS | {404}:
                break
    raise erreur


# --- Point d'entree ----------------------------------------------------------
_COMPAT = ("groq", "openrouter", "mistral", "ollama")


async def _un_fournisseur(provider: str, prompt: str, effort: str, max_tokens: int, essai: float) -> str:
    if provider == "anthropic":
        return await _anthropic_complete(prompt, effort, max_tokens)
    if provider == "gemini":
        return await _gemini_complete(prompt, max_tokens, essai)
    if provider in _COMPAT:
        return await _compat_complete(provider, prompt, max_tokens, essai)
    raise IAError(f"Fournisseur LLM inconnu: {provider}")


def _est_configure(provider: str) -> bool:
    """Les fournisseurs sans cle sont ignores sans bruit (Ollama et Anthropic se tentent toujours)."""
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY)
    if provider in ("groq", "openrouter", "mistral"):
        return bool(_compat_config(provider)["key"])
    return True


async def _chaine(prompt: str, effort: str, max_tokens: int, essai: float, delai: float | None) -> str:
    """Un passage sur les fournisseurs configures, puis un second sur ceux dont l'echec est passager."""
    fournisseurs = [p for p in settings.llm_provider_chain if _est_configure(p)]
    # Un fournisseur muet ne prend pas tout le temps des suivants
    part = max(essai, delai / len(fournisseurs)) if delai and fournisseurs else None
    derniere_erreur = IAError("Aucun fournisseur d'IA configure (LLM_PROVIDERS)")
    for passage in range(2):
        a_reprendre = []
        for provider in fournisseurs:
            debut = time.monotonic()
            try:
                async with asyncio.timeout(part):
                    texte = (await _un_fournisseur(provider, prompt, effort, max_tokens, essai)).strip()
            except (IAError, TimeoutError) as e:
                derniere_erreur = e if isinstance(e, IAError) else IAError(f"{provider} : delai depasse", temporaire=True)
                logger.warning("Fournisseur %s indisponible (%s), passage au suivant", provider, derniere_erreur)
                if derniere_erreur.temporaire:
                    a_reprendre.append(provider)
                continue
            if texte:
                logger.info("IA %s : reponse en %.1f s", provider, time.monotonic() - debut)
                return texte
            derniere_erreur = IAError(f"Reponse vide de {provider}")
        fournisseurs = a_reprendre
        if not fournisseurs:
            break
        if passage == 0:
            await asyncio.sleep(2)
    raise derniere_erreur


async def complete(
    prompt: str, *, effort: str = "medium", max_tokens: int = 8000, essai: float = DELAI_ESSAI, delai: float | None = DELAI_TOTAL,
) -> str:
    """essai : attente maximale d'un modele ; delai : duree maximale de toute la chaine (secondes)."""
    if "ollama" in settings.llm_provider_chain:
        delai = None  # un modele local peut etre lent
    try:
        async with asyncio.timeout(delai):
            return await _chaine(prompt, effort, max_tokens, essai, delai)
    except TimeoutError as e:
        erreur = IAError(f"Aucune reponse de l'IA en {delai} s", temporaire=True)
        logger.error("Tous les fournisseurs d'IA ont echoue: %s", erreur)
        raise erreur from e
    except IAError as e:
        logger.error("Tous les fournisseurs d'IA ont echoue: %s", e)
        raise
