import os
import uuid
import mimetypes
from typing import Dict, Any, Optional, Tuple, Iterator
import logging
import aiofiles
from fastapi import UploadFile
import boto3
from botocore.exceptions import ClientError
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)


def media_s3_key(user_id: int, filename: str) -> str:
    safe_name = os.path.basename(filename)
    return f"uploads/{user_id}/{safe_name}"


def local_media_path(user_id: int, filename: str) -> str:
    safe_name = os.path.basename(filename)
    return os.path.join(settings.LOCAL_STORAGE_PATH, str(user_id), safe_name)


def resolve_media_for_serving(
    user_id: int, filename: str
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Resolve media for HTTP serving: local disk first, then S3.
    Returns (source, ref, content_type) where source is 'local' or 's3'.
    """
    safe_name = os.path.basename(filename)
    content_type, _ = mimetypes.guess_type(safe_name)
    content_type = content_type or "application/octet-stream"

    local_path = local_media_path(user_id, safe_name)
    if os.path.isfile(local_path):
        return "local", local_path, content_type

    bucket = (settings.S3_BUCKET_NAME or settings.AWS_S3_BUCKET or "").strip()
    if bucket and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        s3_key = media_s3_key(user_id, safe_name)
        try:
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.S3_REGION,
            )
            s3_client.head_object(Bucket=bucket, Key=s3_key)
            return "s3", s3_key, content_type
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                logger.warning("S3 head_object failed for %s: %s", s3_key, e)

    return None, None, content_type


def iter_s3_object(bucket: str, key: str) -> Iterator[bytes]:
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
    )
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    while True:
        chunk = body.read(1024 * 64)
        if not chunk:
            break
        yield chunk


def _build_public_media_url(user_id: int, filename: str) -> str:
    """
    Build a browser-safe media URL served by backend API (works even when `/media/*`
    is not exposed by reverse proxy).
    """
    base = (settings.BACKEND_PUBLIC_URL or settings.FRONTEND_URL or "").rstrip("/")
    path = f"/api/v1/media/file/{user_id}/{filename}"
    if base:
        return f"{base}{path}"
    return path

# Proof-of-address: scans / photos / PDF bills
KYC_POA_MAX_BYTES = 10 * 1024 * 1024
KYC_POA_ALLOWED_CT_PREFIXES = ("image/", "application/pdf")


async def store_kyc_proof_file(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """
    Store a proof-of-address upload (image or PDF). Same storage backend as media (local or S3).
    """
    content_type = (file.content_type or "").lower()
    if not any(content_type.startswith(p) for p in KYC_POA_ALLOWED_CT_PREFIXES):
        raise ValueError(
            "Proof of address must be an image (JPEG, PNG, WebP, etc.) or a PDF."
        )

    content = await file.read()
    if len(content) > KYC_POA_MAX_BYTES:
        raise ValueError(f"File too large (max {KYC_POA_MAX_BYTES // (1024 * 1024)} MB).")

    extension = os.path.splitext(file.filename or "")[1].lower()
    if not extension:
        if "pdf" in content_type:
            extension = ".pdf"
        elif "png" in content_type:
            extension = ".png"
        elif "jpeg" in content_type or "jpg" in content_type:
            extension = ".jpg"
        else:
            extension = ".bin"

    file_uuid = str(uuid.uuid4())
    filename = f"kyc_poa_{file_uuid}{extension}"

    if settings.STORAGE_TYPE == "s3":
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=settings.S3_REGION,
        )
        s3_path = f"uploads/{user_id}/{filename}"
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=s3_path,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        url = f"https://{settings.S3_BUCKET_NAME}.s3.amazonaws.com/{s3_path}"
        return {"path": s3_path, "url": url, "metadata": {}}

    user_dir = os.path.join(settings.LOCAL_STORAGE_PATH, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, filename)
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(content)

    url = _build_public_media_url(user_id, filename)
    metadata: Dict[str, Any] = {}
    if content_type.startswith("image/"):
        try:
            with Image.open(file_path) as img:
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["file_size"] = os.path.getsize(file_path)
        except Exception:
            pass

    return {"path": file_path, "url": url, "metadata": metadata}


async def store_media(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """
    Stocke un fichier média (image ou vidéo) et retourne les informations nécessaires
    """
    # Créer un nom de fichier unique
    extension = os.path.splitext(file.filename)[1].lower()
    file_uuid = str(uuid.uuid4())
    filename = f"{file_uuid}{extension}"
    
    # Déterminer le chemin du fichier selon le type de stockage
    if settings.STORAGE_TYPE == "s3":
        try:
            return await store_in_s3(file, filename, user_id)
        except Exception as e:
            # Production safety: if S3 is misconfigured, do not block user uploads.
            logger.exception("S3 upload failed, falling back to local storage: %s", e)
            return await store_locally(file, filename, user_id)
    # local par défaut
    return await store_locally(file, filename, user_id)


async def store_locally(file: UploadFile, filename: str, user_id: int) -> Dict[str, Any]:
    """
    Stocke un fichier localement
    """
    # Créer le dossier de stockage s'il n'existe pas
    user_dir = os.path.join(settings.LOCAL_STORAGE_PATH, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    # Chemin complet du fichier
    file_path = os.path.join(user_dir, filename)
    
    # Stocker le fichier
    async with aiofiles.open(file_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)
    
    # Public URL served by backend API route
    url = _build_public_media_url(user_id, filename)
    
    # Récupérer les métadonnées pour les images
    metadata = {}
    if file.content_type.startswith("image/"):
        try:
            with Image.open(file_path) as img:
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["file_size"] = os.path.getsize(file_path)
        except Exception:
            pass
    
    return {
        "path": file_path,
        "url": url,
        "metadata": metadata
    }


async def store_in_s3(file: UploadFile, filename: str, user_id: int) -> Dict[str, Any]:
    """
    Stocke un fichier sur AWS S3
    """
    # Configuration de S3
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=settings.S3_REGION
    )
    
    # Chemin dans le bucket
    s3_path = f"uploads/{user_id}/{filename}"
    
    # Lire le contenu du fichier
    content = await file.read()
    
    # Upload vers S3
    s3_client.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=s3_path,
        Body=content,
        ContentType=file.content_type
    )
    
    # Always expose the API file route (works for private S3 buckets).
    url = _build_public_media_url(user_id, filename)

    return {
        "path": s3_path,
        "url": url,
        "metadata": {}
    }
