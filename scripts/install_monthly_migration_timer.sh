#!/usr/bin/env bash
# Install systemd timer: season migrations on the 1st of each month at 00:05 UTC.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_SRC="${ROOT}/deploy/myhigh5-monthly-migration.service"
TIMER_SRC="${ROOT}/deploy/myhigh5-monthly-migration.timer"
CRON_SCRIPT="${ROOT}/scripts/run_monthly_migration_cron.sh"

chmod +x "$CRON_SCRIPT"

for f in "$SERVICE_SRC" "$TIMER_SRC"; do
  name="$(basename "$f")"
  sed "s|/root/mh5|${ROOT}|g" "$f" > "/etc/systemd/system/${name}"
done

systemctl daemon-reload
systemctl enable myhigh5-monthly-migration.timer
systemctl start myhigh5-monthly-migration.timer

echo "Installed myhigh5-monthly-migration.timer"
systemctl list-timers myhigh5-monthly-migration.timer --no-pager || true
