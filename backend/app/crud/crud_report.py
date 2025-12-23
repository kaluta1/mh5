from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.comment import Report
from app.schemas.comment import ContestantReportCreate


class CRUDReport:
    def get(self, db: Session, id: int) -> Optional[Report]:
        """Récupère un signalement par son ID"""
        return db.query(Report).filter(Report.id == id).first()

    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        contestant_id: Optional[int] = None,
        contest_id: Optional[int] = None
    ) -> List[Report]:
        """Récupère plusieurs signalements avec filtres optionnels"""
        query = db.query(Report)
        
        if status:
            query = query.filter(Report.status == status)
        if contestant_id:
            query = query.filter(Report.contestant_id == contestant_id)
        if contest_id:
            query = query.filter(Report.contest_id == contest_id)
        
        return query.offset(skip).limit(limit).all()

    def create_contestant_report(
        self,
        db: Session,
        *,
        obj_in: ContestantReportCreate,
        reporter_id: int
    ) -> Report:
        """Crée un signalement pour un contestant"""
        db_obj = Report(
            reporter_id=reporter_id,
            contestant_id=obj_in.contestant_id,
            contest_id=obj_in.contest_id,
            reason=obj_in.reason,
            description=obj_in.description,
            status="pending"
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: Report,
        obj_in: Union[Dict[str, Any], Report]
    ) -> Report:
        """Met à jour un signalement"""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: int) -> Report:
        """Supprime un signalement"""
        obj = db.query(Report).filter(Report.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def mark_as_reviewed(
        self,
        db: Session,
        *,
        report_id: int,
        reviewer_id: int,
        moderator_notes: Optional[str] = None
    ) -> Report:
        """Marque un signalement comme examiné"""
        from datetime import datetime
        report = self.get(db, id=report_id)
        if not report:
            raise ValueError("Report not found")
        
        report.status = "reviewed"
        report.reviewed_by = reviewer_id
        report.reviewed_at = datetime.utcnow()
        if moderator_notes:
            report.moderator_notes = moderator_notes
        
        db.add(report)
        db.commit()
        db.refresh(report)
        return report


report = CRUDReport()

