from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.schemas.token import Token
from app.schemas.user import UserCreate, User
from app.schemas.password_reset import PasswordResetRequest, PasswordResetConfirm, PasswordResetResponse, PasswordChange
from app.core.security import (
    create_access_token, 
    get_password_hash, 
    verify_password,
    create_password_reset_token,
    verify_password_reset_token,
    create_email_verification_token,
    verify_email_verification_token
)
from app.core.config import settings
from app.db.session import get_db
from app.crud import user as crud_user
from app.api.deps import get_current_active_user
from app.services.email import email_service

router = APIRouter()

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    background_tasks: BackgroundTasks,
    sponsor_code: Optional[str] = Query(None, description="Code de parrainage du parrain"),
    lang: Optional[str] = Query("fr", description="Langue préférée (fr, en, es, de)")
) -> Any:
    """
    Créer un nouvel utilisateur.
    
    - **sponsor_code**: Code de parrainage optionnel pour associer l'utilisateur à un parrain
    - **lang**: Langue préférée pour les communications
    """
    # Vérifier si l'email existe déjà
    user = crud_user.get_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un utilisateur avec cet email existe déjà."
        )
    
    # Vérifier si le username existe déjà
    if user_in.username:
        existing_user = crud_user.get_by_username(db, username=user_in.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce nom d'utilisateur est déjà pris."
            )
    
    # Créer l'utilisateur avec le parrain si un code est fourni
    try:
        user = crud_user.create_with_sponsor(db, obj_in=user_in, sponsor_code=sponsor_code)
    except IntegrityError as e:
        db.rollback()
        error_str = str(e.orig).lower()
        if 'email' in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un utilisateur avec cet email existe déjà."
            )
        elif 'username' in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce nom d'utilisateur est déjà pris."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur lors de la création du compte. Veuillez réessayer."
            )
    
    # Mettre à jour la langue préférée
    if lang and hasattr(user, 'preferred_language'):
        user.preferred_language = lang
        db.commit()
    
    # Envoyer l'email de bienvenue avec token de vérification
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={create_email_verification_token(user.email)}"
    background_tasks.add_task(
        email_service.send_welcome_email,
        to_email=user.email,
        verify_url=verify_url,
        lang=lang or "en"
    )
    
    return user

@router.post("/verify-email")
def verify_email(
    *,
    db: Session = Depends(get_db),
    token: str = Query(..., description="Token de vérification d'email")
) -> Any:
    """
    Vérifier l'adresse email d'un utilisateur avec le token reçu par email.
    """
    # Vérifier le token
    email = verify_email_verification_token(token)
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
    
    # Marquer l'email comme vérifié
    user.email_verified = True
    db.commit()
    db.refresh(user)
    
    return {"message": "Email vérifié avec succès", "email": email}

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
    password_reset: PasswordResetRequest,
    background_tasks: BackgroundTasks
) -> Any:
    """
    Demander une réinitialisation de mot de passe.
    Envoie un token de réinitialisation par email.
    """
    user = crud_user.get_by_email(db, email=password_reset.email)
    
    # Pour des raisons de sécurité, on retourne toujours le même message
    # même si l'utilisateur n'existe pas
    if user and user.is_active:
        # Générer le token de réinitialisation
        reset_token = create_password_reset_token(user.email)
        
        # Construire l'URL de réinitialisation
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        # Récupérer la langue préférée de l'utilisateur
        user_lang = getattr(user, 'preferred_language', 'fr') or 'fr'
        
        # Envoyer l'email de réinitialisation
        background_tasks.add_task(
            email_service.send_password_reset_email,
            to_email=user.email,
            reset_url=reset_url,
            lang=user_lang
        )
        
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


@router.post("/change-password", response_model=PasswordResetResponse)
def change_password(
    *,
    db: Session = Depends(get_db),
    password_data: PasswordChange,
    current_user = Depends(get_current_active_user)
) -> Any:
    """
    Changer le mot de passe de l'utilisateur connecté.
    Nécessite de fournir le mot de passe actuel.
    """
    # Vérifier le mot de passe actuel
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect"
        )
    
    # Vérifier que le nouveau mot de passe est différent
    if password_data.current_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nouveau mot de passe doit être différent de l'ancien"
        )
    
    # Vérifier la longueur minimale du nouveau mot de passe
    if len(password_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le mot de passe doit contenir au moins 6 caractères"
        )
    
    # Mettre à jour le mot de passe
    crud_user.reset_password(db, user=current_user, new_password=password_data.new_password)
    
    return PasswordResetResponse(message="Mot de passe modifié avec succès")
