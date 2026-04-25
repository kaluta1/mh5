from typing import List, Optional, Any, Set, Tuple, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Request, Body
import json
import re
from urllib.parse import parse_qs, unquote, urlparse

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.api import deps
from app.crud import contestant as crud_contestant, report
from app.models.user import User
from app.models.contests import Contestant, ContestSubmission, ContestSeason, ContestStage, ContestantSeason, SeasonLevel
from app.models.voting import MyFavorites, Vote, ContestantReaction, ContestantShare, ReactionType, ContestantVoting, ContestLike, ContestComment, PageView
from app.models.contest import Contest
from app.schemas.comment import ContestantReportCreate, ReportResponse
from app.schemas.voting import (
    ReactionCreate, Reaction, ReactionStats, ReactionDetails, ReactionUserDetail,
    VoteDetails, VoteUserDetail,
    FavoriteDetails, FavoriteUserDetail,
    ShareCreate, Share, ShareStats, ShareUserDetail
)
from app.schemas.contestant import (
    ContestantCreate, ContestantResponse, ContestantListResponse, ContestantSubmissionResponse,
    ContestantWithAuthorAndStats
)
from app.services.content_moderation import content_moderation_service, ContentType
from app.services.content_relevance import content_relevance_service

router = APIRouter()


def _resolve_media_url(db: Session, media_ref: Any) -> Optional[str]:
    """Resolve a media reference that can be either a direct URL or a media ID."""
    from app.models.media import Media

    if isinstance(media_ref, str):
        cleaned = media_ref.strip()
        if not cleaned:
            return None
        if cleaned.startswith(("http://", "https://")):
            return cleaned
        try:
            media_id = int(cleaned)
        except ValueError:
            return None
        media = db.query(Media).filter(Media.id == media_id).first()
        return media.url if media else None

    if isinstance(media_ref, int):
        media = db.query(Media).filter(Media.id == media_ref).first()
        return media.url if media else None

    return None


def _clean_video_url(value: str) -> str:
    cleaned = value.strip()
    max_depth = 3

    while max_depth > 0 and cleaned and cleaned[0] in ('[', '"'):
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            break

        if isinstance(parsed, list) and parsed:
            cleaned = str(parsed[0]).strip()
        elif isinstance(parsed, str):
            cleaned = parsed.strip()
        else:
            break
        max_depth -= 1

    match = re.search(r'https?://[^\s"\'<>\[\]]+', cleaned)
    return (match.group(0) if match else cleaned).rstrip("/")


def _normalize_contest_mode(mode: Any) -> str:
    """Normalize contest_mode from enum/string variants to nomination/participation."""
    if mode is None:
        return "participation"

    raw_value = mode.value if hasattr(mode, "value") else mode
    text = str(raw_value).strip().strip('"').strip("'")
    if not text:
        return "participation"

    # Handle values like "ContestMode.NOMINATION"
    token = text.split(".")[-1].strip().lower()
    if token in {"nomination", "participation"}:
        return token

    return "participation"


def _canonicalize_social_media_url(url: str) -> Optional[str]:
    if not url:
        return None

    cleaned = _clean_video_url(url)
    if not cleaned.startswith(("http://", "https://")):
        return None

    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return None

    hostname = (parsed.netloc or "").lower()
    hostname = hostname[4:] if hostname.startswith("www.") else hostname
    path = unquote(parsed.path or "").rstrip("/")
    path_parts = [part for part in path.split("/") if part]
    query = parse_qs(parsed.query)

    if not hostname:
        return None

    if any(domain in hostname for domain in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
        video_id = None
        if hostname == "youtu.be" and path_parts:
            video_id = path_parts[0]
        elif "watch" in path and query.get("v"):
            video_id = query["v"][0]
        else:
            for marker in ("shorts", "embed", "live", "v"):
                if marker in path_parts:
                    index = path_parts.index(marker)
                    if index + 1 < len(path_parts):
                        video_id = path_parts[index + 1]
                        break
        return f"youtube:{video_id}" if video_id else f"youtube:path:{path.lower()}"

    if "tiktok.com" in hostname:
        for marker in ("video", "photo", "t"):
            if marker in path_parts:
                index = path_parts.index(marker)
                if index + 1 < len(path_parts):
                    return f"tiktok:{path_parts[index + 1]}"
        return f"tiktok:path:{path.lower()}"

    if hostname in {"twitter.com", "x.com"}:
        if "status" in path_parts:
            index = path_parts.index("status")
            if index + 1 < len(path_parts):
                return f"x:{path_parts[index + 1]}"
        return f"x:path:{path.lower()}"

    if "instagram.com" in hostname or "instagr.am" in hostname:
        if path_parts:
            if path_parts[0] in {"p", "reel", "reels", "tv"} and len(path_parts) > 1:
                return f"instagram:{path_parts[0]}:{path_parts[1]}"
            return f"instagram:path:{'/'.join(path_parts).lower()}"
        return "instagram:root"

    if hostname in {"facebook.com", "m.facebook.com", "fb.com", "fb.watch"}:
        if hostname == "fb.watch" and path_parts:
            return f"facebook:{path_parts[0]}"
        if query.get("v"):
            return f"facebook:{query['v'][0]}"
        for key in ("story_fbid", "fbid"):
            if query.get(key):
                return f"facebook:{query[key][0]}"
        for marker in ("videos", "reel"):
            if marker in path_parts:
                index = path_parts.index(marker)
                if index + 1 < len(path_parts):
                    return f"facebook:{path_parts[index + 1]}"
        return f"facebook:path:{path.lower()}"

    filtered_query = []
    for key in sorted(query.keys()):
        if key.lower().startswith("utm_"):
            continue
        filtered_query.append(f"{key}={','.join(sorted(query[key]))}")
    query_suffix = f"?{'&'.join(filtered_query)}" if filtered_query else ""
    normalized_path = path.lower() or "/"
    return f"{hostname}{normalized_path}{query_suffix}"


def _extract_canonical_video_urls(db: Session, video_media_ids: Optional[str]) -> Set[str]:
    if not video_media_ids:
        return set()

    try:
        video_refs = json.loads(video_media_ids)
    except json.JSONDecodeError:
        video_refs = [video_media_ids]

    refs_to_process = video_refs if isinstance(video_refs, list) else [video_refs]

    normalized_urls: Set[str] = set()
    while refs_to_process:
        ref = refs_to_process.pop(0)
        if ref is None:
            continue

        if isinstance(ref, list):
            refs_to_process = list(ref) + refs_to_process
            continue

        if isinstance(ref, str):
            stripped_ref = ref.strip()
            if stripped_ref and stripped_ref[0] in ('[', '"'):
                try:
                    nested_ref = json.loads(stripped_ref)
                except json.JSONDecodeError:
                    nested_ref = None
                if nested_ref is not None and nested_ref != ref:
                    refs_to_process.insert(0, nested_ref)
                    continue

        resolved_url = _resolve_media_url(db, ref)
        candidate = resolved_url or str(ref).strip()
        canonical = _canonicalize_social_media_url(candidate)
        if canonical:
            normalized_urls.add(canonical)

    return normalized_urls


def _get_contest_ids_from_season(db: Session, season_id: Optional[int]) -> Set[int]:
    if not season_id:
        return set()

    contest_ids: Set[int] = set()

    direct_contest = db.query(Contest).filter(
        Contest.id == season_id,
        Contest.is_deleted == False
    ).first()
    if direct_contest:
        contest_ids.add(direct_contest.id)

    from app.models.contests import ContestSeasonLink
    linked_ids = db.query(ContestSeasonLink.contest_id).filter(
        ContestSeasonLink.season_id == season_id,
        ContestSeasonLink.is_active == True
    ).all()
    contest_ids.update(contest_id for contest_id, in linked_ids if contest_id is not None)

    return contest_ids


def _get_contest_context_from_season(db: Session, season_id: Optional[int]) -> Set[Tuple[Optional[int], Optional[str]]]:
    if not season_id:
        return set()

    contexts: Set[Tuple[Optional[int], Optional[str]]] = set()

    direct_contest = db.query(Contest).filter(
        Contest.id == season_id,
        Contest.is_deleted == False
    ).first()
    if direct_contest:
        contexts.add((direct_contest.category_id, direct_contest.contest_mode))

    from app.models.contests import ContestSeasonLink
    linked_contests = db.query(Contest).join(
        ContestSeasonLink,
        ContestSeasonLink.contest_id == Contest.id
    ).filter(
        ContestSeasonLink.season_id == season_id,
        ContestSeasonLink.is_active == True,
        Contest.is_deleted == False
    ).all()

    for linked_contest in linked_contests:
        contexts.add((linked_contest.category_id, linked_contest.contest_mode))

    return contexts


def _contestant_belongs_to_contest(
    db: Session,
    contestant: Contestant,
    contest_id: int,
    season: ContestSeason,
) -> bool:
    """
    True if this contestant entry is under ``contest_id`` for the active ``season``.
    Aligns with ``_resolve_contest_for_contestant_vote`` (round ∩ season), and allows
    a single-contest season when ``round_id`` is missing.
    """
    from app.models.contests import ContestSeasonLink
    from app.models.round import Round, round_contests

    # Legacy: Contestant.season_id is often the Contest.id (see model on Contestant).
    # GET /contest/{contest_id} lists rows with Contestant.season_id == contest_id.
    # Do not require ContestSeasonLink for that case — the link row is sometimes missing
    # in migrated data while the contestant row still points at the contest.
    if contestant.season_id is not None and contestant.season_id == contest_id:
        if db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first():
            return True

    link = db.query(ContestSeasonLink).filter(
        ContestSeasonLink.contest_id == contest_id,
        ContestSeasonLink.season_id == season.id,
        ContestSeasonLink.is_active == True,
    ).first()
    if not link:
        return False

    links = (
        db.query(ContestSeasonLink)
        .filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.is_active == True,
        )
        .all()
    )
    season_cids = [L.contest_id for L in links]

    if contestant.round_id is not None:
        rc_rows = db.query(round_contests.c.contest_id).filter(
            round_contests.c.round_id == contestant.round_id
        ).all()
        round_cids = {r[0] for r in rc_rows}
        r_obj = db.query(Round).filter(Round.id == contestant.round_id).first()
        if r_obj and r_obj.contest_id:
            round_cids.add(r_obj.contest_id)
        if contest_id in round_cids and contest_id in season_cids:
            return True

    if len(season_cids) == 1 and season_cids[0] == contest_id:
        return True

    return False


def _resolve_contest_for_contestant_vote(
    db: Session,
    contestant: Contestant,
    season: ContestSeason,
) -> Optional[Contest]:
    """
    Pick the Contest row for this vote. ContestSeason can link to multiple contests
    (different categories). Disambiguate via Contestant.season_id (contest id), then
    intersection of round_contests(round_id) with this season's linked contests — not
    the first arbitrary contest that shares the round.
    """
    from app.models.contests import ContestSeasonLink
    from app.models.round import Round, round_contests

    links = (
        db.query(ContestSeasonLink)
        .filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.is_active == True,
        )
        .all()
    )
    if not links:
        return None

    season_cids = [L.contest_id for L in links]

    # 1) Primary: legacy column Contestant.season_id == contest.id for this contestant
    if contestant.season_id is not None:
        link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.contest_id == contestant.season_id,
            ContestSeasonLink.is_active == True,
        ).first()
        if link:
            contest = db.query(Contest).filter(
                Contest.id == contestant.season_id,
                Contest.is_deleted == False,
            ).first()
            if contest:
                return contest

    # 2) Same calendar round can be linked to several contests — intersect with season
    if contestant.round_id is not None:
        rc_rows = db.query(round_contests.c.contest_id).filter(
            round_contests.c.round_id == contestant.round_id
        ).all()
        round_cids = {r[0] for r in rc_rows}
        r_obj = db.query(Round).filter(Round.id == contestant.round_id).first()
        if r_obj and r_obj.contest_id:
            round_cids.add(r_obj.contest_id)
        inter = [cid for cid in round_cids if cid in season_cids]
        if len(inter) == 1:
            return db.query(Contest).filter(Contest.id == inter[0], Contest.is_deleted == False).first()
        if len(inter) > 1:
            if contestant.season_id in inter:
                return db.query(Contest).filter(
                    Contest.id == contestant.season_id,
                    Contest.is_deleted == False,
                ).first()
            # Ambiguous without explicit contest_id from client — do not guess
            return None

    # 3) Single contest linked to this season — previous behavior
    if len(links) == 1:
        return db.query(Contest).filter(
            Contest.id == links[0].contest_id,
            Contest.is_deleted == False,
        ).first()

    return None


def _bucket_key_for_contest(contest: Contest) -> str:
    """
    Stable MyHigh5 scope for a contest: one bucket per category FK, else (contest_type, contest_mode).
    Must match persisted vote_bucket_key on ContestantVoting rows.
    """
    if contest.category_id is not None:
        return f"cat:{contest.category_id}"
    ct = (contest.contest_type or "").strip()
    cm = (contest.contest_mode or "").strip()
    return f"ty:{ct}:{cm}"


def _bucket_key_for_vote_row(db: Session, vote: ContestantVoting) -> str:
    """Bucket for grouping/display; prefers stored vote_bucket_key, else derives from contest."""
    if getattr(vote, "vote_bucket_key", None):
        return vote.vote_bucket_key
    c = vote.contest
    if c is None and vote.contest_id:
        c = db.query(Contest).filter(Contest.id == vote.contest_id).first()
    if c is None:
        return f"ct:{vote.contest_id}"
    return _bucket_key_for_contest(c)


def _myhigh5_scope_votes_query(
    db: Session,
    *,
    user_id: int,
    season_id: int,
    contest: Contest,
):
    """
    Votes that count toward the 5-slot MyHigh5 cap for this season and category bucket.

    Primary filter: ``vote_bucket_key`` (set at vote time from the contestant's resolved contest).
    Legacy rows with NULL bucket (pre-migration) still match via joined contest fields.
    """
    from sqlalchemy.orm import aliased

    bucket = _bucket_key_for_contest(contest)
    VoteContest = aliased(Contest)
    if contest.category_id is not None:
        legacy_match = VoteContest.category_id == contest.category_id
    else:
        legacy_match = and_(
            VoteContest.contest_type == contest.contest_type,
            VoteContest.contest_mode == contest.contest_mode,
        )
    return (
        db.query(ContestantVoting)
        .join(VoteContest, ContestantVoting.contest_id == VoteContest.id)
        .filter(
            ContestantVoting.user_id == user_id,
            ContestantVoting.season_id == season_id,
            or_(
                ContestantVoting.vote_bucket_key == bucket,
                and_(ContestantVoting.vote_bucket_key.is_(None), legacy_match),
            ),
        )
    )


