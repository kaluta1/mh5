from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.search_history import SearchHistory


class CRUDSearchHistory:
    def create(self, db: Session, *, user_id: int, term: str) -> SearchHistory:
        # Normaliser le terme pour éviter les doublons (espaces et casse)
        normalized = " ".join(term.split())
        normalized_lower = normalized.lower()

        existing = (
            db.query(SearchHistory)
            .filter(
                SearchHistory.user_id == user_id,
                func.lower(func.trim(SearchHistory.term)) == normalized_lower,
            )
            .first()
        )

        now = datetime.utcnow()

        if existing:
            # Mettre à jour la date pour remonter cette recherche en tête
            existing.term = normalized
            existing.created_at = now
            existing.updated_at = now
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing

        history = SearchHistory(user_id=user_id, term=normalized, created_at=now, updated_at=now)
        db.add(history)
        db.commit()
        db.refresh(history)
        return history

    def get_by_user(self, db: Session, *, user_id: int, limit: int = 20) -> list[SearchHistory]:
        # Récupérer les entrées les plus récentes puis dédoublonner par terme normalisé
        rows = (
            db.query(SearchHistory)
            .filter(SearchHistory.user_id == user_id)
            .order_by(SearchHistory.created_at.desc())
            .all()
        )

        seen: set[str] = set()
        unique: list[SearchHistory] = []

        for row in rows:
            key = " ".join((row.term or "").split()).lower()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)

        return unique[:limit]


search_history = CRUDSearchHistory()
