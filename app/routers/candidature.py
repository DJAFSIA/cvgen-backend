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
    data: GenerationRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    candidature = db.query(Candidature).filter(
        Candidature.id == candidature_id,
        Candidature.utilisateur_id == current_user.id
    ).first()
    
    if not candidature:
        raise HTTPException(status_code=404, detail="Candidature introuvable")

    # On récupère le profil et l'offre liés
    profil = candidature.profil
    offre = candidature.offre

    # A. Génération par l'IA
    # On utilise les modèles ou les tons si fournis dans la requête
    modele = getattr(data, 'modele_cv', 'classique')
    ton = getattr(data, 'ton_lettre', 'professionnel')

    contenu_cv = await generer_cv(profil, offre)
    contenu_lettre = await generer_lettre_motivation(profil, offre)

    # B. Sauvegarde ou Mise à jour du CV en base
    cv = db.query(CV).filter(CV.candidature_id == candidature.id).first()
    if not cv:
        cv = CV(candidature_id=candidature.id, contenu_genere=contenu_cv, modele=modele)
        db.add(cv)
    else:
        cv.contenu_genere = contenu_cv

    # C. Sauvegarde ou Mise à jour de la Lettre en base
    lettre = db.query(LettreMotivation).filter(LettreMotivation.candidature_id == candidature.id).first()
    if not lettre:
        lettre = LettreMotivation(candidature_id=candidature.id, contenu_genere=contenu_lettre, ton=ton)
        db.add(lettre)
    else:
        lettre.contenu_genere = contenu_lettre

    # D. Mise à jour du statut
    candidature.statut = "generee"
    db.commit()

    return {
        "message": "Documents rédigés avec succès par l'IA",
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