def _myhigh5_group_key_for_vote(db: Session, vote: ContestantVoting) -> Tuple:
    """One MyHigh5 group per season + persisted bucket key."""
    return (vote.season_id, _bucket_key_for_vote_row(db, vote))


def _labels_for_myhigh5_bucket(db: Session, bucket_key: str, fallback_contest: Optional[Contest]) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    """
    Returns (category_id, category_name, contest_type_label, representative_contest_name).
    """
    category_id_out: Optional[int] = None
    category_name_out: Optional[str] = None
    contest_type_out: Optional[str] = None
    contest_name_out: Optional[str] = None

    if bucket_key.startswith("cat:"):
        rest = bucket_key[4:]
        if rest.isdigit():
            cid = int(rest)
            category_id_out = cid
            from app.models.category import Category

            cat = db.query(Category).filter(Category.id == cid).first()
            category_name_out = cat.name if cat else None
    elif bucket_key.startswith("ty:"):
        parts = bucket_key.split(":", 2)
        contest_type_out = parts[1] if len(parts) > 1 else None
        category_name_out = contest_type_out
    if fallback_contest:
        contest_name_out = fallback_contest.name
        if contest_type_out is None:
            contest_type_out = fallback_contest.contest_type
    return category_id_out, category_name_out, contest_type_out, contest_name_out


def _find_duplicate_video_submission(
    db: Session,
    *,
    video_media_ids: Optional[str],
    target_round_id: Optional[int],
    current_category_id: Optional[int],
    current_contest_mode: Optional[str],
    current_contest_ids: Optional[Set[int]] = None,
    exclude_contestant_id: Optional[int] = None
) -> Optional[Tuple[Contestant, str]]:
    submitted_urls = _extract_canonical_video_urls(db, video_media_ids)
    if not submitted_urls:
        return None

    duplicate_query = db.query(Contestant).filter(
        Contestant.is_deleted == False,
        Contestant.video_media_ids.isnot(None)
    )

    if exclude_contestant_id is not None:
        duplicate_query = duplicate_query.filter(Contestant.id != exclude_contestant_id)

    current_context = (current_category_id, current_contest_mode)
    strict_context_match = current_category_id is not None or current_contest_mode is not None
    normalized_current_contest_ids = current_contest_ids or set()

    for existing_contestant in duplicate_query.all():
        if target_round_id is not None:
            same_round = existing_contestant.round_id == target_round_id

            # Legacy submissions can belong to the same contest but have no stored round_id.
            # In that case, still block duplicates within the same contest/category context.
            if not same_round and existing_contestant.round_id is None and normalized_current_contest_ids:
                existing_contest_ids = _get_contest_ids_from_season(db, existing_contestant.season_id)
                same_round = bool(existing_contest_ids.intersection(normalized_current_contest_ids))

            if not same_round:
                continue

        existing_contexts = _get_contest_context_from_season(db, existing_contestant.season_id)
        if strict_context_match:
            if not existing_contexts or current_context not in existing_contexts:
                continue

        existing_urls = _extract_canonical_video_urls(db, existing_contestant.video_media_ids)
        overlap = submitted_urls.intersection(existing_urls)
        if overlap:
            return existing_contestant, next(iter(overlap))

    return None


# DEBUG ENDPOINT: Test if contestants exist in database
@router.get("/debug/all-contestants")
def debug_get_all_contestants(
    *,
    db: Session = Depends(deps.get_db),
    limit: int = Query(20, ge=1, le=100)
):
    """
    DEBUG: Get all contestants from database (no filters) to verify they exist.
    This endpoint helps diagnose why contestants aren't appearing.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Query ALL non-deleted contestants
        all_contestants = db.query(Contestant).filter(
            Contestant.is_deleted == False
        ).limit(limit).all()
        
        logger.info(f"[DEBUG] Found {len(all_contestants)} total contestants in database")
        
        result = []
        for c in all_contestants:
            result.append({
                "id": c.id,
                "user_id": c.user_id,
                "season_id": c.season_id,
                "round_id": c.round_id,
                "title": c.title,
                "is_deleted": c.is_deleted,
                "registration_date": c.registration_date.isoformat() if c.registration_date else None
            })
            logger.info(f"[DEBUG] Contestant {c.id}: season_id={c.season_id}, round_id={c.round_id}, user_id={c.user_id}")
        
        return {
            "total_found": len(all_contestants),
            "contestants": result,
            "message": f"Found {len(all_contestants)} contestants. Check logs for details."
        }
    except Exception as e:
        logger.error(f"[DEBUG] Error querying contestants: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# Routes spécifiques d'abord (avant les routes génériques avec {id})
# IMPORTANT: Les routes plus spécifiques DOIVENT venir avant les routes générales

@router.get("/user/{user_id}/entries", response_model=List[ContestantWithAuthorAndStats])
def get_user_contestants(
    *,
    db: Session = Depends(deps.get_db),
    user_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
) -> List[ContestantWithAuthorAndStats]:
    """Récupère les candidatures d'un utilisateur spécifique avec stats enrichies"""
    contestants = crud_contestant.get_multi_by_user_with_stats(
        db, user_id, skip=skip, limit=limit
    )
    return contestants


@router.get("/user/my-entries", response_model=List[ContestantWithAuthorAndStats])
def get_my_contestants(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
) -> List[ContestantWithAuthorAndStats]:
    """Récupère les candidatures de l'utilisateur connecté avec stats enrichies"""
    contestants = crud_contestant.get_multi_by_user_with_stats(
        db, current_user.id, skip=skip, limit=limit
    )
    return contestants


@router.get("/user/my-votes")
def get_my_votes(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    season_id: Optional[int] = Query(None, description="Filter by season_id"),
    contest_id: Optional[int] = Query(None, description="Filter by contest_id"),
    include_empty_buckets: bool = Query(
        False,
        description="Include every active contest–season MyHigh5 bucket with no votes yet (for dashboard UI)",
    ),
) -> dict:
    """
    Récupère les votes MyHigh5, groupés par saison + (category_id si défini, sinon
    contest_type + contest_mode). Chaque groupe a au plus 5 votes.

    Ne pas exiger un ContestSeasonLink actif : après migration de saison le lien peut
    être inactif alors que le vote reste valide — sinon les votes disparaissent du dashboard.
    """
    from sqlalchemy.orm import joinedload
    from sqlalchemy import case, func
    from app.models.contests import Contestant, ContestSeasonLink
    from app.models.contest import Contest

    query = db.query(ContestantVoting).options(
        joinedload(ContestantVoting.contestant),
        joinedload(ContestantVoting.season),
        joinedload(ContestantVoting.contest)
    ).filter(
        ContestantVoting.user_id == current_user.id
    )
    
    # Filtrer par season_id si fourni
    if season_id:
        query = query.filter(ContestantVoting.season_id == season_id)

    # Filtrer par contest_id : même bucket MyHigh5 que POST /vote (vote_bucket_key + legacy)
    if contest_id:
        from sqlalchemy.orm import aliased

        scope_contest = (
            db.query(Contest)
            .options(joinedload(Contest.category))
            .filter(Contest.id == contest_id)
            .first()
        )
        if scope_contest:
            VC = aliased(Contest)
            bucket = _bucket_key_for_contest(scope_contest)
            if scope_contest.category_id is not None:
                legacy = VC.category_id == scope_contest.category_id
            else:
                legacy = and_(
                    VC.contest_type == scope_contest.contest_type,
                    VC.contest_mode == scope_contest.contest_mode,
                )
            query = query.join(VC, ContestantVoting.contest_id == VC.id)
            query = query.filter(
                or_(
                    ContestantVoting.vote_bucket_key == bucket,
                    and_(ContestantVoting.vote_bucket_key.is_(None), legacy),
                )
            )
        else:
            query = query.filter(ContestantVoting.contest_id == contest_id)
    
    # Récupérer tous les votes
    all_votes = query.order_by(
        ContestantVoting.season_id,
        # Les votes avec position définie d'abord, triés par position
        # Puis les votes sans position, triés par date
        case(
            (ContestantVoting.position.isnot(None), ContestantVoting.position),
            else_=1000  # Mettre les votes sans position à la fin
        ),
        ContestantVoting.vote_date.asc()
    ).all()
    
    # Grouper par saison + vote_bucket_key (une ligne MyHigh5 par catégorie réelle)
    votes_by_group: dict = {}
    for vote in all_votes:
        key = _myhigh5_group_key_for_vote(db, vote)
        if key not in votes_by_group:
            votes_by_group[key] = []
        votes_by_group[key].append(vote)

    # Buckets actifs sans aucun vote (dashboard : liste toutes les catégories)
    empty_bucket_representative: Dict[Tuple, Contest] = {}
    inject_empty = (
        include_empty_buckets
        and season_id is None
        and contest_id is None
    )
    if inject_empty:
        link_rows = (
            db.query(ContestSeasonLink)
            .options(
                joinedload(ContestSeasonLink.contest),
                joinedload(ContestSeasonLink.season),
            )
            .join(Contest, ContestSeasonLink.contest_id == Contest.id)
            .filter(
                ContestSeasonLink.is_active == True,
                Contest.is_deleted == False,
            )
            .all()
        )
        for link in link_rows:
            s = link.season
            if s is not None and getattr(s, "is_deleted", False):
                continue
            contest = link.contest
            if contest is None:
                continue
            bucket = _bucket_key_for_contest(contest)
            gkey = (link.season_id, bucket)
            if gkey not in votes_by_group:
                votes_by_group[gkey] = []
                empty_bucket_representative[gkey] = contest

    # Précharger contests pour libellés secondaires (évite N+1)
    contest_ids_in_groups = {vote.contest_id for vote in all_votes}
    contests_by_id = {}
    if contest_ids_in_groups:
        loaded = (
            db.query(Contest)
            .options(joinedload(Contest.category))
            .filter(Contest.id.in_(contest_ids_in_groups))
            .all()
        )
        contests_by_id = {c.id: c for c in loaded}

    def _myhigh5_group_sort_key(k: Tuple) -> Tuple:
        season_id_key, bucket_key = k[0], k[1]
        if bucket_key.startswith("cat:"):
            rest = bucket_key[4:]
            cat_name = ""
            if rest.isdigit():
                from app.models.category import Category

                cat = db.query(Category).filter(Category.id == int(rest)).first()
                cat_name = (cat.name or "").lower() if cat else ""
            return (season_id_key, 0, cat_name, bucket_key.lower())
        if bucket_key.startswith("ty:"):
            return (season_id_key, 1, bucket_key.lower(), "")
        return (season_id_key, 2, bucket_key.lower(), "")

    sorted_group_keys = sorted(votes_by_group.keys(), key=_myhigh5_group_sort_key)
    
    # Limiter à 5 votes par groupe et construire le résultat
    result = {
        "seasons": []
    }
    
    for group_key in sorted_group_keys:
        votes = votes_by_group[group_key]
        if not votes:
            contest = empty_bucket_representative.get(group_key)
            if not contest:
                continue
            bucket_key = group_key[1]
            season = db.query(ContestSeason).filter(ContestSeason.id == group_key[0]).first()
            category_id_out, category_name_out, contest_type_out, rep_contest_name = _labels_for_myhigh5_bucket(
                db, bucket_key, contest
            )
            result["seasons"].append({
                "season_id": group_key[0],
                "season_level": season.level if season else None,
                "contest_id": contest.id,
                "contest_name": category_name_out or rep_contest_name or (contest.name if contest else None),
                "category_id": category_id_out,
                "category_name": category_name_out,
                "contest_type": contest_type_out or (contest.contest_type if contest else None),
                "vote_bucket_key": bucket_key,
                "votes": [],
                "votes_count": 0,
                "remaining_slots": 5,
            })
            continue

        # Ordre correct par position dans ce concours (l'ordre global par season_id peut mélanger les concours)
        votes_sorted = sorted(
            votes,
            key=lambda v: (
                v.position if v.position is not None else 1000,
                v.vote_date.timestamp() if v.vote_date else 0.0,
            ),
        )
        # Limiter à 5 votes par concours / saison
        season_votes = votes_sorted[:5]
        
        # Infos saison + libellés depuis le bucket (pas seulement le contest du 1er vote)
        first_vote = season_votes[0]
        season = first_vote.season
        bucket_key = group_key[1]
        contest = contests_by_id.get(first_vote.contest_id) or db.query(Contest).filter(
            Contest.id == first_vote.contest_id
        ).first()
        category_id_out, category_name_out, contest_type_out, rep_contest_name = _labels_for_myhigh5_bucket(
            db, bucket_key, contest
        )

        season_votes_list = []
        for idx, vote in enumerate(season_votes, 1):
            contestant = vote.contestant
            if not contestant:
                continue
                
            # Récupérer l'auteur du contestant
            author = db.query(User).filter(User.id == contestant.user_id).first()
            
            # Compter les votes pour ce contestant
            votes_count = db.query(ContestantVoting).filter(
                ContestantVoting.contestant_id == contestant.id
            ).count()
            
            # Points always follow rank (position): 1→5, 2→4, … (ignore stale stored points)
            position = vote.position if vote.position else idx
            points = (6 - position) if 1 <= position <= 5 else None
            
            c_for_row = contests_by_id.get(vote.contest_id)
            if c_for_row is None and vote.contest_id:
                c_for_row = db.query(Contest).filter(Contest.id == vote.contest_id).first()
                if c_for_row:
                    contests_by_id[vote.contest_id] = c_for_row
            season_votes_list.append({
                "position": position,
                "points": points,
                "contestant_id": contestant.id,
                "contestant_title": contestant.title,
                "contestant_description": contestant.description,
                "author_id": contestant.user_id,
                "author_name": author.full_name if author else None,
                "author_avatar_url": author.avatar_url if author else None,
                "author_country": author.country if author else None,
                "author_city": author.city if author else None,
                "votes_count": votes_count,
                "vote_date": vote.vote_date.isoformat() if vote.vote_date else None,
                "season_id": vote.season_id,
                "contest_id": vote.contest_id,
                "voted_contest_name": c_for_row.name if c_for_row else None,
                "vote_bucket_key": vote.vote_bucket_key if getattr(vote, "vote_bucket_key", None) else bucket_key,
                "season_level": season.level if season else None
            })
        
        season_id_key = group_key[0]
        result["seasons"].append({
            "season_id": season_id_key,
            "season_level": season.level if season else None,
            "contest_id": first_vote.contest_id,
            "contest_name": category_name_out or rep_contest_name or (contest.name if contest else None),
            "category_id": category_id_out,
            "category_name": category_name_out,
            "contest_type": contest_type_out or (contest.contest_type if contest else None),
            "vote_bucket_key": bucket_key,
            "votes": season_votes_list,
            "votes_count": len(season_votes_list),
            "remaining_slots": 5 - len(season_votes_list)
        })

    # Highest vote count first (most active MyHigh5 slots filled), then name for ties
    result["seasons"].sort(
        key=lambda s: (
            -int(s.get("votes_count") or 0),
            (s.get("category_name") or s.get("contest_name") or "").lower(),
        )
    )

    return result


