from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from datetime import datetime
from typing import Any, Dict, List, Optional

class OffreCreate(BaseModel):
    url_source: Optional[str] = Field(default=None, max_length=1000)
    contenu_brut: str = Field(min_length=30, max_length=30000)

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
    modele_cv: str = Field(default="classique", max_length=100)
    ton_lettre: str = Field(default="professionnel", max_length=100)
    reponses_alignement: Optional[List[Dict[str, Any]]] = Field(default=None, max_length=10)

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
