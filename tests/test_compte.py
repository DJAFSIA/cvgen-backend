"""Droits RGPD : rectification, export, suppression ; acceptation des conditions a l'inscription."""
import uuid

import pytest
import stripe

from app.core.config import settings
from app.core.security import hash_password
from app.models.candidature import CV, Candidature, LettreMotivation
from app.models.facturation import Paiement, Usage
from app.models.offre import OffreEmploi
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur
from conftest import code

MDP = "Secret-Pass-2026"


@pytest.fixture
def compte_rempli(db, make_user):
    """Compte email avec mot de passe, profil, offre, candidature + documents, paiement et usage."""
    u, h = make_user()
    u.mot_de_passe = hash_password(MDP)
    profil = db.query(Profil).filter(Profil.utilisateur_id == u.id).one()
    profil.titre_profil, profil.competences = "Data Engineer", "Python, SQL"
    offre = OffreEmploi(utilisateur_id=u.id, contenu_brut="Offre de test " * 5, titre_poste="Dev", entreprise="Acme")
    db.add(offre)
    db.flush()
    cand = Candidature(utilisateur_id=u.id, profil_id=profil.id, offre_id=offre.id, statut="generee")
    db.add(cand)
    db.flush()
    db.add(CV(candidature_id=cand.id, contenu_genere="# CV", donnees={"nom": "Test"}))
    db.add(LettreMotivation(candidature_id=cand.id, contenu_genere="Lettre", donnees={"paragraphes": ["x"]}))
    db.add(Paiement(utilisateur_id=u.id, fournisseur="flutterwave", reference=f"apply-{uuid.uuid4().hex}",
                    montant=3000, devise="XAF", statut="paid", jours=30))
    db.add(Usage(utilisateur_id=u.id, periode="2026-11", generations=1, analyses=2, imports=1))
    db.commit()
    return u, h, cand.id


