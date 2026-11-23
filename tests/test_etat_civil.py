"""Photo et etat civil : facultatifs, mis en forme par le serveur, jamais transmis a l'IA, effacables."""
import asyncio
import json
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

import app.routers.candidature as rc
from app import pays
from app.models.candidature import CV, Candidature
from app.models.offre import OffreEmploi
from app.models.profil import Profil
from app.services import etat_civil, ia_service, photo_service
from app.services.document_service import rendre_cv_html, rendre_lettre_html
from app.services.pdf_service import _ressource_autorisee
from conftest import code


def profil(**champs):
    base = dict(date_naissance=date(1994, 3, 12), lieu_naissance="Douala", nationalite="CM", situation_familiale="marie_f",
                enfants=2, permis_sejour=None, photo=None, a_photo=False)
    return SimpleNamespace(**{**base, **champs})


def image(largeur=600, hauteur=800, format_="JPEG", mode="RGB", exif=None, couleur=(120, 160, 200)) -> bytes:
    sortie = BytesIO()
    img = Image.new(mode, (largeur, hauteur), couleur if mode == "RGB" else (120, 160, 200, 128))
    img.save(sortie, format_, **({"exif": exif} if exif else {}))
    return sortie.getvalue()


# --- Mise en forme ---

@pytest.mark.parametrize("langue, attendu", [
    ("fr", [("Date et lieu de naissance", "12 mars 1994, Douala"), ("Nationalité", "camerounaise"), ("Situation familiale", "Mariée, 2 enfants")]),
    ("en", [("Date and place of birth", "12 March 1994, Douala"), ("Nationality", "Cameroonian"), ("Marital status", "Married, 2 children")]),
    ("es", [("Fecha y lugar de nacimiento", "12 de marzo de 1994, Douala"), ("Nacionalidad", "Camerún"), ("Estado civil", "Casada, 2 hijos")]),
    ("de", [("Geburtsdatum und -ort", "12. März 1994, Douala"), ("Staatsangehörigkeit", "Kamerun"), ("Familienstand", "Verheiratet, 2 Kinder")]),
    ("pt", [("Data e local de nascimento", "12 de março de 1994, Douala"), ("Nacionalidade", "Camarões"), ("Estado civil", "Casada, 2 filhos")]),
    ("it", [("Data e luogo di nascita", "12 marzo 1994, Douala"), ("Nazionalità", "Camerun"), ("Stato civile", "Coniugata, 2 figli")]),
])
def test_etat_civil_dans_les_six_langues(langue, attendu):
    assert etat_civil.lignes(profil(), langue) == attendu


def test_langue_inconnue_en_anglais_et_champs_absents_omis():
    assert etat_civil.lignes(profil(), "nl")[0][0] == "Date and place of birth"
    assert etat_civil.lignes(profil(), "FR-ca")[1] == ("Nationalité", "camerounaise")
    vide = profil(date_naissance=None, lieu_naissance=None, nationalite=None, situation_familiale=None, enfants=None)
    assert etat_civil.lignes(vide, "fr") == [] and not etat_civil.renseigne(vide)
    assert etat_civil.lignes(profil(date_naissance=date(2000, 1, 1), lieu_naissance=None), "fr")[0] == ("Date de naissance", "1er janvier 2000")
    assert etat_civil.lignes(profil(situation_familiale=None, enfants=1), "fr")[-1] == ("Situation familiale", "1 enfant")


def test_chaque_situation_existe_dans_les_six_langues():
    for langue in etat_civil.LANGUES:
        for situation in etat_civil.SITUATIONS:
            assert etat_civil.ecrire_situation(situation, None, langue)
    for noms in etat_civil.noms_pays().values():
        assert set(noms) == set(etat_civil.LANGUES) and all(noms.values())
    # les adjectifs de nationalite correspondent a de vrais pays
    for adjectifs in etat_civil._NATIONALITES.values():
        assert set(adjectifs) <= set(etat_civil.noms_pays())


def test_les_usages_du_pays_filtrent_les_champs():
    assert etat_civil.lignes(profil(), "fr", pays.fiche("ca-qc")) == []
    assert etat_civil.lignes(profil(), "en", pays.fiche("us")) == []
    libelles_france = [l for l, _ in etat_civil.lignes(profil(), "fr", pays.fiche("fr"))]
    assert "Situation familiale" not in libelles_france and "Nationalité" in libelles_france
    assert len(etat_civil.lignes(profil(), "fr", pays.fiche("cm"))) == 3
    suisse = etat_civil.lignes(profil(permis_sejour="Permis B"), "fr", pays.fiche("ch"))
    assert ("Titre de séjour ou de travail", "Permis B") in suisse


