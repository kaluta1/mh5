from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from app.models.contest import SuggestedContest, SuggestedContestStatus
from app.schemas.contest import SuggestedContestCreate, SuggestedContestUpdate


class CRUDSuggestedContest:
    def get(self, db: Session, id: int) -> Optional[SuggestedContest]:
        """Récupère une suggestion de concours par son ID"""
        return db.query(SuggestedContest).filter(SuggestedContest.id == id).first()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100,
        status: Optional[SuggestedContestStatus] = None,
        category: Optional[str] = None
    ) -> List[SuggestedContest]:
        """Récupère une liste de suggestions de concours avec filtrage optionnel"""
        query = db.query(SuggestedContest)
        
        if status:
            query = query.filter(SuggestedContest.status == status)
        
        if category:
            query = query.filter(SuggestedContest.category == category)
        
        return query.order_by(SuggestedContest.created_at.desc()).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: SuggestedContestCreate) -> SuggestedContest:
        """Crée une nouvelle suggestion de concours"""
        # Convertir le status en enum si nécessaire
        status = obj_in.status
        if isinstance(status, str):
            try:
                status = SuggestedContestStatus(status)
            except ValueError:
                raise ValueError(f"Statut invalide: {status}")

        db_obj = SuggestedContest(
            name=obj_in.name,
            description=obj_in.description,
            category=obj_in.category,
            status=status
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self, db: Session, *, db_obj: SuggestedContest, obj_in: Union[SuggestedContestUpdate, Dict[str, Any]]
    ) -> SuggestedContest:
        """Met à jour une suggestion de concours existante"""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            # Gérer Pydantic v1 et v2
            if hasattr(obj_in, 'model_dump'):
                # Pydantic v2
                update_data = obj_in.model_dump(exclude_unset=True)
            else:
                # Pydantic v1
                update_data = obj_in.dict(exclude_unset=True)

        for field, value in update_data.items():
            if field == 'status' and value is not None:
                if isinstance(value, str):
                    try:
                        value = SuggestedContestStatus(value)
                    except ValueError:
                        raise ValueError(f"Statut invalide: {value}")
            
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> SuggestedContest:
        """Supprime une suggestion de concours"""
        obj = db.query(SuggestedContest).filter(SuggestedContest.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


suggested_contest = CRUDSuggestedContest()

