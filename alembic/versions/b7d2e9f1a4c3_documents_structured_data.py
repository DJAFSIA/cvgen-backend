"""structured data columns for generated CVs and cover letters

Revision ID: b7d2e9f1a4c3
Revises: a3f1c2d4e5b6
Create Date: 2026-10-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7d2e9f1a4c3'
down_revision: Union[str, None] = 'a3f1c2d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(c['name'] == name for c in inspector.get_columns(table))


def upgrade() -> None:
    for table in ('cvs', 'lettres_motivation'):
        if not _has_column(table, 'donnees'):
            op.add_column(table, sa.Column('donnees', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for table in ('lettres_motivation', 'cvs'):
        op.drop_column(table, 'donnees')
