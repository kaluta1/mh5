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

@router.get("/", response_model=List[Contest])
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
) -> Any:
    """
    Récupérer tous les concours avec filtrage optionnel et statistiques.
    Endpoint public - accessible sans authentification.
    Cache géré avec Redis (TTL: 1 heure, désactivé si recherche active).
    """
    # Ne pas utiliser le cache si on fait une recherche (pour avoir les résultats à jour)
    use_cache = not search
    
    # Générer la clé de cache
    cache_key = cache_service._make_key(
        "cache:contests:list",
        skip=skip,
        limit=limit,
        location_id=location_id,
        contest_type=contest_type,
        active=active,
        voting_level=voting_level,
        voting_type_id=voting_type_id,
        has_voting_type=has_voting_type
    )
    
    # Vérifier le cache
    if use_cache:
        cached_result = cache_service.get(cache_key)
        if cached_result is not None:
            return cached_result
    
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
    
    contests = contest.get_multi_with_filters(
        db=db, skip=skip, limit=limit, filters=filters
    )
    
    # Enrichir chaque contest avec les statistiques
    enriched_contests = []
    for c in contests:
        # S'assurer que c'est bien un objet Contest SQLAlchemy, pas déjà un dictionnaire
        if isinstance(c, dict):
            # Si c'est déjà un dictionnaire, l'utiliser directement
            enriched = c
        else:
            # Récupérer directement voting_restriction depuis le modèle Contest
            voting_restriction_value = 'none'
            if c.voting_restriction:
                if hasattr(c.voting_restriction, 'value'):
                    voting_restriction_value = c.voting_restriction.value
                elif isinstance(c.voting_restriction, str):
                    voting_restriction_value = c.voting_restriction
                else:
                    voting_restriction_value = str(c.voting_restriction)
            
            # Enrichir avec les stats
            enriched = contest.enrich_contest_with_stats(db=db, contest=c)
            
            # FORCER voting_restriction à être présent avec la valeur du modèle
            # S'assurer que c'est toujours une chaîne de caractères
            enriched['voting_restriction'] = str(voting_restriction_value) if voting_restriction_value else 'none'
        
        # S'assurer que tous les champs requis sont présents
        if 'gender_restriction' not in enriched:
            enriched['gender_restriction'] = None
        
        # Convertir voting_type de dictionnaire à objet VotingType si nécessaire
        if 'voting_type' in enriched and enriched['voting_type'] is not None:
            if isinstance(enriched['voting_type'], dict):
                try:
                    enriched['voting_type'] = VotingType(**enriched['voting_type'])
                except Exception as e:
                    # Si la conversion échoue, mettre à None
                    enriched['voting_type'] = None
            elif not isinstance(enriched['voting_type'], VotingType):
                # Si c'est un objet SQLAlchemy, le convertir en dictionnaire puis en VotingType
                try:
                    vt = enriched['voting_type']
                    voting_type_dict = {
                        "id": vt.id,
                        "name": vt.name,
                        "voting_level": vt.voting_level.value if hasattr(vt.voting_level, 'value') else str(vt.voting_level),
                        "commission_source": vt.commission_source.value if hasattr(vt.commission_source, 'value') else str(vt.commission_source),
                        "commission_rules": vt.commission_rules,
                        "created_at": vt.created_at,
                        "updated_at": vt.updated_at
                    }
                    enriched['voting_type'] = VotingType(**voting_type_dict)
                except Exception as e:
                    enriched['voting_type'] = None
        
        # S'assurer que tous les enums sont convertis en strings
        if 'verification_type' in enriched and enriched['verification_type'] is not None:
            if not isinstance(enriched['verification_type'], str):
                if hasattr(enriched['verification_type'], 'value'):
                    enriched['verification_type'] = enriched['verification_type'].value
                else:
                    enriched['verification_type'] = str(enriched['verification_type'])
        
        if 'participant_type' in enriched and enriched['participant_type'] is not None:
            if not isinstance(enriched['participant_type'], str):
                if hasattr(enriched['participant_type'], 'value'):
                    enriched['participant_type'] = enriched['participant_type'].value
                else:
                    enriched['participant_type'] = str(enriched['participant_type'])
        
        # Créer l'objet Contest à partir du dictionnaire
        try:
            contest_response = Contest(**enriched)
            enriched_contests.append(contest_response)
        except Exception as e:
            # En cas d'erreur, logger et essayer de nettoyer le dictionnaire
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la création de l'objet Contest: {e}")
            logger.error(f"Données enrichies (premiers 500 chars): {str(enriched)[:500]}")
            
            # Nettoyer le dictionnaire en convertissant tous les objets SQLAlchemy en types primitifs
            cleaned_enriched = {}
            for key, value in enriched.items():
                if hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, type(None), dict, list)):
                    # C'est probablement un objet SQLAlchemy, le convertir en string ou None
                    cleaned_enriched[key] = None
                else:
                    cleaned_enriched[key] = value
            
            try:
                contest_response = Contest(**cleaned_enriched)
                enriched_contests.append(contest_response)
            except Exception as e2:
                logger.error(f"Erreur même après nettoyage: {e2}")
                # Dernier recours : retourner un dictionnaire minimal
                enriched_contests.append(cleaned_enriched)
    
    # Stocker dans le cache si activé
    if use_cache:
        cache_service.set(cache_key, enriched_contests, ttl=3600)  # 1 heure
    
    return enriched_contests


@router.get("/{contest_id}", response_model=ContestWithEnrichedContestants)
def read_contest(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    current_user: Optional[Any] = Depends(get_current_active_user_optional),
) -> Any:
    """
    Récupérer un concours par ID avec tous ses contestants enrichis de toutes les informations :
    - Commentaires avec utilisateurs
    - Votes avec utilisateurs
    - Réactions avec utilisateurs
    - Favoris avec utilisateurs
    - Partages avec utilisateurs
    - Saison
    Endpoint public - accessible sans authentification.
    """
    current_user_id = current_user.id if current_user else None
    
    # Récupérer le contest avec tous les contestants enrichis
    enriched_data = contest.get_contest_with_enriched_contestants(
        db=db, 
        contest_id=contest_id,
        current_user_id=current_user_id
    )
    
    if not enriched_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found"
        )
    
    return enriched_data

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
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante"
        )
    contest_obj = contest.update(db=db, db_obj=contest_obj, obj_in=contest_in)
    
    # Invalider le cache des contests
    cache_service.invalidate_contest(contest_id)
    
    return contest_obj

@router.post("/{contest_id}/entry", status_code=status.HTTP_201_CREATED)
def create_contest_entry(
    *,
    db: Session = Depends(get_db),
    contest_id: int,
    media_id: int,
    current_user: Any = Depends(get_current_active_user),
) -> Any:
    """
    Participer à un concours avec un média.
    """
    contest_obj = contest.get(db=db, id=contest_id)
    if not contest_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concours non trouvé"
        )
    
    # Vérifier si les soumissions sont autorisées
    from app.services.contest_status import contest_status_service
    is_allowed, error_message = contest_status_service.check_submission_allowed(db, contest_id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Créer la participation
    result = contest.create_entry(
        db=db, contest_id=contest_id, media_id=media_id, user_id=current_user.id
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
        
    return {"message": "Participation enregistrée avec succès"}
