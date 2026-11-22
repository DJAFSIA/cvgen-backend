"""pays: target country of the job offer and of the generated documents

- offres_emploi.pays : pays du poste detecte par l'analyse de l'offre (code de app/pays, ou "autre")
- candidatures.pays : usages du pays appliques a la derniere generation du CV et de la lettre

Revision ID: f6b3d8e2a1c9
Revises: e3f1a9c7b2d4
Create Date: 2026-11-22

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6b3d8e2a1c9'
down_revision: Union[str, None] = 'e3f1a9c7b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('offres_emploi', 'candidatures')


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if 'pays' not in {c['name'] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column('pays', sa.String(length=10), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if 'pays' in {c['name'] for c in inspector.get_columns(table)}:
            op.drop_column(table, 'pays')