def test_l_affichage_respecte_le_choix_le_profil_et_le_pays():
    avec, sans = profil(a_photo=True), profil()
    assert etat_civil.affichage(avec, pays.fiche("cm"), True, True).model_dump() == {"photo": True, "etat_civil": True}
    assert etat_civil.affichage(avec, pays.fiche("cm"), False, False).model_dump() == {"photo": False, "etat_civil": False}
    assert etat_civil.affichage(sans, pays.fiche("cm"), True, True).photo is False
    for deconseille in ("us", "ca", "ca-qc"):
        assert etat_civil.affichage(avec, pays.fiche(deconseille), True, True).model_dump() == {"photo": False, "etat_civil": False}
    # pays hors liste : au choix de la personne
    assert etat_civil.affichage(avec, None, True, True).model_dump() == {"photo": True, "etat_civil": True}


# --- Rendu ---

CV_TEST = {"nom": "Amina Exemple", "titre": "Cheffe de projet", "langue": "fr"}
PHOTO = "data:image/jpeg;base64,QUJD"


def test_la_photo_et_l_etat_civil_vont_seulement_dans_leur_modele():
    lignes = etat_civil.lignes(profil(), "fr")
    html = rendre_cv_html(CV_TEST, "etat_civil", "a4", lignes, PHOTO)
    assert PHOTO in html and "camerounaise" in html and "12 mars 1994, Douala" in html
    for modele in ("classique", "moderne", "ats", "nord_americain"):
        autre = rendre_cv_html(CV_TEST, modele, "a4", lignes, PHOTO)
        assert "data:image" not in autre and "camerounaise" not in autre
    # sans photo ni etat civil, ce modele reste valable
    nu = rendre_cv_html(CV_TEST, "etat_civil")
    assert "<img" not in nu and 'class="perso"' not in nu


def test_un_etat_civil_hostile_est_echappe():
    html = rendre_cv_html(CV_TEST, "etat_civil", "a4", etat_civil.lignes(profil(lieu_naissance="<script>x</script>"), "fr"))
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_papier_letter_en_amerique_du_nord_seulement():
    assert "size: letter" in rendre_cv_html(CV_TEST, "nord_americain", "letter") and "size: letter" in rendre_lettre_html({}, "letter")
    assert "size: letter" not in rendre_cv_html(CV_TEST, "classique") and "size: letter" not in rendre_lettre_html({})
    assert {f.code for f in pays.fiches().values() if f.format_page == "letter"} == {"us", "ca", "ca-qc"}


def test_le_pdf_ne_charge_aucune_ressource_externe():
    for url in ("file:///etc/passwd", "https://example.com/x.jpg", "http://169.254.169.254/", "data:text/html;base64,AAAA", "data:image/svg+xml;base64,AAAA"):
        with pytest.raises(ValueError):
            _ressource_autorisee(url)


# --- Photo ---

def test_la_photo_est_recadree_et_sans_metadonnees():
    exif = Image.Exif()
    exif[0x0112] = 6  # tournee de 90 degres
    exif[0x010F] = "Appareil secret"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (4.0, 3.0, 2.0)
    brut = image(800, 600, exif=exif)
    assert b"Appareil secret" in brut
    sortie = photo_service.normaliser(brut)
    img = Image.open(BytesIO(sortie))
    assert img.format == "JPEG" and img.size == (413, 531) and not img.getexif() and b"Appareil secret" not in sortie
    assert len(sortie) < 150_000


def test_photo_transparente_sur_fond_blanc():
    img = Image.open(BytesIO(photo_service.normaliser(image(format_="PNG", mode="RGBA"))))
    assert img.mode == "RGB" and all(v > 120 for v in img.getpixel((200, 200)))


