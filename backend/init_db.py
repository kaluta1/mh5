#!/usr/bin/env python
"""
Script pour initialiser les tables de la base de données.
À exécuter une seule fois pour créer les tables manquantes.
"""

from app.db.session import engine
from app.db.base_class import Base

# Import all models to ensure they are registered with SQLAlchemy
import app.models

def init_db():
    """Crée toutes les tables définies dans les modèles."""
    print("Création des tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables créées avec succès!")

if __name__ == "__main__":
    init_db()
