"""add verification_url, attempts_count to kyc_verifications and unique constraint on user_id

Revision ID: add_verification_url
Revises: add_invitations_table
Create Date: 2024-12-06

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_verification_url'
down_revision = 'add_invitations_table'
branch_labels = None
depends_on = None


def upgrade():
    # Add verification_url column to kyc_verifications table
    op.add_column('kyc_verifications', sa.Column('verification_url', sa.Text(), nullable=True))
    
    # Add unique constraint on user_id (un seul enregistrement KYC par utilisateur)
    # D'abord, supprimer les doublons s'il y en a (garder le plus récent)
    op.execute("""
        DELETE FROM kyc_verifications 
        WHERE id NOT IN (
            SELECT MAX(id) FROM kyc_verifications GROUP BY user_id
        )
    """)
    
    # Ensuite, ajouter la contrainte unique
    op.create_unique_constraint('uq_kyc_verifications_user_id', 'kyc_verifications', ['user_id'])


def downgrade():
    op.drop_constraint('uq_kyc_verifications_user_id', 'kyc_verifications', type_='unique')
    op.drop_column('kyc_verifications', 'verification_url')
