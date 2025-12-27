"""
Service de cache Redis pour améliorer les performances du backend
"""
import json
import logging
from typing import Optional, Any
from functools import wraps
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Instance Redis globale
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Obtient ou crée l'instance Redis"""
    global _redis_client
    
    if _redis_client is not None:
        return _redis_client
    
    try:
        # Construire l'URL Redis
        redis_url = getattr(settings, 'REDIS_URL', None)
        if redis_url:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
        else:
            redis_host = getattr(settings, 'REDIS_HOST', 'localhost')
            redis_port = getattr(settings, 'REDIS_PORT', 6379)
            _redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True
            )
        
        # Tester la connexion
        _redis_client.ping()
        logger.info("✅ Connexion Redis établie avec succès")
        return _redis_client
    except Exception as e:
        logger.warning(f"⚠️ Redis non disponible: {e}. L'application continuera sans cache.")
        return None


class CacheService:
    """Service de cache utilisant Redis"""
    
    def __init__(self):
        self.redis = get_redis_client()
        self.default_ttl = 3600  # 1 heure par défaut
    
    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Génère une clé de cache à partir d'un préfixe et de paramètres"""
        key_parts = [prefix]
        
        # Ajouter les arguments positionnels
        for arg in args:
            if arg is not None:
                key_parts.append(str(arg))
        
        # Ajouter les arguments nommés triés
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            for k, v in sorted_kwargs:
                if v is not None:
                    key_parts.append(f"{k}:{v}")
        
        return ":".join(key_parts)
    
    def get(self, key: str) -> Optional[Any]:
        """Récupère une valeur du cache"""
        if not self.redis:
            return None
        
        try:
            cached = self.redis.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du cache pour {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Stocke une valeur dans le cache"""
        if not self.redis:
            return False
        
        try:
            ttl = ttl or self.default_ttl
            serialized = json.dumps(value, default=str)  # default=str pour gérer les dates
            self.redis.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Erreur lors du stockage dans le cache pour {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Supprime une clé du cache"""
        if not self.redis:
            return False
        
        try:
            self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du cache pour {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Supprime toutes les clés correspondant à un pattern"""
        if not self.redis:
            return 0
        
        try:
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Erreur lors de la suppression par pattern {pattern}: {e}")
            return 0
    
    def invalidate_contests(self):
        """Invalide le cache des contests"""
        return self.delete_pattern("cache:contests:*")
    
    def invalidate_contest(self, contest_id: Optional[int] = None):
        """Invalide le cache d'un contest spécifique ou tous les contests"""
        if contest_id:
            return self.delete_pattern(f"cache:contests:*{contest_id}*")
        else:
            return self.invalidate_contests()


# Instance globale du service de cache
cache_service = CacheService()


def cached(prefix: str, ttl: int = 3600, key_func=None):
    """
    Décorateur pour mettre en cache les résultats d'une fonction
    
    Args:
        prefix: Préfixe pour la clé de cache
        ttl: Durée de vie du cache en secondes (défaut: 1 heure)
        key_func: Fonction optionnelle pour générer la clé de cache à partir des arguments
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Générer la clé de cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache_service._make_key(prefix, *args, **kwargs)
            
            # Vérifier le cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit pour {cache_key}")
                return cached_result
            
            # Exécuter la fonction
            logger.debug(f"Cache miss pour {cache_key}, exécution de la fonction")
            result = await func(*args, **kwargs)
            
            # Stocker dans le cache
            cache_service.set(cache_key, result, ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Générer la clé de cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache_service._make_key(prefix, *args, **kwargs)
            
            # Vérifier le cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit pour {cache_key}")
                return cached_result
            
            # Exécuter la fonction
            logger.debug(f"Cache miss pour {cache_key}, exécution de la fonction")
            result = func(*args, **kwargs)
            
            # Stocker dans le cache
            cache_service.set(cache_key, result, ttl)
            
            return result
        
        # Retourner le wrapper approprié selon que la fonction est async ou non
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

