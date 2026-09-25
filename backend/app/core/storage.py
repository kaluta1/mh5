import os
import re
import shutil
import uuid
import mimetypes
from io import BytesIO
from typing import Dict, Any, Optional, Tuple, Iterator
import logging
import aiofiles
from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from functools import lru_cache
from urllib.parse import unquote, urlparse
from PIL import Image
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from app.core.config import settings

logger = logging.getLogger(__name__)

MEDIA_IMAGE_MAX_BYTES = 8 * 1024 * 1024
MEDIA_VIDEO_MAX_BYTES = 32 * 1024 * 1024
MEDIA_MAX_PIXELS = 50_000_000

_S3_CONFIG = Config(
    connect_timeout=3,
    read_timeout=10,
    retries={"max_attempts": 2, "mode": "standard"},
    max_pool_connections=10,
)


@lru_cache(maxsize=1)
def _s3_client():
    """Reuse the bounded botocore connection pool across media requests."""
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
        config=_S3_CONFIG,
    )

_IMAGE_SIGNATURES = (
    ("jpeg", ".jpg", "image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ("png", ".png", "image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ("gif", ".gif", "image/gif", lambda data: data.startswith((b"GIF87a", b"GIF89a"))),
    ("webp", ".webp", "image/webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
)

# KYC documents are private. Every KYC file ever written uses a "kyc_" name
# prefix (store_kyc_proof_file), while ordinary media is always "<uuid>.<ext>",
# so the prefix reliably identifies KYC files, including legacy ones that still
# live inside the public media roots. Public routes must refuse them.
PRIVATE_KYC_FILENAME_PREFIXES = ("kyc_",)
KYC_PRIVATE_REF_SCHEME = "kyc-private://"
KYC_PRIVATE_S3_PREFIX = "private/kyc"


def is_private_kyc_filename(name: str) -> bool:
    """True for KYC document file names (case-insensitive, as Windows/NTFS paths are)."""
    return str(name or "").strip().lower().startswith(PRIVATE_KYC_FILENAME_PREFIXES)


def path_contains_private_kyc(path: str) -> bool:
    """True if any segment of a request path names a KYC file."""
    return any(is_private_kyc_filename(part) for part in re.split(r"[\\/]+", str(path or "")))


def validate_media_content(filename: str, declared_content_type: str, content: bytes) -> Dict[str, Any]:
    """Validate filename, size, extension, MIME declaration, and file signature."""
    raw_name = str(filename or "")
    if not raw_name or raw_name != os.path.basename(raw_name) or "\\" in raw_name or "\x00" in raw_name:
        raise ValueError("Invalid upload filename")
    extension = os.path.splitext(raw_name)[1].lower()
    declared = str(declared_content_type or "").split(";", 1)[0].strip().lower()

    detected = None
    for kind, canonical_extension, content_type, matches in _IMAGE_SIGNATURES:
        if matches(content):
            detected = (kind, canonical_extension, content_type)
            break
    if detected is None and len(content) >= 12 and content[4:8] == b"ftyp":
        is_quicktime = content[8:12] == b"qt  "
        detected = ("video", ".mov" if is_quicktime else ".mp4", "video/quicktime" if is_quicktime else "video/mp4")
    if detected is None and content.startswith(b"\x1aE\xdf\xa3"):
        detected = ("video", ".webm", "video/webm")
    if detected is None:
        raise ValueError("Unsupported or malformed media content")

    kind, canonical_extension, detected_type = detected
    media_type = "image" if kind != "video" else "video"
    max_bytes = MEDIA_IMAGE_MAX_BYTES if media_type == "image" else MEDIA_VIDEO_MAX_BYTES
    if not content:
        raise ValueError("Upload is empty")
    if len(content) > max_bytes:
        raise ValueError(f"File too large (maximum {max_bytes // (1024 * 1024)} MB)")

    allowed_extensions = {canonical_extension}
    if canonical_extension == ".jpg":
        allowed_extensions.add(".jpeg")
    if extension not in allowed_extensions:
        raise ValueError("Filename extension does not match media content")
    allowed_declared = {detected_type}
    if detected_type == "image/jpeg":
        allowed_declared.add("image/jpg")
    if declared not in allowed_declared:
        raise ValueError("Declared MIME type does not match media content")

    metadata: Dict[str, Any] = {
        "file_size": len(content),
        "content_type": detected_type,
        "extension": canonical_extension,
        "media_type": media_type,
    }
    if media_type == "image":
        try:
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > MEDIA_MAX_PIXELS:
                    raise ValueError("Image dimensions are too large")
                image.verify()
            with Image.open(BytesIO(content)) as image:
                metadata["width"] = image.width
                metadata["height"] = image.height
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Malformed image content") from exc
    return metadata


def media_s3_key(user_id: int, filename: str) -> str:
    safe_name = os.path.basename(filename)
    return f"uploads/{user_id}/{safe_name}"


def local_media_path(user_id: int, filename: str) -> str:
    safe_name = os.path.basename(filename)
    return os.path.join(settings.LOCAL_STORAGE_PATH, str(user_id), safe_name)


def _mirror_local_media_file(user_id: int, filename: str, source_path: str) -> None:
    """Copy a freshly written upload to every known local media root."""
    safe_name = os.path.basename(filename)
    normalized_source = os.path.normpath(source_path)
    for root in media_storage_roots():
        dest_dir = os.path.join(root, str(user_id))
        dest_path = os.path.normpath(os.path.join(dest_dir, safe_name))
        if dest_path == normalized_source:
            continue
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(normalized_source, dest_path)
        except OSError as exc:
            logger.warning("Could not mirror media to %s: %s", dest_path, exc)


def media_storage_roots() -> list[str]:
    """Candidate directories for locally stored uploads (VPS + Docker + dev)."""
    roots: list[str] = []
    for candidate in (
        settings.LOCAL_STORAGE_PATH,
        "/var/lib/myhigh5/media",
        "/app/storage",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "media"),
    ):
        text = str(candidate or "").strip()
        if text and text not in roots:
            roots.append(text)
    return roots


def resolve_media_for_serving(
    user_id: int, filename: str
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Resolve media for HTTP serving: local disk first, then S3.
    Returns (source, ref, content_type) where source is 'local' or 's3'.
    """
    safe_name = _safe_basename(filename)
    if not safe_name:
        return None, None, "application/octet-stream"
    if is_private_kyc_filename(safe_name):
        # KYC documents are never served through public media delivery. Answer
        # exactly like a missing file so existence is not revealed.
        return None, None, "application/octet-stream"
    return _locate_stored_file(
        [os.path.join(root, str(user_id)) for root in media_storage_roots()],
        media_s3_key(user_id, safe_name),
        safe_name,
    )


def _safe_basename(filename: str) -> Optional[str]:
    safe_name = os.path.basename(filename or "")
    if not safe_name or safe_name != filename or "\\" in filename or "\x00" in filename:
        return None
    if safe_name in (".", ".."):
        return None
    return safe_name


def _locate_stored_file(
    local_dirs: list[str], s3_key: str, safe_name: str
) -> Tuple[Optional[str], Optional[str], str]:
    """Find a stored file on local disk (first match) or in S3. No access checks."""
    content_type, _ = mimetypes.guess_type(safe_name)
    content_type = content_type or "application/octet-stream"

    for directory in local_dirs:
        local_path = os.path.join(directory, safe_name)
        if os.path.isfile(local_path):
            return "local", local_path, content_type

    bucket = (settings.S3_BUCKET_NAME or settings.AWS_S3_BUCKET or "").strip()
    if bucket and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        try:
            s3_client = _s3_client()
            s3_client.head_object(Bucket=bucket, Key=s3_key)
            return "s3", s3_key, content_type
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                logger.warning("S3 head_object failed for %s: %s", s3_key, e)

    return None, None, content_type


def iter_s3_object(bucket: str, key: str) -> Iterator[bytes]:
    s3_client = _s3_client()
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    while True:
        chunk = body.read(1024 * 64)
        if not chunk:
            break
        yield chunk


def _build_public_media_url(user_id: int, filename: str) -> str:
    """
    Relative API path — frontend resolves host via getEffectiveApiUrl() / nginx proxy.
    Avoids hard-coding api.myhigh5.com when the UI is served from myhigh5.com.
    """
    safe_name = os.path.basename(filename)
    return f"/api/v1/media/file/{user_id}/{safe_name}"

# Proof-of-address: scans / photos / PDF bills
KYC_POA_MAX_BYTES = 10 * 1024 * 1024
KYC_POA_ALLOWED_CT_PREFIXES = ("image/", "application/pdf")


async def store_kyc_proof_file(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """
    Store a proof-of-address upload (image or PDF) in PRIVATE KYC storage.

    Local: kyc_private_storage_root()/{user_id}/ (outside every public media root).
    S3: private/kyc/{user_id}/ (never produced by media_s3_key()).
    The returned "url" is an opaque kyc-private:// reference, not a public URL;
    only the admin-authorized KYC document route can resolve it.
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

    url = f"{KYC_PRIVATE_REF_SCHEME}{int(user_id)}/{filename}"

    if settings.STORAGE_TYPE == "s3":
        s3_client = _s3_client()
        s3_path = kyc_private_s3_key(user_id, filename)
        await run_in_threadpool(
            s3_client.put_object,
            Bucket=settings.S3_BUCKET_NAME,
            Key=s3_path,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        return {"path": s3_path, "url": url, "metadata": {}}

    user_dir = os.path.join(kyc_private_storage_root(), str(int(user_id)))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, filename)
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(content)

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


def kyc_private_storage_root() -> str:
    """Local directory for private KYC documents: never a public media root."""
    configured = (getattr(settings, "KYC_PRIVATE_STORAGE_PATH", "") or "").strip()
    if configured:
        root = os.path.abspath(configured)
    else:
        media_root = os.path.abspath(settings.LOCAL_STORAGE_PATH or "./media")
        root = os.path.join(os.path.dirname(media_root), "private_kyc")
    # Fail closed: a KYC directory inside (or equal to) a public media root would
    # be reachable by the public media routes' directory lookups.
    normalized = os.path.normcase(os.path.normpath(root))
    for media in media_storage_roots():
        media_norm = os.path.normcase(os.path.normpath(os.path.abspath(media)))
        if normalized == media_norm or normalized.startswith(media_norm + os.sep):
            raise RuntimeError("KYC private storage must be outside every public media directory")
    return root


def kyc_private_s3_key(user_id: int, filename: str) -> str:
    return f"{KYC_PRIVATE_S3_PREFIX}/{int(user_id)}/{os.path.basename(filename)}"


def parse_kyc_document_reference(stored: Optional[str]) -> Optional[Tuple[str, int, str]]:
    """
    Parse a kyc_documents.*_image_url value into (location, user_id, filename).

    location is "private" for new kyc-private:// references, or "legacy" for
    files written before the private namespace existed (still inside the public
    media roots / uploads/ S3 key space, denied by the public routes):
      /api/v1/media/file/{uid}/{name}   (local storage, relative or absolute)
      /media/{uid}/{name}               (local static mount)
      https://{bucket}.s3.amazonaws.com/uploads/{uid}/{name}  (S3)
    Only KYC file names are accepted.
    """
    raw = str(stored or "").strip()
    if not raw:
        return None
    if raw.startswith(KYC_PRIVATE_REF_SCHEME):
        location, rest = "private", raw[len(KYC_PRIVATE_REF_SCHEME):]
    else:
        path = unquote(urlparse(raw).path or "")
        match = re.search(r"/(?:api/v1/media/file|media|uploads)/(\d+/[^/]+)$", path)
        if not match:
            return None
        location, rest = "legacy", match.group(1)
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    filename = _safe_basename(parts[1])
    if not filename or not is_private_kyc_filename(filename):
        return None
    return location, int(parts[0]), filename


_KYC_SERVABLE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def resolve_kyc_document_for_serving(
    stored: Optional[str], owner_user_id: int
) -> Tuple[Optional[str], Optional[str], str, bool]:
    """
    Locate a KYC document for the admin-authorized KYC route ONLY.
    Returns (source, ref, content_type, inline). The file must belong to
    owner_user_id. Unknown extensions are served as an attachment of type
    application/octet-stream so an uploaded file can never render as HTML.
    """
    parsed = parse_kyc_document_reference(stored)
    if not parsed:
        return None, None, "application/octet-stream", False
    location, user_id, filename = parsed
    if user_id != int(owner_user_id):
        return None, None, "application/octet-stream", False

    if location == "private":
        local_dirs = [os.path.join(kyc_private_storage_root(), str(user_id))]
        s3_key = kyc_private_s3_key(user_id, filename)
    else:
        local_dirs = [os.path.join(root, str(user_id)) for root in media_storage_roots()]
        s3_key = media_s3_key(user_id, filename)

    source, ref, _ = _locate_stored_file(local_dirs, s3_key, filename)
    content_type = _KYC_SERVABLE_CONTENT_TYPES.get(os.path.splitext(filename)[1].lower())
    if content_type is None:
        return source, ref, "application/octet-stream", False
    return source, ref, content_type, True


class PublicMediaStaticFiles(StaticFiles):
    """The public /media mount, refusing KYC documents (legacy ones live under it)."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        if path_contains_private_kyc(path):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response(path, scope)

    def lookup_path(self, path: str):  # type: ignore[override]
        full_path, stat_result = super().lookup_path(path)
        # Also check the resolved name (e.g. Windows 8.3 short names / case).
        if full_path and path_contains_private_kyc(os.path.basename(full_path)):
            return "", None
        return full_path, stat_result


async def store_media(file: UploadFile, user_id: int) -> Dict[str, Any]:
    """
    Stocke un fichier média (image ou vidéo) et retourne les informations nécessaires
    """
    # Créer un nom de fichier unique
    content = await file.read(MEDIA_VIDEO_MAX_BYTES + 1)
    validation = await run_in_threadpool(
        validate_media_content,
        file.filename or "",
        file.content_type or "",
        content,
    )
    extension = validation["extension"]
    file_uuid = str(uuid.uuid4())
    filename = f"{file_uuid}{extension}"
    
    # Déterminer le chemin du fichier selon le type de stockage
    if settings.STORAGE_TYPE == "s3":
        try:
            return await store_in_s3(
                content, filename, user_id, validation["content_type"], validation
            )
        except Exception as e:
            if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
                raise
            logger.exception("S3 upload failed; using local storage outside production: %s", e)
            return await store_locally(content, filename, user_id, validation)
    # local par défaut
    return await store_locally(content, filename, user_id, validation)


async def store_locally(
    content: bytes, filename: str, user_id: int, metadata: Dict[str, Any]
) -> Dict[str, Any]:
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
        await out_file.write(content)

    _mirror_local_media_file(user_id, filename, file_path)

    # Public URL served by backend API route
    url = _build_public_media_url(user_id, filename)
    
    # Récupérer les métadonnées pour les images
    return {
        "path": file_path,
        "url": url,
        "metadata": dict(metadata),
        "content_type": metadata["content_type"],
        "media_type": metadata["media_type"],
    }


async def store_in_s3(
    content: bytes,
    filename: str,
    user_id: int,
    content_type: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Stocke un fichier sur AWS S3
    """
    # Configuration de S3
    bucket = (settings.S3_BUCKET_NAME or settings.AWS_S3_BUCKET or "").strip()
    if not bucket:
        raise ValueError("S3 bucket is not configured")

    s3_client = _s3_client()

    s3_path = media_s3_key(user_id, filename)
    await run_in_threadpool(
        s3_client.put_object,
        Bucket=bucket,
        Key=s3_path,
        Body=content,
        ContentType=content_type,
    )
    
    # Always expose the API file route (works for private S3 buckets).
    url = _build_public_media_url(user_id, filename)

    return {
        "path": s3_path,
        "url": url,
        "metadata": dict(metadata),
        "content_type": content_type,
        "media_type": metadata["media_type"],
    }
