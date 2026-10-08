from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Any, Optional


class ProfilCreate(BaseModel):
    nom_complet_cv: Optional[str] = None
    email_cv: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    titre_profil: Optional[str] = None
    # Texte libre (saisie manuelle) ou liste structuree (import de CV)
    experiences: Optional[Any] = None
    formations: Optional[Any] = None
    competences: Optional[str] = None
    langues: Optional[str] = None


class ProfilUpdate(ProfilCreate):
    pass


class ProfilResponse(ProfilCreate):
    id: UUID
    utilisateur_id: UUID
    cv_importe_url: Optional[str] = None
    date_maj: datetime

    model_config = ConfigDict(from_attributes=True)
