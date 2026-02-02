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
    
    # Valider que DATABASE_URL est défini
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.error(
            "DATABASE_URL n'est pas défini dans les variables d'environnement. "
            "Veuillez définir DATABASE_URL avec une URL de base de données valide. "
            "Format attendu: postgresql://user:password@host:port/database"
        )
        return False
    
    # Vérifier que l'URL commence par un schéma valide
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://", "postgres://")):
        logger.error(
            f"DATABASE_URL doit commencer par 'postgresql://', 'postgresql+psycopg2://' ou 'postgres://'. "
            f"Valeur reçue: {database_url[:50]}..."
        )
        return False
    
    logger.info(f"Connexion à la base de données: {database_url.split('@')[-1] if '@' in database_url else '***'}")
    
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
        
        # FIXED: Always use 'heads' to handle multiple migration branches
        # This prevents "Multiple head revisions" errors on Render
        logger.info("Running database migrations with 'alembic upgrade heads'...")
        try:
            subprocess.run(["alembic", "upgrade", "heads"], check=True, env=env)
            logger.info("Migrations completed successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Migration failed: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"Migration stderr: {e.stderr}")
            raise
        
        logger.info("Migrations terminées avec succès")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur lors des migrations: {e}")
        # En cas d'erreur avec 'head', essayer avec 'heads' comme fallback
        if "Multiple head revisions" in str(e.stderr) if hasattr(e, 'stderr') else "":
            logger.info("Tentative avec 'heads' comme fallback...")
            try:
                subprocess.run(["alembic", "upgrade", "heads"], check=True, env=env)
                logger.info("Migrations terminées avec succès (fallback)")
                return True
            except subprocess.CalledProcessError as e2:
                logger.error(f"Erreur lors des migrations (fallback): {e2}")
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
    
    # Utiliser python -m uvicorn pour s'assurer qu'il trouve uvicorn
    cmd = [
        sys.executable, "-m", "uvicorn", 
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
    parser = argparse.ArgumentParser(description="Script de démarrage pour l'application MyHigh5")
    
    parser.add_argument("--no-migrations", action="store_true", help="Ne pas exécuter les migrations de base de données")
    parser.add_argument("--no-init-data", action="store_true", help="Ne pas initialiser les données")
    parser.add_argument("--host", default="0.0.0.0", help="Hôte sur lequel démarrer l'application")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)), help="Port sur lequel démarrer l'application")
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
            db_url = os.getenv('DATABASE_URL', 'Non défini')
            if db_url and db_url != 'Non défini':
                # Masquer le mot de passe dans l'URL pour la sécurité
                if '@' in db_url:
                    parts = db_url.split('@')
                    if '://' in parts[0]:
                        scheme_user_pass = parts[0]
                        if ':' in scheme_user_pass:
                            scheme_user, password = scheme_user_pass.rsplit(':', 1)
                            masked_url = f"{scheme_user}:****@{parts[1]}"
                            logger.debug(f"DATABASE_URL: {masked_url}")
                        else:
                            logger.debug(f"DATABASE_URL: {db_url.split('@')[0]}@****@{db_url.split('@')[1]}")
                    else:
                        logger.debug(f"DATABASE_URL: ****@{parts[1]}")
                else:
                    logger.debug(f"DATABASE_URL: {db_url}")
            else:
                logger.debug(f"DATABASE_URL: {db_url}")
            logger.debug(f"PYTHONPATH: {os.getenv('PYTHONPATH', 'Non défini')}")
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage des variables d'environnement: {e}")
    
    if not args.no_migrations:
        logger.info("Démarrage des migrations en arrière-plan...")
        import threading
        migration_thread = threading.Thread(target=run_alembic_migrations)
        migration_thread.daemon = True
        migration_thread.start()
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
        logger.info(f"🚀 API MyHigh5 sera disponible sur:")
        logger.info(f"   - {localhost_url}")
        logger.info(f"   - {local_ip_url}")
        logger.info(f"📚 Documentation API: {localhost_url}/docs")
        logger.info(f"🔧 Interface Redoc: {localhost_url}/redoc")
    else:
        api_url = f"http://{args.host}:{args.port}"
        logger.info(f"🚀 API MyHigh5 sera disponible sur: {api_url}")
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
        print("Démarrage de l'application MyHigh5")
        sys.stdout.flush()
        main()
    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
        print("Traceback:")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)
