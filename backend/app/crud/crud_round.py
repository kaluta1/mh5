from typing import List, Optional, Union, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
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
        is_nomination = contest.voting_type_id is not None if contest else False
        
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

    def get_active_round_for_contest(self, db: Session, contest_id: int) -> Optional[Round]:
        """
        Trouve le round actif pour l'inscription (submission_start <= now <= submission_end)
        """
        now = date.today()
        return db.query(Round).filter(
            Round.contest_id == contest_id,
            Round.submission_start_date <= now,
            Round.submission_end_date >= now,
            Round.status != RoundStatus.CANCELLED
        ).first()


round = CRUDRound()
