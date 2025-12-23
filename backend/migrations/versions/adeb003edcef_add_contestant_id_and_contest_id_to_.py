"""add_contestant_id_and_contest_id_to_report

Revision ID: adeb003edcef
Revises: b1c2d3e4f5a6
Create Date: 2025-12-23 12:42:09.431050

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'adeb003edcef'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [col['name'] for col in insp.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # Ajouter la colonne contestant_id à la table report si elle n'existe pas
    if not column_exists('report', 'contestant_id'):
        op.add_column(
            'report',
            sa.Column('contestant_id', sa.Integer(), nullable=True)
        )
        # Ajouter la contrainte de clé étrangère
        op.create_foreign_key(
            'fk_report_contestant_id',
            'report', 'contestants',
            ['contestant_id'], ['id'],
            ondelete='CASCADE'
        )
    
    # Ajouter la colonne contest_id à la table report si elle n'existe pas
    if not column_exists('report', 'contest_id'):
        op.add_column(
            'report',
            sa.Column('contest_id', sa.Integer(), nullable=True)
        )
        # Ajouter la contrainte de clé étrangère
        op.create_foreign_key(
            'fk_report_contest_id',
            'report', 'contest',
            ['contest_id'], ['id'],
            ondelete='CASCADE'
        )


def downgrade():
    # Supprimer les contraintes de clé étrangère
    if column_exists('report', 'contestant_id'):
        op.drop_constraint('fk_report_contestant_id', 'report', type_='foreignkey')
        op.drop_column('report', 'contestant_id')
    
    if column_exists('report', 'contest_id'):
        op.drop_constraint('fk_report_contest_id', 'report', type_='foreignkey')
        op.drop_column('report', 'contest_id')
