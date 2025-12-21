from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session

from app.models.contest import VotingType, VotingLevel, CommissionSource
from app.schemas.contest import VotingTypeCreate, VotingTypeUpdate


class CRUDVotingType:
    def get(self, db: Session, id: int) -> Optional[VotingType]:
        """Récupère un type de vote par son ID"""
        return db.query(VotingType).filter(VotingType.id == id).first()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> List[VotingType]:
        """Récupère une liste de types de vote"""
        return db.query(VotingType).offset(skip).limit(limit).all()

    def get_by_level(
        self, db: Session, *, voting_level: VotingLevel
    ) -> List[VotingType]:
        """Récupère les types de vote par niveau"""
        return db.query(VotingType).filter(VotingType.voting_level == voting_level).all()

    def get_by_source(
        self, db: Session, *, commission_source: CommissionSource
    ) -> List[VotingType]:
        """Récupère les types de vote par source de commission"""
        return db.query(VotingType).filter(VotingType.commission_source == commission_source).all()

    def create(self, db: Session, *, obj_in: VotingTypeCreate) -> VotingType:
        """Crée un nouveau type de vote"""
        # Convertir les strings en enums si nécessaire
        voting_level = obj_in.voting_level
        if isinstance(voting_level, str):
            try:
                voting_level = VotingLevel(voting_level)
            except ValueError:
                raise ValueError(f"Niveau de vote invalide: {voting_level}")

        commission_source = obj_in.commission_source
        if isinstance(commission_source, str):
            try:
                commission_source = CommissionSource(commission_source)
            except ValueError:
                raise ValueError(f"Source de commission invalide: {commission_source}")

        db_obj = VotingType(
            name=obj_in.name,
            voting_level=voting_level,
            commission_rules=obj_in.commission_rules,
            commission_source=commission_source
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self, db: Session, *, db_obj: VotingType, obj_in: Union[VotingTypeUpdate, Dict[str, Any]]
    ) -> VotingType:
        """Met à jour un type de vote existant"""
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
            if field == 'voting_level' and value is not None:
                if isinstance(value, str):
                    try:
                        value = VotingLevel(value)
                    except ValueError:
                        raise ValueError(f"Niveau de vote invalide: {value}")
            elif field == 'commission_source' and value is not None:
                if isinstance(value, str):
                    try:
                        value = CommissionSource(value)
                    except ValueError:
                        raise ValueError(f"Source de commission invalide: {value}")
            
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> VotingType:
        """Supprime un type de vote"""
        obj = db.query(VotingType).filter(VotingType.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


voting_type = CRUDVotingType()

