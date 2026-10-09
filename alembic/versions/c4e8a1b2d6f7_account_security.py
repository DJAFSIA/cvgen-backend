"""account security: verified email, Google id, preferred language

Existing accounts are marked as verified so nobody is locked out.

Revision ID: c4e8a1b2d6f7
Revises: b7d2e9f1a4c3
Create Date: 2026-10-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4e8a1b2d6f7'
down_revision: Union[str, None] = 'b7d2e9f1a4c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    return {c['name'] for c in inspector.get_columns('utilisateurs')}


def upgrade() -> None:
    cols = _columns()
    if 'email_verifie' not in cols:
        op.add_column('utilisateurs', sa.Column('email_verifie', sa.Boolean(), nullable=False, server_default=sa.false()))
        op.execute("UPDATE utilisateurs SET email_verifie = true")
    if 'google_id' not in cols:
        op.add_column('utilisateurs', sa.Column('google_id', sa.String(length=64), nullable=True))
        op.create_index('ix_utilisateurs_google_id', 'utilisateurs', ['google_id'], unique=True)
    if 'langue' not in cols:
        op.add_column('utilisateurs', sa.Column('langue', sa.String(length=5), nullable=False, server_default='en'))


def downgrade() -> None:
    op.drop_column('utilisateurs', 'langue')
    op.drop_index('ix_utilisateurs_google_id', table_name='utilisateurs')
    op.drop_column('utilisateurs', 'google_id')
    op.drop_column('utilisateurs', 'email_verifie')
