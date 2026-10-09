"""billing: plan on users, payments, monthly usage counters

Revision ID: d2a7c9e3f5b1
Revises: c4e8a1b2d6f7
Create Date: 2026-10-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd2a7c9e3f5b1'
down_revision: Union[str, None] = 'c4e8a1b2d6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c['name'] for c in inspector.get_columns('utilisateurs')}
    if 'plan' not in cols:
        op.add_column('utilisateurs', sa.Column('plan', sa.String(length=20), nullable=False, server_default='free'))
    if 'plan_expire_le' not in cols:
        op.add_column('utilisateurs', sa.Column('plan_expire_le', sa.DateTime(timezone=True), nullable=True))
    if 'stripe_customer_id' not in cols:
        op.add_column('utilisateurs', sa.Column('stripe_customer_id', sa.String(length=64), nullable=True))
        op.create_index('ix_utilisateurs_stripe_customer_id', 'utilisateurs', ['stripe_customer_id'], unique=True)
    if 'stripe_subscription_id' not in cols:
        op.add_column('utilisateurs', sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True))

    tables = set(inspector.get_table_names())
    if 'paiements' not in tables:
        op.create_table(
            'paiements',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('utilisateur_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('utilisateurs.id', ondelete='CASCADE'), nullable=False),
            sa.Column('fournisseur', sa.String(length=20), nullable=False),
            sa.Column('reference', sa.String(length=255), nullable=False, unique=True),
            sa.Column('montant', sa.Integer(), nullable=False),
            sa.Column('devise', sa.String(length=3), nullable=False),
            sa.Column('statut', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('jours', sa.Integer(), nullable=True),
            sa.Column('details', postgresql.JSONB(), nullable=True),
            sa.Column('cree_le', sa.DateTime(timezone=True), server_default=sa.text('now()')),
            sa.Column('paye_le', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_paiements_utilisateur_id', 'paiements', ['utilisateur_id'])
    if 'usages' not in tables:
        op.create_table(
            'usages',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('utilisateur_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('utilisateurs.id', ondelete='CASCADE'), nullable=False),
            sa.Column('periode', sa.String(length=7), nullable=False),
            sa.Column('generations', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('analyses', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('imports', sa.Integer(), nullable=False, server_default='0'),
            sa.UniqueConstraint('utilisateur_id', 'periode', name='uq_usage_utilisateur_periode'),
        )
        op.create_index('ix_usages_utilisateur_id', 'usages', ['utilisateur_id'])


def downgrade() -> None:
    op.drop_table('usages')
    op.drop_table('paiements')
    op.drop_column('utilisateurs', 'stripe_subscription_id')
    op.drop_index('ix_utilisateurs_stripe_customer_id', table_name='utilisateurs')
    op.drop_column('utilisateurs', 'stripe_customer_id')
    op.drop_column('utilisateurs', 'plan_expire_le')
    op.drop_column('utilisateurs', 'plan')
