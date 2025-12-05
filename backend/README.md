# MyFav - Plateforme de Concours Modernes

MyFav est une plateforme multilingue de concours permettant aux utilisateurs de participer à différents types de concours (beauté, talents, etc.) avec un système de vote unique appelé "MyFav".

## Fonctionnalités

- **Gestion des utilisateurs**: Inscription, connexion, profils
- **Système de médias**: Upload et gestion de photos et vidéos
- **Concours**: Création, participation et vote dans divers types de concours
- **Système de vote MyFav**: Notation de 1 à 5 pour plusieurs participants
- **Hiérarchie géographique**: Concours du niveau local à international
- **Modération de contenu**: Système de signalement et modération

## Prérequis

- Python 3.8+
- PostgreSQL
- Redis (optionnel, pour les tâches asynchrones)

## Installation

1. Cloner le dépôt:
```bash
git clone https://github.com/votre-username/myhigh5.git
cd myhigh5
```

2. Créer un environnement virtuel:
```bash
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate
```

3. Installer les dépendances:
```bash
pip install -r requirements.txt
```

4. Configuration:
   - Créez une base de données PostgreSQL
   - Configurez les variables d'environnement (voir `.env.example`)

5. Initialiser la base de données:
```bash
alembic upgrade head
python -m app.initial_data
```

## Démarrage

```bash
uvicorn main:app --reload
```

L'API sera disponible à l'adresse: http://localhost:8000

La documentation de l'API est accessible à: http://localhost:8000/docs

## Structure du projet

```
myhigh5/
│
├── app/                    # Code source principal
│   ├── api/                # Définition des endpoints API
│   │   └── api_v1/         # Version 1 de l'API
│   ├── core/               # Configuration centrale
│   ├── crud/               # Opérations CRUD pour les modèles
│   ├── db/                 # Configuration de la base de données
│   ├── models/             # Modèles SQLAlchemy (tables DB)
│   └── schemas/            # Schémas Pydantic (validation)
│
├── migrations/             # Migrations Alembic
├── tests/                  # Tests unitaires et d'intégration
│
├── main.py                 # Point d'entrée de l'application
├── requirements.txt        # Dépendances Python
└── README.md               # Documentation
```

## API Endpoints

- `/api/v1/auth/`: Authentification (inscription, connexion)
- `/api/v1/users/`: Gestion des utilisateurs et profils
- `/api/v1/media/`: Upload et gestion des médias
- `/api/v1/contests/`: Gestion des concours
- `/api/v1/votes/`: Système de vote

## Contribuer

Les contributions sont les bienvenues! Veuillez consulter le fichier CONTRIBUTING.md pour plus de détails.
