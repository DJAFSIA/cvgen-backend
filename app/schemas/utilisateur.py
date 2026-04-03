from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional

class UtilisateurCreate(BaseModel):
    nom: str
    prenom: str
    email: EmailStr
    mot_de_passe: str

class UtilisateurLogin(BaseModel):
    email: EmailStr
    mot_de_passe: str

class UtilisateurResponse(BaseModel):
    id: UUID
    nom: str
    prenom: str
    email: str
    date_inscription: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    utilisateur: UtilisateurResponse
