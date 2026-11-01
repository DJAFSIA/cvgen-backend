"""rgpd: acceptance of the terms, payments kept (anonymised) when an account is deleted

- utilisateurs.cgu_acceptees_le / cgu_version : preuve de l'acceptation des conditions
- paiements.utilisateur_id devient nullable, ON DELETE SET NULL : a la suppression d'un compte,
  les traces de paiement restent (obligations comptables) mais ne sont plus rattachees a personne

Revision ID: e3f1a9c7b2d4
Revises: d2a7c9e3f5b1
Create Date: 2026-11-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e3f1a9c7b2d4'
down_revision: Union[str, None] = 'd2a7c9e3f5b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK = 'paiements_utilisateur_id_fkey'


def _fk_paiements_utilisateur(inspector) -> list[str]:
    return [
        fk['name'] for fk in inspector.get_foreign_keys('paiements')
        if fk['referred_table'] == 'utilisateurs' and fk['constrained_columns'] == ['utilisateur_id']
    ]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c['name'] for c in inspector.get_columns('utilisateurs')}
    if 'cgu_acceptees_le' not in cols:
        op.add_column('utilisateurs', sa.Column('cgu_acceptees_le', sa.DateTime(timezone=True), nullable=True))
    if 'cgu_version' not in cols:
        op.add_column('utilisateurs', sa.Column('cgu_version', sa.String(length=20), nullable=True))

    for nom in _fk_paiements_utilisateur(inspector):
        op.drop_constraint(nom, 'paiements', type_='foreignkey')
    op.alter_column('paiements', 'utilisateur_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_foreign_key(FK, 'paiements', 'utilisateurs', ['utilisateur_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for nom in _fk_paiements_utilisateur(inspector):
        op.drop_constraint(nom, 'paiements', type_='foreignkey')
    # Les paiements de comptes supprimes ne peuvent pas redevenir obligatoires
    op.execute("DELETE FROM paiements WHERE utilisateur_id IS NULL")
    op.alter_column('paiements', 'utilisateur_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(FK, 'paiements', 'utilisateurs', ['utilisateur_id'], ['id'], ondelete='CASCADE')
    op.drop_column('utilisateurs', 'cgu_version')
    op.drop_column('utilisateurs', 'cgu_acceptees_le')