@router.get("/user/my-votes/history")
def get_my_votes_history(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: Optional[int] = Query(None, description="Filter by contest_id")
) -> dict:
    """
    Récupère l'historique complet des votes de l'utilisateur connecté (MyHigh5).
    Retourne tous les votes, y compris ceux des saisons inactives, groupés par contestant et season.
    """
    from sqlalchemy.orm import joinedload
    from sqlalchemy import case
    from app.models.contests import Contestant
    from app.models.contest import Contest
    
    # Construire la requête de base (sans filtre sur is_active)
    query = db.query(ContestantVoting).options(
        joinedload(ContestantVoting.contestant),
        joinedload(ContestantVoting.season),
        joinedload(ContestantVoting.contest)
    ).filter(
        ContestantVoting.user_id == current_user.id
    )
    
    # Filtrer par contest_id (même bucket MyHigh5 que POST /vote)
    if contest_id:
        from sqlalchemy.orm import aliased

        scope_hist = (
            db.query(Contest)
            .options(joinedload(Contest.category))
            .filter(Contest.id == contest_id)
            .first()
        )
        if scope_hist:
            HVC = aliased(Contest)
            bucket = _bucket_key_for_contest(scope_hist)
            if scope_hist.category_id is not None:
                legacy = HVC.category_id == scope_hist.category_id
            else:
                legacy = and_(
                    HVC.contest_type == scope_hist.contest_type,
                    HVC.contest_mode == scope_hist.contest_mode,
                )
            query = query.join(HVC, ContestantVoting.contest_id == HVC.id)
            query = query.filter(
                or_(
                    ContestantVoting.vote_bucket_key == bucket,
                    and_(ContestantVoting.vote_bucket_key.is_(None), legacy),
                )
            )
        else:
            query = query.filter(ContestantVoting.contest_id == contest_id)
    
    # Récupérer tous les votes, triés par bucket, season, position/date
    all_votes = query.order_by(
        ContestantVoting.vote_bucket_key,
        ContestantVoting.season_id,
        # Les votes avec position définie d'abord, triés par position
        # Puis les votes sans position, triés par date
        case(
            (ContestantVoting.position.isnot(None), ContestantVoting.position),
            else_=1000
        ),
        ContestantVoting.vote_date.asc()
    ).all()
    
    # Grouper par vote_bucket_key (catégorie MyHigh5), puis par season_id
    votes_by_bucket: dict = {}
    for vote in all_votes:
        bk = _bucket_key_for_vote_row(db, vote)
        if bk not in votes_by_bucket:
            votes_by_bucket[bk] = {}
        if vote.season_id not in votes_by_bucket[bk]:
            votes_by_bucket[bk][vote.season_id] = []
        votes_by_bucket[bk][vote.season_id].append(vote)
    
    # Construire le résultat groupé par bucket puis saison
    result = {
        "history": []
    }
    
    for bucket_key in sorted(votes_by_bucket.keys()):
        seasons = votes_by_bucket[bucket_key]
        first_vote_any = None
        for _sid, vlist in seasons.items():
            if vlist:
                first_vote_any = vlist[0]
                break
        if not first_vote_any:
            continue
        contest = (
            db.query(Contest)
            .options(joinedload(Contest.category))
            .filter(Contest.id == first_vote_any.contest_id)
            .first()
        )
        cid_out, cname_out, ctype_out, rep_name = _labels_for_myhigh5_bucket(db, bucket_key, contest)
        
        contest_data = {
            "vote_bucket_key": bucket_key,
            "contest_id": first_vote_any.contest_id,
            "contest_name": cname_out or rep_name or (contest.name if contest else None),
            "category_id": cid_out,
            "category_name": cname_out,
            "contest_type": ctype_out or (contest.contest_type if contest else None),
            "seasons": []
        }
        
        for season_id_key, votes in seasons.items():
            # Limiter à 5 votes par season pour l'affichage
            season_votes = votes[:5]
            
            if not season_votes:
                continue
            
            first_vote = season_votes[0]
            season = first_vote.season
            
            # Vérifier si la saison est active
            from app.models.contests import ContestSeasonLink
            season_link = db.query(ContestSeasonLink).filter(
                ContestSeasonLink.contest_id == first_vote.contest_id,
                ContestSeasonLink.season_id == season_id_key
            ).first()
            is_active = season_link.is_active if season_link else False
            
            season_votes_list = []
            for idx, vote in enumerate(season_votes, 1):
                contestant = vote.contestant
                if not contestant:
                    continue
                    
                # Récupérer l'auteur du contestant
                author = db.query(User).filter(User.id == contestant.user_id).first()
                
                # Compter les votes pour ce contestant
                votes_count = db.query(ContestantVoting).filter(
                    ContestantVoting.contestant_id == contestant.id
                ).count()
                
                # Points always follow rank (position): 1→5, 2→4, … (ignore stale stored points)
                position = vote.position if vote.position else idx
                points = (6 - position) if 1 <= position <= 5 else None
                
                season_votes_list.append({
                    "position": position,
                    "points": points,
                    "contestant_id": contestant.id,
                    "contestant_title": contestant.title,
                    "contestant_description": contestant.description,
                    "author_id": contestant.user_id,
                    "author_name": author.full_name if author else None,
                    "author_avatar_url": author.avatar_url if author else None,
                    "author_country": author.country if author else None,
                    "author_city": author.city if author else None,
                    "votes_count": votes_count,
                    "vote_date": vote.vote_date.isoformat() if vote.vote_date else None,
                    "season_id": vote.season_id,
                    "contest_id": vote.contest_id,
                    "season_level": season.level if season else None
                })
            
            contest_data["seasons"].append({
                "season_id": season_id_key,
                "season_level": season.level if season else None,
                "is_active": is_active,
                "votes": season_votes_list,
                "votes_count": len(season_votes_list)
            })
        
        result["history"].append(contest_data)
    
    return result


@router.put("/user/my-votes/reorder")
def reorder_my_votes(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    data: dict
) -> dict:
    """
    Réordonne les votes MyHigh5 de l'utilisateur pour une season et un bucket catégorie.
    Le 1er reçoit 5 points, le 2ème 4 points, le 3ème 3 points, etc.
    """
    votes_to_reorder = data.get("votes", [])
    season_id = data.get("season_id")
    contest_id = data.get("contest_id")
    
    if not votes_to_reorder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No votes to reorder"
        )
    
    if not season_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="season_id is required"
        )
    
    if len(votes_to_reorder) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 votes allowed per MyHigh5 category for this season"
        )
    
    # Vérifier que tous les votes appartiennent à l'utilisateur et à la même season (+ contest si fourni)
    contestant_ids = [v["contestant_id"] for v in votes_to_reorder]
    
    from sqlalchemy.orm import aliased

    uv_q = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == current_user.id,
        ContestantVoting.contestant_id.in_(contestant_ids),
        ContestantVoting.season_id == season_id,
    )
    if contest_id is not None:
        scope_c = db.query(Contest).filter(Contest.id == contest_id).first()
        if not scope_c:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contest not found",
            )
        bucket = _bucket_key_for_contest(scope_c)
        VC = aliased(Contest)
        if scope_c.category_id is not None:
            legacy = VC.category_id == scope_c.category_id
        else:
            legacy = and_(
                VC.contest_type == scope_c.contest_type,
                VC.contest_mode == scope_c.contest_mode,
            )
        uv_q = uv_q.join(VC, ContestantVoting.contest_id == VC.id)
        uv_q = uv_q.filter(
            or_(
                ContestantVoting.vote_bucket_key == bucket,
                and_(ContestantVoting.vote_bucket_key.is_(None), legacy),
            )
        )
    user_votes = uv_q.all()

    _buckets = {_bucket_key_for_vote_row(db, v) for v in user_votes}
    if len(_buckets) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Votes span multiple MyHigh5 categories; pass contest_id to identify the category bucket.",
        )
    
    user_vote_contestant_ids = {vote.contestant_id for vote in user_votes}
    
    for contestant_id in contestant_ids:
        if contestant_id not in user_vote_contestant_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Vote for contestant {contestant_id} not found in season {season_id}"
            )
    
    # Mettre à jour les positions et les points
    # Points: position 1 = 5 points, position 2 = 4 points, etc.
    for vote_data in votes_to_reorder:
        contestant_id = vote_data["contestant_id"]
        new_position = vote_data["position"]
        
        # Calculer les points selon la position (1->5, 2->4, 3->3, 4->2, 5->1)
        new_points = 6 - new_position if 1 <= new_position <= 5 else None
        
        # Trouver le vote correspondant et mettre à jour sa position et ses points
        for vote in user_votes:
            if vote.contestant_id == contestant_id:
                vote.position = new_position
                vote.points = new_points
                break
    
    db.commit()
    
    return {
        "message": "Votes reordered successfully",
        "count": len(votes_to_reorder),
        "season_id": season_id,
        "contest_id": contest_id,
    }


# IMPORTANT: Cette route DOIT venir avant /contest/{contest_id}
@router.get("/favorites")
def get_user_favorites(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user)
) -> List[int]:
    """Récupère les IDs des contestants en favoris de l'utilisateur"""
    favorites = db.query(MyFavorites.contestant_id).filter(
        MyFavorites.user_id == current_user.id
    ).all()
    
    return [fav[0] for fav in favorites]


# IMPORTANT: Cette route DOIT venir avant /contest/{contest_id}
@router.get("/leaderboard/contest/{contest_id}", response_model=List[ContestantListResponse])
def get_contest_leaderboard(
    *,
    db: Session = Depends(deps.get_db),
    contest_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
) -> List[ContestantListResponse]:
    """Récupère le classement d'un concours"""
    # Vérifier que la saison existe
    season = db.query(ContestSeason).filter(ContestSeason.id == contest_id).first()
    if not season:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found"
        )
    
    contestants = crud_contestant.get_leaderboard(
        db, contest_id, skip=skip, limit=limit
    )
    
    result = []
    for rank, contestant in enumerate(contestants, 1):
        result.append(ContestantListResponse(
            id=contestant.id,
            user_id=contestant.user_id,
            season_id=contestant.season_id,
            title=contestant.title,
            description=contestant.description,
            registration_date=contestant.registration_date,
            is_qualified=contestant.is_qualified
        ))
    
    return result


