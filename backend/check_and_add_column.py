#!/usr/bin/env python
"""
Script pour vérifier et ajouter la colonne participant_count à la table contest.
"""

from app.db.session import engine
from sqlalchemy import text, inspect

def check_and_add_column():
    """Vérifie et ajoute la colonne participant_count si elle n'existe pas."""
    with engine.connect() as conn:
        try:
            # Vérifier si la colonne existe
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('contest')]
            
            print(f"Colonnes existantes dans 'contest': {columns}")
            
            if 'participant_count' in columns:
                print("✅ La colonne participant_count existe déjà")
                return
            
            # Ajouter la colonne
            print("Ajout de la colonne participant_count...")
            conn.execute(text("""
                ALTER TABLE contest 
                ADD COLUMN participant_count INTEGER NOT NULL DEFAULT 0
            """))
            conn.commit()
            print("✅ Colonne participant_count ajoutée avec succès!")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ Erreur: {str(e)}")

if __name__ == "__main__":
    check_and_add_column()
