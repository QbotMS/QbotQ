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

  # ModelQ fast-path (tylko profil michal): po udanym syncu odpal ingest+recompute
  # od razu, zamiast czekac na okresowy cron. Skrypt jest idempotentny, ma wlasny
  # lock i retry na opoznienie Garmina. Odpalany w tle (setsid) -> nie blokuje cyklu.
  if [[ "$PROFILE" == "michal" ]]; then
    PROXY_DIR="$APP_DIR/outgoing/garmin_proxy"
    # Odpal trigger TYLKO gdy sync faktycznie przetworzyl nowa jazde (swiezy proxy FIT).
    # "already processed"/"No unprocessed" nie tworza nowego proxy FIT -> brak triggera,
    # zero zbednego walenia w API Garmina co 10 min.
    if [[ -n "$(find "$PROXY_DIR" -maxdepth 1 -type f -name '*.fit' -mmin -3 2>/dev/null)" ]]; then
      echo "[$(date -Is)] trigger ModelQ launch profile=$PROFILE (nowy proxy FIT)"
      setsid "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/trigger_modelq_after_ride.py" \
        >> "$APP_DIR/logs/activity-ingest-trigger.log" 2>&1 &
    else
      echo "[$(date -Is)] trigger ModelQ pominiety profile=$PROFILE (brak nowej jazdy)"
    fi
  fi
} >> "$LOG_FILE" 2>&1
