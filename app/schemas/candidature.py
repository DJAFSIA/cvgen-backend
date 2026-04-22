from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import List, Optional

class OffreCreate(BaseModel):
    url_source: Optional[str] = None
    contenu_brut: str

class OffreResponse(BaseModel):
    id: UUID
    titre_poste: Optional[str] = None
    entreprise: Optional[str] = None
    score_compatibilite: Optional[int] = 0
    points_forts: List[str] = []
    points_manquants: List[str] = []
    conseil_ia: Optional[str] = None
    date_ajout: datetime
    model_config = ConfigDict(from_attributes=True)

# Pour POST /candidature/
class CandidatureCreate(BaseModel):
    offre_id: UUID

# Pour POST /generer (C'est ici que ton 422 se produisait)
class GenerationRequest(BaseModel):
    modele_cv: str = "classique"
    ton_lettre: str = "professionnel"

class CandidatureResponse(BaseModel):
    id: UUID
    offre_id: UUID
    statut: str
    cv_genere: Optional[str] = None
    lettre_genere: Optional[str] = None
    date_creation: datetime
    model_config = ConfigDict(from_attributes=True)

OffreResponse.model_rebuild()
CandidatureResponse.model_rebuild()