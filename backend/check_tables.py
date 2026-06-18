#!/usr/bin/env python3
"""
Script pour vérifier les tables dans la base de données Neon
"""
import os
import sys
from sqlalchemy import create_engine, text
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL or DATABASE_URL == "postgresql://user:password@localhost/myhigh5":
    print(
        "ERROR: DATABASE_URL is not set. Please set DATABASE_URL in backend/.env.",
        file=sys.stderr,
    )
    sys.exit(2)

def check_tables():
    try:
        # Créer la connexion
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            # Vérifier les tables
            result = conn.execute(text("""
                SELECT table_name, table_type 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """))
            
            tables = result.fetchall()
            
            print(f"🔍 Nombre de tables trouvées: {len(tables)}")
            print("\n📋 Liste des tables:")
            
            if tables:
                for table in tables:
                    print(f"  ✓ {table[0]} ({table[1]})")
            else:
                print("  ❌ Aucune table trouvée dans le schéma 'public'")
            
            # Vérifier les migrations Alembic
            print("\n🔧 Vérification des migrations Alembic:")
            try:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.fetchone()
                if version:
                    print(f"  ✓ Version actuelle: {version[0]}")
                else:
                    print("  ❌ Aucune version de migration trouvée")
            except Exception as e:
                print(f"  ❌ Table alembic_version non trouvée: {e}")
            
            # Vérifier quelques tables clés
            key_tables = ['users', 'contest', 'contest_entry', 'media', 'comment']
            print("\n🎯 Vérification des tables clés:")
            
            for table_name in key_tables:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}' AND table_schema = 'public'"))
                    count = result.fetchone()[0]
                    if count > 0:
                        print(f"  ✓ {table_name} existe")
                    else:
                        print(f"  ❌ {table_name} manquante")
                except Exception as e:
                    print(f"  ❌ Erreur pour {table_name}: {e}")
                    
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Vérification des tables dans Neon...")
    check_tables()