@router.get("/contest/{contest_id}", response_model=List[ContestantWithAuthorAndStats])
def get_contest_contestants(
    *,
    db: Session = Depends(deps.get_db),
    contest_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    filter_country: str = Query(None, description="Filtrer par pays"),
    filter_region: str = Query(None, description="Filtrer par région"),
    filter_continent: str = Query(None, description="Filtrer par continent"),
    filter_city: str = Query(None, description="Filtrer par ville"),
    user_id: Optional[int] = Query(None, description="Filtrer par user_id"),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional)
) -> List[ContestantWithAuthorAndStats]:
    """
    Récupère les candidatures d'un concours avec stats enrichies.
    
    Paramètres de filtrage géographique:
    - filter_country: Affiche uniquement les contestants de ce pays
    - filter_region: Affiche uniquement les contestants de cette région  
    - filter_continent: Affiche uniquement les contestants de ce continent
    - filter_city: Affiche uniquement les contestants de cette ville
    - user_id: Affiche uniquement les contestants de cet utilisateur
    """
    # IMPORTANT: this route is called with Contest.id from frontend.
    # Resolve Contest first to avoid collisions with ContestSeason.id values.
    from app.models.contest import Contest as MyfavContest
    contest = db.query(MyfavContest).filter(
        MyfavContest.id == contest_id,
        MyfavContest.is_deleted == False
    ).first()

    season = None
    real_contest_id = None
    if contest:
        real_contest_id = contest.id
    else:
        season = db.query(ContestSeason).filter(
            ContestSeason.id == contest_id,
            ContestSeason.is_deleted == False
        ).first()
        if not season:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contest not found"
            )
        from app.models.contests import ContestSeasonLink
        link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season.id,
            ContestSeasonLink.is_active == True
        ).first()
        if link:
            real_contest_id = link.contest_id
        else:
            # Legacy fallback: keep provided id if no active link exists.
            real_contest_id = contest_id
    
    # FIXED: Simplified query to avoid database errors and 503 responses
    from app.models.round import Round
    from app.models.round import round_contests
    from app.models.contests import Contestant
    from sqlalchemy import or_, func
    from sqlalchemy.orm import joinedload
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Step 1: Find round IDs linked to this contest (simplified approach)
        all_round_ids = []
        
        try:
            # Method 1: Via round_contests table
            round_ids_via_table = db.query(round_contests.c.round_id).filter(
                round_contests.c.contest_id == real_contest_id
            ).all()
            if round_ids_via_table:
                all_round_ids.extend([r[0] for r in round_ids_via_table])
        except Exception as e:
            logger.warning(f"Error querying round_contests: {e}")
        
        try:
            # Method 2: Via legacy round.contest_id
            legacy_rounds = db.query(Round.id).filter(Round.contest_id == real_contest_id).all()
            if legacy_rounds:
                all_round_ids.extend([r[0] for r in legacy_rounds])
        except Exception as e:
            logger.warning(f"Error querying legacy rounds: {e}")
        
        # Remove duplicates
        all_round_ids = list(set(all_round_ids))
        
        # DEBUG: First check if ANY contestants exist for this contest (without filters)
        debug_query = db.query(
            Contestant.id,
            Contestant.season_id,
            Contestant.round_id,
            Contestant.is_deleted
        ).filter(Contestant.is_deleted == False)
        
        # Try to find contestants by ANY possible link
        debug_conditions = []
        if all_round_ids:
            debug_conditions.append(Contestant.round_id.in_(all_round_ids))
        debug_conditions.append(Contestant.season_id == real_contest_id)
        
        if debug_conditions:
            debug_results = debug_query.filter(or_(*debug_conditions)).limit(10).all()
            logger.info(f"[DEBUG] Found {len(debug_results)} contestants matching contest_id={contest_id}, round_ids={all_round_ids}")
            for d in debug_results:
                logger.info(f"[DEBUG] Contestant id={d.id}, season_id={d.season_id}, round_id={d.round_id}")
        else:
            # If no conditions, check ALL non-deleted contestants to see what exists
            all_contestants_sample = db.query(
                Contestant.id,
                Contestant.season_id,
                Contestant.round_id
            ).filter(Contestant.is_deleted == False).limit(20).all()
            logger.warning(f"[DEBUG] No round_ids found. Sample of all contestants: {[(c.id, c.season_id, c.round_id) for c in all_contestants_sample]}")
        
        # Step 2: Build simplified query - try season_id first (most common)
        query = db.query(Contestant).filter(Contestant.is_deleted == False)
        
        # Filter by season_id only (round_id is shared between ALL contests)
        query = query.filter(Contestant.season_id == real_contest_id)
        
        # Apply geographic filters
        if filter_country:
            query = query.filter(func.lower(Contestant.country) == func.lower(filter_country))
        if filter_region:
            query = query.filter(func.lower(Contestant.region) == func.lower(filter_region))
        if filter_continent:
            query = query.filter(func.lower(Contestant.continent) == func.lower(filter_continent))
        if filter_city:
            query = query.filter(func.lower(Contestant.city) == func.lower(filter_city))
        if user_id:
            query = query.filter(Contestant.user_id == user_id)
        
        # Get contestants with relations (limit joins to avoid timeouts)
        # Note: We'll sort by votes after fetching stats, but order by registration_date as fallback
        try:
            contestants = query.options(
                joinedload(Contestant.user)
            ).order_by(Contestant.registration_date.desc()).offset(skip).limit(limit * 2).all()  # Fetch more to sort properly
        except Exception as e:
            logger.error(f"Error fetching contestants with relations: {e}")
            # Fallback: fetch without relations
            contestants = query.order_by(Contestant.registration_date.desc()).offset(skip).limit(limit * 2).all()
        
        # If no contestants found, try simpler fallback
        if not contestants:
            logger.warning(f"[get_contest_contestants] No contestants found with filters. Trying fallback queries...")
            
            # Fallback 1: Try by season_id only (no geographic filters)
            try:
                fallback1 = db.query(Contestant).filter(
                    Contestant.is_deleted == False,
                    Contestant.season_id == real_contest_id
                ).limit(limit).all()
                logger.info(f"[get_contest_contestants] Fallback 1 (season_id only): Found {len(fallback1)} contestants")
                if fallback1:
                    contestants = fallback1
            except Exception as e:
                logger.error(f"Error in fallback 1: {e}")
            

            

            
            # Apply geographic filters to fallback results if we found any
            if contestants and (filter_country or filter_region or filter_continent or filter_city):
                original_count = len(contestants)
                if filter_country:
                    contestants = [c for c in contestants if c.country and func.lower(c.country) == func.lower(filter_country)]
                if filter_region:
                    contestants = [c for c in contestants if c.region and func.lower(c.region) == func.lower(filter_region)]
                if filter_continent:
                    contestants = [c for c in contestants if c.continent and func.lower(c.continent) == func.lower(filter_continent)]
                if filter_city:
                    contestants = [c for c in contestants if c.city and func.lower(c.city) == func.lower(filter_city)]
                logger.info(f"[get_contest_contestants] After geographic filters: {len(contestants)}/{original_count} contestants remain")
            
            # Apply user_id filter if specified
            if contestants and user_id:
                contestants = [c for c in contestants if c.user_id == user_id]
            
            # Load user relations for fallback results
            if contestants:
                contestant_ids = [c.id for c in contestants]
                contestants_with_users = db.query(Contestant).filter(
                    Contestant.id.in_(contestant_ids)
                ).options(joinedload(Contestant.user)).all()
                contestants = contestants_with_users
        
        # Enrich contestants with stats (with error handling)
        contestant_ids = [c.id for c in contestants] if contestants else []
        
        if not contestant_ids:
            return []
        
        # Initialize stats dictionaries
        votes_by_contestant = {}
        favorites_by_contestant = {}
        reactions_by_contestant = {}
        comments_by_contestant = {}
        
        # Get stats with error handling for each query
        try:
            from app.models.voting import Vote, ContestLike, ContestComment
            
            votes_results = db.query(Vote.contestant_id, func.count(Vote.id))\
                .filter(Vote.contestant_id.in_(contestant_ids))\
                .group_by(Vote.contestant_id).all()
            votes_by_contestant = {cid: count for cid, count in votes_results}
        except Exception as e:
            logger.warning(f"Error fetching votes: {e}")
        
        try:
            fav_results = db.query(MyFavorites.contestant_id, func.count(MyFavorites.id))\
                .filter(MyFavorites.contestant_id.in_(contestant_ids))\
                .group_by(MyFavorites.contestant_id).all()
            favorites_by_contestant = {cid: count for cid, count in fav_results}
        except Exception as e:
            logger.warning(f"Error fetching favorites: {e}")
        
        try:
            like_results = db.query(ContestLike.contestant_id, func.count(ContestLike.id))\
                .filter(ContestLike.contestant_id.in_(contestant_ids))\
                .group_by(ContestLike.contestant_id).all()
            reactions_by_contestant = {cid: count for cid, count in like_results}
        except Exception as e:
            logger.warning(f"Error fetching reactions: {e}")
        
        try:
            comment_results = db.query(ContestComment.contestant_id, func.count(ContestComment.id))\
                .filter(ContestComment.contestant_id.in_(contestant_ids))\
                .group_by(ContestComment.contestant_id).all()
            comments_by_contestant = {cid: count for cid, count in comment_results}
        except Exception as e:
            logger.warning(f"Error fetching comments: {e}")
        
        # Calculate ranks
        ranked_contestants = sorted(
            [(c.id, votes_by_contestant.get(c.id, 0)) for c in contestants],
            key=lambda x: x[1],
            reverse=True
        )
        ranks = {cid: rank + 1 for rank, (cid, _) in enumerate(ranked_contestants)}
        
        # Check user votes: legacy Vote + MyHigh5 ContestantVoting (same contest scope)
        user_votes = set()
        current_user_id = current_user.id if current_user else None
        if current_user_id:
            try:
                from app.models.voting import Vote, ContestantVoting
                user_votes_list = db.query(Vote.contestant_id)\
                    .filter(Vote.voter_id == current_user_id, Vote.contestant_id.in_(contestant_ids))\
                    .all()
                user_votes = {row[0] for row in user_votes_list}
                cv_rows = db.query(ContestantVoting.contestant_id).filter(
                    ContestantVoting.user_id == current_user_id,
                    ContestantVoting.contest_id == real_contest_id,
                    ContestantVoting.contestant_id.in_(contestant_ids),
                ).all()
                user_votes.update(row[0] for row in cv_rows)
            except Exception as e:
                logger.warning(f"Error fetching user votes: {e}")
        
        # Build enriched response
        import json
        contestants_data = []
        for contestant in contestants:
            # Count images and videos
            images_count = 0
            videos_count = 0
            if contestant.image_media_ids:
                try:
                    images_count = len(json.loads(contestant.image_media_ids))
                except (json.JSONDecodeError, TypeError):
                    images_count = 0
            if contestant.video_media_ids:
                try:
                    videos_count = len(json.loads(contestant.video_media_ids))
                except (json.JSONDecodeError, TypeError):
                    videos_count = 0
            
            can_vote = False
            if current_user_id and current_user_id != contestant.user_id:
                can_vote = contestant.id not in user_votes
            
            contestants_data.append({
                "id": contestant.id,
                "user_id": contestant.user_id,
                "season_id": contestant.season_id,
                "round_id": contestant.round_id,
                "entry_type": getattr(contestant, "entry_type", "participation"),
                "title": contestant.title,
                "description": contestant.description,
                "image_media_ids": contestant.image_media_ids,
                "video_media_ids": contestant.video_media_ids,
                "nominator_city": contestant.nominator_city,
                "nominator_country": contestant.nominator_country,
                "registration_date": contestant.registration_date,
                "is_qualified": contestant.is_qualified,
                "author_name": contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip() if contestant.user else None,
                "author_country": contestant.user.country if contestant.user else None,
                "author_city": contestant.user.city if contestant.user else None,
                "author_continent": contestant.user.continent if contestant.user else None,
                "author_region": contestant.user.region if contestant.user else None,
                "author_avatar_url": contestant.user.avatar_url if contestant.user else None,
                "country": contestant.country,
                "city": contestant.city,
                "continent": contestant.continent,
                "region": contestant.region,
                "rank": ranks.get(contestant.id),
                "votes_count": votes_by_contestant.get(contestant.id, 0),
                "images_count": images_count,
                "videos_count": videos_count,
                "favorites_count": favorites_by_contestant.get(contestant.id, 0),
                "reactions_count": reactions_by_contestant.get(contestant.id, 0),
                "comments_count": comments_by_contestant.get(contestant.id, 0),
                "has_voted": contestant.id in user_votes,
                "can_vote": can_vote,
            })
        
        # Sort by votes descending first (most votes first), then by rank
        # This ensures contestants with most participants/votes appear at top immediately
        contestants_data.sort(key=lambda x: (
            -x["votes_count"],  # Votes first (descending - most votes first)
            x.get("rank", float('inf'))  # Then by rank (lower is better)
        ))
        
        # Log pour vérifier les données
        if contestants_data and len(contestants_data) > 0:
            first_contestant = contestants_data[0]
            print(f"[ContestantEndpoint] First contestant data: id={first_contestant.get('id')}, image_media_ids={first_contestant.get('image_media_ids')}, video_media_ids={first_contestant.get('video_media_ids')}")
        
    except Exception as e:
        import traceback
        logger.error(f"[ContestantEndpoint] ERROR fetching contestants for contest {contest_id}: {str(e)}")
        logger.error(traceback.format_exc())
        # Return empty array instead of raising exception to prevent network errors
        # This allows the frontend to handle gracefully
        return []
    
    # Convertir en schéma Pydantic
    try:
        result = [ContestantWithAuthorAndStats(**data) for data in contestants_data]
    except Exception as e:
        logger.error(f"[ContestantEndpoint] ERROR serializing contestants: {str(e)}")
        # Return empty array if serialization fails
        return []
    
    return result


# Routes génériques après les routes spécifiques

