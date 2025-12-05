"""
Endpoints pour les analytics du dashboard utilisateur
"""
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta

from app.api import deps
from app.models.user import User
from app.models.contests import Contestant, ContestSeason
from app.models.voting import Vote, ContestantReaction
from app.models.comment import Comment
from app.schemas.analytics import (
    DashboardAnalytics,
    ContestPerformance,
    ReactionStats,
    WeeklyActivity,
    AffiliatesStats,
    AffiliatesGrowth
)

router = APIRouter()


@router.get("/dashboard", response_model=DashboardAnalytics)
def get_dashboard_analytics(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> Any:
    """
    Récupérer les analytics du dashboard pour l'utilisateur connecté.
    """
    user_id = current_user.id
    
    # Récupérer les candidatures de l'utilisateur
    user_contestants = db.query(Contestant).filter(
        Contestant.user_id == user_id,
        Contestant.is_deleted == False
    ).all()
    
    contestant_ids = [c.id for c in user_contestants]
    
    # Stats globales
    total_votes = 0
    total_comments = 0
    total_views = 0
    total_reactions = 0
    
    if contestant_ids:
        # Compter les votes
        total_votes = db.query(func.count(Vote.id)).filter(
            Vote.contestant_id.in_(contestant_ids)
        ).scalar() or 0
        
        # Compter les commentaires
        total_comments = db.query(func.count(Comment.id)).filter(
            Comment.contestant_id.in_(contestant_ids)
        ).scalar() or 0
        
        # Compter les réactions
        total_reactions = db.query(func.count(ContestantReaction.id)).filter(
            ContestantReaction.contestant_id.in_(contestant_ids)
        ).scalar() or 0
    
    # Performance par concours (basé sur season_id)
    contest_performance = []
    for contestant in user_contestants[:5]:  # Top 5
        # Récupérer le nom de la saison/concours
        season = db.query(ContestSeason).filter(
            ContestSeason.id == contestant.season_id
        ).first()
        
        contest_name = contestant.title or (season.title if season else f"Concours #{contestant.season_id}")
        
        votes = db.query(func.count(Vote.id)).filter(
            Vote.contestant_id == contestant.id
        ).scalar() or 0
        
        comments = db.query(func.count(Comment.id)).filter(
            Comment.contestant_id == contestant.id
        ).scalar() or 0
        
        reactions = db.query(func.count(ContestantReaction.id)).filter(
            ContestantReaction.contestant_id == contestant.id
        ).scalar() or 0
        
        contest_performance.append(ContestPerformance(
            name=contest_name[:20] if contest_name else "Contest",
            votes=votes,
            comments=comments,
            views=0,  # Pas de tracking des vues pour l'instant
            likes=reactions
        ))
    
    # Distribution des réactions par type
    reactions_by_type = []
    reaction_colors = {
        'love': {'name': '❤️ Love', 'color': '#ef4444'},
        'like': {'name': '👍 Like', 'color': '#3b82f6'},
        'wow': {'name': '😍 Wow', 'color': '#ec4899'},
        'bravo': {'name': '👏 Bravo', 'color': '#f59e0b'},
        'fire': {'name': '🔥 Fire', 'color': '#f97316'},
    }
    
    if contestant_ids:
        reaction_counts = db.query(
            ContestantReaction.reaction_type,
            func.count(ContestantReaction.id).label('count')
        ).filter(
            ContestantReaction.contestant_id.in_(contestant_ids)
        ).group_by(ContestantReaction.reaction_type).all()
        
        for reaction_type, count in reaction_counts:
            rt = str(reaction_type.value) if hasattr(reaction_type, 'value') else str(reaction_type)
            config = reaction_colors.get(rt, {'name': rt, 'color': '#6b7280'})
            reactions_by_type.append(ReactionStats(
                name=config['name'],
                value=count,
                color=config['color']
            ))
    
    # Si pas de réactions, ajouter des valeurs par défaut
    if not reactions_by_type:
        for key, config in reaction_colors.items():
            reactions_by_type.append(ReactionStats(
                name=config['name'],
                value=0,
                color=config['color']
            ))
    
    # Activité hebdomadaire
    weekly_activity = []
    today = datetime.utcnow().date()
    days_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())
        
        day_votes = 0
        
        if contestant_ids:
            day_votes = db.query(func.count(Vote.id)).filter(
                Vote.contestant_id.in_(contestant_ids),
                Vote.created_at >= day_start,
                Vote.created_at <= day_end
            ).scalar() or 0
        
        weekly_activity.append(WeeklyActivity(
            day=days_fr[day.weekday()],
            votes=day_votes,
            views=0
        ))
    
    # Stats affiliés - vérifier si le champ referral_code existe
    direct_affiliates = 0
    try:
        if hasattr(User, 'referred_by'):
            direct_affiliates = db.query(func.count(User.id)).filter(
                User.referred_by == user_id
            ).scalar() or 0
    except:
        pass
    
    affiliates_stats = AffiliatesStats(
        direct_count=direct_affiliates,
        total_network=direct_affiliates,
        total_commissions=0.0,
        conversion_rate=0.0
    )
    
    # Croissance des affiliés par mois (6 derniers mois)
    affiliates_growth = []
    months_fr = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
    
    for i in range(5, -1, -1):
        month_date = today - timedelta(days=i*30)
        affiliates_growth.append(AffiliatesGrowth(
            month=months_fr[month_date.month - 1],
            directs=0,
            total=0,
            commissions=0.0
        ))
    
    # Compter les concours actifs
    active_contests = len([c for c in user_contestants if c.is_active])
    
    return DashboardAnalytics(
        total_votes=total_votes,
        total_comments=total_comments,
        total_views=total_views,
        total_reactions=total_reactions,
        votes_change=0.0,
        comments_change=0.0,
        views_change=0.0,
        reactions_change=0.0,
        contest_performance=contest_performance,
        reactions_by_type=reactions_by_type,
        weekly_activity=weekly_activity,
        affiliates_stats=affiliates_stats,
        affiliates_growth=affiliates_growth,
        active_contests=active_contests,
        best_ranking=0,
        engagement_change=0.0
    )
