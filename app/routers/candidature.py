import asyncio
import logging
import os
import re
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload # Import de joinedload ajouté
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.candidature import Candidature, CV, LettreMotivation
from app.models.offre import OffreEmploi
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur
from app.schemas.candidature import CandidatureCreate, CandidatureResponse, GenerationRequest
from app.services.ia_service import generer_cv, generer_lettre_motivation
from app.services.pdf_service import generer_pdf
from app.services.document_service import (
    rendre_cv_html, rendre_lettre_html, rendre_markdown_html, cv_en_markdown, lettre_en_markdown,
)
from app.schemas.document import CVData, LettreData, ModeleCV
from app.core.rate_limit import generation_limiter

router = APIRouter()
logger = logging.getLogger(__name__)


def _nom_sur(nom: str) -> str:
    """Nom utilisable dans un nom de fichier et un en-tete HTTP."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", nom).strip("_") or "document"

# 1. CRÉER UNE CANDIDATURE (Lier une offre à un profil)
@router.post("/", response_model=CandidatureResponse, status_code=201)
def creer_candidature(
    data: CandidatureCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    # Vérifier que le profil existe
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Veuillez remplir votre profil avant de postuler.")

    # Vérifier que l'offre appartient bien à l'utilisateur (ou existe)
    offre = db.query(OffreEmploi).filter(
        OffreEmploi.id == data.offre_id,
        OffreEmploi.utilisateur_id == current_user.id
    ).first()
    
    if not offre:
        raise HTTPException(status_code=404, detail="Offre introuvable.")

    # Créer l'entrée
    candidature = Candidature(
        utilisateur_id=current_user.id,
        profil_id=profil.id,
        offre_id=offre.id,
        statut="en_cours",
        score_compatibilite=offre.score_compatibilite
    )
    db.add(candidature)
    db.commit()
    db.refresh(candidature)
    return candidature


# 2. GÉNÉRER LES DOCUMENTS (Appel IA)
@router.post("/{candidature_id}/generer", dependencies=[generation_limiter.by_user()])
async def lancer_generation(
    candidature_id: UUID,
    data: GenerationRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    # CHARGEMENT CRUCIAL : On récupère la candidature avec le profil ET l'utilisateur (pour nom/email)
    candidature = db.query(Candidature).options(
        joinedload(Candidature.profil).joinedload(Profil.utilisateur),
        joinedload(Candidature.offre)
    ).filter(
        Candidature.id == candidature_id,
        Candidature.utilisateur_id == current_user.id
    ).first()
    
    if not candidature:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    # On appelle l'IA (le service utilisera candidature.profil.utilisateur pour l'identité)
    donnees_cv, donnees_lettre = await asyncio.gather(
        generer_cv(candidature.profil, candidature.offre, data.modele_cv),
        generer_lettre_motivation(
            candidature.profil,
            candidature.offre,
            data.reponses_alignement
        ),
    )

    # Normalisation des sorties du LLM (champs manquants, null, extras)
    donnees_cv = CVData.model_validate(donnees_cv).model_dump()
    donnees_lettre = LettreData.model_validate(donnees_lettre).model_dump()
    contenu_cv = cv_en_markdown(donnees_cv)
    contenu_lettre = lettre_en_markdown(donnees_lettre)

    # 4. Sauvegarde ou mise a jour du CV
    cv_obj = db.query(CV).filter(CV.candidature_id == candidature.id).first()
    if not cv_obj:
        cv_obj = CV(candidature_id=candidature.id)
        db.add(cv_obj)
    cv_obj.contenu_genere = contenu_cv
    cv_obj.donnees = donnees_cv
    cv_obj.modele = data.modele_cv

    # 5. Sauvegarde ou mise a jour de la lettre
    lettre_obj = db.query(LettreMotivation).filter(LettreMotivation.candidature_id == candidature.id).first()
    if not lettre_obj:
        lettre_obj = LettreMotivation(candidature_id=candidature.id)
        db.add(lettre_obj)
    lettre_obj.contenu_genere = contenu_lettre
    lettre_obj.donnees = donnees_lettre
    lettre_obj.ton = data.ton_lettre

    # 6. Mise a jour du statut final
    candidature.statut = "generee"
    db.commit()

    return {
        "id": candidature.id,
        "cv": contenu_cv,
        "lettre": contenu_lettre,
        "modele": data.modele_cv,
    }


# 3. EXPORTER EN PDF (Appel WeasyPrint)
@router.get("/{candidature_id}/export-pdf")
async def exporter_pdf(
    candidature_id: UUID,
    background_tasks: BackgroundTasks,
    type_doc: str = "cv",  # "cv" ou "lettre"
    modele: ModeleCV | None = None,  # change le modele de CV sans regenerer
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    candidature = db.query(Candidature).options(
        joinedload(Candidature.cv),
        joinedload(Candidature.lettre)
    ).filter(
        Candidature.id == candidature_id,
        Candidature.utilisateur_id == current_user.id
    ).first()

    if not candidature:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    if type_doc == "cv" and candidature.cv:
        doc = candidature.cv
        html_contenu = (
            rendre_cv_html(doc.donnees, modele or doc.modele or "classique")
            if doc.donnees else rendre_markdown_html(doc.contenu_genere)
        )
        nom_fichier = f"CV_{_nom_sur(current_user.nom)}.pdf"
    elif type_doc == "lettre" and candidature.lettre:
        doc = candidature.lettre
        html_contenu = (
            rendre_lettre_html(doc.donnees)
            if doc.donnees else rendre_markdown_html(doc.contenu_genere)
        )
        nom_fichier = f"Lettre_{_nom_sur(current_user.nom)}.pdf"
    else:
        raise HTTPException(status_code=404, detail="Document non genere ou type inconnu.")

    try:
        chemin_pdf = await generer_pdf(html_contenu)
    except Exception:
        logger.exception("Echec de la generation du PDF")
        raise HTTPException(status_code=500, detail="Impossible de generer le PDF.")
    background_tasks.add_task(os.remove, chemin_pdf)

    return FileResponse(
        chemin_pdf,
        media_type="application/pdf",
        filename=nom_fichier
    )


# 4. LISTER SES CANDIDATURES
@router.get("/", response_model=List[CandidatureResponse])
def liste_candidatures(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    return db.query(Candidature).options(joinedload(Candidature.offre)).filter(
        Candidature.utilisateur_id == current_user.id
    ).order_by(Candidature.date_creation.desc()).all()
