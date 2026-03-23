"""Update contestants table with new fields

Revision ID: 003_update_contestants
Revises: f9e6829e1555
Create Date: 2025-11-13 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_update_contestants'
down_revision = 'f9e6829e1555'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    def has_table(name: str) -> bool:
        return name in insp.get_table_names()

    def has_column(table: str, column: str) -> bool:
        if not has_table(table):
            return False
        return column in {c["name"] for c in insp.get_columns(table)}

    # Supprimer les colonnes inutiles
    if has_column('contestants', 'category_id'):
        op.drop_column('contestants', 'category_id')
    if has_column('contestants', 'city_id'):
        op.drop_column('contestants', 'city_id')
    
    # Ajouter les nouvelles colonnes
    if not has_column('contestants', 'title'):
        op.add_column('contestants', sa.Column('title', sa.String(200), nullable=True))
    if not has_column('contestants', 'description'):
        op.add_column('contestants', sa.Column('description', sa.Text(), nullable=True))
    if not has_column('contestants', 'image_media_ids'):
        op.add_column('contestants', sa.Column('image_media_ids', sa.String(1000), nullable=True))
    if not has_column('contestants', 'video_media_id'):
        op.add_column('contestants', sa.Column('video_media_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Supprimer les nouvelles colonnes
    op.drop_column('contestants', 'video_media_id')
    op.drop_column('contestants', 'image_media_ids')
    op.drop_column('contestants', 'description')
    op.drop_column('contestants', 'title')
    
    # Restaurer les anciennes colonnes
    op.add_column('contestants', sa.Column('city_id', sa.Integer(), nullable=False))
    op.add_column('contestants', sa.Column('category_id', sa.Integer(), nullable=True))
