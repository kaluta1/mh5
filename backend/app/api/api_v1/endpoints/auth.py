from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request
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
    verify_email_verification_token,
    validate_access_token,
    get_user_id_from_token
)
from app.core.config import settings
from app.db.session import get_db
from app.crud import user as crud_user
from app.api.deps import get_current_active_user
from app.services.email import email_service
from app.crud.crud_login_log import crud_login_log
from app.services.device_location import extract_login_info, get_location_info
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    background_tasks: BackgroundTasks,
    sponsor_code: Optional[str] = Query(None, description="Code de parrainage du parrain"),
    lang: Optional[str] = Query("en", description="Langue préférée (fr, en, es, de)")
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

def log_login_attempt(
    db: Session,
    user_id: int,
    request: Request,
    is_successful: bool = True,
    failure_reason: Optional[str] = None
):
    """Enregistrer une tentative de connexion dans les logs"""
    try:
        # Extraire les informations de base (synchrone)
        login_info = extract_login_info(request)
        
        # Pour la localisation, on essaie de la récupérer mais on ne bloque pas si ça échoue
        location_info = {}
        try:
            # Utiliser asyncio pour récupérer la localisation
            import asyncio
            try:
                # Essayer de récupérer la boucle d'événements existante
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Si on est déjà dans une boucle, on ne peut pas utiliser run_until_complete
                    # On laisse location_info vide et on continue (la géolocalisation est optionnelle)
                    pass
                else:
                    location_info = loop.run_until_complete(
                        get_location_info(request, login_info.get("ip_address"))
                    )
            except RuntimeError:
                # Pas de boucle d'événements, créer une nouvelle
                try:
                    location_info = asyncio.run(
                        get_location_info(request, login_info.get("ip_address"))
                    )
                except:
                    pass
        except Exception as e:
            logger.warning(f"Impossible de récupérer la localisation: {e}")
        
        # Créer le log
        crud_login_log.create(
            db,
            obj_in={
                "user_id": user_id,
                "ip_address": login_info.get("ip_address"),
                "user_agent": login_info.get("user_agent"),
                "device_info": login_info.get("device_info"),
                "location_info": location_info,
                "is_successful": is_successful,
                "failure_reason": failure_reason
            }
        )
    except Exception as e:
        # Ne pas faire échouer la connexion si le logging échoue
        logger.error(f"Erreur lors de l'enregistrement du log de connexion: {e}")


@router.post("/login", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    background_tasks: BackgroundTasks = None
) -> Any:
    """
    OAuth2 compatible token login, obtenir un access token pour les futures requêtes.
    """
    user = crud_user.authenticate(
        db, email_or_username=form_data.username, password=form_data.password
    )
    
    if not user:
        # Enregistrer la tentative de connexion échouée
        if request and background_tasks:
            background_tasks.add_task(
                log_login_attempt,
                db=db,
                user_id=0,  # Pas d'utilisateur pour un échec
                request=request,
                is_successful=False,
                failure_reason="Email/Username ou mot de passe incorrect"
            )
        elif request:
            # Si pas de background_tasks, essayer de logger directement (peut être lent)
            try:
                log_login_attempt(db, 0, request, False, "Email/Username ou mot de passe incorrect")
            except:
                pass
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/Username ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Enregistrer la connexion réussie en arrière-plan
    if request and background_tasks:
        background_tasks.add_task(
            log_login_attempt,
            db=db,
            user_id=user.id,
            request=request,
            is_successful=True
        )
    elif request:
        # Si pas de background_tasks, logger directement (peut être lent)
        try:
            log_login_attempt(db, user.id, request, True)
        except:
            pass
    
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
        user_lang = getattr(user, 'preferred_language', 'en') or 'en'
        
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
    request: Request,
    db: Session = Depends(get_db),
    password_reset: PasswordResetConfirm,
    background_tasks: BackgroundTasks
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
    
    # Récupérer l'adresse IP du client
    client_ip = request.client.host if request.client else None
    # Récupérer l'IP depuis les headers si disponible (pour les proxies)
    if not client_ip or client_ip == "127.0.0.1":
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                client_ip = real_ip
    
    # Pour la localisation, on peut utiliser l'IP pour une géolocalisation basique
    # Pour l'instant, on affiche juste l'IP
    location = None  # Peut être amélioré avec un service de géolocalisation IP
    
    # Réinitialiser le mot de passe
    crud_user.reset_password(db, user=user, new_password=password_reset.new_password)
    
    # Envoyer l'email de notification de sécurité
    user_lang = getattr(user, 'preferred_language', 'en') or 'en'
    support_url = f"{settings.FRONTEND_URL}/contact"
    background_tasks.add_task(
        email_service.send_password_change_security_email,
        to_email=user.email,
        support_url=support_url,
        lang=user_lang,
        ip_address=client_ip,
        location=location
    )
    
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


@router.post("/validate-token")
def validate_token(
    token: str = Query(..., description="Token JWT à valider")
) -> Any:
    """
    Valide un token JWT et retourne l'ID utilisateur si valide.
    Utilisé par les microservices pour valider les tokens sans accès à la base de données.
    """
    payload = validate_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide: ID utilisateur manquant",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return {
        "valid": True,
        "user_id": user_id,
        "exp": payload.get("exp")
    }


@router.post("/change-password", response_model=PasswordResetResponse)
def change_password(
    *,
    request: Request,
    db: Session = Depends(get_db),
    password_data: PasswordChange,
    current_user = Depends(get_current_active_user),
    background_tasks: BackgroundTasks
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
        
    # Récupérer l'adresse IP du client
    client_ip = request.client.host if request.client else None
    # Récupérer l'IP depuis les headers si disponible (pour les proxies)
    if not client_ip or client_ip == "127.0.0.1":
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            real_ip = request.headers.get("X-Real-IP")
            if real_ip:
                client_ip = real_ip
    
    # Pour la localisation, on peut utiliser l'IP pour une géolocalisation basique
    # Pour l'instant, on affiche juste l'IP
    location = None  # Peut être amélioré avec un service de géolocalisation IP
    
    # Mettre à jour le mot de passe
    crud_user.reset_password(db, user=current_user, new_password=password_data.new_password)
    
    # Envoyer l'email de sécurité
    user_lang = getattr(current_user, 'preferred_language', 'en') or 'en'
    support_url = f"{settings.FRONTEND_URL}/contact"
    background_tasks.add_task(
        email_service.send_password_change_security_email,
        to_email=current_user.email,
        support_url=support_url,
        lang=user_lang,
        ip_address=client_ip,
        location=location
    )
    
    return PasswordResetResponse(message="Mot de passe modifié avec succès")
