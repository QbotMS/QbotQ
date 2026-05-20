#!/usr/bin/env bash
set -uo pipefail

APP_DIR="/opt/qbot/app"
PROFILE="${1:-}"

if [[ -z "$PROFILE" || ! "$PROFILE" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "Usage: $0 PROFILE" >&2
  exit 2
fi

ENV_FILE="$APP_DIR/config/profiles/$PROFILE.env"
LOG_FILE="$APP_DIR/logs/hammerhead-garmin-sync-$PROFILE.log"
LOCK_FILE="/tmp/qbot-hammerhead-garmin-sync-$PROFILE.lock"

mkdir -p "$APP_DIR/logs"

{
  echo "[$(date -Is)] qbot-hammerhead-sync start profile=$PROFILE"

  if [[ ! -r "$ENV_FILE" ]]; then
    echo "[$(date -Is)] ERROR: profile env missing or unreadable: $ENV_FILE"
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

  if [[ -z "${HAMMERHEAD_REFRESH_TOKEN:-}" && ! -s "${HAMMERHEAD_TOKENSTORE:-}" ]]; then
    echo "[$(date -Is)] ERROR: Hammerhead auth missing for profile=$PROFILE"
    exit 1
  fi

  flock -n "$LOCK_FILE" "$APP_DIR/.venv/bin/python" "$APP_DIR/qbot-hammerhead-sync" --profile "$PROFILE" --upload
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    echo "[$(date -Is)] qbot-hammerhead-sync failed profile=$PROFILE rc=$rc"
    exit "$rc"
  fi

  echo "[$(date -Is)] qbot-hammerhead-sync done profile=$PROFILE"
} >> "$LOG_FILE" 2>&1
