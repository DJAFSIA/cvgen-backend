import uuid
from sqlalchemy import Boolean, Column, String, DateTime
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
    email_verifie = Column(Boolean, nullable=False, default=False, server_default="false")
    google_id = Column(String(64), unique=True, nullable=True, index=True)
    langue = Column(String(5), nullable=False, default="en", server_default="en")
    # Facturation : plan "pro" valable jusqu'a plan_expire_le (renouvele par Stripe ou par un pass Mobile Money)
    plan = Column(String(20), nullable=False, default="free", server_default="free")
    plan_expire_le = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(64), unique=True, nullable=True, index=True)
    stripe_subscription_id = Column(String(64), nullable=True)
    date_inscription = Column(DateTime(timezone=True), server_default=func.now())
    derniere_connexion = Column(DateTime(timezone=True), nullable=True)

    profil = relationship("Profil", back_populates="utilisateur", uselist=False, cascade="all, delete-orphan")
    candidatures = relationship("Candidature", back_populates="utilisateur", cascade="all, delete-orphan")
    offres = relationship("OffreEmploi", back_populates="utilisateur", cascade="all, delete-orphan")
