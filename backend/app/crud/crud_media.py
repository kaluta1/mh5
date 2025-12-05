from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from app.models.media import Media
from app.schemas.media import MediaCreate, MediaUpdate


class CRUDMedia:
    def get(self, db: Session, id: int) -> Optional[Media]:
        """Récupère un média par son ID"""
        return db.query(Media).filter(Media.id == id).first()

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Media]:
        """Récupère une liste de médias"""
        return db.query(Media).offset(skip).limit(limit).all()

    def get_multi_by_user(self, db: Session, *, user_id: int, skip: int = 0, limit: int = 100) -> List[Media]:
        """Récupère les médias d'un utilisateur spécifique"""
        return db.query(Media).filter(Media.user_id == user_id).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: MediaCreate) -> Media:
        """Crée un nouveau média"""
        db_obj = Media(
            title=obj_in.title,
            description=obj_in.description,
            media_type=obj_in.media_type,
            path=obj_in.path,
            url=obj_in.url,
            user_id=obj_in.user_id,
            file_size=obj_in.file_size,
            width=obj_in.width,
            height=obj_in.height,
            duration=obj_in.duration
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, *, db_obj: Media, obj_in: Union[MediaUpdate, Dict[str, Any]]) -> Media:
        """Met à jour un média existant"""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
        
        for field in update_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> Media:
        """Supprime un média"""
        obj = db.query(Media).get(id)
        db.delete(obj)
        db.commit()
        return obj


media = CRUDMedia()
