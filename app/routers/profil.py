from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from sqlalchemy.orm import Session
import asyncio
import logging
import os
import tempfile
from app.services.pdf_service import extraire_texte_du_pdf
from app.services.ia_service import parser_cv_avec_ia
from app.services.ia_service import IAError
from app.services import photo_service
from app.core.database import get_db
from app.core.rate_limit import import_cv_limiter, photo_limiter
from app.core.errors import http_error
from app.services.billing import quota
from app.core.security import get_current_user, get_verified_user
from app.models.profil import Profil
from app.models.utilisateur import Utilisateur
from app.schemas.profil import ProfilCreate, ProfilUpdate, ProfilResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=ProfilResponse)
def get_profil(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise http_error(404, "profile_not_found", "Profil introuvable")
    return profil


@router.put("/", response_model=ProfilResponse)
def update_profil(
    data: ProfilUpdate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil:
        raise http_error(404, "profile_not_found", "Profil introuvable")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profil, field, value)

    db.commit()
    db.refresh(profil)
    return profil
    

# --- Photo du CV (facultative) : jamais transmise a l'IA, effacable a tout moment ---
def _profil_de(db: Session, utilisateur: Utilisateur) -> Profil:
    profil = db.query(Profil).filter(Profil.utilisateur_id == utilisateur.id).first()
    if not profil:
        raise http_error(404, "profile_not_found", "Profil introuvable")
    return profil


@router.put("/photo", dependencies=[photo_limiter.by_user()])
async def envoyer_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_verified_user),
):
    profil = _profil_de(db, current_user)
    contenu = await file.read(photo_service.MAX_OCTETS + 1)
    if len(contenu) > photo_service.MAX_OCTETS:
        raise http_error(413, "photo_too_large", "Photo trop volumineuse (8 Mo maximum).")
    try:
        profil.photo = await asyncio.to_thread(photo_service.normaliser, contenu)
    except photo_service.PhotoInvalide as e:
        raise http_error(400, e.code, "Cette photo ne peut pas etre utilisee.")
    profil.photo_maj = datetime.now(timezone.utc)
    db.commit()
    return {"a_photo": True}


@router.get("/photo")
def lire_photo(db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user)):
    profil = _profil_de(db, current_user)
    if not profil.a_photo:
        raise http_error(404, "photo_not_found", "Aucune photo")
    return Response(content=profil.photo, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.delete("/photo")
def supprimer_photo(db: Session = Depends(get_db), current_user: Utilisateur = Depends(get_current_user)):
    profil = _profil_de(db, current_user)
    profil.photo = None
    profil.photo_maj = None
    db.commit()
    return {"a_photo": False}


MAX_CV_BYTES = 5 * 1024 * 1024


@router.post("/import-cv", dependencies=[Depends(get_verified_user), import_cv_limiter.by_user(), quota("imports")])
async def import_cv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    contenu = await file.read(MAX_CV_BYTES + 1)
    if len(contenu) > MAX_CV_BYTES:
        raise http_error(413, "file_too_large", "Fichier trop volumineux (5 Mo maximum).")
    if not contenu.startswith(b"%PDF-"):
        raise http_error(400, "file_not_pdf", "Le fichier doit etre un PDF.")

    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as buffer:
            buffer.write(contenu)

        texte_brut = await asyncio.to_thread(extraire_texte_du_pdf, temp_path)
        if not texte_brut or len(texte_brut) < 10:
            raise http_error(400, "pdf_no_text", "Impossible d'extraire le texte du PDF (document scanne ?).")

        donnees = await parser_cv_avec_ia(texte_brut[:60000])

        profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
        if not profil:
            profil = Profil(utilisateur_id=current_user.id)
            db.add(profil)

        profil.nom_complet_cv = donnees.get("nom_complet_cv")
        profil.email_cv = donnees.get("email_cv")
        profil.telephone = donnees.get("telephone")
        profil.adresse = donnees.get("adresse")
        profil.titre_profil = donnees.get("titre_profil")
        profil.experiences = donnees.get("experiences")
        profil.formations = donnees.get("formations")
        profil.competences = donnees.get("competences")
        profil.langues = donnees.get("langues")

        db.commit()
        db.refresh(profil)
        return {"message": "Import et analyse reussis", "data": donnees}

    except (HTTPException, IAError):
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("Echec de l'import de CV")
        raise http_error(500, "import_failed", "Erreur lors de l'import du CV.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
