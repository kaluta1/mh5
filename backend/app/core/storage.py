import os
import uuid
from typing import Dict, Any
import aiofiles
from fastapi import UploadFile
import boto3
from PIL import Image

from app.core.config import settings


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
        return await store_in_s3(file, filename, user_id)
    else:  # local par défaut
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
    
    # URL relative
    url = f"/media/{user_id}/{filename}"
    
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
    
    # URL publique
    url = f"https://{settings.S3_BUCKET_NAME}.s3.amazonaws.com/{s3_path}"
    
    # Métadonnées - pour les images, nous pourrions utiliser les services AWS pour les récupérer
    # mais pour simplifier, nous ne les incluons pas ici
    
    return {
        "path": s3_path,
        "url": url,
        "metadata": {}
    }
