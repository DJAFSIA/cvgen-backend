"""Usages du CV par pays : fiches valides, consignes donnees a l'IA, pays detecte puis choisi."""
import asyncio
from types import SimpleNamespace

import pytest

import app.routers.candidature as rc
from app import pays
from app.models.candidature import Candidature
from app.models.facturation import Usage
from app.models.offre import OffreEmploi
from app.routers.offre import _pays_detecte
from app.services import ia_service
from conftest import code

CODES = {"cm", "ca-qc", "ca", "fr", "be", "ch", "ci", "sn", "us"}


def test_les_fiches_sont_completes_et_sourcees():
    fiches = pays.fiches()
    assert set(fiches) == CODES
    for f in fiches.values():
        assert f.nom["fr"] and f.nom["en"]
        assert len(f.resume["fr"]) >= 2 and len(f.resume["fr"]) == len(f.resume["en"])
        assert f.sources and f.verifie_le
        # « officielle » suppose au moins une source publique
        if f.fiabilite == "officielle":
            assert any(s.type == "officielle" for s in f.sources), f.code


def _profil():
    return SimpleNamespace(
        titre_profil="Cheffe de projet", competences="Jira", experiences=[], formations=[], langues="Anglais",
        telephone=None, adresse="Douala", nom_complet_cv="Amina Exemple", email_cv="a@example.com", utilisateur=None,
    )


def _offre():
    return SimpleNamespace(titre_poste="PM", entreprise="Exemple", mots_cles="Jira", contenu_brut="Poste a Montreal")


@pytest.fixture
def prompts(monkeypatch):
    recus = []

    async def fausse_reponse(prompt, *args, **kwargs):
        recus.append(prompt)
        return "{}"

    monkeypatch.setattr(ia_service, "_complete", fausse_reponse)
    return recus


def test_les_usages_du_pays_entrent_dans_le_cv_et_la_lettre(prompts):
    quebec = pays.fiche("ca-qc")
    asyncio.run(ia_service.generer_cv(_profil(), _offre(), fiche_pays=quebec))
    asyncio.run(ia_service.generer_lettre_motivation(_profil(), _offre(), fiche_pays=quebec))
    cv, lettre = prompts
    assert "Usages du pays vise, Québec (Canada)" in cv and "2 pages au plus" in cv
    assert "Aucune photo, ni âge" in cv and "Elles ne te sont pas transmises" in cv
    assert "Lettre de présentation d'une page" in lettre


def test_sans_pays_aucune_consigne_de_pays(prompts):
    asyncio.run(ia_service.generer_cv(_profil(), _offre()))
    assert "Usages du pays vise" not in prompts[0]


def test_l_analyse_demande_le_pays_du_poste(prompts):
    asyncio.run(ia_service.analyser_offre("Poste a Montreal", _profil(), "fr"))
    assert '"pays"' in prompts[0] and "ca-qc (Québec (Canada))" in prompts[0] and '"autre"' in prompts[0]


def test_seuls_les_codes_connus_sont_gardes():
    assert _pays_detecte("CA-QC") == "ca-qc"
    assert _pays_detecte("autre") == "autre"
    assert _pays_detecte("Cameroun") is None
    assert _pays_detecte(None) is None


def test_la_liste_des_pays_pour_le_site(client):
    r = client.get("/pays/")
    assert r.status_code == 200
    liste = r.json()
    assert {p["code"] for p in liste} == CODES
    quebec = next(p for p in liste if p["code"] == "ca-qc")
    assert quebec["nom"]["en"] == "Quebec (Canada)" and quebec["photo"] == "deconseillee"
    assert quebec["sources"][0]["url"].startswith("https://")


def test_l_analyse_enregistre_le_pays_detecte(client, make_user, monkeypatch):
    import app.routers.offre as ro

    async def fausse_analyse(contenu, profil, langue):
        return {"titre_poste": "PM", "entreprise": "Exemple", "score_compatibilite": 70, "mots_cles": [], "pays": "CM"}

    monkeypatch.setattr(ro, "analyser_offre", fausse_analyse)
    _, h = make_user()
    r = client.post("/offre/", json={"contenu_brut": "Cheffe de projet digital a Douala, Cameroun, CDI."}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["pays"] == "cm"


@pytest.fixture
def generation(db, make_user, monkeypatch):
    """Une candidature dont l'offre a ete detectee au Cameroun, et une IA factice qui note la fiche recue."""
    u, h = make_user()
    u.profil.competences = "Jira, gestion de projet"  # profil renseigne : la generation est permise
    offre = OffreEmploi(utilisateur_id=u.id, contenu_brut="x" * 50, titre_poste="T", entreprise="E", pays="cm")
    db.add(offre)
    db.flush()
    c = Candidature(utilisateur_id=u.id, profil_id=u.profil.id, offre_id=offre.id)
    db.add(c)
    db.commit()
    recues = []

    async def faux_cv(profil, offre, modele, langue, fiche_pays=None):
        recues.append(fiche_pays.code if fiche_pays else None)
        return {"nom": "X", "experiences": []}

    async def fausse_lettre(profil, offre, reponses, langue, fiche_pays=None):
        return {"paragraphes": ["ok"]}

    monkeypatch.setattr(rc, "generer_cv", faux_cv)
    monkeypatch.setattr(rc, "generer_lettre_motivation", fausse_lettre)
    return u, h, c.id, recues


def _generations(db, u):
    db.expire_all()
    usage = db.query(Usage).filter(Usage.utilisateur_id == u.id).first()
    return usage.generations if usage else 0


def test_la_generation_suit_le_pays_detecte_puis_le_choix(client, db, generation):
    u, h, cid, recues = generation
    assert client.post(f"/candidature/{cid}/generer", json={}, headers=h).json()["pays"] == "cm"
    assert client.post(f"/candidature/{cid}/generer", json={"pays": "ca-qc"}, headers=h).json()["pays"] == "ca-qc"
    assert client.post(f"/candidature/{cid}/generer", json={"pays": "autre"}, headers=h).json()["pays"] == "autre"
    assert recues == ["cm", "ca-qc", None]


def test_un_pays_inconnu_est_refuse_sans_consommer_le_quota(client, db, generation):
    u, h, cid, recues = generation
    avant = _generations(db, u)
    r = client.post(f"/candidature/{cid}/generer", json={"pays": "zz"}, headers=h)
    assert r.status_code == 422 and code(r) == "unknown_country"
    assert _generations(db, u) == avant and recues == []


def test_pas_de_generation_avec_un_profil_vide(client, db, generation):
    """Avec un profil vide, l'IA ecrivait la lettre a partir des exigences de l'offre (faits inventes)."""
    u, h, cid, recues = generation
    u.profil.competences = None
    db.commit()
    avant = _generations(db, u)
    r = client.post(f"/candidature/{cid}/generer", json={}, headers=h)
    assert r.status_code == 400 and code(r) == "profile_incomplete"
    assert _generations(db, u) == avant and recues == []


def test_la_lettre_n_attribue_pas_les_exigences_de_l_offre(prompts):
    asyncio.run(ia_service.generer_lettre_motivation(_profil(), _offre()))
    assert "L'offre decrit le poste, pas le candidat" in prompts[0]
