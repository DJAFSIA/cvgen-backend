from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload # Import de joinedload ajouté
from typing import List
import os

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.candidature import Candidature, CV, LettreMotivation
from app.models.offre import OffreEmploi
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur
from app.schemas.candidature import CandidatureCreate, CandidatureResponse, GenerationRequest
from app.services.ia_service import generer_cv, generer_lettre_motivation
from app.services.pdf_service import generer_pdf

router = APIRouter()

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
        statut="en_cours"
    )
    db.add(candidature)
    db.commit()
    db.refresh(candidature)
    return candidature


# 2. GÉNÉRER LES DOCUMENTS (Appel IA)
@router.post("/{candidature_id}/generer")
async def lancer_generation(
    candidature_id: str,
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
    contenu_cv = await generer_cv(candidature.profil, candidature.offre)
    contenu_lettre = await generer_lettre_motivation(candidature.profil, candidature.offre)

    # 4. Sauvegarde ou mise à jour du CV
    cv_obj = db.query(CV).filter(CV.candidature_id == candidature.id).first()
    if not cv_obj:
        cv_obj = CV(
            candidature_id=candidature.id, 
            contenu_genere=contenu_cv, 
            modele=data.modele_cv
        )
        db.add(cv_obj)
    else:
        cv_obj.contenu_genere = contenu_cv

    # 5. Sauvegarde ou mise à jour de la Lettre
    lettre_obj = db.query(LettreMotivation).filter(LettreMotivation.candidature_id == candidature.id).first()
    if not lettre_obj:
        lettre_obj = LettreMotivation(
            candidature_id=candidature.id, 
            contenu_genere=contenu_lettre, 
            ton=data.ton_lettre
        )
        db.add(lettre_obj)
    else:
        lettre_obj.contenu_genere = contenu_lettre

    # 6. Mise à jour du statut final
    candidature.statut = "generee"
    db.commit()

    return {
        "id": candidature.id,
        "cv": contenu_cv,
        "lettre": contenu_lettre
    }


# 3. EXPORTER EN PDF (Appel WeasyPrint)
@router.get("/{candidature_id}/export-pdf")
async def exporter_pdf(
    candidature_id: str,
    type_doc: str = "cv", # "cv" ou "lettre"
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

    # Sélection du contenu selon le type demandé
    if type_doc == "cv" and candidature.cv:
        contenu = candidature.cv.contenu_genere
        nom_fichier = f"CV_{current_user.nom}.pdf"
    elif type_doc == "lettre" and candidature.lettre:
        contenu = candidature.lettre.contenu_genere
        nom_fichier = f"Lettre_{current_user.nom}.pdf"
    else:
        raise HTTPException(status_code=404, detail="Document non généré ou type inconnu.")

    # Génération du fichier via le service PDF
    chemin_pdf = await generer_pdf(contenu, nom_fichier)
    
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
    return db.query(Candidature).filter(
        Candidature.utilisateur_id == current_user.id
    ).order_by(Candidature.date_creation.desc()).all()