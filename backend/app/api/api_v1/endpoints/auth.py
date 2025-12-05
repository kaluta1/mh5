from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.schemas.token import Token
from app.schemas.user import UserCreate, User
from app.schemas.password_reset import PasswordResetRequest, PasswordResetConfirm, PasswordResetResponse
from app.core.security import (
    create_access_token, 
    get_password_hash, 
    verify_password,
    create_password_reset_token,
    verify_password_reset_token
)
from app.core.config import settings
from app.db.session import get_db
from app.crud import user as crud_user
from app.api.deps import get_current_active_user

router = APIRouter()

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    sponsor_code: Optional[str] = Query(None, description="Code de parrainage du parrain")
) -> Any:
    """
    Créer un nouvel utilisateur.
    
    - **sponsor_code**: Code de parrainage optionnel pour associer l'utilisateur à un parrain
    """
    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà."
        )
    
    # Créer l'utilisateur avec le parrain si un code est fourni
    user = crud_user.create_with_sponsor(db, obj_in=user_in, sponsor_code=sponsor_code)
    return user

@router.post("/login", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, obtenir un access token pour les futures requêtes.
    """
    user = crud_user.authenticate(
        db, email_or_username=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/Username ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": create_access_token(
            subject=user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/password-reset-request", response_model=PasswordResetResponse)
def request_password_reset(
    *,
    db: Session = Depends(get_db),
    password_reset: PasswordResetRequest
) -> Any:
    """
    Demander une réinitialisation de mot de passe.
    Envoie un token de réinitialisation (normalement par email).
    """
    user = crud_user.get_by_email(db, email=password_reset.email)
    
    # Pour des raisons de sécurité, on retourne toujours le même message
    # même si l'utilisateur n'existe pas
    if user and user.is_active:
        # Générer le token de réinitialisation
        reset_token = create_password_reset_token(user.email)
        
        # TODO: Ici, vous devriez envoyer un email avec le token
        # Pour le développement, on peut logger le token
        print(f"Token de réinitialisation pour {user.email}: {reset_token}")
        
    return PasswordResetResponse(
        message="Si cet email existe, un lien de réinitialisation a été envoyé"
    )

@router.post("/password-reset-confirm", response_model=PasswordResetResponse)
def confirm_password_reset(
    *,
    db: Session = Depends(get_db),
    password_reset: PasswordResetConfirm
) -> Any:
    """
    Confirmer la réinitialisation de mot de passe avec le token.
    """
    # Vérifier le token
    email = verify_password_reset_token(password_reset.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token invalide ou expiré"
        )
    
    # Récupérer l'utilisateur
    user = crud_user.get_by_email(db, email=email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utilisateur inactif"
        )
    
    # Réinitialiser le mot de passe
    crud_user.reset_password(db, user=user, new_password=password_reset.new_password)
    
    return PasswordResetResponse(
        message="Mot de passe réinitialisé avec succès"
    )

@router.get("/me", response_model=User)
def read_user_me(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Récupérer les informations de l'utilisateur connecté.
    """
    return current_user
