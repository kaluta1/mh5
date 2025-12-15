"""add_season_dates_to_contests

Revision ID: a0f02aec6fc9
Revises: add_author_ref_to_shares
Create Date: 2025-12-15 19:41:45.188848

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a0f02aec6fc9'
down_revision = 'add_author_ref_to_shares'
branch_labels = None
depends_on = None


def upgrade():
    # Ajouter les colonnes de dates des saisons à la table contest (singulier)
    op.add_column('contest', sa.Column('city_season_start_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('city_season_end_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('country_season_start_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('country_season_end_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('regional_start_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('regional_end_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('continental_start_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('continental_end_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('global_start_date', sa.Date(), nullable=True))
    op.add_column('contest', sa.Column('global_end_date', sa.Date(), nullable=True))
    
    # Calculer et mettre à jour les dates pour les contests existants
    from sqlalchemy import text
    
    # Note: Cette requête SQL calcule les dates pour tous les contests existants
    # Les dates sont calculées à partir de voting_start_date
    op.execute(text("""
        UPDATE contest
        SET 
            city_season_start_date = voting_start_date,
            city_season_end_date = voting_start_date + INTERVAL '1 month',
            country_season_start_date = voting_start_date + INTERVAL '1 month',
            country_season_end_date = voting_start_date + INTERVAL '2 months',
            regional_start_date = voting_start_date + INTERVAL '2 months',
            regional_end_date = voting_start_date + INTERVAL '3 months',
            continental_start_date = voting_start_date + INTERVAL '3 months',
            continental_end_date = voting_start_date + INTERVAL '4 months',
            global_start_date = voting_start_date + INTERVAL '4 months',
            global_end_date = voting_start_date + INTERVAL '5 months'
        WHERE voting_start_date IS NOT NULL
    """))


def downgrade():
    # Supprimer les colonnes de dates des saisons
    op.drop_column('contest', 'global_end_date')
    op.drop_column('contest', 'global_start_date')
    op.drop_column('contest', 'continental_end_date')
    op.drop_column('contest', 'continental_start_date')
    op.drop_column('contest', 'regional_end_date')
    op.drop_column('contest', 'regional_start_date')
    op.drop_column('contest', 'country_season_end_date')
    op.drop_column('contest', 'country_season_start_date')
    op.drop_column('contest', 'city_season_end_date')
    op.drop_column('contest', 'city_season_start_date')
