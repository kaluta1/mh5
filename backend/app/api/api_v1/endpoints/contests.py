from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_active_user_optional
from app.crud import contest
from app.db.session import get_db
from app.schemas.contest import Contest, ContestCreate, ContestUpdate, ContestWithEntries, ContestWithEnrichedContestants, VotingType
from app.core.cache import cache_service

router = APIRouter()

@router.post("/", response_model=Contest, status_code=status.HTTP_201_CREATED)
def create_contest(
    *,
    db: Session = Depends(get_db),
    contest_in: ContestCreate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Créer un nouveau concours.
    """
    # Seuls les administrateurs peuvent créer des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour créer un concours"
        )
    
    new_contest = contest.create(db=db, obj_in=contest_in)
    
    # Invalider le cache des contests
    cache_service.invalidate_contests()
    
    return new_contest

@router.get("/")
def read_contests(
    *,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    location_id: int = None,
    contest_type: str = None,
    active: bool = Query(None),
    search: str = Query(None, description="Recherche par nom de concours"),
    voting_level: str = Query(None, description="Filtrer par niveau de vote (country pour Nomination)"),
    voting_type_id: int = Query(None, description="Filtrer par ID du type de vote (pour Nominations)"),
    has_voting_type: bool = Query(None, description="Filtrer les contests avec/sans voting_type (True = avec, False = sans)"),
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> List[dict]:
    """
    Récupérer tous les concours avec filtrage optionnel et statistiques.
    Endpoint public - accessible sans authentification.
    Le nombre de contestants affiché dépend de la saison du contest et de la localisation de l'utilisateur connecté (si authentifié).
    """
    # Construire les filtres
    filters = {}
    if location_id:
        filters["location_id"] = location_id
    if contest_type:
        filters["contest_type"] = contest_type
    if active is not None:
        filters["is_active"] = active
    if search:
        filters["search"] = search
    if voting_level:
        filters["voting_level"] = voting_level
    if voting_type_id:
        filters["voting_type_id"] = voting_type_id
    if has_voting_type is not None:
        filters["has_voting_type"] = has_voting_type
    
    # Récupérer les contests depuis la base de données
    contests = contest.get_multi_with_filters(
        db=db, skip=skip, limit=limit, filters=filters
    )
    
    # Enrichir chaque contest avec les statistiques
    # enrich_contest_with_stats retourne un dictionnaire avec toutes les valeurs converties
    enriched_contests = []
    for c in contests:
        try:
            enriched = contest.enrich_contest_with_stats(db=db, contest=c, current_user=current_user)
            if isinstance(enriched, dict):
                enriched_contests.append(enriched)
        except Exception as e:
            # Logger l'erreur mais continuer avec les autres contests
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de l'enrichissement du contest {c.id}: {str(e)}")
            continue
    
    return enriched_contests


@router.get("/{contest_id}", response_model=ContestWithEnrichedContestants)
def read_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> Any:
    """
    Récupérer un concours spécifique avec ses contestants enrichis.
    Le nombre de contestants affiché dépend de la saison du contest et de la localisation de l'utilisateur connecté (si authentifié).
    
    Filtrage géographique basé sur la saison active :
    - city: même ville et pays
    - country: même pays
    - regional: même région
    - continent: même continent
    - global: tous les contestants
    """
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Utiliser la méthode simplifiée qui utilise directement les champs du Contestant
    current_user_id = current_user.id if current_user else None
    enriched_contest = contest.get_contest_with_enriched_contestants(
        db=db, 
        contest_id=contest_id, 
        current_user_id=current_user_id
    )
    
    if not enriched_contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    return enriched_contest


@router.put("/{contest_id}", response_model=Contest)
def update_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    contest_in: ContestUpdate,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Mettre à jour un concours.
    """
    # Seuls les administrateurs peuvent mettre à jour des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour mettre à jour un concours"
        )
    
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    updated_contest = contest.update(db=db, db_obj=contest_obj, obj_in=contest_in)
    
    # Invalider le cache des contests
    cache_service.invalidate_contests()
    
    return updated_contest


@router.delete("/{contest_id}", response_model=Contest)
def delete_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Supprimer un concours (soft delete).
    """
    # Seuls les administrateurs peuvent supprimer des concours
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante pour supprimer un concours"
        )
    
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    deleted_contest = contest.remove(db=db, id=contest_id)
    
    # Invalider le cache des contests
    cache_service.invalidate_contests()
    
    return deleted_contest
