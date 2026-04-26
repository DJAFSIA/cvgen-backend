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
async def import_cv(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    # 1. Sauvegarde temporaire du fichier PDF
    temp_path = f"temp_{current_user.id}.pdf"
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 2. Extraction du texte (C'est ici qu'on définit 'texte_brut')
        texte_brut = extraire_texte_du_pdf(temp_path)
        
        if not texte_brut or len(texte_brut) < 10:
            raise HTTPException(status_code=400, detail="Impossible d'extraire le texte du PDF.")

        # 3. Analyse par l'IA (On utilise maintenant 'texte_brut')
        donnees = await parser_cv_avec_ia(texte_brut)
        
        # 4. Mise à jour du profil en base de données
        profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
        
        if not profil:
            profil = Profil(utilisateur_id=current_user.id)
            db.add(profil)

        # On remplit les nouveaux champs structurés
        profil.nom_complet_cv = donnees.get("nom_complet_cv")
        profil.email_cv = donnees.get("email_cv")
        profil.telephone = donnees.get("telephone")
        profil.adresse = donnees.get("adresse")
        profil.titre_profil = donnees.get("titre_profil")
        
        # SQLAlchemy gère automatiquement la conversion dict/list vers JSONB
        profil.experiences = donnees.get("experiences") 
        profil.formations = donnees.get("formations")
        profil.competences = donnees.get("competences")
        profil.langues = donnees.get("langues")
        
        db.commit()
        db.refresh(profil)

        return {
            "message": "Import et analyse réussis", 
            "data": donnees
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'import : {str(e)}")
    
    finally:
        # Nettoyage : on supprime toujours le fichier temporaire
        if os.path.exists(temp_path):
            os.remove(temp_path)