@pytest.mark.parametrize("contenu, attendu", [
    (b"pas une image", "photo_invalid"),
    (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "photo_invalid"),
    (image(format_="GIF", couleur=(1, 2, 3)), "photo_invalid"),
    (image(100, 100), "photo_too_small"),
    (image(8000, 8000, format_="PNG"), "photo_too_large"),
    (image()[:200], "photo_invalid"),
], ids=["texte", "svg", "gif", "trop_petite", "image_geante", "tronquee"])
def test_photo_refusee(contenu, attendu):
    with pytest.raises(photo_service.PhotoInvalide) as e:
        photo_service.normaliser(contenu)
    assert e.value.code == attendu


def test_envoi_lecture_et_suppression_de_la_photo(client, make_user):
    _, h = make_user()
    assert client.get("/profil/", headers=h).json()["a_photo"] is False
    assert client.get("/profil/photo", headers=h).status_code == 404
    r = client.put("/profil/photo", files={"file": ("moi.jpg", image())}, headers=h)
    assert r.status_code == 200 and r.json() == {"a_photo": True}
    r = client.get("/profil/photo", headers=h)
    assert r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "private, no-store"
    assert Image.open(BytesIO(r.content)).size == (413, 531)
    assert client.get("/profil/", headers=h).json()["a_photo"] is True
    # la photo d'une personne n'est jamais lisible par une autre
    _, autre = make_user()
    assert client.get("/profil/photo", headers=autre).status_code == 404 and client.get("/profil/photo").status_code in (401, 403)
    assert client.delete("/profil/photo", headers=h).json() == {"a_photo": False}
    assert client.get("/profil/photo", headers=h).status_code == 404


def test_photo_refusee_par_la_route(client, make_user):
    _, h = make_user()
    r = client.put("/profil/photo", files={"file": ("x.jpg", b"texte")}, headers=h)
    assert r.status_code == 400 and code(r) == "photo_invalid"
    r = client.put("/profil/photo", files={"file": ("x.jpg", b"0" * (photo_service.MAX_OCTETS + 1))}, headers=h)
    assert r.status_code == 413 and code(r) == "photo_too_large"
    _, non_verifie = make_user(verifie=False)
    assert client.put("/profil/photo", files={"file": ("x.jpg", image())}, headers=non_verifie).status_code == 403


# --- Profil ---

def test_etat_civil_enregistre_puis_efface(client, make_user):
    _, h = make_user()
    r = client.put("/profil/", json={"date_naissance": "1994-03-12", "lieu_naissance": " Douala ", "nationalite": "cm",
                                     "situation_familiale": "marie_f", "enfants": 2, "permis_sejour": ""}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["date_naissance"], d["lieu_naissance"], d["nationalite"], d["situation_familiale"], d["enfants"], d["permis_sejour"]) == (
        "1994-03-12", "Douala", "CM", "marie_f", 2, None)
    r = client.put("/profil/", json={"date_naissance": "", "lieu_naissance": "", "nationalite": "", "situation_familiale": "", "enfants": ""}, headers=h)
    assert r.status_code == 200 and all(r.json()[c] is None for c in ("date_naissance", "lieu_naissance", "nationalite", "situation_familiale", "enfants"))


@pytest.mark.parametrize("champs", [
    {"date_naissance": "2020-01-01"}, {"date_naissance": "1850-01-01"}, {"nationalite": "ZZ"},
    {"situation_familiale": "complique"}, {"enfants": 99}, {"lieu_naissance": "x" * 121},
])
def test_etat_civil_invalide_refuse(client, make_user, champs):
    _, h = make_user()
    assert client.put("/profil/", json=champs, headers=h).status_code == 422


# --- Generation ---

@pytest.fixture
def generation(db, make_user, monkeypatch):
    u, h = make_user()
    p = u.profil
    p.competences = "Jira"
    p.date_naissance, p.lieu_naissance, p.nationalite, p.situation_familiale = date(1994, 3, 12), "Douala", "CM", "marie_f"
    p.photo, p.photo_maj = photo_service.normaliser(image()), p.date_maj
    offre = OffreEmploi(utilisateur_id=u.id, contenu_brut="x" * 50, titre_poste="T", entreprise="E", pays="cm")
    db.add(offre)
    db.flush()
    c = Candidature(utilisateur_id=u.id, profil_id=p.id, offre_id=offre.id)
    db.add(c)
    db.commit()

    async def faux_cv(*args, **kwargs):
        # une IA trop zelee tente de decider elle-meme de l'affichage
        return {"nom": "X", "langue": "fr", "affichage": {"photo": True, "etat_civil": True}}

    async def fausse_lettre(*args, **kwargs):
        return {"paragraphes": ["ok"]}

    monkeypatch.setattr(rc, "generer_cv", faux_cv)
    monkeypatch.setattr(rc, "generer_lettre_motivation", fausse_lettre)
    return u, h, c.id


