#!/usr/bin/env python
"""Run alembic migrations, auto-fixing duplicate table/column errors."""
import subprocess
import sys
import os
import re
import psycopg2

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from app.core.env_loader import require_database_url


def recreate_db():
    database_url = require_database_url()
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP DATABASE IF EXISTS myhigh5;")
    cur.execute("CREATE DATABASE myhigh5;")
    cur.close()
    conn.close()
    print("Database recreated.")
