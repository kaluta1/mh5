#!/usr/bin/env python3
"""
Script pour créer la table suggested_contest dans la base de données PostgreSQL.
Ce script peut être exécuté directement sans passer par Alembic.
"""
import os
import sys
import psycopg
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Récupérer les informations de connexion depuis les variables d'environnement
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Essayer de construire l'URL depuis les variables individuelles
    DB_USER = os.getenv("POSTGRES_USER", "postgres")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    DB_HOST = os.getenv("POSTGRES_SERVER", "localhost")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB", "myfav")
    
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def create_table():
    """Créer la table suggested_contest et le type ENUM"""
    try:
        print("Connexion à la base de données...")
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Créer le type ENUM pour le statut si il n'existe pas
                print("Création du type ENUM suggestedconteststatus...")
                cur.execute("""
                    DO $$ BEGIN
                        CREATE TYPE suggestedconteststatus AS ENUM ('pending', 'approved', 'rejected');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
                
                # Vérifier si la table existe déjà
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'suggested_contest'
                    );
                """)
                table_exists = cur.fetchone()[0]
                
                if table_exists:
                    print("La table suggested_contest existe déjà.")
                    return
                
                # Créer la table suggested_contest
                print("Création de la table suggested_contest...")
                cur.execute("""
                    CREATE TABLE suggested_contest (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        category VARCHAR(100) NOT NULL,
                        status suggestedconteststatus NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                
                conn.commit()
                print("✅ Table suggested_contest créée avec succès!")
                
    except psycopg.Error as e:
        print(f"❌ Erreur lors de la création de la table: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        sys.exit(1)

if __name__ == "__main__":
    create_table()

