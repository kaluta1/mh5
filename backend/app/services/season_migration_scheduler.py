"""
Background Season Migration Scheduler Service
Vérifie et traite les migrations de saisons toutes les heures
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.services.season_migration import season_migration_service

logger = logging.getLogger(__name__)


class SeasonMigrationScheduler:
    """
    Background service that periodically checks and processes season migrations
    """
    
    def __init__(self, check_interval_seconds: int = 60*60):  # 1 minute par défaut (60 secondes) pour les tests
        self.check_interval = check_interval_seconds
        self.running = False
        self._task = None
    
    async def start(self):
        """Start the background season migration checker"""
        if self.running:
            logger.warning("Season migration scheduler already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"Season migration scheduler started (interval: {self.check_interval}s = {self.check_interval/60} minutes)")
        print(f"[SeasonMigrationScheduler] Started with interval: {self.check_interval/60} minutes")
    
    async def stop(self):
        """Stop the background season migration checker"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Season migration scheduler stopped")
    
    async def _check_loop(self):
        """Main loop that checks migrations periodically"""
        # Wait a bit before first check to let the app fully start
        await asyncio.sleep(10)  # Attendre 10 secondes au démarrage pour les tests
        
        while self.running:
            try:
                print(f"[SeasonMigrationScheduler] Running check at {datetime.utcnow()}")
                logger.info(f"[SeasonMigrationScheduler] Running check at {datetime.utcnow()}")
                await self._process_migrations()
            except Exception as e:
                print(f"[SeasonMigrationScheduler] Error: {e}")
                logger.error(f"Error in season migration check loop: {e}", exc_info=True)
            
            print(f"[SeasonMigrationScheduler] Next check in {self.check_interval/60} minutes")
            logger.info(f"[SeasonMigrationScheduler] Next check in {self.check_interval/60} minutes")
            await asyncio.sleep(self.check_interval)
    
    async def _process_migrations(self):
        """Process all pending season migrations"""
        # Exécuter la fonction synchrone dans un thread pour ne pas bloquer l'event loop
        def run_migration():
            db: Session = SessionLocal()
            try:
                logger.info("Starting season migration check...")
                print("[SeasonMigrationScheduler] Starting migration check...")
                result = season_migration_service.check_and_process_migrations(db)
                # Les fonctions de migration font déjà leurs propres commits
                # Mais on s'assure qu'il n'y a pas de transaction en attente
                try:
                    db.commit()
                except Exception:
                    pass  # Ignorer si déjà commité
                return result
            except Exception as e:
                logger.error(f"Error in migration function: {e}", exc_info=True)
                print(f"[SeasonMigrationScheduler] Error in migration: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        
        try:
            # Exécuter dans un thread pour ne pas bloquer (compatible Python 3.7+)
            import sys
            if sys.version_info >= (3, 9):
                result = await asyncio.to_thread(run_migration)
            else:
                # Fallback pour Python < 3.9
                from concurrent.futures import ThreadPoolExecutor
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as executor:
                    result = await loop.run_in_executor(executor, run_migration)
            
            if result and isinstance(result, dict) and result.get("processed", 0) > 0:
                print(f"[SeasonMigrationScheduler] Processed {result['processed']} migrations")
                logger.info(f"Processed {result['processed']} season migrations: {result['results']}")
                for item in result.get('results', []):
                    contest_id = item.get('contest_id')
                    action = item.get('action')
                    migration_result = item.get('result', {})
                    
                    # Extraire les IDs des contestants promus/migrés
                    promoted_ids = []
                    error_msg = None
                    if isinstance(migration_result, dict):
                        # Vérifier s'il y a une erreur
                        if 'error' in migration_result:
                            error_msg = migration_result.get('error')
                            print(f"  - Contest {contest_id}: {action} - ERROR: {error_msg}")
                            logger.error(f"  - Contest {contest_id}: {action} - ERROR: {error_msg}")
                        else:
                            promoted_ids = migration_result.get('promoted_contestant_ids', [])
                            if not promoted_ids:
                                promoted_ids = migration_result.get('migrated_contestant_ids', [])
                            # Pour les migrations en deux étapes (city_then_country)
                            if 'country_result' in migration_result:
                                country_result = migration_result.get('country_result', {})
                                if isinstance(country_result, dict):
                                    if 'error' in country_result:
                                        error_msg = country_result.get('error')
                                        print(f"  - Contest {contest_id}: {action} - ERROR dans country_result: {error_msg}")
                                    else:
                                        promoted_ids = country_result.get('promoted_contestant_ids', [])
                    
                    if not error_msg:
                        print(f"  - Contest {contest_id}: {action}")
                        if promoted_ids:
                            print(f"    ✓ Contestants promus/migrés ({len(promoted_ids)}): {promoted_ids}")
                            logger.info(f"  - Contest {contest_id}: {action} - Contestants: {promoted_ids}")
                        else:
                            print(f"    ⚠ Aucun contestant promu/migré")
                            logger.warning(f"  - Contest {contest_id}: {action} - Aucun contestant promu/migré - {migration_result}")
            else:
                print("[SeasonMigrationScheduler] No migrations to process")
                logger.info("No migrations to process at this time")
        except Exception as e:
            logger.error(f"Error processing season migrations: {e}", exc_info=True)
            print(f"[SeasonMigrationScheduler] Error processing migrations: {e}")
            import traceback
            traceback.print_exc()


# Instance globale du scheduler
season_migration_scheduler = SeasonMigrationScheduler()