def test_export_contient_toutes_les_donnees_sans_le_mot_de_passe(client, compte_rempli):
    u, h, cand_id = compte_rempli
    r = client.get("/compte/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["compte"]["email"] == u.email
    assert data["profil"]["titre"] == "Data Engineer"
    assert len(data["offres"]) == 1 and data["offres"][0]["entreprise"] == "Acme"
    assert data["candidatures"][0]["cv"]["donnees"] == {"nom": "Test"}
    assert data["candidatures"][0]["lettre"]["contenu"] == "Lettre"
    assert data["paiements"][0]["montant"] == 3000 and data["consommation"][0]["mois"] == "2026-11"
    assert "mot_de_passe" not in r.text and u.mot_de_passe not in r.text


def test_rectification_du_nom_et_de_la_langue(client, make_user):
    _, h = make_user()
    r = client.patch("/compte/", json={"prenom": "  Amina ", "langue": "fr"}, headers=h)
    assert r.status_code == 200 and r.json()["prenom"] == "Amina" and r.json()["langue"] == "fr"
    assert client.patch("/compte/", json={"nom": "   "}, headers=h).status_code == 422


def test_suppression_refusee_avec_un_mauvais_mot_de_passe(client, db, compte_rempli):
    u, h, _ = compte_rempli
    r = client.post("/compte/supprimer", json={"mot_de_passe": "mauvais"}, headers=h)
    assert r.status_code == 400 and code(r) == "wrong_password"
    db.expire_all()
    assert db.query(Utilisateur).filter(Utilisateur.id == u.id).first() is not None


def test_suppression_efface_tout_et_garde_les_paiements_anonymises(client, db, compte_rempli):
    u, h, cand_id = compte_rempli
    uid = u.id  # l'objet ne sera plus relisible une fois la ligne supprimee
    paiement_ref = db.query(Paiement).filter(Paiement.utilisateur_id == uid).one().reference

    r = client.post("/compte/supprimer", json={"mot_de_passe": MDP}, headers=h)
    assert r.status_code == 200 and r.json() == {"supprime": True}

    db.expire_all()
    assert db.query(Utilisateur).filter(Utilisateur.id == uid).first() is None
    assert db.query(Profil).filter(Profil.utilisateur_id == uid).count() == 0
    assert db.query(OffreEmploi).filter(OffreEmploi.utilisateur_id == uid).count() == 0
    assert db.query(Candidature).filter(Candidature.id == cand_id).count() == 0
    assert db.query(CV).filter(CV.candidature_id == cand_id).count() == 0
    assert db.query(LettreMotivation).filter(LettreMotivation.candidature_id == cand_id).count() == 0
    assert db.query(Usage).filter(Usage.utilisateur_id == uid).count() == 0
    # Trace comptable conservee, mais plus rattachee a personne
    reste = db.query(Paiement).filter(Paiement.reference == paiement_ref).one()
    assert reste.utilisateur_id is None and reste.montant == 3000
    # La session ne fonctionne plus
    assert client.get("/auth/me", headers=h).status_code == 401


def test_compte_google_confirme_par_son_email(client, db, make_user):
    u, h = make_user(provider="google")
    r = client.post("/compte/supprimer", json={"confirmation": "autre@example.com"}, headers=h)
    assert r.status_code == 400 and code(r) == "confirmation_invalid"
    assert client.post("/compte/supprimer", json={"confirmation": u.email.upper()}, headers=h).status_code == 200


@pytest.fixture
def stripe_suppression(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    appels = {"supprimes": [], "erreur": None}

    def supprimer(cid, api_key=None):
        assert api_key == "sk_test_fake"
        if appels["erreur"]:
            raise appels["erreur"]
        appels["supprimes"].append(cid)
        return {"id": cid, "deleted": True}

    monkeypatch.setattr(stripe.Customer, "delete", supprimer)
    return appels


def test_suppression_arrete_l_abonnement_stripe(client, db, make_user, stripe_suppression):
    cus = f"cus_{uuid.uuid4().hex[:10]}"
    u, h = make_user(stripe_customer_id=cus, stripe_subscription_id="sub_1", plan="pro")
    u.mot_de_passe = hash_password(MDP)
    db.commit()
    assert client.post("/compte/supprimer", json={"mot_de_passe": MDP}, headers=h).status_code == 200
    assert stripe_suppression["supprimes"] == [cus]


def test_suppression_bloquee_si_stripe_ne_peut_pas_arreter_l_abonnement(client, db, make_user, stripe_suppression):
    u, h = make_user(stripe_customer_id=f"cus_{uuid.uuid4().hex[:10]}", stripe_subscription_id="sub_1")
    u.mot_de_passe = hash_password(MDP)
    db.commit()
    stripe_suppression["erreur"] = stripe.APIConnectionError("reseau indisponible")
    r = client.post("/compte/supprimer", json={"mot_de_passe": MDP}, headers=h)
    assert r.status_code == 502 and code(r) == "payment_provider_error"
    db.expire_all()
    assert db.query(Utilisateur).filter(Utilisateur.id == u.id).first() is not None  # rien n'est supprime


def test_client_stripe_deja_supprime_n_empeche_pas_la_suppression(client, db, make_user, stripe_suppression):
    u, h = make_user(stripe_customer_id=f"cus_{uuid.uuid4().hex[:10]}")
    u.mot_de_passe = hash_password(MDP)
    db.commit()
    stripe_suppression["erreur"] = stripe.InvalidRequestError("No such customer", "id", code="resource_missing")
    assert client.post("/compte/supprimer", json={"mot_de_passe": MDP}, headers=h).status_code == 200


def test_inscription_exige_l_acceptation_des_conditions(client):
    corps = {"nom": "T", "prenom": "U", "email": f"cgu-{uuid.uuid4().hex[:8]}@example.com", "mot_de_passe": "FirstPass-7731"}
    r = client.post("/auth/inscription", json=corps)
    assert r.status_code == 400 and code(r) == "terms_required"
    r = client.post("/auth/inscription", json={**corps, "accepte_cgu": True})
    assert r.status_code == 201 and r.json()["utilisateur"]["cgu_acceptees_le"] is not None
