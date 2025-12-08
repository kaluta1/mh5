"""Add RBAC permissions and roles system

Revision ID: add_rbac_permissions
Revises: bb2015d76c4b
Create Date: 2025-12-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_rbac_permissions'
down_revision = 'bb2015d76c4b'
branch_labels = None
depends_on = None


def upgrade():
    # Créer la table permissions
    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_permissions_name', 'permissions', ['name'], unique=True)
    
    # Renommer la table role en roles si elle existe
    # D'abord vérifier et supprimer l'ancienne table user_roles si elle existe
    op.execute("DROP TABLE IF EXISTS user_roles CASCADE")
    
    # Renommer la table role en roles
    op.execute("ALTER TABLE IF EXISTS role RENAME TO roles")
    
    # Ajouter les nouvelles colonnes à roles
    op.add_column('roles', sa.Column('is_system', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('roles', sa.Column('inherit_from_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_roles_inherit_from', 'roles', 'roles', ['inherit_from_id'], ['id'])
    
    # Créer la table role_permissions
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    
    # Ajouter role_id à la table users
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_role', 'users', 'roles', ['role_id'], ['id'])
    
    # Insérer les permissions par défaut
    permissions_data = [
        # Permissions User (catégorie: user)
        ('read', 'Lire le contenu public', 'user'),
        ('vote', 'Voter pour un contestant', 'user'),
        ('comment', 'Commenter', 'user'),
        ('like', 'Liker du contenu', 'user'),
        ('react', 'Réagir au contenu', 'user'),
        ('share', 'Partager du contenu', 'user'),
        ('edit_own_comment', 'Modifier ses propres commentaires', 'user'),
        ('delete_own_comment', 'Supprimer ses propres commentaires', 'user'),
        ('edit_own_contestant', 'Modifier sa propre participation (si non actif)', 'user'),
        ('delete_own_contestant', 'Supprimer sa participation (si éliminé)', 'user'),
        ('delete_own_reaction', 'Supprimer ses propres réactions', 'user'),
        ('create_contestant', 'Créer une participation à un concours', 'user'),
        
        # Permissions Moderator (catégorie: moderator)
        ('view_users', 'Voir la liste des utilisateurs', 'moderator'),
        ('view_contestants', 'Voir la liste des contestants', 'moderator'),
        ('validate_contestant', 'Valider un contestant', 'moderator'),
        ('reject_contestant', 'Rejeter un contestant', 'moderator'),
        ('approve_kyc', 'Approuver un KYC', 'moderator'),
        ('reject_kyc', 'Rejeter un KYC', 'moderator'),
        ('delete_comment', 'Supprimer un commentaire', 'moderator'),
        ('remove_like', 'Retirer un like', 'moderator'),
        ('remove_reaction', 'Retirer une réaction', 'moderator'),
        ('ban_contestant', 'Bannir un contestant', 'moderator'),
        ('suspend_user', 'Suspendre un utilisateur', 'moderator'),
        
        # Permissions Admin (catégorie: admin)
        ('manage_users', 'Gérer les utilisateurs', 'admin'),
        ('manage_roles', 'Gérer les rôles', 'admin'),
        ('manage_permissions', 'Gérer les permissions', 'admin'),
        ('manage_contests', 'Gérer les concours', 'admin'),
        ('manage_payments', 'Gérer les paiements', 'admin'),
        ('manage_commissions', 'Gérer les commissions', 'admin'),
        ('ban_user', 'Bannir un utilisateur', 'admin'),
        ('unban_user', 'Débannir un utilisateur', 'admin'),
        ('view_analytics', 'Voir les analytics', 'admin'),
        ('view_financial_reports', 'Voir les rapports financiers', 'admin'),
        ('manage_settings', 'Gérer les paramètres système', 'admin'),
        ('all', 'Toutes les permissions (super admin)', 'admin'),
    ]
    
    # Insérer les permissions
    for name, description, category in permissions_data:
        op.execute(
            f"INSERT INTO permissions (name, description, category) VALUES ('{name}', '{description}', '{category}')"
        )
    
    # Créer les rôles système
    # 1. Rôle User
    op.execute(
        "INSERT INTO roles (name, description, is_system, created_at, updated_at) VALUES ('user', 'Utilisateur standard', true, NOW(), NOW()) ON CONFLICT (name) DO UPDATE SET is_system = true, description = 'Utilisateur standard'"
    )
    
    # 2. Rôle Moderator (hérite de user)
    op.execute("""
        INSERT INTO roles (name, description, is_system, inherit_from_id, created_at, updated_at) 
        VALUES ('moderator', 'Modérateur de contenu', true, (SELECT id FROM roles WHERE name = 'user'), NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET is_system = true, description = 'Modérateur de contenu', inherit_from_id = (SELECT id FROM roles WHERE name = 'user')
    """)
    
    # 3. Rôle Admin (hérite de moderator)
    op.execute("""
        INSERT INTO roles (name, description, is_system, inherit_from_id, created_at, updated_at) 
        VALUES ('admin', 'Administrateur', true, (SELECT id FROM roles WHERE name = 'moderator'), NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET is_system = true, description = 'Administrateur', inherit_from_id = (SELECT id FROM roles WHERE name = 'moderator')
    """)
    
    # Assigner les permissions au rôle User
    user_permissions = ['read', 'vote', 'comment', 'like', 'react', 'share', 'edit_own_comment', 
                        'delete_own_comment', 'edit_own_contestant', 'delete_own_contestant', 
                        'delete_own_reaction', 'create_contestant']
    for perm in user_permissions:
        op.execute(f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p 
            WHERE r.name = 'user' AND p.name = '{perm}'
            ON CONFLICT DO NOTHING
        """)
    
    # Assigner les permissions au rôle Moderator (en plus de celles héritées de user)
    moderator_permissions = ['view_users', 'view_contestants', 'validate_contestant', 'reject_contestant',
                             'approve_kyc', 'reject_kyc', 'delete_comment', 'remove_like', 
                             'remove_reaction', 'ban_contestant', 'suspend_user']
    for perm in moderator_permissions:
        op.execute(f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p 
            WHERE r.name = 'moderator' AND p.name = '{perm}'
            ON CONFLICT DO NOTHING
        """)
    
    # Assigner les permissions au rôle Admin (en plus de celles héritées de moderator)
    admin_permissions = ['manage_users', 'manage_roles', 'manage_permissions', 'manage_contests',
                         'manage_payments', 'manage_commissions', 'ban_user', 'unban_user',
                         'view_analytics', 'view_financial_reports', 'manage_settings', 'all']
    for perm in admin_permissions:
        op.execute(f"""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p 
            WHERE r.name = 'admin' AND p.name = '{perm}'
            ON CONFLICT DO NOTHING
        """)
    
    # Migrer les utilisateurs existants: assigner le rôle 'user' aux utilisateurs sans rôle
    # et le rôle 'admin' à ceux qui ont is_admin = true
    op.execute("""
        UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'admin')
        WHERE is_admin = true AND role_id IS NULL
    """)
    op.execute("""
        UPDATE users SET role_id = (SELECT id FROM roles WHERE name = 'user')
        WHERE role_id IS NULL
    """)


def downgrade():
    # Supprimer la contrainte FK sur users
    op.drop_constraint('fk_users_role', 'users', type_='foreignkey')
    op.drop_column('users', 'role_id')
    
    # Supprimer la table role_permissions
    op.drop_table('role_permissions')
    
    # Supprimer les colonnes ajoutées à roles
    op.drop_constraint('fk_roles_inherit_from', 'roles', type_='foreignkey')
    op.drop_column('roles', 'inherit_from_id')
    op.drop_column('roles', 'is_system')
    
    # Renommer roles en role
    op.execute("ALTER TABLE roles RENAME TO role")
    
    # Recréer la table user_roles (many-to-many original)
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['role_id'], ['role.id']),
        sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    
    # Supprimer la table permissions
    op.drop_index('ix_permissions_name', table_name='permissions')
    op.drop_table('permissions')