@router.post("/{contest_id}", response_model=ContestantSubmissionResponse)
def create_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contest_id: int,
    contestant_data: ContestantCreate
) -> ContestantSubmissionResponse:
    """
    Créer une nouvelle candidature pour un concours
    
    - Prend le contest_id depuis l'URL (peut être Contest.id ou ContestSeason.id)
    - Vérifie que le concours existe
    - Vérifie que l'utilisateur n'a pas déjà une candidature
    - Vérifie que les soumissions sont ouvertes (pas de soumission si le vote est ouvert)
    - Crée la candidature avec titre, description et médias
    """
    from app.services.contest_status import contest_status_service
    
    # IMPORTANT: route /contests/{contest_id}/participate receives Contest.id from frontend.
    # We must resolve Contest first to avoid accidental collisions with ContestSeason IDs.
    contest = None
    season = None
    from app.models.contest import Contest as MyfavContest
    contest = db.query(MyfavContest).filter(
        MyfavContest.id == contest_id,
        MyfavContest.is_deleted == False
    ).first()

    if contest:
        # Canonical storage: Contestant.season_id stores contest.id in this codebase
        season_id = contest.id
        is_allowed, error_message = contest_status_service.check_submission_allowed(db, contest.id)
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
    else:
        # Fallback legacy path: allow ContestSeason id only when no contest matches.
        season = db.query(ContestSeason).filter(
            ContestSeason.id == contest_id,
            ContestSeason.is_deleted == False
        ).first()
        if not season:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contest not found"
            )

        season_id = season.id
        # Si c'est une saison, vérifier si elle est liée à un contest
        from app.models.contests import ContestSeasonLink
        contest_link = db.query(ContestSeasonLink).filter(
            ContestSeasonLink.season_id == season_id,
            ContestSeasonLink.is_active == True
        ).first()
        if contest_link:
            contest = db.query(MyfavContest).filter(
                MyfavContest.id == contest_link.contest_id,
                MyfavContest.is_deleted == False
            ).first()
            if contest:
                is_allowed, error_message = contest_status_service.check_submission_allowed(db, contest.id)
                if not is_allowed:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=error_message
                    )
    
    # Vérifier les restrictions de genre si le contest existe
    if contest:
        # Récupérer la restriction de genre (peut venir de gender_restriction ou voting_restriction)
        gender_restriction = contest.gender_restriction
        
        # Si pas de gender_restriction directe, vérifier voting_restriction
        if not gender_restriction and hasattr(contest, 'voting_restriction') and contest.voting_restriction:
            # Accéder à la valeur de l'enum de manière sécurisée
            voting_restriction_value = contest.voting_restriction.value if hasattr(contest.voting_restriction, 'value') else str(contest.voting_restriction)
            voting_restriction_str = voting_restriction_value.lower().strip()
            
            # MALE_ONLY signifie que seuls les hommes peuvent participer
            if voting_restriction_str == 'male_only':
                gender_restriction = 'male'
            # FEMALE_ONLY signifie que seules les femmes peuvent participer
            elif voting_restriction_str == 'female_only':
                gender_restriction = 'female'
        
        # Vérifier si l'utilisateur respecte la restriction de genre pour participer
        if gender_restriction:
            if not current_user.gender:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Your profile does not contain gender information. Please complete your profile to participate in this contest."
                )
            
            # Récupérer le genre de l'utilisateur de manière sécurisée
            user_gender = current_user.gender.value.lower() if hasattr(current_user.gender, 'value') else str(current_user.gender).lower()
            gender_restriction_lower = gender_restriction.lower()
            
            # Vérifier la correspondance : si le contest est MALE_ONLY, seuls les hommes peuvent participer
            # Si le contest est FEMALE_ONLY, seules les femmes peuvent participer
            if gender_restriction_lower == 'male' and user_gender != 'male':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for male participants only."
                )
            elif gender_restriction_lower == 'female' and user_gender != 'female':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for female participants only."
                )
    
    # Determine the target round before checking participation
    target_round_id = contestant_data.round_id
    from app.models.round import Round
    
    # Extract real_contest_id needed for validations
    real_contest_id = contest.id if hasattr(contest, "id") and contest else contest_id
    if not contest and season:
        from app.models.contests import ContestSeasonLink
        link = db.query(ContestSeasonLink).filter(ContestSeasonLink.season_id == season.id, ContestSeasonLink.is_active == True).first()
        if link:
            real_contest_id = link.contest_id
            
    if target_round_id:
        round_obj = db.query(Round).filter(Round.id == target_round_id).first()
        if not round_obj:
            raise HTTPException(status_code=404, detail="Round id not found")
            
        # The round might belong directly to the contest we found (via legacy contest_id OR via round_contests N:N table).
        # Check both the legacy column and the many-to-many relationship.
        from app.models.round import round_contests
        round_belongs_to_contest = False
        
        if real_contest_id:
            # Check legacy contest_id column
            if round_obj.contest_id == real_contest_id:
                round_belongs_to_contest = True
            else:
                # Check N:N round_contests association table
                nn_link = db.query(round_contests).filter(
                    round_contests.c.round_id == target_round_id,
                    round_contests.c.contest_id == real_contest_id
                ).first()
                if nn_link:
                    round_belongs_to_contest = True
        
        if real_contest_id and not round_belongs_to_contest:
            # Maybe the user participated directly with the season ID in the URL, verify it matches
            if season and not contest:
                link = db.query(ContestSeasonLink).filter(
                    ContestSeasonLink.season_id == season.id, 
                    ContestSeasonLink.contest_id == round_obj.contest_id,
                    ContestSeasonLink.is_active == True
                ).first()
                if not link:
                    # Also check via round_contests N:N table
                    for rc_contest_id_row in db.query(round_contests.c.contest_id).filter(round_contests.c.round_id == target_round_id).all():
                        link = db.query(ContestSeasonLink).filter(
                            ContestSeasonLink.season_id == season.id, 
                            ContestSeasonLink.contest_id == rc_contest_id_row[0],
                            ContestSeasonLink.is_active == True
                        ).first()
                        if link:
                            break
                    if not link:
                        # Frontend can send stale round_id from cached URLs. Fall back to active round.
                        from app import crud
                        fallback_round = crud.round.get_active_round_for_contest(db, real_contest_id) if real_contest_id else None
                        if fallback_round:
                            target_round_id = fallback_round.id
                        else:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST, 
                                detail=f"Requested round does not belong to this contest/season"
                            )
            else:
                # Frontend can send stale round_id from cached URLs. Fall back to active round.
                from app import crud
                fallback_round = crud.round.get_active_round_for_contest(db, real_contest_id) if real_contest_id else None
                if fallback_round:
                    target_round_id = fallback_round.id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Requested round does not belong to this contest"
                    )
    else:
        # Trouver le round actif
        if real_contest_id:
            from app import crud
            active_round = crud.round.get_active_round_for_contest(db, real_contest_id)
            if active_round:
                target_round_id = active_round.id
                
    if not target_round_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active round found for this contest. Participation requires an active round."
        )

    # Déterminer le type d'entrée (nomination ou participation)
    # Le contest_mode du concours détermine toujours le type d'entrée (source de vérité).
    # IMPORTANT: si l'ID URL correspond d'abord à ContestSeason, `contest` peut rester None.
    # On doit donc toujours re-résoudre le contest réel avant de fixer entry_type.
    contest_mode_value = None
    contest_for_mode = contest
    if contest_for_mode is None and real_contest_id:
        from app.models.contest import Contest as ContestModelForEntryType
        contest_for_mode = db.query(ContestModelForEntryType).filter(
            ContestModelForEntryType.id == real_contest_id,
            ContestModelForEntryType.is_deleted == False
        ).first()
    if contest_for_mode and hasattr(contest_for_mode, "contest_mode"):
        contest_mode_value = _normalize_contest_mode(contest_for_mode.contest_mode)
    submission_entry_type = "nomination" if contest_mode_value == "nomination" else "participation"
    
    # Vérifier que l'utilisateur n'a pas déjà une candidature POUR CE ROUND ET CE CONTEST
    # Un seul entry par contest par round (peu importe le type nomination/participation)
    existing = crud_contestant.get_by_round_and_user(
        db, target_round_id, current_user.id, season_id=season_id
    )
    if existing:
        # Idempotent behavior: if submission already exists for this round/contest,
        # return it as success so frontend can open/edit instead of hard-failing with 400.
        return ContestantSubmissionResponse(
            id=existing.id,
            season_id=existing.season_id,
            round_id=existing.round_id,
            user_id=existing.user_id,
            title=existing.title,
            description=existing.description,
            registration_date=existing.registration_date,
            message="Submission already exists for this round. Returning existing submission."
        )

    from app.services.contest_entry_eligibility import raise_if_user_missing_contest_entry_requirements
    from app.models.contest import Contest as ContestModelForEligibility

    eligibility_contest = contest
    if eligibility_contest is None and real_contest_id:
        eligibility_contest = db.query(ContestModelForEligibility).filter(
            ContestModelForEligibility.id == real_contest_id,
            ContestModelForEligibility.is_deleted == False,
        ).first()
    if eligibility_contest:
        raise_if_user_missing_contest_entry_requirements(db, current_user, eligibility_contest)
    
    # ============================================
    # MODÉRATION DU CONTENU AVANT CRÉATION
    # ============================================
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting content moderation for contestant submission by user {current_user.id}")
    
    # Modérer le texte (titre et description)
    text_to_moderate = f"{contestant_data.title} {contestant_data.description}"
    logger.info("Moderating text content...")
    text_moderation = content_moderation_service.moderate_text(text_to_moderate)
    logger.info(f"Text moderation completed: approved={text_moderation.is_approved}")
    
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Text content rejected: {flags_desc}"
        )
    
    # Helper pour extraire l'URL d'un média (ID ou URL directe)
    def get_media_url(media_ref: Any) -> Optional[str]:
        """Retourne l'URL du média, que ce soit un ID ou une URL directe"""
        return _resolve_media_url(db, media_ref)
    

    # ============================================
    # VERIFICATION UNICITE DES LIENS VIDEO (même round/concours)
    # ============================================
    if contestant_data.video_media_ids:
        current_contest_ids = {real_contest_id} if real_contest_id else _get_contest_ids_from_season(db, season_id)
        duplicate_submission = _find_duplicate_video_submission(
            db,
            video_media_ids=contestant_data.video_media_ids,
            target_round_id=target_round_id,
            current_category_id=contest.category_id if contest else None,
            current_contest_mode=contest.contest_mode if contest else None,
            current_contest_ids=current_contest_ids
        )
        if duplicate_submission:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This content link has already been submitted by another participant "
                    "on the same social media in this category and round."
                )
            )

    # Modérer les images si présentes
    if contestant_data.image_media_ids:
        logger.info(f"Moderating images: {contestant_data.image_media_ids[:100]}")
        try:
            image_refs = json.loads(contestant_data.image_media_ids)
            if isinstance(image_refs, list):
                for idx, media_ref in enumerate(image_refs[:10]):  # Max 10 images
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating image {idx+1}/{len(image_refs)}")
                        moderation_result = content_moderation_service.moderate_image(media_url)
                        logger.info(f"Image {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Image rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for image_media_ids: {e}")
    else:
        logger.info("No images to moderate")
    
    # Modérer les vidéos si présentes
    if contestant_data.video_media_ids:
        logger.info(f"Moderating videos: {contestant_data.video_media_ids[:100]}")
        try:
            video_refs = json.loads(contestant_data.video_media_ids)
            if isinstance(video_refs, list):
                for idx, media_ref in enumerate(video_refs[:5]):  # Max 5 vidéos
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating video {idx+1}/{len(video_refs)}")
                        moderation_result = content_moderation_service.moderate_video(media_url)
                        logger.info(f"Video {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Video rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for video_media_ids: {e}")
    else:
        logger.info("No videos to moderate")
    
    logger.info("Content moderation completed successfully")
    
    # ============================================
    # VÉRIFICATION DE LA PERTINENCE
    # ============================================
    logger.info("Starting relevance check...")
    
    # Récupérer les infos du concours pour la vérification de pertinence
    contest_title = ""
    contest_description = ""
    contest_type = None
    
    if contest:
        contest_title = contest.name or ""
        contest_description = contest.description or ""
        contest_type = getattr(contest, 'contest_type', None)
        if contest_type and hasattr(contest_type, 'value'):
            contest_type = contest_type.value
    elif season:
        contest_title = season.title or ""
        contest_description = getattr(season, 'description', "") or ""
    
    # Vérifier la pertinence de la candidature par rapport au concours
    relevance_result = content_relevance_service.check_relevance(
        contestant_title=contestant_data.title,
        contestant_description=contestant_data.description,
        contest_title=contest_title,
        contest_description=contest_description,
        contest_type=contest_type
    )
    
    logger.info(f"Relevance check completed: is_relevant={relevance_result.is_relevant}, score={relevance_result.score}")
    
    if not relevance_result.is_relevant:
        suggestions_text = " ".join(relevance_result.suggestions[:2])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Submission not relevant for this contest. {suggestions_text}"
        )
    
    # ============================================
    # VALIDATION DU PAYS DU NOMINATEUR
    # ============================================
    if contestant_data.nominator_country:
        user_country = current_user.country
        if user_country and contestant_data.nominator_country.lower().strip() != user_country.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The nominator country must match your country. Your country: {user_country}, Specified: {contestant_data.nominator_country}"
            )
    
    # ============================================
    # CRÉATION DE LA CANDIDATURE
    # ============================================
    logger.info("Starting contestant creation...")
    # Créer la candidature
    try:
        # Lier automatiquement le contestant à la saison "city"
        from app.services.season_migration import SeasonMigrationService
        from datetime import datetime


        # Trouver ou créer la saison "city" avant de créer le contestant
        # IMPORTANT: Utiliser le round_id pour scoper la saison
        city_season = SeasonMigrationService.get_or_create_season(
            db, 
            level=SeasonLevel.CITY,
            title="Saison City",
            round_id=target_round_id
        )
        
        # Créer la candidature
        contestant = crud_contestant.create(
            db, 
            user_id=current_user.id,
            season_id=season_id,
            title=contestant_data.title,
            description=contestant_data.description,
            image_media_ids=contestant_data.image_media_ids,
            video_media_ids=contestant_data.video_media_ids,
            nominator_city=contestant_data.nominator_city,
            nominator_country=contestant_data.nominator_country,
            entry_type=submission_entry_type,
            round_id=target_round_id
        )
        
        # Vérifier si le lien existe déjà
        existing_link = db.query(ContestantSeason).filter(
            ContestantSeason.contestant_id == contestant.id,
            ContestantSeason.season_id == city_season.id
        ).first()
        
        if not existing_link:
            # Créer le lien contestant-season pour la saison city
            contestant_season_link = ContestantSeason(
                contestant_id=contestant.id,
                season_id=city_season.id,
                joined_at=datetime.utcnow(),
                is_active=True
            )
            db.add(contestant_season_link)
            db.commit()
            db.refresh(contestant)
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating submission: {str(e)}"
        )
    
    return ContestantSubmissionResponse(
        id=contestant.id,
        season_id=contestant.season_id,
        round_id=contestant.round_id,
        user_id=contestant.user_id,
        title=contestant.title,
        description=contestant.description,
        registration_date=contestant.registration_date,
        message="Submission created successfully."
    )


@router.get("/{contestant_id}", response_model=ContestantWithAuthorAndStats)
def get_contestant(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional)
) -> ContestantWithAuthorAndStats:
    """Récupère les détails d'une candidature avec infos auteur et stats enrichies"""
    contestant_data = crud_contestant.get_with_stats(
        db, contestant_id, current_user_id=current_user.id if current_user else None
    )
    if not contestant_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    return ContestantWithAuthorAndStats(**contestant_data)


@router.post("/{contestant_id}/view", status_code=status.HTTP_201_CREATED)
def track_contestant_view(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    request: Request,
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
    watched_seconds: int = Body(default=30, embed=True),
) -> dict:
    """
    Track a contestant page view after a minimum dwell time.
    Frontend should call this only after user stays on page >= 30s.
    """
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if watched_seconds < 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A view is counted only after at least 30 seconds.",
        )

    db.add(
        PageView(
            user_id=current_user.id if current_user else None,
            contestant_id=contestant_id,
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
    )
    db.commit()
    return {"message": "View tracked"}


@router.post("/{contestant_id}/submission")
def add_submission(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    media_type: str = Query(...),
    file_url: Optional[str] = Query(None),
    external_url: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    description: Optional[str] = Query(None)
) -> dict:
    """Ajoute une soumission à une candidature"""
    # Vérifier que la candidature existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que c'est le propriétaire
    if contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only add a submission for your own submission"
        )
    
    # Ajouter la soumission
    submission = crud_contestant.add_submission(
        db,
        contestant_id=contestant_id,
        media_type=media_type,
        file_url=file_url,
        external_url=external_url,
        title=title,
        description=description
    )
    
    return {"message": "Submission added successfully", "submission_id": submission.id}


