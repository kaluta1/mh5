#!/usr/bin/env python
"""
Script pour corriger le type de la colonne voting_restriction.
"""

from app.db.session import engine
from sqlalchemy import text

def fix_contest_enum():
    """Corrige le type de la colonne voting_restriction."""
    with engine.connect() as conn:
        try:
            # Supprimer la colonne voting_restriction
            conn.execute(text("""
                ALTER TABLE contest 
                DROP COLUMN IF EXISTS voting_restriction
            """))
            print("✅ Colonne voting_restriction supprimée")
            
            # Créer le type ENUM
            conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE votingrestriction AS ENUM ('NONE', 'MALE_ONLY', 'FEMALE_ONLY', 'GEOGRAPHIC', 'AGE_RESTRICTED');
                EXCEPTION WHEN duplicate_object THEN null;
                END $$;
            """))
            print("✅ Type ENUM votingrestriction créé")
            
            # Ajouter la colonne avec le bon type
            conn.execute(text("""
                ALTER TABLE contest 
                ADD COLUMN voting_restriction votingrestriction DEFAULT 'NONE'
            """))
            print("✅ Colonne voting_restriction ajoutée avec le bon type")
            
            conn.commit()
            print("✅ Correction complétée avec succès!")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Erreur lors de la correction: {str(e)}")

if __name__ == "__main__":
    fix_contest_enum()
