import uuid
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class OffreEmploi(Base):
    __tablename__ = "offres_emploi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    utilisateur_id = Column(UUID(as_uuid=True), ForeignKey("utilisateurs.id"), nullable=False)
    titre_poste = Column(String(200), nullable=True)
    entreprise = Column(String(200), nullable=True)
    url_source = Column(String(1000), nullable=True)
    contenu_brut = Column(Text, nullable=False)
    mots_cles = Column(Text, nullable=True)
    score_compatibilite = Column(Float, nullable=True)
    date_ajout = Column(DateTime(timezone=True), server_default=func.now())

    utilisateur = relationship("Utilisateur", back_populates="offres")
    candidatures = relationship("Candidature", back_populates="offre")
