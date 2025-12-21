"""
Script pour ajouter manuellement la colonne voting_type_id à la table contest
si la migration Alembic a échoué partiellement.
"""
import sys
import os

# Ajouter le répertoire parent au PYTHONPATH
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from sqlalchemy import text, inspect, create_engine
from app.db.session import SessionLocal
from app.core.config import settings

def column_exists(engine, table_name, column_name):
    """Vérifie si une colonne existe dans une table"""
    insp = inspect(engine)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns

def table_exists(engine, table_name):
    """Vérifie si une table existe"""
    insp = inspect(engine)
    return table_name in insp.get_table_names()

def main():
    # Créer un engine pour les opérations de schéma
    engine = create_engine(settings.DATABASE_URL)
    db = SessionLocal()
    try:
        
        # Vérifier si la colonne existe déjà
        if column_exists(engine, 'contest', 'voting_type_id'):
            print("✓ La colonne voting_type_id existe déjà dans la table contest")
            return
        
        print("Ajout de la colonne voting_type_id à la table contest...")
        
        # Ajouter la colonne
        db.execute(text("ALTER TABLE contest ADD COLUMN voting_type_id INTEGER"))
        
        # Vérifier si la table voting_type existe avant de créer la clé étrangère
        if table_exists(engine, 'voting_type'):
            print("Création de la clé étrangère...")
            # Vérifier si la contrainte existe déjà
            result = db.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'contest' 
                AND constraint_name = 'fk_contest_voting_type'
            """))
            if not result.fetchone():
                db.execute(text("""
                    ALTER TABLE contest 
                    ADD CONSTRAINT fk_contest_voting_type 
                    FOREIGN KEY (voting_type_id) 
                    REFERENCES voting_type(id) 
                    ON DELETE SET NULL
                """))
                print("✓ Clé étrangère créée")
            else:
                print("✓ La clé étrangère existe déjà")
        else:
            print("⚠ La table voting_type n'existe pas encore. La clé étrangère ne sera pas créée.")
            print("  Exécutez d'abord la migration Alembic pour créer la table voting_type.")
        
        db.commit()
        print("✓ Colonne voting_type_id ajoutée avec succès!")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Erreur: {e}")
        raise
    finally:
        db.close()
        engine.dispose()

if __name__ == "__main__":
    main()

