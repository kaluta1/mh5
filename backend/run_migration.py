import subprocess
import sys

# Run the add_is_deleted_column.py script
result = subprocess.run([sys.executable, "add_is_deleted_column.py"], cwd=".")
sys.exit(result.returncode)
