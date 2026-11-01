"""Droits RGPD : export des donnees (acces, portabilite) et suppression du compte (effacement)."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.candidature import CV, Candidature, LettreMotivation
from app.models.facturation import Paiement, Usage
from app.models.offre import OffreEmploi
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur


def _document(doc) -> dict | None:
    if not doc:
        return None
    return {
        "contenu": doc.contenu_genere,
        "donnees": doc.donnees,
        "date_generation": doc.date_generation,
        **({"modele": doc.modele} if isinstance(doc, CV) else {"ton": doc.ton}),
    }


def exporter(db: Session, u: Utilisateur) -> dict:
    """Toutes les donnees personnelles du compte, dans un format lisible et reutilisable (JSON).
    Seul le hachage du mot de passe est exclu : ce n'est pas une donnee exploitable par la personne."""
    profil = db.query(Profil).filter(Profil.utilisateur_id == u.id).first()
    offres = db.query(OffreEmploi).filter(OffreEmploi.utilisateur_id == u.id).order_by(OffreEmploi.date_ajout).all()
    candidatures = (
        db.query(Candidature).filter(Candidature.utilisateur_id == u.id).order_by(Candidature.date_creation).all()
    )
    paiements = db.query(Paiement).filter(Paiement.utilisateur_id == u.id).order_by(Paiement.cree_le).all()
    usages = db.query(Usage).filter(Usage.utilisateur_id == u.id).order_by(Usage.periode).all()

    return {
        "format": "cvgen-export",
        "version": 1,
        "genere_le": datetime.now(timezone.utc),
        "compte": {
            "id": u.id,
            "prenom": u.prenom,
            "nom": u.nom,
            "email": u.email,
            "email_verifie": u.email_verifie,
            "connexion": u.provider or "email",
            "connexion_google_liee": bool(u.google_id),
            "langue": u.langue,
            "date_inscription": u.date_inscription,
            "derniere_connexion": u.derniere_connexion,
            "conditions_acceptees_le": u.cgu_acceptees_le,
            "version_conditions": u.cgu_version,
            "plan": u.plan,
            "plan_expire_le": u.plan_expire_le,
            "client_stripe": u.stripe_customer_id,
        },
        "profil": None if not profil else {
            "nom_complet": profil.nom_complet_cv,
            "email": profil.email_cv,
            "telephone": profil.telephone,
            "adresse": profil.adresse,
            "titre": profil.titre_profil,
            "experiences": profil.experiences,
            "formations": profil.formations,
            "competences": profil.competences,
            "langues": profil.langues,
            "mis_a_jour_le": profil.date_maj,
        },
        "offres": [
            {
                "id": o.id,
                "titre_poste": o.titre_poste,
                "entreprise": o.entreprise,
                "url_source": o.url_source,
                "texte": o.contenu_brut,
                "mots_cles": o.mots_cles,
                "score_compatibilite": o.score_compatibilite,
                "ajoutee_le": o.date_ajout,
            }
            for o in offres
        ],
        "candidatures": [
            {
                "id": c.id,
                "offre_id": c.offre_id,
                "statut": c.statut,
                "score_compatibilite": c.score_compatibilite,
                "creee_le": c.date_creation,
                "cv": _document(c.cv),
                "lettre": _document(c.lettre),
            }
            for c in candidatures
        ],
        "paiements": [
            {
                "fournisseur": p.fournisseur,
                "reference": p.reference,
                "montant": p.montant,
                "devise": p.devise,
                "statut": p.statut,
                "jours": p.jours,
                "cree_le": p.cree_le,
                "paye_le": p.paye_le,
            }
            for p in paiements
        ],
        "consommation": [
            {"mois": x.periode, "generations": x.generations, "analyses": x.analyses, "imports": x.imports}
            for x in usages
        ],
    }


def supprimer(db: Session, utilisateur_id) -> None:
    """Efface le compte et tout son contenu, dans une seule transaction.

    Les paiements sont conserves pour les obligations comptables, mais detaches du compte
    (aucune donnee d'identite ne reste associee). L'ordre des suppressions respecte les
    cles etrangeres (documents -> candidatures -> offres et profil -> compte).
    """
    ids_candidatures = [cid for (cid,) in db.query(Candidature.id).filter(Candidature.utilisateur_id == utilisateur_id)]
    try:
        if ids_candidatures:
            db.query(CV).filter(CV.candidature_id.in_(ids_candidatures)).delete(synchronize_session=False)
            db.query(LettreMotivation).filter(LettreMotivation.candidature_id.in_(ids_candidatures)).delete(synchronize_session=False)
            db.query(Candidature).filter(Candidature.id.in_(ids_candidatures)).delete(synchronize_session=False)
        db.query(OffreEmploi).filter(OffreEmploi.utilisateur_id == utilisateur_id).delete(synchronize_session=False)
        db.query(Profil).filter(Profil.utilisateur_id == utilisateur_id).delete(synchronize_session=False)
        db.query(Usage).filter(Usage.utilisateur_id == utilisateur_id).delete(synchronize_session=False)
        db.query(Paiement).filter(Paiement.utilisateur_id == utilisateur_id).update(
            {Paiement.utilisateur_id: None}, synchronize_session=False,
        )
        db.query(Utilisateur).filter(Utilisateur.id == utilisateur_id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
