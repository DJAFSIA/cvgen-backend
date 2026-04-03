import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nom = Column(String(100), nullable=False)
    prenom = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    mot_de_passe = Column(String(255), nullable=False)
    provider = Column(String(50), default="email")
    date_inscription = Column(DateTime(timezone=True), server_default=func.now())
    derniere_connexion = Column(DateTime(timezone=True), nullable=True)

    profil = relationship("Profil", back_populates="utilisateur", uselist=False, cascade="all, delete-orphan")
    candidatures = relationship("Candidature", back_populates="utilisateur", cascade="all, delete-orphan")
    offres = relationship("OffreEmploi", back_populates="utilisateur", cascade="all, delete-orphan")
