import asyncio
import logging
import html
import os
import tempfile
import fitz 

def _refuser_ressource(url, *args, **kwargs):
    raise ValueError("Chargement de ressources externes interdit")


def _generer_pdf_sync(contenu_texte: str) -> str:
    from weasyprint import HTML

    # Le contenu vient de l'IA (et indirectement d'une offre non fiable) : on l'echappe
    # et on interdit tout chargement de ressource (file://, http://...).
    corps = html.escape(contenu_texte).replace("\n", "<br>")
    html_contenu = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
      <meta charset="UTF-8">
      <style>
        body {{ font-family: Arial, sans-serif; font-size: 12px; line-height: 1.6; color: #333; margin: 40px; }}
        .section {{ margin-bottom: 18px; }}
      </style>
    </head>
    <body><div class="section">{corps}</div></body>
    </html>
    """
    fd, chemin = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        HTML(string=html_contenu, url_fetcher=_refuser_ressource).write_pdf(chemin)
    except Exception:
        os.remove(chemin)
        raise
    return chemin


async def generer_pdf(contenu_texte: str) -> str:
    """Genere un PDF dans un fichier temporaire unique ; l'appelant doit le supprimer."""
    return await asyncio.to_thread(_generer_pdf_sync, contenu_texte)


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