# Routes spécifiques pour les favoris (DOIVENT venir AVANT les routes génériques avec {id})
@router.post("/{contestant_id}/favorite")
def add_to_favorites(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Ajoute un contestant aux favoris de l'utilisateur"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Vérifier que l'utilisateur n'a pas déjà ce contestant en favoris
    existing = db.query(MyFavorites).filter(
        and_(
            MyFavorites.user_id == current_user.id,
            MyFavorites.contestant_id == contestant_id
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contestant is already in your favorites"
        )
    
    # Vérifier la limite de 5 favoris
    favorites_count = db.query(MyFavorites).filter(
        MyFavorites.user_id == current_user.id
    ).count()
    
    if favorites_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have reached the limit of 5 favorites"
        )
    
    # Ajouter aux favoris
    favorite = MyFavorites(
        user_id=current_user.id,
        contestant_id=contestant_id
    )
    db.add(favorite)
    db.commit()
    
    return {"message": f"Contestant added to favorites"}


@router.delete("/{contestant_id}/favorite")
def remove_from_favorites(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Retire un contestant des favoris de l'utilisateur"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Trouver et supprimer le favori
    favorite = db.query(MyFavorites).filter(
        and_(
            MyFavorites.user_id == current_user.id,
            MyFavorites.contestant_id == contestant_id
        )
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This contestant is not in your favorites"
        )
    
    db.delete(favorite)
    db.commit()
    
    return {"message": "Contestant removed from favorites"}


# Routes génériques (DOIVENT venir APRÈS les routes spécifiques)
@router.put("/{contestant_id}", response_model=ContestantResponse)
def update_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    contestant_data: ContestantCreate
) -> ContestantResponse:
    """Met à jour une candidature (l'utilisateur peut mettre à jour sa propre candidature)"""
    # Vérifier que la candidature existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que c'est le propriétaire
    if contestant.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own submission"
        )

    from app.services.contest_entry_eligibility import raise_if_user_missing_contest_entry_requirements
    from app.models.contest import Contest as MyfavContestForEligibility
    from app.models.contests import ContestSeasonLink as CSLForEligibility

    entry_contest = db.query(MyfavContestForEligibility).filter(
        MyfavContestForEligibility.id == contestant.season_id,
        MyfavContestForEligibility.is_deleted == False,
    ).first()
    if not entry_contest:
        _link = db.query(CSLForEligibility).filter(
            CSLForEligibility.season_id == contestant.season_id,
            CSLForEligibility.is_active == True,
        ).first()
        if _link:
            entry_contest = db.query(MyfavContestForEligibility).filter(
                MyfavContestForEligibility.id == _link.contest_id,
                MyfavContestForEligibility.is_deleted == False,
            ).first()
    if entry_contest:
        raise_if_user_missing_contest_entry_requirements(db, current_user, entry_contest)
    
    # ============================================
    # MODÉRATION DU CONTENU AVANT MISE À JOUR
    # ============================================
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting content moderation for contestant update by user {current_user.id}")
    
    # Modérer le texte (titre et description)
    text_to_moderate = f"{contestant_data.title} {contestant_data.description}"
    logger.info("Moderating text content...")
    text_moderation = content_moderation_service.moderate_text(text_to_moderate)
    logger.info(f"Text moderation completed: approved={text_moderation.is_approved}")
    
    if not text_moderation.is_approved:
        flags_desc = ", ".join([f.description for f in text_moderation.flags])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Text content rejected: {flags_desc}"
        )
    
    # Helper pour extraire l'URL d'un média (ID ou URL directe)
    def get_media_url(media_ref: Any) -> Optional[str]:
        return _resolve_media_url(db, media_ref)
    

    # ============================================
    # VERIFICATION UNICITE DES LIENS VIDEO
    # ============================================
    if contestant_data.video_media_ids:
        current_contexts = _get_contest_context_from_season(db, contestant.season_id)
        current_category_id, current_contest_mode = next(iter(current_contexts), (None, None))
        current_contest_ids = _get_contest_ids_from_season(db, contestant.season_id)
        duplicate_submission = _find_duplicate_video_submission(
            db,
            video_media_ids=contestant_data.video_media_ids,
            target_round_id=contestant.round_id,
            current_category_id=current_category_id,
            current_contest_mode=current_contest_mode,
            current_contest_ids=current_contest_ids,
            exclude_contestant_id=contestant_id
        )
        if duplicate_submission:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This content link has already been submitted by another participant "
                    "on the same social media in this category and round."
                )
            )

    # Modérer les images si présentes
    if contestant_data.image_media_ids:
        logger.info(f"Moderating images: {contestant_data.image_media_ids[:100]}")
        try:
            image_refs = json.loads(contestant_data.image_media_ids)
            if isinstance(image_refs, list):
                for idx, media_ref in enumerate(image_refs[:10]):
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating image {idx+1}/{len(image_refs)}")
                        moderation_result = content_moderation_service.moderate_image(media_url)
                        logger.info(f"Image {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Image rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for image_media_ids: {e}")
    else:
        logger.info("No images to moderate")
    
    # Modérer les vidéos si présentes
    if contestant_data.video_media_ids:
        logger.info(f"Moderating videos: {contestant_data.video_media_ids[:100]}")
        try:
            video_refs = json.loads(contestant_data.video_media_ids)
            if isinstance(video_refs, list):
                for idx, media_ref in enumerate(video_refs[:5]):
                    media_url = get_media_url(media_ref)
                    if media_url:
                        logger.info(f"Moderating video {idx+1}/{len(video_refs)}")
                        moderation_result = content_moderation_service.moderate_video(media_url)
                        logger.info(f"Video {idx+1} moderation: approved={moderation_result.is_approved}")
                        if not moderation_result.is_approved:
                            flags_desc = ", ".join([f.description for f in moderation_result.flags])
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Video rejected by moderation: {flags_desc}"
                            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for video_media_ids: {e}")
    else:
        logger.info("No videos to moderate")
    
    logger.info("Content moderation completed successfully")
    
    # ============================================
    # VÉRIFICATION DE LA PERTINENCE
    # ============================================
    logger.info(f"Starting relevance check for contestant update {contestant_id}")
    
    # Récupérer les infos du concours pour la vérification de pertinence
    contest_title = ""
    contest_description = ""
    contest_type = None
    
    # Essayer de récupérer le Contest associé
    from app.models.contest import Contest as MyfavContest
    contest = db.query(MyfavContest).filter(
        MyfavContest.id == contestant.season_id,
        MyfavContest.is_deleted == False
    ).first()
    
    if contest:
        contest_title = contest.name or ""
        contest_description = contest.description or ""
        contest_type = getattr(contest, 'contest_type', None)
        if contest_type and hasattr(contest_type, 'value'):
            contest_type = contest_type.value
    else:
        # Sinon, essayer de récupérer la ContestSeason
        season = db.query(ContestSeason).filter(ContestSeason.id == contestant.season_id).first()
        if season:
            contest_title = season.title or ""
            contest_description = getattr(season, 'description', "") or ""
    
    # Vérifier la pertinence de la candidature par rapport au concours
    relevance_result = content_relevance_service.check_relevance(
        contestant_title=contestant_data.title,
        contestant_description=contestant_data.description,
        contest_title=contest_title,
        contest_description=contest_description,
        contest_type=contest_type
    )
    
    logger.info(f"Relevance check completed: is_relevant={relevance_result.is_relevant}, score={relevance_result.score}")
    
    if not relevance_result.is_relevant:
        suggestions_text = " ".join(relevance_result.suggestions[:2])
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Submission not relevant for this contest. {suggestions_text}"
        )
    
    # ============================================
    # VALIDATION DU PAYS DU NOMINATEUR
    # ============================================
    if contestant_data.nominator_country:
        user_country = current_user.country
        if user_country and contestant_data.nominator_country.lower().strip() != user_country.lower().strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The nominator country must match your country. Your country: {user_country}, Specified: {contestant_data.nominator_country}"
            )
    
    # Mettre à jour la candidature
    updated_contestant = crud_contestant.update(
        db,
        id=contestant_id,
        title=contestant_data.title,
        description=contestant_data.description,
        image_media_ids=contestant_data.image_media_ids,
        video_media_ids=contestant_data.video_media_ids,
        nominator_city=contestant_data.nominator_city,
        nominator_country=contestant_data.nominator_country
    )
    
    return ContestantResponse.model_validate(updated_contestant)


@router.delete("/{contestant_id}")
def delete_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Supprime une candidature (l'utilisateur peut supprimer sa propre candidature)"""
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que la candidature n'est pas déjà supprimée
    if contestant.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission already deleted"
        )
    
    # Vérifier que c'est le propriétaire ou un admin
    if contestant.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own submission"
        )
    
    # Vérifier que les soumissions sont encore ouvertes (optionnel, mais recommandé)
    # On peut permettre la suppression même si les soumissions sont fermées
    
    success = crud_contestant.delete(db, id=contestant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting submission"
        )
    
    return {"message": "Submission deleted successfully"}


