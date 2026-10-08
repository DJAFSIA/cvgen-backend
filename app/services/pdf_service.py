import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import fitz

logger = logging.getLogger(__name__)

_CHEMINS_NAVIGATEUR = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
)


def _refuser_ressource(url, *args, **kwargs):
    raise ValueError("Chargement de ressources externes interdit")


_weasyprint_lock = threading.Lock()
_weasyprint_html = None  # classe HTML de WeasyPrint, ou False si indisponible
_weasyprint_teste = False


def _charger_weasyprint():
    """Importe WeasyPrint une seule fois, de facon sure entre threads.

    Quand ses bibliotheques natives (pango/gobject) manquent, l'import echoue et laisse un
    module a moitie charge : des imports concurrents levaient alors d'autres erreurs
    (NameError...). On tranche une fois pour toutes et on memorise le resultat.
    """
    global _weasyprint_html, _weasyprint_teste
    with _weasyprint_lock:
        if not _weasyprint_teste:
            _weasyprint_teste = True
            try:
                from weasyprint import HTML
                _weasyprint_html = HTML
            except Exception as e:  # OSError, ImportError, NameError selon l'etat de l'import
                logger.warning("WeasyPrint indisponible (%s), repli sur le navigateur headless", type(e).__name__)
                _weasyprint_html = False
        return _weasyprint_html


def _pdf_weasyprint(html_contenu: str, chemin: str) -> bool:
    """Retourne False si WeasyPrint n'est pas utilisable sur cette machine."""
    html_cls = _charger_weasyprint()
    if not html_cls:
        return False
    html_cls(string=html_contenu, url_fetcher=_refuser_ressource).write_pdf(chemin)
    return True


def _trouver_navigateur() -> str | None:
    for candidat in _CHEMINS_NAVIGATEUR:
        if os.path.exists(candidat):
            return candidat
    return shutil.which("chromium") or shutil.which("google-chrome")


def _pdf_navigateur(html_contenu: str, chemin: str) -> None:
    """Repli de developpement quand les bibliotheques natives de WeasyPrint sont absentes."""
    navigateur = _trouver_navigateur()
    if not navigateur:
        raise RuntimeError("Aucun moteur PDF disponible (WeasyPrint ou Chrome/Edge requis).")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dossier:
        source = Path(dossier) / "document.html"
        sortie = Path(dossier) / "document.pdf"
        source.write_text(html_contenu, encoding="utf-8")
        subprocess.run(
            [
                navigateur, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--user-data-dir={Path(dossier) / 'profil'}",
                f"--print-to-pdf={sortie}", source.as_uri(),
            ],
            check=True, capture_output=True, timeout=60,
        )
        # Le navigateur rend la main avant la fin de l'ecriture : on attend un fichier stable
        derniere_taille, fin = -1, time.monotonic() + 30
        while time.monotonic() < fin:
            taille = sortie.stat().st_size if sortie.exists() else 0
            if taille > 0 and taille == derniere_taille:
                break
            derniere_taille = taille
            time.sleep(0.4)
        else:
            raise RuntimeError("Le navigateur n'a pas produit de PDF.")
        shutil.copyfile(sortie, chemin)


def _html_vers_pdf(html_contenu: str) -> str:
    fd, chemin = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        if not _pdf_weasyprint(html_contenu, chemin):
            _pdf_navigateur(html_contenu, chemin)
        if os.path.getsize(chemin) == 0:
            raise RuntimeError("PDF vide genere")
    except Exception:
        os.remove(chemin)
        raise
    return chemin


async def generer_pdf(html_contenu: str) -> str:
    """Genere un PDF dans un fichier temporaire unique ; l'appelant doit le supprimer."""
    return await asyncio.to_thread(_html_vers_pdf, html_contenu)


def extraire_texte_du_pdf(chemin_fichier: str) -> str:
    """Extrait le texte brut d'un fichier PDF pour l'analyse IA."""
    try:
        doc = fitz.open(chemin_fichier)
        texte = ""
        for page in doc:
            texte += page.get_text()
        return texte
    except Exception as e:
        logger.warning("Erreur lors de la lecture du PDF : %s", e)
        return ""
