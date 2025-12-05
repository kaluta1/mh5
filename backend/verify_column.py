#!/usr/bin/env python
"""
Script pour vérifier directement en base de données.
"""

from app.db.session import engine
from sqlalchemy import text

def verify_column():
    """Vérifie la colonne directement en base."""
    with engine.connect() as conn:
        try:
            # Requête directe pour voir les colonnes
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'contest' 
                ORDER BY ordinal_position
            """))
            
            columns = [row[0] for row in result]
            print("Colonnes dans la table 'contest':")
            for col in columns:
                print(f"  - {col}")
            
            if 'participant_count' in columns:
                print("\n✅ La colonne participant_count existe!")
            else:
                print("\n❌ La colonne participant_count N'EXISTE PAS!")
                print("\nAjout de la colonne...")
                conn.execute(text("""
                    ALTER TABLE contest 
                    ADD COLUMN participant_count INTEGER NOT NULL DEFAULT 0
                """))
                conn.commit()
                print("✅ Colonne ajoutée!")
            
        except Exception as e:
            print(f"❌ Erreur: {str(e)}")

if __name__ == "__main__":
    verify_column()
