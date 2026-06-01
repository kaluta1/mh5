#!/usr/bin/env python
"""Run alembic migrations, auto-fixing duplicate table/column errors."""
import subprocess
import sys
import os
import re
import psycopg2

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def recreate_db():
    conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='', database='postgres')
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute('DROP DATABASE IF EXISTS myhigh5;')
    cur.execute('CREATE DATABASE myhigh5;')
    cur.close()
    conn.close()
    print("Database recreated.")

def run_alembic():
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'upgrade', 'heads'],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr

def find_failing_migration(stderr):
    # Look for migration file in traceback (Windows paths)
    match = re.search(r'migrations[\/]versions[\/]([^\s:]+\.py)', stderr)
    if match:
        return match.group(1)
    return None

def fix_migration(filename, stderr):
    filepath = f'migrations/versions/{filename}'
    with open(filepath, 'r') as f:
        content = f.read()
    
    # If already has inspect, skip
    if 'sa.inspect(bind)' in content:
        print(f"  Migration {filename} already has inspect checks.")
        return False
    
    lower_err = stderr.lower()
    
    # Check for duplicate table
    if 'already exists' in lower_err and 'relation' in lower_err:
        table_match = re.search(r'relation "([^"]+)" already exists', stderr)
        if table_match:
            table = table_match.group(1)
            print(f"  Fixing duplicate table: {table}")
            # Wrap create_table calls
            pattern = rf"(op\.create_table\('{re.escape(table)}',)"
            replacement = f"bind = op.get_bind()\n    insp = sa.inspect(bind)\n    if '{table}' not in insp.get_table_names():\n        \1"
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                with open(filepath, 'w') as f:
                    f.write(new_content)
                return True
    
    # Check for duplicate column
    if 'already exists' in lower_err and 'column' in lower_err:
        col_match = re.search(r'column "([^"]+)" of relation "([^"]+)" already exists', stderr)
        if col_match:
            col, table = col_match.group(1), col_match.group(2)
            print(f"  Fixing duplicate column: {col} in {table}")
            lines = content.split('\n')
            new_lines = []
            added_check = False
            for i, line in enumerate(lines):
                if f"op.add_column('{table}'" in line and f"'{col}'" in line:
                    indent = len(line) - len(line.lstrip())
                    spaces = ' ' * indent
                    new_lines.append(f"{spaces}bind = op.get_bind()")
                    new_lines.append(f"{spaces}insp = sa.inspect(bind)")
                    new_lines.append(f"{spaces}columns = [c['name'] for c in insp.get_columns('{table}')]")
                    new_lines.append(f"{spaces}if '{col}' not in columns:")
                    new_lines.append(f"{spaces}    {line.strip()}")
                    added_check = True
                else:
                    new_lines.append(line)
            if added_check:
                with open(filepath, 'w') as f:
                    f.write('\n'.join(new_lines))
                return True
    
    return False

def main():
    recreate_db()
    
    max_iterations = 30
    for i in range(max_iterations):
        print(f"\n--- Attempt {i+1} ---")
        code, stdout, stderr = run_alembic()
        
        if code == 0:
            print("SUCCESS! All migrations applied.")
            print(stdout)
            return
        
        print("Migration failed. Analyzing error...")
        failing_migration = find_failing_migration(stderr)
        
        if failing_migration:
            print(f"Failing migration: {failing_migration}")
            if fix_migration(failing_migration, stderr):
                print(f"  Fixed {failing_migration}, retrying...")
                continue
            else:
                print(f"  Could not auto-fix {failing_migration}")
                print(stderr)
                break
        else:
            print("Could not identify failing migration.")
            print(stderr)
            break
    
    print("\nFailed to apply all migrations.")

if __name__ == '__main__':
    main()
