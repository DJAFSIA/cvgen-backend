from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.etat_civil import SITUATIONS, noms_pays

AGE_MIN, AGE_MAX = 14, 100


class ProfilBase(BaseModel):
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
    # Etat civil facultatif (jamais transmis a l'IA)
    date_naissance: Optional[date] = None
    lieu_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    situation_familiale: Optional[str] = None
    enfants: Optional[int] = None
    permis_sejour: Optional[str] = None


class ProfilUpdate(ProfilBase):
    lieu_naissance: Optional[str] = Field(default=None, max_length=120)
    nationalite: Optional[str] = Field(default=None, max_length=2)
    situation_familiale: Optional[Literal[SITUATIONS]] = None
    enfants: Optional[int] = Field(default=None, ge=0, le=20)
    permis_sejour: Optional[str] = Field(default=None, max_length=80)

    @field_validator(
        "date_naissance", "lieu_naissance", "nationalite", "situation_familiale", "enfants", "permis_sejour",
        mode="before",
    )
    @classmethod
    def _vide_en_none(cls, v):
        """Un champ vide du formulaire efface la donnee."""
        return (v.strip() or None) if isinstance(v, str) else v

    @field_validator("date_naissance")
    @classmethod
    def _age_plausible(cls, v):
        if v is not None:
            auj = date.today()
            age = auj.year - v.year - ((auj.month, auj.day) < (v.month, v.day))
            if not AGE_MIN <= age <= AGE_MAX:
                raise ValueError("Date de naissance invalide")
        return v

    @field_validator("nationalite")
    @classmethod
    def _pays_connu(cls, v):
        if v is not None:
            v = v.upper()
            if v not in noms_pays():
                raise ValueError("Pays inconnu")
        return v


class ProfilCreate(ProfilUpdate):
    pass


class ProfilResponse(ProfilBase):
    id: UUID
    utilisateur_id: UUID
    cv_importe_url: Optional[str] = None
    date_maj: datetime
    a_photo: bool = False

    model_config = ConfigDict(from_attributes=True)
