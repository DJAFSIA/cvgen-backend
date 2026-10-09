import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from app.core.database import Base


class Paiement(Base):
    """Trace de chaque paiement (Stripe ou Flutterwave). La reference unique rend le
    traitement idempotent : un webhook rejoue ne credite jamais deux fois."""
    __tablename__ = "paiements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    utilisateur_id = Column(UUID(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False, index=True)
    fournisseur = Column(String(20), nullable=False)          # stripe | flutterwave
    reference = Column(String(255), nullable=False, unique=True)  # tx_ref Flutterwave, id de facture Stripe
    montant = Column(Integer, nullable=False)                 # unite mineure (centimes) ou FCFA
    devise = Column(String(3), nullable=False)
    statut = Column(String(20), nullable=False, default="pending")  # pending | paid | failed
    jours = Column(Integer, nullable=True)                    # duree accordee pour un paiement ponctuel
    details = Column(JSONB, nullable=True)
    cree_le = Column(DateTime(timezone=True), server_default=func.now())
    paye_le = Column(DateTime(timezone=True), nullable=True)


class Usage(Base):
    """Compteurs d'utilisation par utilisateur et par mois (YYYY-MM)."""
    __tablename__ = "usages"
    __table_args__ = (UniqueConstraint("utilisateur_id", "periode", name="uq_usage_utilisateur_periode"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    utilisateur_id = Column(UUID(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False, index=True)
    periode = Column(String(7), nullable=False)
    generations = Column(Integer, nullable=False, default=0, server_default="0")
    analyses = Column(Integer, nullable=False, default=0, server_default="0")
    imports = Column(Integer, nullable=False, default=0, server_default="0")
