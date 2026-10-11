import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

import app.routers.candidature as rc
from app.models.candidature import Candidature
from app.models.facturation import Usage
from app.models.offre import OffreEmploi
from app.services.llm import IAError
from conftest import code


@pytest.fixture
def ia_lente(monkeypatch):
    etat = {"echec": False}

    async def faux_cv(*args, **kwargs):
        await asyncio.sleep(0.5)
        if etat["echec"]:
            raise IAError("panne simulee")
        return {"nom": "X", "experiences": []}

    async def fausse_lettre(*args, **kwargs):
        await asyncio.sleep(0.5)
        return {"paragraphes": ["ok"]}

    monkeypatch.setattr(rc, "generer_cv", faux_cv)
    monkeypatch.setattr(rc, "generer_lettre_motivation", fausse_lettre)
    return etat


@pytest.fixture
def candidatures(db, make_user):
    u, h = make_user()
    offre = OffreEmploi(utilisateur_id=u.id, contenu_brut="x" * 50, titre_poste="T", entreprise="E")
    db.add(offre)
    db.flush()
    ids = []
    for _ in range(8):
        c = Candidature(utilisateur_id=u.id, profil_id=u.profil.id, offre_id=offre.id)
        db.add(c)
        db.flush()
        ids.append(c.id)
    db.commit()
    return u, h, ids


def compteur(db, u):
    db.expire_all()
    usage = db.query(Usage).filter(Usage.utilisateur_id == u.id).first()
    return usage.generations if usage else 0


def test_generations_simultanees_ne_depassent_pas_le_quota(client, db, candidatures, ia_lente):
    u, h, ids = candidatures

    def generer(cid):
        return client.post(f"/candidature/{cid}/generer", json={}, headers=h).status_code

    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(generer, ids))
    assert codes.count(200) == 3 and codes.count(402) == 5
    assert compteur(db, u) == 3


def test_echec_de_generation_ne_consomme_pas_le_quota(client, db, candidatures, ia_lente):
    u, h, ids = candidatures
    ia_lente["echec"] = True
    r = client.post(f"/candidature/{ids[0]}/generer", json={}, headers=h)
    assert r.status_code == 502 and code(r) == "ia_unavailable"
    assert compteur(db, u) == 0


def test_quota_atteint_message_explicite(client, db, candidatures, ia_lente):
    u, h, ids = candidatures
    for cid in ids[:3]:
        assert client.post(f"/candidature/{cid}/generer", json={}, headers=h).status_code == 200
    r = client.post(f"/candidature/{ids[3]}/generer", json={}, headers=h)
    assert r.status_code == 402 and code(r) == "quota_exceeded"
