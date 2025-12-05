#!/usr/bin/env python3
"""
Script pour démarrer Celery Beat (scheduler)
Usage: python start_celery_beat.py
"""
import sys
import os

# Ajouter le répertoire au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    os.system("celery -A app.celery_app beat --loglevel=info")