@router.post("/{contestant_id}/vote", status_code=status.HTTP_201_CREATED)
def vote_for_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    contest_id: Optional[int] = Query(
        None,
        description="Contest page the user is voting from (required when multiple contests share the same season/round).",
    ),
) -> dict:
    """Vote pour un contestant"""
    from app.services.contest_status import contest_status_service
    
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que l'utilisateur ne vote pas pour sa propre candidature
    if contestant.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot vote for your own submission"
        )
    
    # Récupérer la saison active du contestant via ContestantSeason
    from app.models.contests import ContestSeason, ContestantSeason
    
    # Récupérer la saison active pour ce contestant
    contestant_season_link = db.query(ContestantSeason).filter(
        ContestantSeason.contestant_id == contestant_id,
        ContestantSeason.is_active == True
    ).first()
    
    if not contestant_season_link:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contestant is not active in any season"
        )
    
    # Récupérer la saison
    season = db.query(ContestSeason).filter(
        ContestSeason.id == contestant_season_link.season_id,
        ContestSeason.is_deleted == False
    ).first()
    
    if not season:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Season not found for this contestant"
        )
    
    # Contest associé : préférer le contest_id de la page (évite mélange Bongo Fleva vs Tennis Club).
    contest: Optional[Contest] = None
    if contest_id is not None:
        c = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
        if not c:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
        if _contestant_belongs_to_contest(db, contestant, contest_id, season):
            contest = c
        else:
            resolved = _resolve_contest_for_contestant_vote(db, contestant, season)
            if resolved is not None and resolved.id == contest_id:
                contest = c
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This submission is not part of the selected contest. Refresh the page and try again.",
                )
    else:
        contest = _resolve_contest_for_contestant_vote(db, contestant, season)
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active contest found for this season. Open the contest from the list and vote again, or pass contest_id.",
        )
    
    # Vérifier que le vote est ouvert pour ce contest
    is_allowed, error_message = contest_status_service.check_voting_allowed(db, contest.id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )
    
    # Vérifier que le round du contestant est en phase de vote (pas en soumission)
    if contestant.round_id:
        from app.models.round import Round as RoundModel
        from datetime import datetime, time as time_type

        contestant_round = db.query(RoundModel).filter(RoundModel.id == contestant.round_id).first()
        if contestant_round and contestant_round.voting_start_date and contestant_round.voting_end_date:
            now_vote = contest_status_service._utc_now()
            vs = datetime.combine(contestant_round.voting_start_date, time_type.min)
            ve = datetime.combine(contestant_round.voting_end_date, time_type(23, 59, 59))
            if now_vote < vs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Voting for {contestant_round.name} has not started yet. Submission phase is active until {contestant_round.submission_end_date}. Voting starts on {contestant_round.voting_start_date}."
                )
            if now_vote > ve:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Voting for {contestant_round.name} has ended on {contestant_round.voting_end_date}."
                )
            if not contest_status_service.round_voting_open_at(contestant_round, now_vote):
                nom_close = contest_status_service.round_nomination_closes_at(contestant_round)
                detail = (
                    f"Voting for {contestant_round.name} opens after nominations close "
                    f"({nom_close.isoformat()} UTC)."
                    if nom_close
                    else f"Voting is not open yet for {contestant_round.name}."
                )
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    # Règles de vote basées sur la localisation et le niveau de la saison
    # (Les concours en mode "nomination" utilisent toujours le niveau country, jamais city — même si la saison est city.)
    # city      -> seuls les utilisateurs de la même ville (et même pays) peuvent voter
    # country   -> mêmes pays et continent
    # regional  -> mêmes région et continent
    # continent -> même continent
    # global    -> tout le monde peut voter
    season_level = None
    if hasattr(season, "level") and season.level is not None:
        season_level = season.level.value if hasattr(season.level, "value") else str(season.level)
        if isinstance(season_level, str):
            season_level = season_level.lower()

    # Nomination contests: voters are scoped by country, not city, even if the season level is "city".
    if (
        season_level == "city"
        and contest
        and _normalize_contest_mode(getattr(contest, "contest_mode", None)) == "nomination"
    ):
        season_level = "country"

    from app.models.user import User as MyfavUser

    def location_vote_error() -> Optional[str]:
        """Returns None if voting is allowed; otherwise a clear message for the client."""
        if not season_level:
            return None

        lvl = str(season_level).lower()
        voter: MyfavUser = current_user
        author: MyfavUser = contestant.user  # chargé par crud_contestant.get avec joinedload

        if not author:
            return None

        def eq(a: Optional[str], b: Optional[str]) -> bool:
            return bool(a and b and a.lower() == b.lower())

        def is_valid_location(value: Optional[str]) -> bool:
            if not value:
                return False
            val_lower = str(value).lower().strip()
            return val_lower not in ("unknown", "none", "", "null")

        def compare_with_unknown(val1: Optional[str], val2: Optional[str]) -> bool:
            """Compare deux valeurs géographiques en ignorant 'Unknown'"""
            valid1 = is_valid_location(val1)
            valid2 = is_valid_location(val2)
            if valid1 and valid2:
                return eq(val1, val2)
            # Si au moins une est "Unknown", on accepte (pas de restriction)
            return True

        def author_location_for_vote() -> tuple:
            """Référence géographique du participant : snapshot contestant si renseigné, sinon profil user.
            Évite les écarts quand le profil a changé après l'inscription ou que la ligne contestant a été corrigée."""
            def pick(c_val: Optional[str], u_val: Optional[str]) -> Optional[str]:
                if is_valid_location(c_val):
                    return c_val
                return u_val

            c = contestant
            return (
                pick(getattr(c, "continent", None), author.continent),
                pick(getattr(c, "region", None), getattr(author, "region", None)),
                pick(getattr(c, "country", None), author.country),
                pick(getattr(c, "city", None), author.city),
            )

        ac_continent, ac_region, ac_country, ac_city = author_location_for_vote()

        if lvl == "city":
            country_match = compare_with_unknown(voter.country, ac_country)
            if not country_match:
                msg = (
                    "You cannot vote for this contestant because this season is limited to the same country and city. "
                    "Your country on your profile does not match this contestant's country."
                )
                if is_valid_location(voter.country) and is_valid_location(ac_country):
                    msg += f" Your profile: {voter.country}. This contestant: {ac_country}."
                return msg
            if not compare_with_unknown(voter.city, ac_city):
                msg = (
                    "You cannot vote for this contestant because this season is limited to voters in the same city. "
                    "You are not in the same city as this contestant. "
                    "Update your profile city to match their city, or vote for contestants who are in your city."
                )
                if is_valid_location(voter.city) and is_valid_location(ac_city):
                    msg += f" Your profile city: {voter.city}. This contestant's city: {ac_city}."
                return msg
            return None
        if lvl == "country":
            if not compare_with_unknown(voter.continent, ac_continent):
                msg = (
                    "You cannot vote for this contestant because this season is limited to the same continent and country. "
                    "Your continent on your profile does not match this contestant's continent."
                )
                if is_valid_location(voter.continent) and is_valid_location(ac_continent):
                    msg += f" Yours: {voter.continent}. Theirs: {ac_continent}."
                return msg
            if not compare_with_unknown(voter.country, ac_country):
                msg = (
                    "You cannot vote for this contestant because this season is limited to voters in the same country. "
                    "Your country on your profile does not match this contestant's country."
                )
                if is_valid_location(voter.country) and is_valid_location(ac_country):
                    msg += f" Your profile: {voter.country}. This contestant: {ac_country}."
                return msg
            return None
        if lvl in ("regional", "region"):
            if not compare_with_unknown(voter.continent, ac_continent):
                msg = (
                    "You cannot vote for this contestant because this season is limited to the same continent and region. "
                    "Your continent does not match this contestant's continent."
                )
                if is_valid_location(voter.continent) and is_valid_location(ac_continent):
                    msg += f" Yours: {voter.continent}. Theirs: {ac_continent}."
                return msg
            v_region = getattr(voter, "region", None)
            if not compare_with_unknown(v_region, ac_region):
                msg = (
                    "You cannot vote for this contestant because this season is limited to voters in the same region. "
                    "Your region on your profile does not match this contestant's region."
                )
                if is_valid_location(v_region) and is_valid_location(ac_region):
                    msg += f" Your profile: {v_region}. This contestant: {ac_region}."
                return msg
            return None
        if lvl == "continent":
            if not compare_with_unknown(voter.continent, ac_continent):
                msg = (
                    "You cannot vote for this contestant because this season is limited to voters on the same continent. "
                    "Your continent on your profile does not match this contestant's continent."
                )
                if is_valid_location(voter.continent) and is_valid_location(ac_continent):
                    msg += f" Your profile: {voter.continent}. This contestant: {ac_continent}."
                return msg
            return None
        # global or unknown level: no restriction
        return None

    geo_error = location_vote_error()
    if geo_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=geo_error,
        )
    
    # Vérifier les restrictions de genre pour le vote
    # Si le contest est MALE_ONLY (réservé aux hommes pour participer), seules les femmes peuvent voter
    # Si le contest est FEMALE_ONLY (réservé aux femmes pour participer), seuls les hommes peuvent voter
    gender_restriction = contest.gender_restriction
    
    # Si pas de gender_restriction directe, vérifier voting_restriction
    if not gender_restriction and hasattr(contest, 'voting_restriction') and contest.voting_restriction:
        voting_restriction_str = str(contest.voting_restriction).lower().strip()
        if voting_restriction_str == 'male_only':
            gender_restriction = 'male'
        elif voting_restriction_str == 'female_only':
            gender_restriction = 'female'
    
    # Vérifier si l'utilisateur respecte la restriction de genre pour voter
    if gender_restriction:
        if not current_user.gender:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your profile does not contain gender information. Please complete your profile to vote in this contest."
            )
        
        user_gender = current_user.gender.value.lower() if hasattr(current_user.gender, 'value') else str(current_user.gender).lower()
        gender_restriction_lower = gender_restriction.lower()
        
        # Logique inverse : si le contest est réservé aux hommes (pour participer), seules les femmes peuvent voter
        # Si le contest est réservé aux femmes (pour participer), seuls les hommes peuvent voter
        if gender_restriction_lower == 'male':
            # Contest réservé aux hommes pour participer, donc seules les femmes peuvent voter
            if user_gender != 'female':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for male participants. Only female participants can vote."
                )
        elif gender_restriction_lower == 'female':
            # Contest réservé aux femmes pour participer, donc seuls les hommes peuvent voter
            if user_gender != 'male':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This contest is reserved for female participants. Only male participants can vote."
                )
    
    # Vérifier si l'utilisateur a déjà voté pour ce contestant dans cette saison active
    # IMPORTANT: Un utilisateur peut voter pour plusieurs contestants différents dans la même saison
    # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
    # Un utilisateur peut voter à nouveau dans une nouvelle saison, même pour le même contestant
    import logging
    logger = logging.getLogger(__name__)
    
    # Log pour déboguer la saison récupérée
    logger.info(
        f"[VOTE CHECK] Checking vote for user {current_user.id}, contestant {contestant_id}, "
        f"season_id: {season.id}, season_level: {season_level}"
    )
    
    # Vérifier si l'utilisateur a déjà voté pour ce contestant dans cette saison
    # IMPORTANT: La vérification se fait par (user_id, contestant_id, season_id)
    # Un utilisateur peut voter pour plusieurs contestants dans la même saison
    # Mais il ne peut pas voter deux fois pour le même contestant dans la même saison
    existing_vote = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == current_user.id,
        ContestantVoting.contestant_id == contestant_id,
        ContestantVoting.season_id == season.id  # Vérification par (user_id, contestant_id, season_id)
    ).first()
    
    if existing_vote:
        logger.warning(
            f"[VOTE CHECK] User {current_user.id} already voted for contestant {contestant_id} "
            f"in season {season.id} (level: {season_level}). "
            f"Existing vote ID: {existing_vote.id}, vote_date: {existing_vote.vote_date}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "already_voted",
                "message": "You have already voted for this contestant in this season."
            }
        )
    
    logger.info(
        f"[VOTE CHECK] User {current_user.id} can vote in season {season.id} "
        f"(no existing vote found for this season)"
    )
    
    # Compter les votes existants pour cette saison et cette catégorie MyHigh5 (5 slots par catégorie)
    from sqlalchemy import case

    existing_votes_for_season = (
        _myhigh5_scope_votes_query(
            db,
            user_id=current_user.id,
            season_id=season.id,
            contest=contest,
        )
        .order_by(
            case(
                (ContestantVoting.position.isnot(None), ContestantVoting.position),
                else_=1000
            ),
            ContestantVoting.vote_date.asc(),
        )
        .all()
    )

    votes_count = len(existing_votes_for_season)

    # Si max 5 votes atteint, retourner 409 pour le dialogue de confirmation frontend
    if votes_count >= 5:
        fifth_vote = existing_votes_for_season[4]
        fifth_contestant = db.query(Contestant).filter(Contestant.id == fifth_vote.contestant_id).first()
        fifth_name = fifth_contestant.title if fifth_contestant else "Unknown"

        logger.info(
            f"[VOTE MAX] User {current_user.id} has {votes_count} votes in season {season.id}. "
            f"5th vote: contestant {fifth_vote.contestant_id} ({fifth_name})"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "max_votes_reached",
                "message": f"You already have 5 votes in this category for this season. Replace {fifth_name}?",
                "replaced_contestant": {
                    "id": fifth_vote.contestant_id,
                    "name": fifth_name,
                    "position": 5
                },
                "current_votes_count": votes_count
            }
        )

    # Créer le nouveau vote à la position suivante
    new_position = votes_count + 1  # 1er vote = position 1, 2e = position 2, etc.
    new_points = 6 - new_position   # position 1 = 5pts, 2 = 4pts, ..., 5 = 1pt

    new_voting = ContestantVoting(
        user_id=current_user.id,
        contestant_id=contestant_id,
        contest_id=contest.id,
        season_id=season.id,
        vote_bucket_key=_bucket_key_for_contest(contest),
        position=new_position,
        points=new_points
    )

    try:
        db.add(new_voting)
        db.commit()
        db.refresh(new_voting)
        logger.info(
            f"[VOTE SUCCESS] Vote created: user {current_user.id}, contestant {contestant_id}, "
            f"season {season.id}, voting_id: {new_voting.id}, position={new_position}, points={new_points}"
        )
    except Exception as e:
        db.rollback()
        error_str = str(e).lower()
        logger.error(
            f"[VOTE ERROR] Error creating vote: {e}. "
            f"User {current_user.id}, contestant {contestant_id}, season {season.id}"
        )

        if "unique constraint" in error_str or "duplicate key" in error_str:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "already_voted",
                    "message": "You have already voted for this contestant in this season."
                }
            )
        raise
    
    # Mettre à jour les rangs de tous les contestants du contest pour cette saison
    from app.crud.crud_contest import contest as crud_contest
    try:
        crud_contest.update_contestant_rankings(db, contest.id, season.id)
    except Exception as e:
        # Log l'erreur mais ne bloque pas le vote
        import logging
        logging.error(f"Error updating rankings after vote: {e}")
    
    # Créer une notification pour le propriétaire du contestant
    from app.crud.crud_notification import crud_notification
    from app.models.notification import NotificationType
    
    voter_name = current_user.full_name or current_user.username or "Someone"
    crud_notification.create(
        db,
        user_id=contestant.user_id,
        type=NotificationType.CONTEST,
        title="New vote",
        message=f"{voter_name} voted for your application",
        related_contestant_id=contestant_id,
        related_contest_id=contest.id if contest else None
    )
    db.commit()
    
    return {
        "message": f"Vote recorded successfully for {season_level or 'season'} season",
        "voting_id": new_voting.id,
        "season_id": season.id,
        "season_level": season_level
    }


@router.post("/{contestant_id}/vote/replace", status_code=status.HTTP_200_OK)
def replace_fifth_vote(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    contest_id: Optional[int] = Query(
        None,
        description="Contest page context (same as /vote).",
    ),
) -> dict:
    """
    Remplace le 5e vote de l'utilisateur par un nouveau contestant.
    Appelé après confirmation de l'utilisateur via le dialogue frontend.
    """
    from app.services.contest_status import contest_status_service
    from app.models.contests import ContestSeason, ContestantSeason
    from sqlalchemy import case
    import logging
    logger = logging.getLogger(__name__)

    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    # Vérifier que l'utilisateur ne vote pas pour sa propre candidature
    if contestant.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot vote for your own submission")

    # Récupérer la saison active du contestant
    contestant_season_link = db.query(ContestantSeason).filter(
        ContestantSeason.contestant_id == contestant_id,
        ContestantSeason.is_active == True
    ).first()

    if not contestant_season_link:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This contestant is not active in any season")

    season = db.query(ContestSeason).filter(
        ContestSeason.id == contestant_season_link.season_id,
        ContestSeason.is_deleted == False
    ).first()

    if not season:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Season not found")

    contest: Optional[Contest] = None
    if contest_id is not None:
        c = db.query(Contest).filter(Contest.id == contest_id, Contest.is_deleted == False).first()
        if not c:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
        if _contestant_belongs_to_contest(db, contestant, contest_id, season):
            contest = c
        else:
            resolved = _resolve_contest_for_contestant_vote(db, contestant, season)
            if resolved is not None and resolved.id == contest_id:
                contest = c
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This submission is not part of the selected contest.",
                )
    else:
        contest = _resolve_contest_for_contestant_vote(db, contestant, season)
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contest not found. Pass contest_id if multiple contests share this season.",
        )

    # Vérifier que le vote est ouvert
    is_allowed, error_message = contest_status_service.check_voting_allowed(db, contest.id)
    if not is_allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    
    # Vérifier que le round du contestant est en phase de vote
    if contestant.round_id:
        from app.models.round import Round as RoundModel
        from datetime import datetime, time as time_type

        contestant_round = db.query(RoundModel).filter(RoundModel.id == contestant.round_id).first()
        if contestant_round and contestant_round.voting_start_date and contestant_round.voting_end_date:
            now_vote = contest_status_service._utc_now()
            vs = datetime.combine(contestant_round.voting_start_date, time_type.min)
            ve = datetime.combine(contestant_round.voting_end_date, time_type(23, 59, 59))
            if now_vote < vs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Voting for {contestant_round.name} has not started yet. Voting starts on {contestant_round.voting_start_date}."
                )
            if now_vote > ve:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Voting for {contestant_round.name} has ended on {contestant_round.voting_end_date}."
                )
            if not contest_status_service.round_voting_open_at(contestant_round, now_vote):
                nom_close = contest_status_service.round_nomination_closes_at(contestant_round)
                detail = (
                    f"Voting opens after nominations close ({nom_close.isoformat()} UTC)."
                    if nom_close
                    else "Voting is not open yet for this round."
                )
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    # Vérifier que l'utilisateur n'a pas déjà voté pour ce contestant
    existing_vote_for_contestant = db.query(ContestantVoting).filter(
        ContestantVoting.user_id == current_user.id,
        ContestantVoting.contestant_id == contestant_id,
        ContestantVoting.season_id == season.id
    ).first()

    if existing_vote_for_contestant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "already_voted", "message": "You have already voted for this contestant."}
        )

    # Même scope que POST /vote : 5e place dans la même catégorie / saison
    existing_votes = (
        _myhigh5_scope_votes_query(
            db,
            user_id=current_user.id,
            season_id=season.id,
            contest=contest,
        )
        .order_by(
            case(
                (ContestantVoting.position.isnot(None), ContestantVoting.position),
                else_=1000
            ),
            ContestantVoting.vote_date.asc(),
        )
        .all()
    )

    if len(existing_votes) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have less than 5 votes. Use the regular vote endpoint."
        )

    # Supprimer le 5e vote (dernier dans le classement)
    vote_to_remove = existing_votes[4]
    removed_contestant_id = vote_to_remove.contestant_id
    logger.info(
        f"[VOTE REPLACE] Removing 5th vote: ID={vote_to_remove.id}, "
        f"contestant_id={removed_contestant_id}, replacing with contestant_id={contestant_id}"
    )
    db.delete(vote_to_remove)
    db.flush()

    # Créer le nouveau vote en position 5 (1 point)
    new_voting = ContestantVoting(
        user_id=current_user.id,
        contestant_id=contestant_id,
        contest_id=contest.id,
        season_id=season.id,
        vote_bucket_key=_bucket_key_for_contest(contest),
        position=5,
        points=1
    )
    db.add(new_voting)

    try:
        db.commit()
        db.refresh(new_voting)
    except Exception as e:
        db.rollback()
        logger.error(f"[VOTE REPLACE ERROR] {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error replacing vote")

    # Mettre à jour les rankings des deux contestants
    from app.crud.crud_contest import contest as crud_contest
    try:
        crud_contest.update_contestant_rankings(db, contest.id, season.id)
    except Exception as e:
        logger.error(f"Error updating rankings after vote replace: {e}")

    # Notification au propriétaire du nouveau contestant voté
    from app.crud.crud_notification import crud_notification
    from app.models.notification import NotificationType

    voter_name = current_user.full_name or current_user.username or "Someone"
    crud_notification.create(
        db,
        user_id=contestant.user_id,
        type=NotificationType.CONTEST,
        title="New vote",
        message=f"{voter_name} voted for your application",
        related_contestant_id=contestant_id,
        related_contest_id=contest.id
    )
    db.commit()

    return {
        "message": "Vote replaced successfully",
        "voting_id": new_voting.id,
        "replaced_contestant_id": removed_contestant_id,
        "new_contestant_id": contestant_id,
        "position": 5,
        "points": 1,
        "season_id": season.id
    }


