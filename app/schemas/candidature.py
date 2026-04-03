from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class OffreCreate(BaseModel):
    url_source: Optional[str] = None
    contenu_brut: str

class OffreResponse(BaseModel):
    id: UUID
    titre_poste: Optional[str]
    entreprise: Optional[str]
    url_source: Optional[str]
    mots_cles: Optional[str]
    score_compatibilite: Optional[float]
    date_ajout: datetime

    class Config:
        from_attributes = True

class CandidatureCreate(BaseModel):
    offre_id: UUID

class CandidatureResponse(BaseModel):
    id: UUID
    statut: str
    score_compatibilite: Optional[float]
    date_creation: datetime

    class Config:
        from_attributes = True

class GenerationRequest(BaseModel):
    candidature_id: UUID
    modele_cv: Optional[str] = "classique"
    ton_lettre: Optional[str] = "professionnel"
