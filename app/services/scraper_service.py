import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
import trafilatura

MAX_REDIRECTS = 3
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


class ScrapingError(Exception):
    """Erreur affichable a l'utilisateur lors de l'extraction d'une offre."""


def _verifier_url(url: str) -> None:
    """Refuse tout ce qui n'est pas une URL web publique (protection SSRF)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ScrapingError("URL invalide : seules les adresses http(s) sont acceptees.")
    if parsed.port not in (None, 80, 443):
        raise ScrapingError("URL invalide : port non autorise.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ScrapingError("Impossible de resoudre le nom de domaine de cette URL.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ScrapingError("URL invalide : adresse non publique.")


def _telecharger(url: str) -> str:
    courante = url
    for _ in range(MAX_REDIRECTS + 1):
        _verifier_url(courante)
        try:
            reponse = requests.get(
                courante, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True
            )
        except requests.RequestException:
            raise ScrapingError("Le site est injoignable.")
        with reponse:
            if reponse.is_redirect and reponse.headers.get("Location"):
                courante = urljoin(courante, reponse.headers["Location"])
                continue
            if reponse.status_code != 200:
                raise ScrapingError(f"Le site bloque l'acces (code {reponse.status_code}). Collez le texte de l'offre manuellement.")
            type_contenu = reponse.headers.get("Content-Type", "")
            if "html" not in type_contenu and "text" not in type_contenu:
                raise ScrapingError("Cette URL ne pointe pas vers une page web.")
            morceaux, taille = [], 0
            for morceau in reponse.iter_content(chunk_size=65536):
                taille += len(morceau)
                if taille > MAX_BYTES:
                    raise ScrapingError("La page est trop volumineuse.")
                morceaux.append(morceau)
            encodage = reponse.encoding or "utf-8"
            return b"".join(morceaux).decode(encodage, errors="replace")
    raise ScrapingError("Trop de redirections.")


async def extraire_texte_offre_url(url: str) -> str:
    """Recupere le texte d'une offre. Leve ScrapingError avec un message affichable."""
    html = await asyncio.to_thread(_telecharger, url)
    texte = trafilatura.extract(html, include_comments=False)
    if not texte:
        raise ScrapingError("Le contenu de l'offre est vide ou illisible. Collez le texte manuellement.")
    return texte
