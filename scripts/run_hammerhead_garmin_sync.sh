#!/usr/bin/env bash
set -uo pipefail

APP_DIR="/opt/qbot/app"
ENV_FILE="$APP_DIR/.env.hammerhead-garmin-sync"
LOG_FILE="$APP_DIR/logs/hammerhead-garmin-sync.log"
LOCK_FILE="/tmp/qbot-hammerhead-garmin-sync.lock"

mkdir -p "$APP_DIR/logs"

{
  echo "[$(date -Is)] qbot-hammerhead-sync start"

  if [[ ! -r "$ENV_FILE" ]]; then
    echo "[$(date -Is)] ERROR: env file missing or unreadable: $ENV_FILE"
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  mode="${QBOT_GARMIN_SYNC_MODE:-upload}"
  if [[ "$mode" != "upload" ]]; then
    echo "[$(date -Is)] ERROR: unsupported QBOT_GARMIN_SYNC_MODE=$mode"
    exit 1
  fi

  if [[ -z "${HAMMERHEAD_BEARER_TOKEN:-}" ]]; then
    echo "[$(date -Is)] ERROR: Hammerhead auth missing"
    exit 1
  fi

  flock -n "$LOCK_FILE" "$APP_DIR/.venv/bin/python" "$APP_DIR/qbot-hammerhead-sync" --upload
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    echo "[$(date -Is)] qbot-hammerhead-sync failed rc=$rc"
    exit "$rc"
  fi

  echo "[$(date -Is)] qbot-hammerhead-sync done"
} >> "$LOG_FILE" 2>&1
