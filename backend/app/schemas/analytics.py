"""
Schemas pour les analytics du dashboard
"""
from typing import List, Optional
from pydantic import BaseModel


class ContestPerformance(BaseModel):
    """Performance d'un contestant par concours"""
    name: str
    votes: int
    comments: int
    views: int
    likes: int


class ReactionStats(BaseModel):
    """Statistiques des réactions par type"""
    name: str
    value: int
    color: str


class WeeklyActivity(BaseModel):
    """Activité quotidienne de la semaine"""
    day: str
    votes: int
    views: int


class AffiliatesStats(BaseModel):
    """Statistiques des affiliés"""
    direct_count: int
    total_network: int
    total_commissions: float
    conversion_rate: float


class AffiliatesGrowth(BaseModel):
    """Croissance mensuelle des affiliés"""
    month: str
    directs: int
    total: int
    commissions: float


class DashboardAnalytics(BaseModel):
    """Données complètes du dashboard analytics"""
    # Stats globales
    total_votes: int
    total_comments: int
    total_views: int
    total_reactions: int
    
    # Changements en pourcentage
    votes_change: float
    comments_change: float
    views_change: float
    reactions_change: float
    
    # Performance par concours
    contest_performance: List[ContestPerformance]
    
    # Réactions par type
    reactions_by_type: List[ReactionStats]
    
    # Activité hebdomadaire
    weekly_activity: List[WeeklyActivity]
    
    # Stats affiliés
    affiliates_stats: AffiliatesStats
    affiliates_growth: List[AffiliatesGrowth]
    
    # Autres stats
    active_contests: int
    best_ranking: int
    engagement_change: float
    
    class Config:
        from_attributes = True
