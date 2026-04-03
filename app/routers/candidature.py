from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
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

router = APIRouter()

@router.post("/", response_model=CandidatureResponse, status_code=201)
def creer_candidature(
    data: CandidatureCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Profil requis")

    offre = db.query(OffreEmploi).filter(
        OffreEmploi.id == data.offre_id,
        OffreEmploi.utilisateur_id == current_user.id
    ).first()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    candidature = Candidature(
        utilisateur_id=current_user.id,
        profil_id=profil.id,
        offre_id=offre.id,
        score_compatibilite=offre.score_compatibilite,
    )
    db.add(candidature)
    db.commit()
    db.refresh(candidature)
    return candidature


@router.post("/{candidature_id}/generer")
async def generer_documents(
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

    profil = candidature.profil
    offre = candidature.offre

    contenu_cv = await generer_cv(profil, offre, data.modele_cv)
    contenu_lettre = await generer_lettre_motivation(profil, offre, data.ton_lettre)

    cv = CV(
        candidature_id=candidature.id,
        contenu_genere=contenu_cv,
        modele=data.modele_cv,
    )
    lettre = LettreMotivation(
        candidature_id=candidature.id,
        contenu_genere=contenu_lettre,
        ton=data.ton_lettre,
    )
    db.add(cv)
    db.add(lettre)

    candidature.statut = "generee"
    db.commit()

    return {
        "message": "Documents générés avec succès",
        "cv": contenu_cv,
        "lettre_motivation": contenu_lettre,
    }


@router.get("/{candidature_id}/export-pdf")
async def exporter_pdf(
    candidature_id: str,
    type_doc: str = "cv",
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
        nom_fichier = f"CV_{candidature_id[:8]}.pdf"
    elif type_doc == "lettre" and candidature.lettre:
        contenu = candidature.lettre.contenu_genere
        nom_fichier = f"Lettre_{candidature_id[:8]}.pdf"
    else:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    chemin_pdf = await generer_pdf(contenu, nom_fichier)
    return FileResponse(chemin_pdf, media_type="application/pdf", filename=nom_fichier)


@router.get("/", response_model=List[CandidatureResponse])
def liste_candidatures(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    return db.query(Candidature).filter(
        Candidature.utilisateur_id == current_user.id
    ).order_by(Candidature.date_creation.desc()).all()
