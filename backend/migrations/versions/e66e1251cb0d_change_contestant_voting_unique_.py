"""change_contestant_voting_unique_constraint_to_season

Revision ID: e66e1251cb0d
Revises: a0f02aec6fc9
Create Date: 2025-12-18 12:24:03.532343

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e66e1251cb0d'
down_revision = 'a0f02aec6fc9'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import text
    
    # Nettoyer les doublons : si un utilisateur a plusieurs votes pour le même contestant dans la même saison,
    # garder uniquement le vote le plus récent
    connection = op.get_bind()
    
    # Trouver les doublons (user_id, contestant_id, season_id) et garder le vote le plus récent
    cleanup_query = text("""
        DELETE FROM contestant_voting
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id, contestant_id, season_id) id
            FROM contestant_voting
            ORDER BY user_id, contestant_id, season_id, vote_date DESC, id DESC
        )
    """)
    
    try:
        connection.execute(cleanup_query)
        connection.commit()
    except Exception as e:
        # Si la requête échoue, continuer quand même (peut-être pas de doublons)
        print(f"Warning: Could not clean duplicates: {e}")
        connection.rollback()
    
    # Supprimer l'ancienne contrainte unique sur (user_id, contestant_id, contest_id)
    try:
        op.drop_constraint('uq_contestant_voting', 'contestant_voting', type_='unique')
    except Exception as e:
        # Si la contrainte n'existe pas ou a un nom différent, continuer
        print(f"Warning: Could not drop old constraint: {e}")
    
    # Créer la nouvelle contrainte unique sur (user_id, contestant_id, season_id)
    # Un utilisateur ne peut voter qu'une seule fois pour un contestant donné dans une saison donnée
    # Mais il peut voter pour plusieurs contestants différents dans la même saison
    op.create_unique_constraint(
        'uq_contestant_voting',
        'contestant_voting',
        ['user_id', 'contestant_id', 'season_id']
    )


def downgrade():
    # Supprimer la nouvelle contrainte unique sur (user_id, contestant_id, season_id)
    op.drop_constraint('uq_contestant_voting', 'contestant_voting', type_='unique')
    
    # Restaurer l'ancienne contrainte unique sur (user_id, contestant_id, contest_id)
    op.create_unique_constraint(
        'uq_contestant_voting',
        'contestant_voting',
        ['user_id', 'contestant_id', 'contest_id']
    )
