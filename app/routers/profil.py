from fastapi import APIRouter, Depends, HTTPException, UploadFile, File 
from sqlalchemy.orm import Session
import shutil
import os
from app.services.pdf_service import extraire_texte_du_pdf
from app.services.ia_service import parser_cv_avec_ia
from app.services.ia_service import extraire_donnees_profil
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
    
@router.post("/import-cv")
async def import_cv(file: UploadFile = File(...), db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    # 1. Sauvegarde temporaire du fichier
    temp_path = f"temp_{current_user.id}.pdf"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # 2. Extraction du texte
    texte_brut = extraire_texte_du_pdf(temp_path)
    # 3. Analyse par l'IA
    donnees_extraites = await parser_cv_avec_ia(texte_brut)
    # 4. Mise à jour du profil en base de données (SQLAlchemy)
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    profil.competences = donnees_extraites.get("competences")
    profil.experiences = donnees_extraites.get("experiences")
    db.commit()
    os.remove(temp_path) # Nettoyage
    return {"message": "Profil mis à jour avec succès", "data": donnees_extraites}
    
