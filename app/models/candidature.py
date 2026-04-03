import uuid
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Candidature(Base):
    __tablename__ = "candidatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    utilisateur_id = Column(UUID(as_uuid=True), ForeignKey("utilisateurs.id"), nullable=False)
    profil_id = Column(UUID(as_uuid=True), ForeignKey("profils.id"), nullable=False)
    offre_id = Column(UUID(as_uuid=True), ForeignKey("offres_emploi.id"), nullable=False)
    statut = Column(String(50), default="en_cours")
    score_compatibilite = Column(Float, nullable=True)
    date_creation = Column(DateTime(timezone=True), server_default=func.now())
    date_modification = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    utilisateur = relationship("Utilisateur", back_populates="candidatures")
    profil = relationship("Profil", back_populates="candidatures")
    offre = relationship("OffreEmploi", back_populates="candidatures")
    cv = relationship("CV", back_populates="candidature", uselist=False, cascade="all, delete-orphan")
    lettre = relationship("LettreMotivation", back_populates="candidature", uselist=False, cascade="all, delete-orphan")


class CV(Base):
    __tablename__ = "cvs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidature_id = Column(UUID(as_uuid=True), ForeignKey("candidatures.id"), nullable=False, unique=True)
    contenu_genere = Column(Text, nullable=True)
    modele = Column(String(100), default="classique")
    fichier_pdf_url = Column(String(500), nullable=True)
    date_generation = Column(DateTime(timezone=True), server_default=func.now())

    candidature = relationship("Candidature", back_populates="cv")


class LettreMotivation(Base):
    __tablename__ = "lettres_motivation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidature_id = Column(UUID(as_uuid=True), ForeignKey("candidatures.id"), nullable=False, unique=True)
    contenu_genere = Column(Text, nullable=True)
    ton = Column(String(100), default="professionnel")
    fichier_pdf_url = Column(String(500), nullable=True)
    date_generation = Column(DateTime(timezone=True), server_default=func.now())

    candidature = relationship("Candidature", back_populates="lettre")
