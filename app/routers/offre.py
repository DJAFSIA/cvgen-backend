from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.offre import OffreEmploi
from app.models.utilisateur import Utilisateur
from app.models.profil import Profil
from app.schemas.candidature import OffreCreate, OffreResponse
from app.services.ia_service import analyser_offre

router = APIRouter()

@router.post("/", response_model=OffreResponse, status_code=201)
async def soumettre_offre(
    data: OffreCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise HTTPException(status_code=400, detail="Complétez votre profil avant de soumettre une offre")

    analyse = await analyser_offre(data.contenu_brut, profil)

    offre = OffreEmploi(
        utilisateur_id=current_user.id,
        url_source=data.url_source,
        contenu_brut=data.contenu_brut,
        titre_poste=analyse.get("titre_poste"),
        entreprise=analyse.get("entreprise"),
        mots_cles=", ".join(analyse.get("mots_cles", [])),
        score_compatibilite=analyse.get("score_compatibilite"),
    )
    db.add(offre)
    db.commit()
    db.refresh(offre)
    return offre


@router.get("/", response_model=List[OffreResponse])
def liste_offres(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    return db.query(OffreEmploi).filter(
        OffreEmploi.utilisateur_id == current_user.id
    ).order_by(OffreEmploi.date_ajout.desc()).all()


@router.get("/{offre_id}", response_model=OffreResponse)
def get_offre(
    offre_id: str,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    offre = db.query(OffreEmploi).filter(
        OffreEmploi.id == offre_id,
        OffreEmploi.utilisateur_id == current_user.id
    ).first()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return offre
