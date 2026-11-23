"""Verifie les PDF avec le moteur de production (WeasyPrint), dans l'image Docker.

Chaque modele de CV en A4 et en Letter, la lettre, et la photo integree : un PDF valide d'une page,
au bon format, avec une image seulement dans le modele qui la montre.

    docker run --rm -e PYTHONPATH=/app -v "$PWD/scripts:/scripts:ro" --entrypoint python cvgen-api /scripts/verifier_pdf.py
"""
import os
from base64 import b64encode
from io import BytesIO

import pymupdf
from PIL import Image

from app.schemas.document import MODELES_CV
from app.services import photo_service
from app.services.document_service import rendre_cv_html, rendre_lettre_html
from app.services.pdf_service import _charger_weasyprint, _html_vers_pdf

TAILLES = {"a4": (595, 842), "letter": (612, 792)}
CV = {
    "nom": "Test CI", "titre": "Engineer", "resume": "Profil de test.", "langues": ["Français", "English"],
    "experiences": [{"poste": "Ingénieure", "entreprise": "Exemple", "date": "2022", "puces": ["Une mission", "Une autre"]}],
}
assert _charger_weasyprint(), "WeasyPrint doit etre utilisable dans l'image"

tampon = BytesIO()
Image.new("RGB", (600, 800), (120, 160, 200)).save(tampon, "JPEG")
photo = "data:image/jpeg;base64," + b64encode(photo_service.normaliser(tampon.getvalue())).decode()
etat_civil = [("Nationalité", "camerounaise"), ("Date de naissance", "12 mars 1994")]


def verifier(nom: str, html: str, page: str, images: int, texte: str) -> None:
    chemin = _html_vers_pdf(html)
    try:
        with pymupdf.open(chemin) as doc:
            r = doc[0].rect
            assert doc.page_count == 1, (nom, doc.page_count)
            assert abs(r.width - TAILLES[page][0]) < 2 and abs(r.height - TAILLES[page][1]) < 2, (nom, r)
            assert len(doc[0].get_images()) == images, (nom, doc[0].get_images())
            assert texte in doc[0].get_text(), nom
        print("PDF OK", nom, page, os.path.getsize(chemin), "octets")
    finally:
        os.remove(chemin)


for page in TAILLES:
    for modele in MODELES_CV:
        avec_photo = modele == "etat_civil"
        verifier(modele, rendre_cv_html(CV, modele, page, etat_civil, photo), page, int(avec_photo), "camerounaise" if avec_photo else "Une mission")
    verifier("lettre", rendre_lettre_html({"paragraphes": ["Bonjour"]}, page), page, 0, "Bonjour")
