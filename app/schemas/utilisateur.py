from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

class UtilisateurCreate(BaseModel):
    nom: str = Field(min_length=1, max_length=100)
    prenom: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # bcrypt ne prend en compte que les 72 premiers octets
    mot_de_passe: str = Field(min_length=8, max_length=72)

class UtilisateurLogin(BaseModel):
    email: EmailStr
    mot_de_passe: str = Field(max_length=72)

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
