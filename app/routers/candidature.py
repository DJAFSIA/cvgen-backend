from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
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
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Veuillez remplir votre profil avant de postuler.")

    offre = db.query(OffreEmploi).filter(
        OffreEmploi.id == data.offre_id,
        OffreEmploi.utilisateur_id == current_user.id
    ).first()
    
    if not offre:
        raise HTTPException(status_code=404, detail="Offre introuvable.")

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
    data: GenerationRequest, # Utilise le schéma mis à jour
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    # 1. Chercher la candidature
    candidature = db.query(Candidature).filter(
        Candidature.id == candidature_id,
        Candidature.utilisateur_id == current_user.id
    ).first()
    
    if not candidature:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    # 2. Récupérer profil et offre via les relations SQLAlchemy
    profil = candidature.profil
    offre = candidature.offre

    if not profil or not offre:
        raise HTTPException(status_code=400, detail="Données de profil ou d'offre manquantes")

    # 3. Appel IA pour la génération
    # On utilise les valeurs envoyées par le front (data.modele_cv, etc.)
    contenu_cv = await generer_cv(profil, offre)
    contenu_lettre = await generer_lettre_motivation(profil, offre)

    # 4. Sauvegarde du CV
    cv_obj = db.query(CV).filter(CV.candidature_id == candidature.id).first()
    if not cv_obj:
        cv_obj = CV(candidature_id=candidature.id, contenu_genere=contenu_cv, modele=data.modele_cv)
        db.add(cv_obj)
    else:
        cv_obj.contenu_genere = contenu_cv

    # 5. Sauvegarde de la Lettre
    lettre_obj = db.query(LettreMotivation).filter(LettreMotivation.candidature_id == candidature.id).first()
    if not lettre_obj:
        lettre_obj = LettreMotivation(candidature_id=candidature.id, contenu_genere=contenu_lettre, ton=data.ton_lettre)
        db.add(lettre_obj)
    else:
        lettre_obj.contenu_genere = contenu_lettre

    # 6. Mise à jour du statut final
    candidature.statut = "generee"
    db.commit()

    # 7. Retourner le format attendu par ton Frontend
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
    candidature = db.query(Candidature).filter(
        Candidature.id == candidature_id,
        Candidature.utilisateur_id == current_user.id
    ).first()
    
    if not candidature:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    if type_doc == "cv" and candidature.cv:
        contenu = candidature.cv.contenu_genere
        nom_fichier = f"CV_{current_user.nom}.pdf"
    elif type_doc == "lettre" and candidature.lettre:
        contenu = candidature.lettre.contenu_genere
        nom_fichier = f"Lettre_{current_user.nom}.pdf"
    else:
        raise HTTPException(status_code=404, detail="Le document n'a pas encore été généré.")

    # Appel au service PDF (WeasyPrint)
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