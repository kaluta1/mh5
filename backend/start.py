#!/usr/bin/env python
import os
import argparse
import subprocess
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("start-script")

def run_alembic_migrations():
    """Exécute les migrations de base de données avec Alembic"""
    logger.info("Exécution des migrations Alembic...")
    try:
        # Utiliser sys.executable pour s'assurer d'utiliser le bon interpréteur Python
        # et ajouter le répertoire courant au PYTHONPATH
        env = os.environ.copy()
        project_root = os.path.dirname(os.path.abspath(__file__))
        
        # Configurer PYTHONPATH pour inclure le répertoire racine du projet
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{project_root}{os.pathsep}{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = project_root
            
        logger.info(f"PYTHONPATH configuré avec: {env['PYTHONPATH']}")
        
        # Exécuter la commande alembic avec l'environnement modifié
        subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
        logger.info("Migrations terminées avec succès")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur lors des migrations: {e}")
        return False

def initialize_data():
    """Initialise les données de base"""
    logger.info("Initialisation des données...")
    try:
        from app.initial_data import init_db
        init_db()
        logger.info("Données initialisées avec succès")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation des données: {e}")
        return False

def run_app(host="0.0.0.0", port=8000, reload=True, workers=1):
    """Démarrage de l'application FastAPI avec Uvicorn"""
    logger.info(f"Démarrage de l'application sur {host}:{port}...")
    
    cmd = [
        "uvicorn", 
        "main:app", 
        "--host", host, 
        "--port", str(port),
        "--log-level", "info"
    ]
    
    # En mode reload, on ne peut pas utiliser plusieurs workers
    if reload:
        cmd.append("--reload")
    else:
        cmd.extend(["--workers", str(workers)])
    
    try:
        logger.debug(f"Exécution de la commande: {' '.join(cmd)}")
        # Utiliser subprocess.run sans capture_output pour permettre l'interaction
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Échec de démarrage avec code: {e.returncode}")
        raise
    except KeyboardInterrupt:
        logger.info("Arrêt de l'application demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"Exception lors du démarrage de l'application: {str(e)}")
        raise

def start_redis():
    """Démarre Redis s'il n'est pas déjà en cours d'exécution"""
    logger.info("Vérification de Redis...")
    try:
        # Vérifier si Redis est en cours d'exécution
        subprocess.run(["redis-cli", "ping"], stdout=subprocess.PIPE, check=True)
        logger.info("Redis est déjà en cours d'exécution")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Redis n'est pas disponible - l'application continuera sans Redis")
        logger.info("Pour installer Redis sur Windows, utilisez: https://github.com/microsoftarchive/redis/releases")
        return False

def main():
    """Fonction principale"""
    logger.info("=== Démarrage du script principal ===")
    parser = argparse.ArgumentParser(description="Script de démarrage pour l'application MyFav")
    
    parser.add_argument("--no-migrations", action="store_true", help="Ne pas exécuter les migrations de base de données")
    parser.add_argument("--no-init-data", action="store_true", help="Ne pas initialiser les données")
    parser.add_argument("--host", default="0.0.0.0", help="Hôte sur lequel démarrer l'application")
    parser.add_argument("--port", type=int, default=8000, help="Port sur lequel démarrer l'application")
    parser.add_argument("--no-reload", action="store_true", help="Désactiver le rechargement automatique")
    parser.add_argument("--workers", type=int, default=1, help="Nombre de workers")
    parser.add_argument("--debug", action="store_true", help="Afficher les informations de débogage")
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Mode débogage activé")
    
    # Afficher les variables d'environnement importantes pour le débogage
    if args.debug:
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            logger.debug(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'Non défini')}")
            logger.debug(f"PYTHONPATH: {os.getenv('PYTHONPATH', 'Non défini')}")
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage des variables d'environnement: {e}")
    
    if not args.no_migrations:
        logger.info("Tentative d'exécution des migrations...")
        if not run_alembic_migrations():
            logger.error("Échec des migrations, arrêt du script")
            sys.exit(1)
    else:
        logger.info("Migrations ignorées (--no-migrations)")
    
    if not args.no_init_data:
        logger.info("Tentative d'initialisation des données...")
        if not initialize_data():
            logger.warning("Échec de l'initialisation des données, continuation...")
    else:
        logger.info("Initialisation des données ignorée (--no-init-data)")
    
    # Démarrage de Redis (optionnel)
    logger.info("Tentative de démarrage de Redis...")
    redis_status = start_redis()
    if not redis_status:
        logger.warning("Redis n'a pas pu être démarré, mais le script continue")
    
    # Affichage des informations de l'API
    if args.host == "0.0.0.0":
        localhost_url = f"http://localhost:{args.port}"
        local_ip_url = f"http://127.0.0.1:{args.port}"
        logger.info(f"🚀 API MyFav sera disponible sur:")
        logger.info(f"   - {localhost_url}")
        logger.info(f"   - {local_ip_url}")
        logger.info(f"📚 Documentation API: {localhost_url}/docs")
        logger.info(f"🔧 Interface Redoc: {localhost_url}/redoc")
    else:
        api_url = f"http://{args.host}:{args.port}"
        logger.info(f"🚀 API MyFav sera disponible sur: {api_url}")
        logger.info(f"📚 Documentation API: {api_url}/docs")
        logger.info(f"🔧 Interface Redoc: {api_url}/redoc")
    
    # Démarrage de l'application
    logger.info("Démarrage de l'application FastAPI...")
    run_app(
        host=args.host, 
        port=args.port, 
        reload=not args.no_reload,
        workers=args.workers
    )

if __name__ == "__main__":
    try:
        print("Démarrage de l'application MyFav")
        sys.stdout.flush()
        main()
    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
        print("Traceback:")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
