from typing import List, Optional, Union, Dict, Any
import re
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date, datetime, timedelta
import calendar


from fastapi.encoders import jsonable_encoder

# Removed CRUDBase import as it does not exist
# from app.crud.base import CRUDBase
from app.models.round import Round, RoundStatus
from app.models.contest import Contest
from app.schemas.round import RoundCreate, RoundUpdate

class CRUDRound:
    def get(self, db: Session, id: int) -> Optional[Round]:
        return db.query(Round).filter(Round.id == id).first()

    def update(
        self,
        db: Session,
        *,
        db_obj: Round,
        obj_in: Union[RoundUpdate, Dict[str, Any]]
    ) -> Round:
        obj_data = jsonable_encoder(db_obj)
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.dict(exclude_unset=True)
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def calculate_dates_for_month(self, month: int, year: int, is_nomination: bool = False) -> Dict[str, date]:
        """
        Calcule toutes les dates pour un round donné (mois/année).
        Logique: Les dates sont fixées par le calendrier.
        
        Participation:
        - Submission: 1er au dernier jour du mois M
        - Voting: 1er au dernier jour du mois M+1
        - City Season: 1er au dernier jour du mois M+2
        - Country Season: 1er au dernier jour du mois M+3
        - Regional Season: 1er au dernier jour du mois M+4
        - Global Season: 1er au dernier jour du mois M+5 (Skip Continent)
        
        Nomination:
        - Submission: 1er au dernier jour du mois M
        - Voting: 1er au dernier jour du mois M+1
        - Country Season (Start): 1er au dernier jour du mois M+1 ou M+2 (selon logique, ici disons M+2 pour aligner)
          (NOTE: Nomination starts at Country directly after voting/submission)
        - Regional Season: M+3
        - Continent Season: M+4
        - Global Season: M+5
        """
        
        def get_month_range(m, y):
            # Gérer le débordement d'année
            while m > 12:
                m -= 12
                y += 1
            last_day = calendar.monthrange(y, m)[1]
            return date(y, m, 1), date(y, m, last_day)

        dates = {}
        
        # Submission (Mois M)
        s_start, s_end = get_month_range(month, year)
        dates["submission_start_date"] = s_start
        # Add 32 days to submission end date for both nominations and participations
        s_end = s_end + timedelta(days=32)
        dates["submission_end_date"] = s_end
        
        # Voting (Mois M+1)
        v_start, v_end = get_month_range(month + 1, year)
        dates["voting_start_date"] = v_start
        dates["voting_end_date"] = v_end
        
        # Seasons
        # City (M+2) - Participation Only
        c_start, c_end = get_month_range(month + 2, year)
        dates["city_season_start_date"] = c_start
        dates["city_season_end_date"] = c_end
        
        # Country (M+3)
        cty_start, cty_end = get_month_range(month + 3, year)
        dates["country_season_start_date"] = cty_start
        dates["country_season_end_date"] = cty_end

        # Regional (M+4)
        reg_start, reg_end = get_month_range(month + 4, year)
        dates["regional_start_date"] = reg_start
        dates["regional_end_date"] = reg_end

        # Continent (M+5)
        cont_start, cont_end = get_month_range(month + 5, year)
        dates["continental_start_date"] = cont_start
        dates["continental_end_date"] = cont_end
        
        # Global (M+6)
        glob_start, glob_end = get_month_range(month + 6, year)
        dates["global_start_date"] = glob_start
        dates["global_end_date"] = glob_end
        
        return dates

    def create_with_contest(self, db: Session, obj_in: RoundCreate, contest_id: int = None) -> Round:
        """
        Creates a round and automatically calculates dates based on the start month 
        derived from the name or current date if not provided.
        """
        # Logic to parse month from Name "Round January 2026" or use current month
        
        name_parts = obj_in.name.split() # expecting "Round January 2026"
        target_month = datetime.now().month
        target_year = datetime.now().year
        
        try:
             # Flexible parsing: iterate parts
             for part in name_parts:
                 if part.isdigit() and len(part) == 4:
                     target_year = int(part)
                 else:
                     # try parsing month name
                     try:
                         # try english
                         m = datetime.strptime(part, "%B").month
                         target_month = m
                     except:
                         try:
                             # try french
                             # basic mapping or locale
                             fr_months = {"janvier":1,"février":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,"août":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12}
                             if part.lower() in fr_months:
                                 target_month = fr_months[part.lower()]
                         except:
                             pass
        except:
            pass
            
        # Check contest type
        cid = contest_id if contest_id else obj_in.contest_id
        contest = db.query(Contest).filter(Contest.id == cid).first()
        is_nomination = (contest.contest_mode == "nomination") if contest else False
        
        # Calculate dates if not provided
        computed_dates = self.calculate_dates_for_month(target_month, target_year, is_nomination)
        
        db_obj = Round(
            contest_id=cid,
            name=obj_in.name,
            status=obj_in.status if obj_in.status else RoundStatus.UPCOMING,
            # Merging computed dates with explicitly provided ones (explicit takes precedence)
            submission_start_date=obj_in.submission_start_date or computed_dates["submission_start_date"],
            submission_end_date=obj_in.submission_end_date or computed_dates["submission_end_date"],
            voting_start_date=obj_in.voting_start_date or computed_dates["voting_start_date"],
            voting_end_date=obj_in.voting_end_date or computed_dates["voting_end_date"],
            city_season_start_date=obj_in.city_season_start_date or computed_dates["city_season_start_date"],
            city_season_end_date=obj_in.city_season_end_date or computed_dates["city_season_end_date"],
            country_season_start_date=obj_in.country_season_start_date or computed_dates["country_season_start_date"],
            country_season_end_date=obj_in.country_season_end_date or computed_dates["country_season_end_date"],
            regional_start_date=obj_in.regional_start_date or computed_dates["regional_start_date"],
            regional_end_date=obj_in.regional_end_date or computed_dates["regional_end_date"],
            continental_start_date=obj_in.continental_start_date or computed_dates["continental_start_date"],
            continental_end_date=obj_in.continental_end_date or computed_dates["continental_end_date"],
            global_start_date=obj_in.global_start_date or computed_dates["global_start_date"],
            global_end_date=obj_in.global_end_date or computed_dates["global_end_date"],
        )
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def is_round_linked_to_contest(self, db: Session, contest_id: int, round_id: int) -> bool:
        """True if this round is linked to the contest (N:N or legacy contest_id)."""
        from app.models.round import round_contests
        linked = db.query(round_contests.c.round_id).filter(
            round_contests.c.contest_id == contest_id,
            round_contests.c.round_id == round_id,
        ).first()
        if linked:
            return True
        legacy = db.query(Round).filter(
            Round.id == round_id,
            Round.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED,
        ).first()
        return legacy is not None

    def resolve_display_round_id_for_contest(
        self,
        db: Session,
        contest_id: int,
        round_id: Optional[int],
        *,
        prefer_nomination_submit_round: bool = False,
        current_user_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Which calendar round to use when listing contestants for a contest.

        - If the client passes an explicit ``round_id``, it is honored by default.
        - For **nomination** contests (``prefer_nomination_submit_round``), if the URL round is
          a stale voting-era scope (e.g. almost no nomination rows) while the canonical nomination
          round has more activity, the explicit ``round_id`` is replaced so redeploys and old
          ``?roundId=`` links still show the right roster.
        - If ``round_id`` is omitted and ``prefer_nomination_submit_round`` is True, prefer the
          current submission month (``get_preferred_nomination_round_for_contest``), then any
          submission window open today, then the latest ``round_id`` among nomination rows, before
          falling back to voting/submission date heuristics — so the API does not stick to an older
          **voting** round when May nominations live in another calendar round.
        - Otherwise (participation): voting window > submission window > most recent started.
        """
        if round_id is not None:
            if not self.is_round_linked_to_contest(db, contest_id, round_id):
                import logging

                logging.getLogger(__name__).warning(
                    "round_id=%s is not linked to contest_id=%s in round_contests; "
                    "using requested round anyway for contestant scope (URL roundId).",
                    round_id,
                    contest_id,
                )
            if prefer_nomination_submit_round:
                canonical = self.resolve_display_round_id_for_contest(
                    db,
                    contest_id,
                    None,
                    prefer_nomination_submit_round=True,
                    current_user_id=current_user_id,
                )
                if canonical is not None and canonical != round_id:
                    from app.models.contests import Contestant

                    # Align with roster counts: legacy rows may have entry_type NULL for nominations.
                    _nom_row = or_(
                        Contestant.entry_type == "nomination",
                        Contestant.entry_type.is_(None),
                    )
                    ne = (
                        db.query(func.count(Contestant.id))
                        .filter(
                            Contestant.season_id == contest_id,
                            Contestant.is_deleted == False,
                            _nom_row,
                            Contestant.round_id == round_id,
                        )
                        .scalar()
                    ) or 0
                    nc = (
                        db.query(func.count(Contestant.id))
                        .filter(
                            Contestant.season_id == contest_id,
                            Contestant.is_deleted == False,
                            _nom_row,
                            Contestant.round_id == canonical,
                        )
                        .scalar()
                    ) or 0
                    # Only jump to canonical when the requested round has *no* nominations.
                    # (ne <= 1 and nc > ne) replaced URL rounds that still had real rows — users saw
                    # another month's roster while ?roundId= pointed at the previous period.)
                    if ne == 0 and nc > 0:
                        if current_user_id:
                            mine_in_requested = (
                                db.query(Contestant.id)
                                .filter(
                                    Contestant.season_id == contest_id,
                                    Contestant.user_id == current_user_id,
                                    Contestant.is_deleted == False,
                                    _nom_row,
                                    Contestant.round_id == round_id,
                                )
                                .first()
                            )
                            if mine_in_requested:
                                return round_id
                        return canonical
            return round_id

        if prefer_nomination_submit_round:
            if current_user_id:
                from app.models.contests import Contestant

                _nom_row = or_(
                    Contestant.entry_type == "nomination",
                    Contestant.entry_type.is_(None),
                )
                latest_user_round = (
                    db.query(Contestant.round_id)
                    .filter(
                        Contestant.season_id == contest_id,
                        Contestant.user_id == current_user_id,
                        Contestant.is_deleted == False,
                        _nom_row,
                        Contestant.round_id.isnot(None),
                    )
                    .order_by(Contestant.registration_date.desc(), Contestant.id.desc())
                    .first()
                )
                if latest_user_round and latest_user_round[0] is not None:
                    return int(latest_user_round[0])

            pref = self.get_preferred_nomination_round_for_contest(db, contest_id)
            if pref is not None:
                return pref.id
            active_sub = self.get_active_round_for_contest(db, contest_id)
            if active_sub is not None:
                return active_sub.id
            from app.models.contests import Contestant

            max_rid = (
                db.query(func.max(Contestant.round_id))
                .filter(
                    Contestant.season_id == contest_id,
                    Contestant.is_deleted == False,
                    Contestant.entry_type == "nomination",
                    Contestant.round_id.isnot(None),
                )
                .scalar()
            )
            if max_rid is not None:
                return int(max_rid)

        rounds = self.get_rounds_for_contest(db, contest_id)
        if not rounds:
            return None
        today = date.today()
        for r in rounds:
            if r.voting_start_date and r.voting_end_date:
                if r.voting_start_date <= today <= r.voting_end_date:
                    return r.id
        for r in rounds:
            if r.submission_start_date and r.submission_end_date:
                if r.submission_start_date <= today <= r.submission_end_date:
                    return r.id
        started = [r for r in rounds if r.submission_start_date and r.submission_start_date <= today]
        if started:
            return max(started, key=lambda x: x.submission_start_date).id
        return rounds[0].id

    def get_active_round_for_contest(self, db: Session, contest_id: int) -> Optional[Round]:
        """
        Trouve le round actif pour l'inscription (submission_start <= now <= submission_end)
        FIXED: Uses new N:N relationship via round_contests table
        """
        from app.models.round import round_contests
        now = date.today()
        
        # Query via N:N relationship — prefer the **latest** submission window that still
        # includes today so May wins over April when both are open (matches dashboard pills).
        round_obj = db.query(Round).join(
            round_contests, Round.id == round_contests.c.round_id
        ).filter(
            round_contests.c.contest_id == contest_id,
            Round.submission_start_date <= now,
            Round.submission_end_date >= now,
            Round.status != RoundStatus.CANCELLED
        ).order_by(Round.submission_start_date.desc()).first()
        
        # Fallback to legacy contest_id field
        if not round_obj:
            round_obj = db.query(Round).filter(
                Round.contest_id == contest_id,
                Round.submission_start_date <= now,
                Round.submission_end_date >= now,
                Round.status != RoundStatus.CANCELLED
            ).order_by(Round.submission_start_date.desc()).first()
        
        return round_obj

    def get_preferred_nomination_round_for_contest(self, db: Session, contest_id: int) -> Optional[Round]:
        """
        Among rounds linked to this contest with submission open today, prefer the one whose
        title starts with the current English month + year (same idea as the dashboard
        ``computeDisplayRounds`` nomination pill). Otherwise use the latest submission_start.
        """
        rounds = self.get_rounds_for_contest(db, contest_id)
        if not rounds:
            return None
        today = date.today()
        open_submit: List[Round] = []
        for r in rounds:
            if r.status == RoundStatus.CANCELLED:
                continue
            if not r.submission_start_date or not r.submission_end_date:
                continue
            if r.submission_start_date <= today <= r.submission_end_date:
                open_submit.append(r)
        if not open_submit:
            return None
        label = f"{calendar.month_name[today.month]} {today.year}".lower()

        def title_starts_current_month(name: Optional[str]) -> bool:
            if not name or not name.strip():
                return False
            n = (
                name.lower()
                .strip()
            )
            n = re.sub(r"^\s*(round|season)\s*#?\d*\s*[:-–—]?\s*", "", n, flags=re.I).strip()
            return n.startswith(label)

        for r in sorted(open_submit, key=lambda x: x.submission_start_date or today, reverse=True):
            if title_starts_current_month(r.name):
                return r
        return max(open_submit, key=lambda x: x.submission_start_date or date.min)

    def get_rounds_for_contest(self, db: Session, contest_id: int) -> List[Round]:
        """
        Récupère tous les rounds d'un contest, triés par date de début
        FIXED: Uses new N:N relationship via round_contests table
        """
        from app.models.round import round_contests
        # Query rounds via the N:N relationship table
        rounds = db.query(Round).join(
            round_contests, Round.id == round_contests.c.round_id
        ).filter(
            round_contests.c.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED
        ).order_by(Round.submission_start_date.asc()).all()
        
        # Also check legacy contest_id field for backward compatibility
        legacy_rounds = db.query(Round).filter(
            Round.contest_id == contest_id,
            Round.status != RoundStatus.CANCELLED
        ).order_by(Round.submission_start_date.asc()).all()
        
        # Combine and deduplicate
        round_ids = {r.id for r in rounds}
        for r in legacy_rounds:
            if r.id not in round_ids:
                rounds.append(r)
        
        return rounds

    def count_participants_for_round(
        self, db: Session, round_id: int, contest_id: Optional[int] = None
    ) -> int:
        """
        Count contestants for a calendar round. When ``contest_id`` is set, only rows
        with ``Contestant.season_id == contest_id`` are counted (contest rows use season_id
        as contest id). Shared rounds must not mix nominations across contests.
        """
        from app.models.contests import Contestant
        q = db.query(func.count(Contestant.id)).filter(
            Contestant.round_id == round_id,
            Contestant.is_deleted == False,
        )
        if contest_id is not None:
            q = q.filter(Contestant.season_id == contest_id)
        return q.scalar() or 0

    def user_participated_in_round(self, db: Session, round_id: int, user_id: int) -> bool:
        """
        Vérifie si un utilisateur a déjà participé à un round
        """
        # We need to find if there is any Contestant for the active round.
        # We'll check all contests in this round using the duplicate checker.
        round_obj = self.get(db, round_id)
        if not round_obj or not hasattr(round_obj, 'contests') or not round_obj.contests:
            return False
            
        from app.models.contests import ContestSeason
        from app.crud import contestant as crud_contestant
        
        for c in round_obj.contests:
            # Check if this contest is linked to a season
            season = db.query(ContestSeason).filter(
                ContestSeason.id == c.id,
                ContestSeason.is_deleted == False
            ).first()
            
            season_id = season.id if season else c.id
            existing = crud_contestant.get_by_season_and_user(db, season_id, user_id)
            if existing:
                return True
                
        return False

    def calculate_current_season_level(self, round_obj: Round) -> Optional[str]:
        """
        Calcule le niveau de saison actuel basé sur les dates du round
        """
        today = date.today()
        
        if round_obj.global_start_date and round_obj.global_end_date:
            if round_obj.global_start_date <= today <= round_obj.global_end_date:
                return "global"
        
        if round_obj.continental_start_date and round_obj.continental_end_date:
            if round_obj.continental_start_date <= today <= round_obj.continental_end_date:
                return "continental"
        
        if round_obj.regional_start_date and round_obj.regional_end_date:
            if round_obj.regional_start_date <= today <= round_obj.regional_end_date:
                return "regional"
        
        if round_obj.country_season_start_date and round_obj.country_season_end_date:
            if round_obj.country_season_start_date <= today <= round_obj.country_season_end_date:
                return "country"
        
        if round_obj.city_season_start_date and round_obj.city_season_end_date:
            if round_obj.city_season_start_date <= today <= round_obj.city_season_end_date:
                return "city"
        
        # Si on est dans la période de soumission/vote
        if round_obj.submission_start_date and round_obj.submission_end_date:
            if round_obj.submission_start_date <= today <= round_obj.submission_end_date:
                return "submission"
        
        if round_obj.voting_start_date and round_obj.voting_end_date:
            if round_obj.voting_start_date <= today <= round_obj.voting_end_date:
                return "voting"
        
        return None

    def is_round_completed(self, round_obj: Round) -> bool:
        """
        Vérifie si un round est complété (global_end_date passée)
        """
        if round_obj.global_end_date:
            return date.today() > round_obj.global_end_date
        return False

    def get_rounds_with_stats(
        self, db: Session, contest_id: int, user_id: Optional[int] = None
    ) -> List[dict]:
        """
        Récupère tous les rounds d'un contest avec leurs statistiques
        """
        rounds = self.get_rounds_for_contest(db, contest_id)
        result = []
        
        for r in rounds:
            participants_count = self.count_participants_for_round(db, r.id, contest_id=contest_id)
            current_user_participated = False
            if user_id:
                current_user_participated = self.user_participated_in_round(db, r.id, user_id)
            
            current_season_level = self.calculate_current_season_level(r)
            is_completed = self.is_round_completed(r)
            
            result.append({
                "id": r.id,
                "contest_id": r.contest_id,
                "name": r.name,
                "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                "is_submission_open": r.is_submission_open,
                "is_voting_open": r.is_voting_open,
                "current_season_level": current_season_level or r.current_season_level,
                "submission_start_date": r.submission_start_date,
                "submission_end_date": r.submission_end_date,
                "voting_start_date": r.voting_start_date,
                "voting_end_date": r.voting_end_date,
                "city_season_start_date": r.city_season_start_date,
                "city_season_end_date": r.city_season_end_date,
                "country_season_start_date": r.country_season_start_date,
                "country_season_end_date": r.country_season_end_date,
                "regional_start_date": r.regional_start_date,
                "regional_end_date": r.regional_end_date,
                "continental_start_date": r.continental_start_date,
                "continental_end_date": r.continental_end_date,
                "global_start_date": r.global_start_date,
                "global_end_date": r.global_end_date,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "participants_count": participants_count,
                "current_user_participated": current_user_participated,
                "is_completed": is_completed,
            })
        
        return result


round = CRUDRound()
