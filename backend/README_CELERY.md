# Configuration Celery pour les migrations de saisons

## Installation

Celery est déjà inclus dans `requirements.txt`. Assurez-vous que Redis est installé et en cours d'exécution.

## Configuration

1. **Redis doit être en cours d'exécution** :
   ```bash
   # Si vous utilisez Docker
   docker-compose up redis
   
   # Ou démarrer Redis localement
   redis-server
   ```

2. **Variables d'environnement** (optionnel) :
   - `REDIS_HOST`: Hôte Redis (défaut: localhost)
   - `REDIS_PORT`: Port Redis (défaut: 6379)
   - `REDIS_URL`: URL complète Redis (ex: redis://localhost:6379/0)

## Démarrage

### 1. Démarrer le worker Celery

Dans un terminal :
```bash
cd backend
celery -A app.celery_app worker --loglevel=info
```

Ou utiliser le script :
```bash
python start_celery_worker.py
```

### 2. Démarrer Celery Beat (scheduler)

Dans un autre terminal :
```bash
cd backend
celery -A app.celery_app beat --loglevel=info
```

Ou utiliser le script :
```bash
python start_celery_beat.py
```

## Tâches automatiques

La tâche `process_season_migrations` est exécutée automatiquement **toutes les heures** via Celery Beat.

## Utilisation via API

### Exécution synchrone (immédiate)
```bash
POST /api/v1/seasons/migrate/check
Headers: Authorization: Bearer <admin_token>
```

### Exécution asynchrone (via Celery)
```bash
POST /api/v1/seasons/migrate/check?async_task=true
Headers: Authorization: Bearer <admin_token>
```

La réponse contiendra un `task_id` que vous pouvez utiliser pour vérifier le statut de la tâche.

## Vérifier le statut d'une tâche

```python
from app.celery_app import celery_app

# Récupérer le résultat d'une tâche
result = celery_app.AsyncResult(task_id)
print(result.state)  # PENDING, SUCCESS, FAILURE, etc.
print(result.result)  # Le résultat de la tâche
```

## Production

Pour la production, utilisez un gestionnaire de processus comme **supervisor** ou **systemd** pour gérer les workers Celery et Celery Beat.

### Exemple avec supervisor

Créer `/etc/supervisor/conf.d/celery.conf` :
```ini
[program:celery_worker]
command=/path/to/venv/bin/celery -A app.celery_app worker --loglevel=info
directory=/path/to/backend
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/worker.log

[program:celery_beat]
command=/path/to/venv/bin/celery -A app.celery_app beat --loglevel=info
directory=/path/to/backend
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/celery/beat.log
```

Puis :
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start celery_worker
sudo supervisorctl start celery_beat
```

