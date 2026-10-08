"""profil structured fields (JSONB experiences/formations, CV identity columns)

Idempotent: safe to run on databases already patched by hand.

Revision ID: a3f1c2d4e5b6
Revises: 1cda5a17070a
Create Date: 2026-10-08

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a3f1c2d4e5b6'
down_revision: Union[str, None] = '1cda5a17070a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = ['telephone', 'adresse', 'nom_complet_cv', 'email_cv']


def _columns() -> dict:
    inspector = sa.inspect(op.get_bind())
    return {c['name']: c for c in inspector.get_columns('profils')}


def upgrade() -> None:
    cols = _columns()
    for name in NEW_COLUMNS:
        if name not in cols:
            op.add_column('profils', sa.Column(name, sa.String(), nullable=True))

    for name in ('experiences', 'formations'):
        if not isinstance(cols[name]['type'], postgresql.JSONB):
            # Existing free text is kept as a JSON string value
            op.execute(
                f"ALTER TABLE profils ALTER COLUMN {name} TYPE JSONB "
                f"USING CASE WHEN {name} IS NULL THEN NULL ELSE to_jsonb({name}::text) END"
            )


def downgrade() -> None:
    for name in ('experiences', 'formations'):
        op.execute(
            f"ALTER TABLE profils ALTER COLUMN {name} TYPE TEXT "
            f"USING CASE WHEN {name} IS NULL THEN NULL "
            f"WHEN jsonb_typeof({name}) = 'string' THEN {name} #>> '{{}}' "
            f"ELSE {name}::text END"
        )
    for name in NEW_COLUMNS:
        op.drop_column('profils', name)
