from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel 

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.offre import OffreEmploi
from app.models.utilisateur import Utilisateur
from app.models.profil import Profil
from app.schemas.candidature import OffreCreate, OffreResponse
from app.services.ia_service import analyser_offre
from app.services.scraper_service import extraire_texte_offre_url # Import du scraper

router = APIRouter()

# --- Schéma pour la requête d'extraction par URL ---
class URLRequest(BaseModel):
    url: str

# --- NOUVELLE ROUTE : EXTRACTION AUTOMATIQUE (PHASE 2) ---
@router.post("/extraire")
async def extraire_offre(
    request: URLRequest,
    current_user: Utilisateur = Depends(get_current_user)
):
    """
    Prend une URL, extrait le texte de l'offre et le renvoie au frontend.
    """
    texte = await extraire_texte_offre_url(request.url)
    
    if texte.startswith("Erreur"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=texte
        )
        
    return {"contenu": texte}


#  SOUMISSION ET ANALYSE IA 
@router.post("/", response_model=OffreResponse, status_code=201)
async def soumettre_offre(
    data: OffreCreate,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    # Vérification que le profil n'est pas vide
    profil = db.query(Profil).filter(Profil.utilisateur_id == current_user.id).first()
    if not profil or not profil.competences:
        raise HTTPException(
            status_code=400, 
            detail="Complétez votre profil (compétences, expériences) avant de soumettre une offre"
        )

    # Analyse croisée IA (C'est ici que le matching se fait)
    analyse = await analyser_offre(data.contenu_brut, profil)

    # Création de l'entrée en base de données
    offre = OffreEmploi(
        utilisateur_id=current_user.id,
        url_source=data.url_source,
        contenu_brut=data.contenu_brut,
        titre_poste=analyse.get("titre_poste") or "Poste non identifié",
        entreprise=analyse.get("entreprise") or "Entreprise non identifiée",
        mots_cles=", ".join(analyse.get("mots_cles", [])),
        score_compatibilite=analyse.get("score_compatibilite") or 0.0,
    )
    
    db.add(offre)
    db.commit()
    db.refresh(offre)
    return offre


# --- ROUTE : LISTER LES OFFRES DE L'UTILISATEUR ---
@router.get("/", response_model=List[OffreResponse])
def liste_offres(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_current_user)
):
    return db.query(OffreEmploi).filter(
        OffreEmploi.utilisateur_id == current_user.id
    ).order_by(OffreEmploi.date_ajout.desc()).all()


# --- ROUTE : OBTENIR LE DÉTAIL D'UNE OFFRE ---
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