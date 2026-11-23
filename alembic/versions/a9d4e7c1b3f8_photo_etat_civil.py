"""photo and personal details: optional profile fields for the countries where a CV shows them

Date et lieu de naissance, nationalite (code ISO), situation familiale, enfants, titre de sejour et photo
(JPEG reencode, moins de 150 Ko). Tous facultatifs, jamais transmis a l'IA (app/services/etat_civil.py).

Revision ID: a9d4e7c1b3f8
Revises: f6b3d8e2a1c9
Create Date: 2026-11-23

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a9d4e7c1b3f8'
down_revision: Union[str, None] = 'f6b3d8e2a1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLONNES = (
    ('date_naissance', sa.Date()),
    ('lieu_naissance', sa.String(length=120)),
    ('nationalite', sa.String(length=2)),
    ('situation_familiale', sa.String(length=20)),
    ('enfants', sa.SmallInteger()),
    ('permis_sejour', sa.String(length=80)),
    ('photo', sa.LargeBinary()),
    ('photo_maj', sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    presentes = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('profils')}
    for nom, type_ in COLONNES:
        if nom not in presentes:
            op.add_column('profils', sa.Column(nom, type_, nullable=True))


def downgrade() -> None:
    presentes = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('profils')}
    for nom, _ in reversed(COLONNES):
        if nom in presentes:
            op.drop_column('profils', nom)
