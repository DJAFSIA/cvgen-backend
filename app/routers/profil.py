from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur
from app.schemas.profil import ProfilCreate, ProfilUpdate, ProfilResponse

router = APIRouter()

@router.get("/", response_model=ProfilResponse)
def get_profil(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return profil


@router.put("/", response_model=ProfilResponse)
def update_profil(
    data: ProfilUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profil, field, value)

    db.commit()
    db.refresh(profil)
    return profil
