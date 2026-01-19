from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.notification import NotificationResponse, NotificationUnreadCount
from app.crud.crud_notification import crud_notification

router = APIRouter()


@router.get("", response_model=List[NotificationResponse])
def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
) -> List[NotificationResponse]:
    """Récupère les notifications de l'utilisateur connecté"""
    notifications = crud_notification.get_user_notifications(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only
    )
    return notifications


@router.get("/unread-count", response_model=NotificationUnreadCount)
def get_unread_count(
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
) -> NotificationUnreadCount:
    """Récupère le nombre de notifications non lues"""
    count = crud_notification.get_unread_count(db, user_id=current_user.id)
    return NotificationUnreadCount(count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
) -> NotificationResponse:
    """Marque une notification comme lue"""
    notification = crud_notification.mark_as_read(
        db,
        notification_id=notification_id,
        user_id=current_user.id
    )
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification non trouvée"
        )
    
    return notification


@router.patch("/read-all", response_model=dict)
def mark_all_notifications_as_read(
    current_user: User = Depends(deps.get_current_active_user),
    db: Session = Depends(deps.get_db)
) -> dict:
    """Marque toutes les notifications comme lues"""
    count = crud_notification.mark_all_as_read(db, user_id=current_user.id)
    return {"message": f"{count} notification(s) marquée(s) comme lue(s)", "count": count}

