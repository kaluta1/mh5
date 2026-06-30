#!/usr/bin/env bash
# Daily safety net + explicit 1st-of-month season migrations on VPS.
# Installed by scripts/install_monthly_migration_timer.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${ROOT}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/monthly-migration-$(date +%Y%m%d).log"

exec >>"$LOG_FILE" 2>&1
echo "=== $(date -Iseconds) monthly migration cron ==="

bash "${ROOT}/backend/scripts/run_ensure_month_round_and_migrations.sh"

echo "=== done ==="
