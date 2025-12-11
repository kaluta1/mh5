from datetime import datetime, timedelta
from typing import Any, Union

from jose import jwt
import bcrypt

from app.core.config import settings


def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifier le mot de passe avec bcrypt directement"""
    try:
        # Encoder et tronquer à 72 bytes (limite bcrypt)
        password_bytes = plain_password.encode('utf-8')[:72]
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Hasher le mot de passe avec bcrypt directement"""
    # Encoder et tronquer à 72 bytes (limite bcrypt)
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def create_password_reset_token(email: str) -> str:
    """Créer un token de réinitialisation de mot de passe"""
    delta = timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    now = datetime.utcnow()
    expires = now + delta
    encoded_jwt = jwt.encode(
        {"exp": expires, "sub": email, "type": "password_reset"}, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def create_email_verification_token(email: str) -> str:
    """Créer un token de vérification d'email"""
    delta = timedelta(hours=24)  # 24 heures pour vérifier l'email
    now = datetime.utcnow()
    expires = now + delta
    encoded_jwt = jwt.encode(
        {"exp": expires, "sub": email, "type": "email_verification"}, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def verify_password_reset_token(token: str) -> str:
    """Vérifier et décoder un token de réinitialisation"""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if decoded_token.get("type") != "password_reset":
            return None
        return decoded_token.get("sub")
    except jwt.JWTError:
        return None

def verify_email_verification_token(token: str) -> str:
    """Vérifier et décoder un token de vérification d'email"""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if decoded_token.get("type") != "email_verification":
            return None
        return decoded_token.get("sub")
    except jwt.JWTError:
        return None
