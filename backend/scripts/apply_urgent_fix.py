#!/usr/bin/env python3
"""
Script d'urgence pour ajouter les colonnes manquantes à la base de données.
À exécuter manuellement si les migrations Alembic ne peuvent pas être appliquées.
"""
import sys
import os

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.db.session import SessionLocal
from app.core.config import settings

def apply_urgent_fix():
    """Applique les corrections d'urgence à la base de données."""
    db = SessionLocal()
    try:
        bind = db.bind
        insp = inspect(bind)
        
        print("🔧 Application des corrections d'urgence...")
        
        # Créer les ENUM types
        print("📝 Création des types ENUM...")
        bind.execute(text("""
            DO $$ BEGIN
                CREATE TYPE votinglevel AS ENUM ('city', 'country', 'regional', 'continent', 'global');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        
        bind.execute(text("""
            DO $$ BEGIN
                CREATE TYPE commissionsource AS ENUM ('advert', 'affiliate', 'kyc', 'MFM');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✅ Types ENUM créés")
        
        # Créer la table voting_type
        if 'voting_type' not in insp.get_table_names():
            print("📝 Création de la table voting_type...")
            bind.execute(text("""
                CREATE TABLE voting_type (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    voting_level votinglevel NOT NULL,
                    commission_rules JSONB,
                    commission_source commissionsource NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """))
            print("✅ Table voting_type créée")
        else:
            print("ℹ️  Table voting_type existe déjà")
        
        # Ajouter les colonnes manquantes à contest
        if 'contest' in insp.get_table_names():
            columns = [c['name'] for c in insp.get_columns('contest')]
            
            if 'cover_image_url' not in columns:
                print("📝 Ajout de la colonne cover_image_url...")
                bind.execute(text("ALTER TABLE contest ADD COLUMN cover_image_url VARCHAR(500)"))
                print("✅ Colonne cover_image_url ajoutée")
            else:
                print("ℹ️  Colonne cover_image_url existe déjà")
            
            if 'voting_type_id' not in columns:
                print("📝 Ajout de la colonne voting_type_id...")
                bind.execute(text("ALTER TABLE contest ADD COLUMN voting_type_id INTEGER"))
                print("✅ Colonne voting_type_id ajoutée")
            else:
                print("ℹ️  Colonne voting_type_id existe déjà")
            
            # Ajouter la contrainte de clé étrangère
            print("📝 Vérification de la contrainte de clé étrangère...")
            bind.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints 
                        WHERE constraint_name = 'fk_contest_voting_type'
                    ) THEN
                        ALTER TABLE contest 
                        ADD CONSTRAINT fk_contest_voting_type 
                        FOREIGN KEY (voting_type_id) REFERENCES voting_type(id) ON DELETE SET NULL;
                    END IF;
                END $$;
            """))
            print("✅ Contrainte de clé étrangère vérifiée")
        
        db.commit()
        print("\n✅ Corrections d'urgence appliquées avec succès!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Erreur lors de l'application des corrections: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print(f"🔗 Connexion à la base de données: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'masqué'}")
    apply_urgent_fix()

