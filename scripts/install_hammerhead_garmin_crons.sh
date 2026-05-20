#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/qbot/app"
TMP="$(mktemp)"
trap 'rm -f "$TMP" "$TMP.new"' EXIT

crontab -l 2>/dev/null > "$TMP" || true

grep -vF "$APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh michal" "$TMP" \
  | grep -vF "$APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh user2" \
  | grep -vF "$APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh user3" > "$TMP.new" || true

{
  cat "$TMP.new"
  echo "*/10 * * * * $APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh michal"
  echo "*/10 * * * * $APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh user2"
  echo "*/10 * * * * $APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh user3"
} | crontab -

crontab -l | grep -F "$APP_DIR/scripts/run_hammerhead_garmin_sync_profile.sh"
