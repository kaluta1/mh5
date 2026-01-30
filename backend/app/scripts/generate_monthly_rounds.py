"""
Script de génération automatique de rounds mensuels.
Crée un round pour tous les contests actifs au début de chaque mois.

Usage:
    python -m app.scripts.generate_monthly_rounds
    
Ou via l'API admin:
    POST /api/v1/admin/rounds/generate-monthly
"""

from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from calendar import monthrange
from sqlalchemy.orm import Session
from sqlalchemy import select, insert
from typing import Optional

from app.db.session import SessionLocal
from app.models.round import Round, RoundStatus, round_contests
from app.models.contest import Contest


def get_month_start(year: int, month: int) -> date:
    """Retourne le premier jour du mois."""
    return date(year, month, 1)


def get_month_end(year: int, month: int) -> date:
    """Retourne le dernier jour du mois."""
    _, last_day = monthrange(year, month)
    return date(year, month, last_day)


def get_next_month(current_date: date) -> tuple[int, int]:
    """Retourne (année, mois) du mois suivant."""
    next_date = current_date + relativedelta(months=1)
    return next_date.year, next_date.month


def generate_monthly_round(db: Session, target_date: Optional[date] = None) -> Round:
    """
    Génère un round mensuel pour tous les contests actifs.
    
    Args:
        db: Session de base de données
        target_date: Date cible (utilise la date actuelle si non spécifiée)
        
    Returns:
        Le round créé
    """
    if target_date is None:
        target_date = date.today()
    
    year = target_date.year
    month = target_date.month
    
    # Nom du round (ex: "Round February 2026")
    month_name = target_date.strftime("%B %Y")
    round_name = f"Round {month_name}"
    
    # Vérifier si un round existe déjà pour ce mois
    existing_round = db.query(Round).filter(
        Round.name == round_name
    ).first()
    
    if existing_round:
        print(f"Round '{round_name}' déjà existant (id={existing_round.id})")
        return existing_round
    
    # Calculer les dates
    # Submission: 1er au dernier jour du mois courant
    submission_start = get_month_start(year, month)
    submission_end = get_month_end(year, month)
    
    # Voting commence le mois suivant (M+1)
    next_year, next_month = get_next_month(submission_end)
    
    # City Season (M+1) - pour contests SANS voting_type_id
    city_start = get_month_start(next_year, next_month)
    city_end = get_month_end(next_year, next_month)
    
    # Country Season (M+1) - pour contests AVEC voting_type_id
    country_start = city_start
    country_end = city_end
    
    # Regional Season (M+2)
    m2_year, m2_month = get_next_month(city_end)
    regional_start = get_month_start(m2_year, m2_month)
    regional_end = get_month_end(m2_year, m2_month)
    
    # Continental Season (M+3)
    m3_year, m3_month = get_next_month(regional_end)
    continental_start = get_month_start(m3_year, m3_month)
    continental_end = get_month_end(m3_year, m3_month)
    
    # Global Season (M+4)
    m4_year, m4_month = get_next_month(continental_end)
    global_start = get_month_start(m4_year, m4_month)
    global_end = get_month_end(m4_year, m4_month)
    
    # Créer le round
    # FIXED: Create round with only required fields first, then add optional date fields
    try:
        # Use ACTIVE status (should exist in RoundStatus enum)
        status_value = RoundStatus.ACTIVE
        
        new_round = Round(
            name=round_name,
            status=status_value,
            is_submission_open=True,
            is_voting_open=False,
            current_season_level=None,  # Sera mis à jour quand le voting commence
        )
        
        # Add date fields using setattr to handle potential missing columns gracefully
        date_fields = {
            'submission_start_date': submission_start,
            'submission_end_date': submission_end,
            'voting_start_date': city_start,
            'voting_end_date': global_end,
            'city_season_start_date': city_start,
            'city_season_end_date': city_end,
            'country_season_start_date': country_start,
            'country_season_end_date': country_end,
            'regional_start_date': regional_start,
            'regional_end_date': regional_end,
            'continental_start_date': continental_start,
            'continental_end_date': continental_end,
            'global_start_date': global_start,
            'global_end_date': global_end,
        }
        
        # Set date fields if they exist in the model
        for field_name, field_value in date_fields.items():
            if hasattr(new_round, field_name):
                setattr(new_round, field_name, field_value)
            else:
                print(f"Warning: Round model doesn't have field {field_name}, skipping")
    except Exception as e:
        print(f"Error creating Round object: {e}")
        raise Exception(f"Failed to create Round object: {str(e)}") from e
    
    try:
        db.add(new_round)
        db.flush()  # Pour obtenir l'ID
        print(f"Round '{round_name}' created with ID: {new_round.id}")
    except Exception as e:
        print(f"Error creating round object: {e}")
        db.rollback()
        raise Exception(f"Failed to create round in database: {str(e)}") from e
    
    # Récupérer tous les contests actifs
    try:
        active_contests = db.query(Contest).filter(
            Contest.is_active == True
        ).all()
        print(f"Found {len(active_contests)} active contests")
        
        # Try to filter by is_deleted if column exists
        try:
            active_contests = [c for c in active_contests if not getattr(c, 'is_deleted', False)]
            print(f"After filtering is_deleted: {len(active_contests)} contests")
        except Exception as e:
            print(f"Warning: Could not filter by is_deleted: {e}")
            pass
    except Exception as e:
        print(f"Warning: Error filtering contests: {e}")
        # Fallback: get all contests
        try:
            active_contests = db.query(Contest).all()
            print(f"Fallback: Found {len(active_contests)} total contests")
        except Exception as e2:
            print(f"Error: Could not query contests at all: {e2}")
            active_contests = []
    
    # Associer tous les contests au round via la table de liaison
    linked_count = 0
    
    for contest in active_contests:
        try:
            # Check if link already exists
            existing_link = db.execute(
                select(round_contests).where(
                    round_contests.c.round_id == new_round.id,
                    round_contests.c.contest_id == contest.id
                )
            ).first()
            
            if not existing_link:
                # Insérer dans la table de liaison
                stmt = insert(round_contests).values(
                    round_id=new_round.id,
                    contest_id=contest.id
                )
                db.execute(stmt)
                linked_count += 1
        except Exception as e:
            print(f"Warning: Could not link contest {contest.id}: {e}")
            continue
    
    try:
        db.commit()
        print(f"Successfully committed round and {linked_count} contest links")
    except Exception as e:
        print(f"Error committing to database: {e}")
        db.rollback()
        raise Exception(f"Failed to commit round to database: {str(e)}") from e
    
    print(f"✅ Round '{round_name}' créé avec succès!")
    print(f"   - ID: {new_round.id}")
    print(f"   - Contests liés: {len(active_contests)}")
    print(f"   - Submission: {submission_start} → {submission_end}")
    print(f"   - City/Country: {city_start} → {city_end}")
    print(f"   - Regional: {regional_start} → {regional_end}")
    print(f"   - Continental: {continental_start} → {continental_end}")
    print(f"   - Global: {global_start} → {global_end}")
    
    return new_round


def main():
    """Point d'entrée principal pour exécution en ligne de commande."""
    print("=" * 50)
    print("Génération du round mensuel")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        round = generate_monthly_round(db)
        print(f"\n✅ Terminé! Round ID: {round.id}")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