def test_le_choix_de_la_personne_decide_pas_l_ia(client, db, generation):
    u, h, cid = generation
    r = client.post(f"/candidature/{cid}/generer", json={"modele_cv": "etat_civil"}, headers=h)
    assert r.json()["affichage"] == {"photo": False, "etat_civil": False}
    r = client.post(f"/candidature/{cid}/generer", json={"modele_cv": "etat_civil", "avec_photo": True, "avec_etat_civil": True}, headers=h)
    assert r.json()["affichage"] == {"photo": True, "etat_civil": True}
    r = client.post(f"/candidature/{cid}/generer", json={"pays": "ca-qc", "avec_photo": True, "avec_etat_civil": True}, headers=h)
    assert r.json()["affichage"] == {"photo": False, "etat_civil": False}


def test_rien_n_est_copie_dans_le_document_enregistre(client, db, generation):
    u, h, cid = generation
    client.post(f"/candidature/{cid}/generer", json={"avec_photo": True, "avec_etat_civil": True}, headers=h)
    doc = db.query(CV).filter(CV.candidature_id == cid).one()
    enregistre = json.dumps(doc.donnees) + (doc.contenu_genere or "")
    assert "1994" not in enregistre and "Douala" not in enregistre and "base64" not in enregistre
    # le PDF lit le profil actuel : retirer la photo la retire aussi des telechargements
    candidature = db.get(Candidature, cid)
    lignes, photo = rc._elements_personnels(candidature, pays.fiche("cm"))
    assert lignes and photo.startswith("data:image/jpeg;base64,")
    client.delete("/profil/photo", headers=h)
    db.expire_all()
    assert rc._elements_personnels(db.get(Candidature, cid), pays.fiche("cm"))[1] is None


def test_l_ia_ne_recoit_jamais_la_photo_ni_l_etat_civil(monkeypatch):
    recus = []

    async def fausse_reponse(prompt, *args, **kwargs):
        recus.append(prompt)
        return '{"questions": [{"id": "q1"}]}'

    monkeypatch.setattr(ia_service, "_complete", fausse_reponse)
    p = SimpleNamespace(
        titre_profil="Cheffe", competences="Jira", experiences=[], formations=[], langues="Anglais", telephone="+237", adresse="Yaounde",
        nom_complet_cv="Amina", email_cv="a@example.com", utilisateur=None, **vars(profil(lieu_naissance="Garoua-Secret", permis_sejour="PERMIS-SECRET")),
    )
    offre = SimpleNamespace(titre_poste="PM", entreprise="E", mots_cles="Jira", contenu_brut="Poste a Douala")
    for f in (None, pays.fiche("cm"), pays.fiche("ch")):
        asyncio.run(ia_service.analyser_offre("Poste a Douala", p))
        asyncio.run(ia_service.generer_questions_alignement(p, offre))
        asyncio.run(ia_service.generer_cv(p, offre, fiche_pays=f))
        asyncio.run(ia_service.generer_lettre_motivation(p, offre, fiche_pays=f))
    assert len(recus) == 12
    for prompt in recus:
        for secret in ("1994", "Garoua-Secret", "PERMIS-SECRET", "camerounaise", "marie_f", "Mariée"):
            assert secret not in prompt


# --- Droits RGPD ---

def test_l_export_contient_la_photo_et_l_etat_civil(client, db, generation):
    u, h, cid = generation
    client.post(f"/candidature/{cid}/generer", json={"pays": "cm"}, headers=h)
    d = client.get("/compte/export", headers=h).json()
    assert d["profil"]["date_naissance"] == "1994-03-12" and d["profil"]["nationalite"] == "CM"
    assert d["profil"]["photo_jpeg_base64"].startswith("/9j/")
    assert d["offres"][0]["pays_detecte"] == "cm" and d["candidatures"][0]["pays_vise"] == "cm"


def test_la_suppression_du_compte_efface_la_photo(db, generation):
    from app.services import compte_service
    u, _, _ = generation
    uid = u.id
    compte_service.supprimer(db, uid)
    assert db.query(Profil).filter(Profil.utilisateur_id == uid).count() == 0
