import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
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


def _pdf_weasyprint(html_contenu: str, chemin: str) -> None:
    from weasyprint import HTML

    HTML(string=html_contenu, url_fetcher=_refuser_ressource).write_pdf(chemin)


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
        try:
            _pdf_weasyprint(html_contenu, chemin)
        except OSError:
            # Bibliotheques natives (pango/gobject) introuvables
            logger.warning("WeasyPrint indisponible, repli sur le navigateur headless")
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
