import pytest

from app.schemas.document import CVData
from app.services.document_service import cv_en_markdown, rendre_cv_html, rendre_lettre_html
from app.services.scraper_service import ScrapingError, _verifier_url
from conftest import code


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.1/", "file:///etc/passwd", "http://[::1]/", "http://example.com:8080/", "ftp://example.com",
])
def test_ssrf_urls_internes_bloquees(url):
    with pytest.raises(ScrapingError):
        _verifier_url(url)


def test_import_cv_controle_du_fichier(client, make_user):
    _, h = make_user()
    r = client.post("/profil/import-cv", files={"file": ("a.pdf", b"pas un pdf")}, headers=h)
    assert r.status_code == 400 and code(r) == "file_not_pdf"
    r = client.post("/profil/import-cv", files={"file": ("a.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10))}, headers=h)
    assert r.status_code == 413


def test_sortie_ia_imparfaite_normalisee():
    cv = CVData.model_validate({"nom": None, "experiences": [{"poste": 3, "puces": ["ok", None, 42]}], "langues": "fr", "inconnu": 1})
    assert cv.nom == "" and cv.experiences[0].poste == "3" and cv.experiences[0].puces == ["ok", "42"] and cv.langues == ["fr"]


@pytest.mark.parametrize("modele", ["classique", "moderne", "ats"])
def test_contenu_hostile_echappe_dans_les_modeles(modele):
    html = rendre_cv_html({"nom": "<script>alert(1)</script>", "resume": '<img src="file:///etc/passwd">'}, modele)
    assert "<script>" not in html and '<img src="file' not in html
    assert "&lt;script&gt;" in html


def test_lettre_et_apercu():
    assert "Bonjour" in rendre_lettre_html({"paragraphes": ["Bonjour"]})
    assert cv_en_markdown({"nom": "A", "experiences": [{"poste": "Dev", "puces": ["x"]}]}).startswith("# A")


def test_sante(client):
    assert client.get("/health").json() == {"status": "ok", "db": True}
