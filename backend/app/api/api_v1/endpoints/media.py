from typing import Any, List, Optional
import os
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import media as crud_media
from app.db.session import get_db
from app.schemas.media import MediaCreate, Media
from app.models.user import User as UserModel
from app.core.storage import (
    store_media,
    resolve_media_for_serving,
    iter_s3_object,
)
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
def open_media_session(request: Request, current_user: UserModel = Depends(get_current_active_user)):
    """Child/Teen Safety Phase 7: bind this browser to the authenticated viewer for
    protected media (<img>/<video> cannot send an Authorization header). The value
    is an HttpOnly, SameSite=Strict cookie scoped to the media route only."""
    from app.services import viewer_access as va

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(value=va.sign_media_session(current_user.id), **va.media_session_cookie_kwargs(request))
    response.headers["Cache-Control"] = "no-store"
    return response


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def close_media_session(request: Request):
    """Forget the media session (called on logout). Needs no authentication."""
    from app.services import viewer_access as va

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    kw = va.media_session_cookie_kwargs(request)
    response.delete_cookie(kw["key"], path=kw["path"], secure=kw["secure"], httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/file/{user_id}/{filename}")
def serve_media_file(user_id: int, filename: str, request: Request,
                     g: Optional[str] = Query(None, max_length=1024),
                     db: Session = Depends(get_db)):
    """Serve user media from local disk or S3 (production STORAGE_TYPE=s3).

    Child/Teen Safety Phase 7: a file used by any entry that may not go to an
    anonymous viewer (held, under review, age-rated above GENERAL, escalated...)
    is PROTECTED. It is served only when ALL of these hold at request time:
    a valid unexpired grant (?g=) bound to this exact file and to an entry that
    uses it; the REQUESTER is the grant's viewer (media-session cookie or bearer;
    never an id taken from the URL); and the entry decision for that viewer,
    re-run now, allows it. Anything else, including a failed check, is the same
    404 as a missing file. Private KYC files are never served (resolver guard).
    Unprotected files keep historical public delivery.
    """
    from app.services import viewer_access as va

    source, ref, content_type = resolve_media_for_serving(user_id, filename)
    if not source or not ref:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found",
        )

    try:
        protected = va.media_is_protected(db, user_id, filename)
        allowed = (not protected) or va.authorize_protected_media(db, request, user_id, filename, g)
    except Exception:  # noqa: BLE001 - a failed check never serves the file
        logger.warning("protected media check failed; refusing")
        protected, allowed = True, False
    if not allowed:
        # Same answer as a missing file: existence and state are not revealed.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media file not found")

    if protected:
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                   "Content-Disposition": "inline", "Referrer-Policy": "no-referrer",
                   "Vary": "Cookie, Authorization"}
    else:
        headers = {
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "X-Content-Type-Options": "nosniff",
        }

    if source == "local":
        return FileResponse(ref, media_type=content_type, headers=headers)

    bucket = (settings.S3_BUCKET_NAME or settings.AWS_S3_BUCKET or "").strip()
    return StreamingResponse(
        iter_s3_object(bucket, ref),
        media_type=content_type,
        headers=headers,
    )


@router.post("/upload", response_model=Media)
async def upload_media(
    *,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    title: str = None,
    description: str = None,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Upload un nouveau média (image ou vidéo).
    """
    try:
        content_type = file.content_type or ""
        if not content_type.startswith(("image/", "video/")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le fichier doit être une image ou une vidéo",
            )

        media_info = await store_media(file, current_user.id)

        # Ensure the file is actually readable before returning success to the client.
        import os as _os

        _url = media_info.get("url") or ""
        _parts = _url.rstrip("/").split("/")
        if len(_parts) >= 2:
            _filename = _os.path.basename(_parts[-1])
            _src, _ref, _ = await run_in_threadpool(
                resolve_media_for_serving, current_user.id, _filename
            )
            if not _src or not _ref:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Upload saved but file is not available to serve. Check S3/local storage.",
                )

        metadata = media_info.get("metadata") or {}
        media_data = MediaCreate(
            title=title or file.filename or "uploaded-media",
            description=description or "",
            media_type=media_info["media_type"],
            path=media_info["path"],
            url=media_info["url"],
            user_id=current_user.id,
            file_size=metadata.get("file_size"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            metadata_sanitized_at=datetime.utcnow() if metadata.get("metadata_sanitized") else None,
        )
        media = crud_media.create(db=db, obj_in=media_data)
        return media
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Media upload failed",
        )


@router.get("/", response_model=List[Media])
def read_medias(
    *,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer tous les médias de l'utilisateur courant.
    """
    medias = crud_media.get_multi_by_user(
        db=db, user_id=current_user.id, skip=skip, limit=limit
    )
    return medias


@router.get("/{media_id}", response_model=Media)
def read_media(
    *,
    db: Session = Depends(get_db),
    media_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Récupérer un média par ID.
    """
    media = crud_media.get(db=db, id=media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Média non trouvé",
        )
    if media.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante",
        )
    return media


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    *,
    db: Session = Depends(get_db),
    media_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> None:
    """
    Supprimer un média.
    """
    media = crud_media.get(db=db, id=media_id)
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Média non trouvé",
        )
    if media.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante",
        )
    crud_media.remove(db=db, id=media_id)
