#!/usr/bin/env python
"""
Script pour créer un concours de test en base de données.
"""

from app.db.session import SessionLocal
from app.models.contest import Contest, VotingRestriction
from datetime import date, timedelta

def create_test_contest():
    """Crée un concours de test."""
    db = SessionLocal()
    
    try:
        # Vérifier s'il existe déjà un concours
        existing = db.query(Contest).first()
        if existing:
            print(f"✅ Il y a déjà {db.query(Contest).count()} concours en base de données")
            for contest in db.query(Contest).all():
                print(f"  - {contest.name} (ID: {contest.id})")
            return
        
        # Créer un concours de test
        today = date.today()
        test_contest = Contest(
            name="Concours de Beauté 2024",
            description="Un concours de beauté pour tester le système",
            contest_type="beauty",
            level="city",
            is_active=True,
            is_submission_open=True,
            is_voting_open=False,
            submission_start_date=today,
            submission_end_date=today + timedelta(days=30),
            voting_start_date=today + timedelta(days=31),
            voting_end_date=today + timedelta(days=61),
            cover_image_url="https://via.placeholder.com/300x200?text=Beauty+Contest",
            image_url="https://via.placeholder.com/300x200?text=Beauty+Contest",
            voting_restriction=VotingRestriction.NONE
        )
        
        db.add(test_contest)
        db.commit()
        db.refresh(test_contest)
        
        print(f"✅ Concours de test créé avec succès!")
        print(f"  - ID: {test_contest.id}")
        print(f"  - Nom: {test_contest.name}")
        print(f"  - Type: {test_contest.contest_type}")
        print(f"  - Niveau: {test_contest.level}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Erreur lors de la création du concours: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    create_test_contest()
