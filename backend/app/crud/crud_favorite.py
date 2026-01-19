from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.contest import ContestFavorite
from app.models.voting import MyFavorites


class CRUDFavorite:
    """CRUD operations for favorites"""
    
    # Contest Favorites
    def add_contest_favorite(self, db: Session, user_id: int, contest_id: int) -> ContestFavorite:
        """Add a contest to user's favorites"""
        favorite = ContestFavorite(user_id=user_id, contest_id=contest_id)
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        return favorite
    
    def remove_contest_favorite(self, db: Session, user_id: int, contest_id: int) -> bool:
        """Remove a contest from user's favorites"""
        favorite = db.query(ContestFavorite).filter(
            ContestFavorite.user_id == user_id,
            ContestFavorite.contest_id == contest_id
        ).first()
        if favorite:
            db.delete(favorite)
            db.commit()
            return True
        return False
    
    def get_contest_favorites(self, db: Session, user_id: int, skip: int = 0, limit: int = 10) -> List[ContestFavorite]:
        """Get user's favorite contests"""
        return db.query(ContestFavorite).filter(
            ContestFavorite.user_id == user_id
        ).offset(skip).limit(limit).all()
    
    def is_contest_favorite(self, db: Session, user_id: int, contest_id: int) -> bool:
        """Check if a contest is in user's favorites"""
        return db.query(ContestFavorite).filter(
            ContestFavorite.user_id == user_id,
            ContestFavorite.contest_id == contest_id
        ).first() is not None
    
    def get_contest_favorites_count(self, db: Session, user_id: int) -> int:
        """Get count of user's favorite contests"""
        return db.query(ContestFavorite).filter(
            ContestFavorite.user_id == user_id
        ).count()
    
    # Contestant Favorites (MyFavorites)
    def add_contestant_favorite(self, db: Session, user_id: int, contestant_id: int, 
                               contest_type_id: int, stage_id: int, position: int) -> MyFavorites:
        """Add a contestant to user's favorites"""
        favorite = MyFavorites(
            user_id=user_id,
            contestant_id=contestant_id,
            contest_type_id=contest_type_id,
            stage_id=stage_id,
            position=position
        )
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        return favorite
    
    def remove_contestant_favorite(self, db: Session, user_id: int, contestant_id: int) -> bool:
        """Remove a contestant from user's favorites"""
        favorite = db.query(MyFavorites).filter(
            MyFavorites.user_id == user_id,
            MyFavorites.contestant_id == contestant_id
        ).first()
        if favorite:
            db.delete(favorite)
            db.commit()
            return True
        return False
    
    def get_contestant_favorites(self, db: Session, user_id: int, skip: int = 0, limit: int = 10) -> List[MyFavorites]:
        """Get user's favorite contestants sorted by position"""
        return db.query(MyFavorites).filter(
            MyFavorites.user_id == user_id
        ).order_by(MyFavorites.position.asc(), MyFavorites.added_date.desc()).offset(skip).limit(limit).all()
    
    def is_contestant_favorite(self, db: Session, user_id: int, contestant_id: int) -> bool:
        """Check if a contestant is in user's favorites"""
        return db.query(MyFavorites).filter(
            MyFavorites.user_id == user_id,
            MyFavorites.contestant_id == contestant_id
        ).first() is not None


favorite = CRUDFavorite()
