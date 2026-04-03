from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class ProfilCreate(BaseModel):
    titre_profil: Optional[str] = None
    experiences: Optional[str] = None
    formations: Optional[str] = None
    competences: Optional[str] = None
    langues: Optional[str] = None

class ProfilUpdate(ProfilCreate):
    pass

class ProfilResponse(BaseModel):
    id: UUID
    utilisateur_id: UUID
    titre_profil: Optional[str]
    experiences: Optional[str]
    formations: Optional[str]
    competences: Optional[str]
    langues: Optional[str]
    cv_importe_url: Optional[str]
    date_maj: datetime

    class Config:
        from_attributes = True
