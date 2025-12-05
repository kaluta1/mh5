#!/usr/bin/env python
"""
Script pour ajouter les colonnes manquantes à la table contest.
"""

from app.db.session import engine
from sqlalchemy import text

def migrate_contest_table():
    """Ajoute les colonnes manquantes à la table contest."""
    with engine.connect() as conn:
        try:
            # Ajouter la colonne voting_restriction
            conn.execute(text("""
                ALTER TABLE contest 
                ADD COLUMN IF NOT EXISTS voting_restriction VARCHAR(20) DEFAULT 'none'
            """))
            print("✅ Colonne voting_restriction ajoutée")
            
            # Ajouter la colonne image_url
            conn.execute(text("""
                ALTER TABLE contest 
                ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)
            """))
            print("✅ Colonne image_url ajoutée")
            
            conn.commit()
            print("✅ Migration complétée avec succès!")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Erreur lors de la migration: {str(e)}")

if __name__ == "__main__":
    migrate_contest_table()
