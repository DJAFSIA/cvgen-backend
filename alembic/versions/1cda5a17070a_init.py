"""init

Revision ID: 1cda5a17070a
Revises: 
Create Date: 2026-04-02

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1cda5a17070a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('utilisateurs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nom', sa.String(length=100), nullable=False),
        sa.Column('prenom', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('mot_de_passe', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('date_inscription', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('derniere_connexion', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_utilisateurs_email', 'utilisateurs', ['email'], unique=True)

    op.create_table('profils',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('utilisateur_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('titre_profil', sa.String(length=200), nullable=True),
        sa.Column('experiences', sa.Text(), nullable=True),
        sa.Column('formations', sa.Text(), nullable=True),
        sa.Column('competences', sa.Text(), nullable=True),
        sa.Column('langues', sa.String(length=500), nullable=True),
        sa.Column('cv_importe_url', sa.String(length=500), nullable=True),
        sa.Column('date_maj', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateurs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('utilisateur_id')
    )

    op.create_table('offres_emploi',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('utilisateur_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('titre_poste', sa.String(length=200), nullable=True),
        sa.Column('entreprise', sa.String(length=200), nullable=True),
        sa.Column('url_source', sa.String(length=1000), nullable=True),
        sa.Column('contenu_brut', sa.Text(), nullable=False),
        sa.Column('mots_cles', sa.Text(), nullable=True),
        sa.Column('score_compatibilite', sa.Float(), nullable=True),
        sa.Column('date_ajout', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateurs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('candidatures',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('utilisateur_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('profil_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('offre_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('statut', sa.String(length=50), nullable=True),
        sa.Column('score_compatibilite', sa.Float(), nullable=True),
        sa.Column('date_creation', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('date_modification', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['offre_id'], ['offres_emploi.id'], ),
        sa.ForeignKeyConstraint(['profil_id'], ['profils.id'], ),
        sa.ForeignKeyConstraint(['utilisateur_id'], ['utilisateurs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('cvs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidature_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contenu_genere', sa.Text(), nullable=True),
        sa.Column('modele', sa.String(length=100), nullable=True),
        sa.Column('fichier_pdf_url', sa.String(length=500), nullable=True),
        sa.Column('date_generation', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['candidature_id'], ['candidatures.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidature_id')
    )

    op.create_table('lettres_motivation',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidature_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contenu_genere', sa.Text(), nullable=True),
        sa.Column('ton', sa.String(length=100), nullable=True),
        sa.Column('fichier_pdf_url', sa.String(length=500), nullable=True),
        sa.Column('date_generation', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['candidature_id'], ['candidatures.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidature_id')
    )


def downgrade() -> None:
    op.drop_table('lettres_motivation')
    op.drop_table('cvs')
    op.drop_table('candidatures')
    op.drop_table('offres_emploi')
    op.drop_table('profils')
    op.drop_index('ix_utilisateurs_email', table_name='utilisateurs')
    op.drop_table('utilisateurs')