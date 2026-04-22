from typing import Any, List
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.crud import media as crud_media
from app.db.session import get_db
from app.schemas.media import MediaCreate, Media
from app.core.storage import store_media

router = APIRouter()

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
        # Vérifier le type de fichier
        content_type = file.content_type or ""
        if not content_type.startswith(('image/', 'video/')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le fichier doit être une image ou une vidéo"
            )

        # Stocker le fichier
        media_info = await store_media(file, current_user.id)

        # Créer l'entrée en base de données
        media_data = MediaCreate(
            title=title or file.filename or "uploaded-media",
            description=description or "",
            media_type=content_type.split('/')[0],
            path=media_info["path"],
            url=media_info["url"],
            user_id=current_user.id
        )
        media = crud_media.create(db=db, obj_in=media_data)
        return media
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Media upload failed: {str(e)}"
        )

@router.get("/", response_model=List[Media])
def read_medias(
    *,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
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
            detail="Média non trouvé"
        )
    if media.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
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
            detail="Média non trouvé"
        )
    if media.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    crud_media.remove(db=db, id=media_id)
