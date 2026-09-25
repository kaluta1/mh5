from datetime import datetime, timedelta
from typing import Any, Union, Optional

from jose import jwt
import bcrypt
import hashlib
import hmac
import uuid

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
    now = datetime.utcnow()
    to_encode = {
        "exp": expire, "iat": now, "sub": str(subject), "type": "access",
        "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE, "jti": uuid.uuid4().hex,
    }
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

def _password_version(hashed_password: str) -> str:
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()


def _decode_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )


def create_password_reset_token(email: str, hashed_password: str) -> str:
    """Créer un token de réinitialisation de mot de passe"""
    delta = timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    now = datetime.utcnow()
    expires = now + delta
    encoded_jwt = jwt.encode(
        {
            "exp": expires, "iat": now, "sub": email, "type": "password_reset",
            "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE,
            "jti": uuid.uuid4().hex, "pwdv": _password_version(hashed_password),
        },
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
        {
            "exp": expires, "iat": now, "sub": email, "type": "email_verification",
            "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE, "jti": uuid.uuid4().hex,
        },
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def verify_password_reset_token(token: str, hashed_password: str) -> str:
    """Vérifier et décoder un token de réinitialisation"""
    try:
        decoded_token = _decode_token(token)
        if decoded_token.get("type") != "password_reset":
            return None
        if not hmac.compare_digest(
            str(decoded_token.get("pwdv") or ""), _password_version(hashed_password)
        ):
            return None
        return decoded_token.get("sub")
    except jwt.JWTError:
        return None


def get_password_reset_subject(token: str) -> Optional[str]:
    """Validate reset-token signature/claims and return its account locator."""
    try:
        payload = _decode_token(token)
        if payload.get("type") != "password_reset" or not payload.get("pwdv"):
            return None
        return payload.get("sub")
    except jwt.JWTError:
        return None

def verify_email_verification_token(token: str) -> str:
    """Vérifier et décoder un token de vérification d'email"""
    try:
        decoded_token = _decode_token(token)
        if decoded_token.get("type") != "email_verification":
            return None
        return decoded_token.get("sub")
    except jwt.JWTError:
        return None

def decode_access_token(token: str) -> dict:
    """Décode un token d'accès JWT"""
    try:
        decoded_token = _decode_token(token)
        if decoded_token.get("type") != "access":
            return {}
        return decoded_token
    except jwt.JWTError:
        return {}

def validate_access_token(token: str) -> Optional[dict]:
    """
    Valide un token d'accès JWT et retourne le payload si valide.
    Utilisé par les microservices pour valider les tokens sans accès à la base de données.
    
    Returns:
        dict: Le payload du token si valide, None sinon
    """
    try:
        decoded_token = _decode_token(token)
        if decoded_token.get("type") != "access":
            return None
        return decoded_token
    except jwt.JWTError:
        return None

KYC_DOCUMENT_VIEW_TOKEN_TYPE = "kyc_document_view"
KYC_DOCUMENT_VIEW_TOKEN_MINUTES = 5


def create_kyc_document_view_token(viewer_user_id: int, document_id: int, side: str) -> str:
    """Short-lived token letting one admin view one side of one KYC document.
    Its type is not "access", so it can never authenticate API requests."""
    now = datetime.utcnow()
    return jwt.encode(
        {
            "exp": now + timedelta(minutes=KYC_DOCUMENT_VIEW_TOKEN_MINUTES),
            "iat": now,
            "sub": str(viewer_user_id),
            "type": KYC_DOCUMENT_VIEW_TOKEN_TYPE,
            "doc": int(document_id),
            "side": side,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "jti": uuid.uuid4().hex,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def verify_kyc_document_view_token(token: str, document_id: int, side: str) -> Optional[int]:
    """Return the viewer user id if the token is valid for exactly this document side."""
    if not token:
        return None
    try:
        payload = _decode_token(token)
    except jwt.JWTError:
        return None
    if payload.get("type") != KYC_DOCUMENT_VIEW_TOKEN_TYPE:
        return None
    if payload.get("doc") != int(document_id) or payload.get("side") != side:
        return None
    try:
        return int(payload.get("sub"))
    except (TypeError, ValueError):
        return None


def get_user_id_from_token(token: str) -> Optional[int]:
    """
    Extrait l'ID utilisateur depuis un token JWT valide.
    Utilisé par les microservices pour obtenir l'ID utilisateur sans accès à la base de données.
    
    Returns:
        int: L'ID utilisateur si le token est valide, None sinon
    """
    payload = validate_access_token(token)
    if payload and "sub" in payload:
        try:
            return int(payload["sub"])
        except (ValueError, TypeError):
            return None
    return None
