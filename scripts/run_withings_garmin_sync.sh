#!/usr/bin/env bash
# Withings -> Garmin Connect. Wzorowane na run_hammerhead_garmin_sync.sh.
# Cron: */15 * * * *  (2026-10-08: cala doba; pytamy TYLKO Withings, Garmin dopiero po nowym wazeniu)
# Po nowym pomiarze (zmiana pliku stanu) -> scripts/weight_refresh.py:
#   import_garmin_body (--days 3) + waga w ModelQ (fitmodel_daily) od razu, bez czekania na noc.
set -uo pipefail

APP_DIR="/opt/qbot/app"
LOG_FILE="/opt/qbot/logs/withings_garmin_sync.log"
LOCK_FILE="/tmp/qbot-withings-garmin-sync.lock"
DAYS="${WITHINGS_SYNC_DAYS:-14}"
STATE_FILE="$APP_DIR/state/processed_withings_measures.json"

mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "[$(date -Is)] qbot-withings-sync start"

  before="$(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0)"

  flock -n "$LOCK_FILE" "$APP_DIR/.venv/bin/python3" "$APP_DIR/qbot-withings-sync" \
      --days "$DAYS" --upload
  rc=$?

  if [[ "$rc" -eq 1 ]]; then
    echo "[$(date -Is)] qbot-withings-sync: blad przejsciowy, ponowienie w kolejnym przebiegu"
  elif [[ "$rc" -eq 2 ]]; then
    echo "[$(date -Is)] qbot-withings-sync: BLAD TRWALY -- wymagana reczna autoryzacja Withings"
  elif [[ "$rc" -ne 0 ]]; then
    echo "[$(date -Is)] qbot-withings-sync failed rc=$rc"
  else
    echo "[$(date -Is)] qbot-withings-sync done"
  fi

  after="$(stat -c %Y "$STATE_FILE" 2>/dev/null || echo 0)"
  if [[ "$rc" -eq 0 && "$after" != "$before" ]]; then
    echo "[$(date -Is)] nowy pomiar -> weight_refresh"
    (cd "$APP_DIR" && "$APP_DIR/.venv/bin/python3" scripts/weight_refresh.py)
    echo "[$(date -Is)] weight_refresh rc=$?"
  fi

  exit "$rc"
} >> "$LOG_FILE" 2>&1
