#!/usr/bin/env bash
# Withings -> Garmin Connect. Wzorowane na run_hammerhead_garmin_sync.sh.
# Cron: */15 5-9 * * *  (wazenie zwykle 7:10-7:25, import_garmin_body o 7:30/9:00/12:00)
set -uo pipefail

APP_DIR="/opt/qbot/app"
LOG_FILE="/opt/qbot/logs/withings_garmin_sync.log"
LOCK_FILE="/tmp/qbot-withings-garmin-sync.lock"
DAYS="${WITHINGS_SYNC_DAYS:-14}"

mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "[$(date -Is)] qbot-withings-sync start"

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

  exit "$rc"
} >> "$LOG_FILE" 2>&1