@router.post("/{contestant_id}/reaction", response_model=Reaction, status_code=status.HTTP_201_CREATED)
def add_reaction(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int,
    reaction_in: ReactionCreate
) -> Reaction:
    """Ajouter ou mettre à jour une réaction pour un contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Vérifier que le type de réaction est valide et le convertir en minuscules
    reaction_type_str = reaction_in.reaction_type.lower()
    try:
        reaction_type = ReactionType(reaction_type_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid reaction type. Valid types: {[e.value for e in ReactionType]}"
        )
    
    # S'assurer que nous utilisons la valeur de l'enum (string) et non l'enum lui-même
    # Avec native_enum=False, SQLAlchemy stocke la valeur comme string
    reaction_type_value = reaction_type.value
    
    # Vérifier si l'utilisateur a déjà une réaction pour ce contestant
    existing_reaction = db.query(ContestantReaction).filter(
        ContestantReaction.user_id == current_user.id,
        ContestantReaction.contestant_id == contestant_id
    ).first()
    
    if existing_reaction:
        # Mettre à jour la réaction existante
        existing_reaction.reaction_type = reaction_type.value
        db.commit()
        db.refresh(existing_reaction)
        return existing_reaction
    else:
        # Créer une nouvelle réaction
        new_reaction = ContestantReaction(
            user_id=current_user.id,
            contestant_id=contestant_id,
            reaction_type=reaction_type.value  # Utiliser la valeur string de l'enum
        )
        db.add(new_reaction)
        db.commit()
        db.refresh(new_reaction)
        
        # Créer une notification pour le propriétaire du contestant
        if contestant.user_id != current_user.id:
            from app.crud.crud_notification import crud_notification
            from app.models.notification import NotificationType
            
            reactor_name = current_user.full_name or current_user.username or "Someone"
            reaction_emoji = {
                'like': '👍',
                'love': '❤️',
                'wow': '😮',
                'dislike': '👎'
            }.get(reaction_type_str, '👍')
            
            crud_notification.create(
                db,
                user_id=contestant.user_id,
                type=NotificationType.CONTEST,
                title="New reaction",
                message=f"{reactor_name} reacted {reaction_emoji} to your application",
                related_contestant_id=contestant_id
            )
            db.commit()
        
        return new_reaction


@router.delete("/{contestant_id}/reaction", status_code=status.HTTP_200_OK)
def remove_reaction(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    contestant_id: int
) -> dict:
    """Supprimer une réaction pour un contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Trouver et supprimer la réaction
    reaction = db.query(ContestantReaction).filter(
        ContestantReaction.user_id == current_user.id,
        ContestantReaction.contestant_id == contestant_id
    ).first()
    
    if not reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reaction not found"
        )
    
    db.delete(reaction)
    db.commit()
    
    return {"message": "Reaction removed successfully"}


@router.get("/{contestant_id}/reactions", response_model=ReactionStats)
def get_reaction_stats(
    *,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
    contestant_id: int
) -> ReactionStats:
    """Récupérer les statistiques de réactions pour un contestant"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Compter les réactions par type
    reactions = db.query(ContestantReaction).filter(
        ContestantReaction.contestant_id == contestant_id
    ).all()
    
    stats = ReactionStats(
        contestant_id=contestant_id,
        total_reactions=len(reactions),
        like_count=sum(1 for r in reactions if r.reaction_type == 'like'),
        love_count=sum(1 for r in reactions if r.reaction_type == 'love'),
        wow_count=sum(1 for r in reactions if r.reaction_type == 'wow'),
        dislike_count=sum(1 for r in reactions if r.reaction_type == 'dislike')
    )
    
    # Si l'utilisateur est connecté, récupérer sa réaction
    if current_user:
        user_reaction = db.query(ContestantReaction).filter(
            ContestantReaction.user_id == current_user.id,
            ContestantReaction.contestant_id == contestant_id
        ).first()
        if user_reaction:
            # reaction_type est maintenant une string
            stats.user_reaction = user_reaction.reaction_type
    
    return stats


@router.post("/{contestant_id}/share", response_model=Share, status_code=status.HTTP_201_CREATED)
def share_contestant(
    *,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_active_user_optional),
    contestant_id: int,
    share_in: ShareCreate
) -> Share:
    """Enregistrer un partage de contestant avec referral code et métadonnées"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Déterminer qui partage
    shared_by_user_id = share_in.shared_by_user_id or (current_user.id if current_user else None)
    
    # Récupérer le referral code de celui qui partage
    referral_code = share_in.referral_code
    if not referral_code and shared_by_user_id:
        sharing_user = db.query(User).filter(User.id == shared_by_user_id).first()
        if sharing_user and sharing_user.personal_referral_code:
            referral_code = sharing_user.personal_referral_code
    
    # Construire le lien de partage avec le referral code si disponible
    share_link = share_in.share_link
    if referral_code:
        from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
        parsed = urlparse(share_link)
        query_params = parse_qs(parsed.query)
        query_params['ref'] = [referral_code]
        new_query = urlencode(query_params, doseq=True)
        share_link = urlunparse(parsed._replace(query=new_query))
    
    # Créer un nouveau partage avec toutes les informations
    new_share = ContestantShare(
        author_id=contestant.user_id,  # L'auteur du contestant
        shared_by_user_id=shared_by_user_id,  # Celui qui partage
        contestant_id=contestant_id,
        referral_code=referral_code,  # Code de parrainage
        share_link=share_link,  # Lien avec referral code
        platform=share_in.platform,
        # Conserver user_id pour compatibilité
        user_id=contestant.user_id
    )
    
    db.add(new_share)
    db.commit()
    db.refresh(new_share)
    
    return new_share


@router.get("/{contestant_id}/shares", response_model=ShareStats)
def get_share_stats(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> ShareStats:
    """Récupérer les statistiques de partage pour un contestant"""
    from sqlalchemy.orm import joinedload
    
    # Vérifier que le contestant existe et charger l'utilisateur (auteur)
    contestant = db.query(Contestant)\
        .options(joinedload(Contestant.user))\
        .filter(Contestant.id == contestant_id)\
        .first()
    
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer tous les partages avec les utilisateurs
    shares = db.query(ContestantShare)\
        .options(joinedload(ContestantShare.shared_by))\
        .filter(ContestantShare.contestant_id == contestant_id)\
        .order_by(ContestantShare.created_at.desc())\
        .all()
    
    # Compter par plateforme
    shares_by_platform = {}
    for share in shares:
        platform = share.platform or "other"
        shares_by_platform[platform] = shares_by_platform.get(platform, 0) + 1
    
    # Construire la liste des utilisateurs qui ont partagé
    shares_list = []
    for share in shares:
        user_detail = ShareUserDetail(
            id=share.id,
            user_id=share.shared_by_user_id,
            username=share.shared_by.username if share.shared_by else None,
            full_name=(
                share.shared_by.full_name or 
                f"{share.shared_by.first_name or ''} {share.shared_by.last_name or ''}".strip()
                if share.shared_by else None
            ),
            avatar_url=share.shared_by.avatar_url if share.shared_by else None,
            platform=share.platform,
            share_link=share.share_link,
            created_at=share.created_at
        )
        shares_list.append(user_detail)
    
    # Récupérer les informations de l'auteur
    author_name = None
    author_username = None
    if contestant.user:
        author_name = contestant.user.full_name or f"{contestant.user.first_name or ''} {contestant.user.last_name or ''}".strip()
        author_username = contestant.user.username
    
    return ShareStats(
        contestant_id=contestant_id,
        total_shares=len(shares),
        shares_by_platform=shares_by_platform,
        # Informations du contestant
        contestant_title=contestant.title,
        contestant_description=contestant.description,
        contestant_registration_date=contestant.registration_date,
        # Informations de l'auteur
        author_id=contestant.user_id,
        author_name=author_name,
        author_username=author_username,
        author_country=contestant.user.country if contestant.user else None,
        author_city=contestant.user.city if contestant.user else None,
        author_avatar_url=contestant.user.avatar_url if contestant.user else None,
        # Liste des utilisateurs qui ont partagé
        shares=shares_list
    )


@router.get("/{contestant_id}/reactions/details", response_model=ReactionDetails)
def get_reaction_details(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> ReactionDetails:
    """Récupérer les détails des réactions avec les noms des utilisateurs"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer toutes les réactions avec les utilisateurs
    reactions = db.query(ContestantReaction).join(User).filter(
        ContestantReaction.contestant_id == contestant_id
    ).all()
    
    # Grouper par type de réaction
    reactions_by_type: dict[str, List[ReactionUserDetail]] = {}
    for reaction in reactions:
        reaction_type = reaction.reaction_type
        if reaction_type not in reactions_by_type:
            reactions_by_type[reaction_type] = []
        
        reactions_by_type[reaction_type].append(
            ReactionUserDetail(
                user_id=reaction.user.id,
                username=reaction.user.username,
                full_name=reaction.user.full_name,
                avatar_url=reaction.user.avatar_url,
                reaction_type=reaction_type
            )
        )
    
    return ReactionDetails(
        contestant_id=contestant_id,
        reactions_by_type=reactions_by_type
    )


@router.get("/{contestant_id}/votes/details", response_model=VoteDetails)
def get_vote_details(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> VoteDetails:
    """Récupérer les détails des votes avec les noms des utilisateurs"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer tous les votes avec les utilisateurs depuis ContestantVoting
    votes = db.query(ContestantVoting).join(User, ContestantVoting.user_id == User.id).filter(
        ContestantVoting.contestant_id == contestant_id
    ).order_by(ContestantVoting.vote_date.desc()).all()
    
    voters = [
        VoteUserDetail(
            id=vote.id,
            user_id=vote.user.id,
            username=vote.user.username,
            full_name=vote.user.full_name,
            avatar_url=vote.user.avatar_url,
            points=1,  # Chaque vote vaut 1 point dans le nouveau système
            vote_date=vote.vote_date,
            contest_id=vote.contest_id,
            season_id=vote.season_id
        )
        for vote in votes
    ]
    
    return VoteDetails(
        contestant_id=contestant_id,
        voters=voters
    )


@router.get("/{contestant_id}/favorites/details", response_model=FavoriteDetails)
def get_favorite_details(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int
) -> FavoriteDetails:
    """Récupérer les détails des favoris avec les noms des utilisateurs"""
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )
    
    # Récupérer tous les favoris avec les utilisateurs
    favorites = db.query(MyFavorites).join(User, MyFavorites.user_id == User.id).filter(
        MyFavorites.contestant_id == contestant_id
    ).order_by(MyFavorites.added_date.desc()).all()
    
    users = [
        FavoriteUserDetail(
            user_id=favorite.user.id,
            username=favorite.user.username,
            full_name=favorite.user.full_name,
            avatar_url=favorite.user.avatar_url,
            position=favorite.position,
            added_date=favorite.added_date
        )
        for favorite in favorites
    ]
    
    return FavoriteDetails(
        contestant_id=contestant_id,
        users=users
    )


@router.post("/{contestant_id}/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def report_contestant(
    *,
    db: Session = Depends(deps.get_db),
    contestant_id: int,
    report_data: ContestantReportCreate,
    current_user: User = Depends(deps.get_current_active_user),
    background_tasks: BackgroundTasks
) -> ReportResponse:
    """
    Signaler un contestant.
    Enregistre le signalement et envoie une notification à l'admin.
    """
    from fastapi import BackgroundTasks
    from app.services.email import email_service
    from app.crud import user as crud_user
    
    # Vérifier que le contestant existe
    contestant = crud_contestant.get(db, contestant_id)
    if not contestant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contestant not found"
        )
    
    # Vérifier que le contest existe
    contest = db.query(Contest).filter(Contest.id == report_data.contest_id).first()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found"
        )
    
    # Vérifier que le contestant appartient bien au contest
    # (vérification basique, peut être améliorée selon votre logique)
    
    # Vérifier que l'utilisateur ne signale pas son propre contestant
    if contestant.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot report your own contestant"
        )
    
    # Vérifier qu'il n'y a pas déjà un signalement en attente du même utilisateur pour ce contestant
    from app.models.comment import Report as ReportModel
    existing_report = db.query(ReportModel).filter(
        ReportModel.reporter_id == current_user.id,
        ReportModel.contestant_id == contestant_id,
        ReportModel.status == "pending"
    ).first()
    
    if existing_report:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reported this contestant. Please wait for admin review."
        )
    
    # Créer le signalement
    try:
        new_report = report.create_contestant_report(
            db=db,
            obj_in=report_data,
            reporter_id=current_user.id
        )
        
        # Récupérer l'auteur du contestant
        contestant_author = crud_user.get(db, contestant.user_id)
        author_name = contestant_author.full_name if contestant_author else "Unknown"
        
        # Envoyer une notification email à l'admin en arrière-plan
        # Récupérer tous les admins
        admin_users = db.query(User).filter(User.is_admin == True, User.is_active == True).all()
        
        if admin_users:
            from app.services.email_templates import get_contestant_report_email
            from app.core.config import settings
            
            for admin in admin_users:
                admin_lang = getattr(admin, 'preferred_language', 'en') or 'en'
                
                # Générer l'email
                subject, html_content, text_content = get_contestant_report_email(
                    lang=admin_lang,
                    contestant_title=contestant.title or "Untitled",
                    contestant_author_name=author_name,
                    contest_name=contest.name,
                    reporter_name=current_user.full_name or current_user.username,
                    reason=report_data.reason,
                    description=report_data.description,
                    report_id=new_report.id,
                    admin_url=f"{settings.FRONTEND_URL}/admin/reports/{new_report.id}"
                )
                
                background_tasks.add_task(
                    email_service.send_email,
                    to_email=admin.email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )
        
        # Construire la réponse
        return ReportResponse(
            id=new_report.id,
            reporter_id=new_report.reporter_id,
            contestant_id=new_report.contestant_id,
            contest_id=new_report.contest_id,
            reason=new_report.reason,
            description=new_report.description,
            status=new_report.status,
            created_at=new_report.created_at,
            updated_at=new_report.updated_at,
            contestant_title=contestant.title,
            contestant_author_name=author_name,
            contest_name=contest.name
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating report: {str(e)}"
    )
