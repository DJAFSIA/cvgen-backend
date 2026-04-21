from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import List, Optional

# --- MODÈLES POUR LES OFFRES ---
class OffreCreate(BaseModel):
    url_source: Optional[str] = None
    contenu_brut: str

class OffreResponse(BaseModel):
    id: UUID
    titre_poste: Optional[str] = None
    entreprise: Optional[str] = None
    score_compatibilite: Optional[int] = 0
    mots_cles: Optional[str] = ""
    points_forts: List[str] = []
    points_manquants: List[str] = []
    conseil_ia: Optional[str] = None
    date_ajout: datetime

    model_config = ConfigDict(from_attributes=True)

# --- MODÈLES POUR LES CANDIDATURES (Génération CV/Lettre) ---
class CandidatureCreate(BaseModel):
    offre_id: UUID

class GenerationRequest(BaseModel):
    offre_id: UUID
    type_document: str  # 'cv' ou 'lettre' ou 'tous'

class CandidatureResponse(BaseModel):
    id: UUID
    offre_id: UUID
    statut: str  # 'en_cours', 'generee', 'exportee'
    cv_genere: Optional[str] = None
    lettre_genere: Optional[str] = None
    date_creation: datetime

    model_config = ConfigDict(from_attributes=True)

OffreResponse.model_rebuild()
CandidatureResponse.model_rebuild()