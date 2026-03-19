"""Pré-chauffe le pool de connexions DB au démarrage"""
import logging
from sqlalchemy import text
from app.db.session import engine

logger = logging.getLogger(__name__)

def warmup_pool():
    """Ouvre pool_size connexions pour éviter la latence au premier appel"""
    try:
        conns = []
        for i in range(5):
            conn = engine.connect()
            conn.execute(text("SELECT 1"))
            conns.append(conn)
        for conn in conns:
            conn.close()
        logger.info(f"DB pool warmed up with {len(conns)} connections")
    except Exception as e:
        logger.warning(f"DB warmup failed: {e}")
