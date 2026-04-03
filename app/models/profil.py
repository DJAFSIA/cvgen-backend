import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class Profil(Base):
    __tablename__ = "profils"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    utilisateur_id = Column(UUID(as_uuid=True), ForeignKey("utilisateurs.id"), nullable=False, unique=True)
    titre_profil = Column(String(200), nullable=True)
    experiences = Column(Text, nullable=True)
    formations = Column(Text, nullable=True)
    competences = Column(Text, nullable=True)
    langues = Column(String(500), nullable=True)
    cv_importe_url = Column(String(500), nullable=True)
    date_maj = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    utilisateur = relationship("Utilisateur", back_populates="profil")
    candidatures = relationship("Candidature", back_populates="profil")
