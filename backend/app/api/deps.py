from typing import Generator, Optional, List, Callable
from functools import wraps
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.token import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Valide le token JWT et récupère l'utilisateur correspondant
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = db.query(User).filter(User.id == token_data.sub).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    return user

def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Vérifie que l'utilisateur est actif
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur inactif"
        )
    return current_user


def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Vérifie que l'utilisateur est administrateur
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilèges administrateur requis"
        )
    return current_user


def get_current_active_user_optional(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme_optional)
) -> Optional[User]:
    """
    Récupère l'utilisateur actif optionnellement (peut être None si pas de token)
    Gère les erreurs de connexion à la base de données en retournant None
    """
    if not token:
        return None
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None
    
    try:
        user = db.query(User).filter(User.id == token_data.sub).first()
        if not user or not user.is_active:
            return None
        return user
    except Exception:
        # En cas d'erreur de connexion à la base de données (SSL, timeout, etc.)
        # on retourne None pour permettre à l'endpoint de continuer sans authentification
        return None


def check_user_permission(user: User, permission_name: str) -> bool:
    """
    Vérifie si un utilisateur a une permission spécifique.
    Les admins avec la permission 'all' ont accès à tout.
    """
    if not user or not user.role:
        return False
    
    # Admin avec permission 'all' peut tout faire
    if user.role.has_permission('all'):
        return True
    
    return user.role.has_permission(permission_name)


def check_user_permissions(user: User, permissions: List[str], require_all: bool = False) -> bool:
    """
    Vérifie si un utilisateur a les permissions requises.
    
    Args:
        user: L'utilisateur à vérifier
        permissions: Liste des permissions à vérifier
        require_all: Si True, toutes les permissions sont requises. Si False, une seule suffit.
    """
    if not user or not user.role:
        return False
    
    # Admin avec permission 'all' peut tout faire
    if user.role.has_permission('all'):
        return True
    
    if require_all:
        return all(user.role.has_permission(p) for p in permissions)
    else:
        return any(user.role.has_permission(p) for p in permissions)


class PermissionChecker:
    """
    Dépendance FastAPI pour vérifier les permissions.
    
    Usage:
        @router.get("/endpoint")
        def endpoint(user: User = Depends(require_permission("manage_users"))):
            ...
    """
    def __init__(self, permissions: List[str], require_all: bool = False):
        self.permissions = permissions
        self.require_all = require_all
    
    def __call__(self, current_user: User = Depends(get_current_active_user)) -> User:
        if not check_user_permissions(current_user, self.permissions, self.require_all):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission(s) requise(s): {', '.join(self.permissions)}"
            )
        return current_user


def require_permission(*permissions: str, require_all: bool = False):
    """
    Factory pour créer une dépendance de vérification de permission.
    
    Usage:
        @router.get("/users")
        def get_users(user: User = Depends(require_permission("view_users"))):
            ...
        
        @router.delete("/users/{id}")
        def delete_user(user: User = Depends(require_permission("manage_users", "ban_user", require_all=False))):
            ...
    """
    return PermissionChecker(list(permissions), require_all)


def require_any_permission(*permissions: str):
    """Raccourci pour require_permission avec require_all=False."""
    return PermissionChecker(list(permissions), require_all=False)


def require_all_permissions(*permissions: str):
    """Raccourci pour require_permission avec require_all=True."""
    return PermissionChecker(list(permissions), require_all=True)


def get_current_moderator_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Vérifie que l'utilisateur est modérateur ou admin.
    """
    if not current_user.role or current_user.role.name not in ['moderator', 'admin']:
        # Vérifier aussi via les permissions
        if not check_user_permission(current_user, 'view_users'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Privilèges modérateur requis"
            )
    return current_user


def is_owner_or_has_permission(
    user: User, 
    resource_owner_id: int, 
    permission_name: str
) -> bool:
    """
    Vérifie si l'utilisateur est le propriétaire de la ressource OU a la permission spécifiée.
    Utile pour les actions comme "supprimer son propre commentaire OU être modérateur".
    """
    if user.id == resource_owner_id:
        return True
    return check_user_permission(user, permission_name)
