#!/usr/bin/env python
"""
Script pour ajouter la colonne participant_count à la table contest.
"""

from app.db.session import engine
from sqlalchemy import text

def add_participant_count():
    """Ajoute la colonne participant_count à la table contest."""
    with engine.connect() as conn:
        try:
            # Ajouter la colonne participant_count
            conn.execute(text("""
                ALTER TABLE contest 
                ADD COLUMN IF NOT EXISTS participant_count INTEGER DEFAULT 0 NOT NULL
            """))
            print("✅ Colonne participant_count ajoutée")
            
            conn.commit()
            print("✅ Migration complétée avec succès!")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Erreur lors de la migration: {str(e)}")

if __name__ == "__main__":
    add_participant_count()
