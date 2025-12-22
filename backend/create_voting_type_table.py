"""
Script pour créer la table voting_type si elle n'existe pas
"""
import sys
import os

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from app.core.config import settings

def table_exists(engine, table_name):
    """Vérifie si une table existe"""
    insp = inspect(engine)
    return table_name in insp.get_table_names()

def column_exists(engine, table_name, column_name):
    """Vérifie si une colonne existe dans une table"""
    if not table_exists(engine, table_name):
        return False
    insp = inspect(engine)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns

def create_voting_type_table():
    """Crée la table voting_type si elle n'existe pas"""
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    
    with engine.connect() as conn:
        # Créer les types ENUM si ils n'existent pas
        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE votinglevel AS ENUM ('city', 'country', 'regional', 'continent', 'global');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        
        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE commissionsource AS ENUM ('advert', 'affiliate', 'kyc', 'MFM');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        
        conn.commit()
        
        # Créer la table voting_type si elle n'existe pas
        if not table_exists(engine, 'voting_type'):
            print("Création de la table voting_type...")
            conn.execute(text("""
                CREATE TABLE voting_type (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    voting_level votinglevel NOT NULL,
                    commission_rules JSON,
                    commission_source commissionsource NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.commit()
            print("Table voting_type créée avec succès!")
        else:
            print("La table voting_type existe déjà.")
        
        # Ajouter la colonne voting_type_id à contest si elle n'existe pas
        if not column_exists(engine, 'contest', 'voting_type_id'):
            print("Ajout de la colonne voting_type_id à la table contest...")
            conn.execute(text("""
                ALTER TABLE contest 
                ADD COLUMN voting_type_id INTEGER
            """))
            conn.commit()
            print("Colonne voting_type_id ajoutée avec succès!")
        else:
            print("La colonne voting_type_id existe déjà dans contest.")
        
        # Créer la clé étrangère si elle n'existe pas
        try:
            conn.execute(text("""
                ALTER TABLE contest 
                ADD CONSTRAINT fk_contest_voting_type 
                FOREIGN KEY (voting_type_id) 
                REFERENCES voting_type(id) 
                ON DELETE SET NULL
            """))
            conn.commit()
            print("Clé étrangère fk_contest_voting_type créée avec succès!")
        except Exception as e:
            if 'already exists' in str(e) or 'duplicate' in str(e).lower():
                print("La clé étrangère fk_contest_voting_type existe déjà.")
            else:
                print(f"Erreur lors de la création de la clé étrangère: {e}")

if __name__ == "__main__":
    try:
        create_voting_type_table()
        print("\n✅ Migration terminée avec succès!")
    except Exception as e:
        print(f"\n❌ Erreur lors de la migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

