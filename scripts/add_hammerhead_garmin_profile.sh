#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/qbot/app"
PROFILE_DIR="$APP_DIR/config/profiles"
STATE_DIR="$APP_DIR/state"
OUTGOING_BASE="$APP_DIR/outgoing"
HAMMERHEAD_TOKEN_DIR="$APP_DIR/.hammerhead_tokens"
GARMIN_TOKEN_BASE="$APP_DIR/.garmin_tokens"

usage() {
  cat <<'EOF'
Interaktywny kreator profilu Hammerhead -> Garmin dla QBot.

Co przygotować przed uruchomieniem:
1. Nazwa profilu, np. user2 albo adam. Dozwolone: litery, cyfry, kropka, podkreślnik, myślnik.
2. HAMMERHEAD_USER_ID z konta Hammerhead.
3. Hammerhead refresh token:
   - zaloguj się do Hammerhead Dashboard jako dany użytkownik,
   - otwórz konsolę przeglądarki,
   - wpisz: localStorage.getItem("jwt:refresh")
   - skopiuj zwrócony UUID.
4. Garmin tokenstore dla tego użytkownika zostanie ustawiony jako:
   /opt/qbot/app/.garmin_tokens/<profile>
   Samo logowanie do Garmin trzeba wykonać osobno dla tego katalogu.

Uruchomienie:
  /opt/qbot/app/scripts/add_hammerhead_garmin_profile.sh

Skrypt nie wypisuje tokenu na ekran i nie uruchamia uploadu.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

read_required() {
  local label="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -p "$label: " value
  done
  printf '%s' "$value"
}

read_secret_required() {
  local label="$1"
  local value=""
  while [[ -z "$value" ]]; do
    read -r -s -p "$label: " value
    echo
  done
  printf '%s' "$value"
}

quote_env() {
  "$APP_DIR/.venv/bin/python" - "$1" <<'PY'
import sys
print(repr(sys.argv[1]))
PY
}

echo "QBot profile creator: Hammerhead -> Garmin"
echo
usage
echo

PROFILE="$(read_required "PROFILE_NAME")"
if [[ ! "$PROFILE" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "ERROR: niepoprawna nazwa profilu: $PROFILE" >&2
  exit 2
fi

ENV_FILE="$PROFILE_DIR/$PROFILE.env"
if [[ -e "$ENV_FILE" ]]; then
  read -r -p "Profil $PROFILE już istnieje. Nadpisać? [y/N]: " overwrite
  if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
    echo "Przerwano bez zmian."
    exit 0
  fi
fi

HAMMERHEAD_USER_ID="$(read_required "HAMMERHEAD_USER_ID")"
HAMMERHEAD_REFRESH_TOKEN="$(read_secret_required "HAMMERHEAD_REFRESH_TOKEN")"

mkdir -p "$PROFILE_DIR" "$STATE_DIR" "$OUTGOING_BASE/$PROFILE/hammerhead_originals" \
  "$OUTGOING_BASE/$PROFILE/garmin_proxy" "$OUTGOING_BASE/$PROFILE/reports" \
  "$HAMMERHEAD_TOKEN_DIR" "$GARMIN_TOKEN_BASE/$PROFILE" "$APP_DIR/logs"

chmod 700 "$HAMMERHEAD_TOKEN_DIR" "$GARMIN_TOKEN_BASE" "$GARMIN_TOKEN_BASE/$PROFILE"

TOKEN_QUOTED="$(quote_env "$HAMMERHEAD_REFRESH_TOKEN")"
cat > "$ENV_FILE" <<EOF
PROFILE_NAME=$PROFILE
HAMMERHEAD_USER_ID=$HAMMERHEAD_USER_ID
HAMMERHEAD_REFRESH_TOKEN=$TOKEN_QUOTED
HAMMERHEAD_TOKENSTORE=$HAMMERHEAD_TOKEN_DIR/$PROFILE.json
GARMIN_TOKENSTORE=$GARMIN_TOKEN_BASE/$PROFILE
PROCESSED_STATE=$STATE_DIR/${PROFILE}_processed_hammerhead_activities.json
OUTGOING_DIR=$OUTGOING_BASE/$PROFILE
QBOT_GARMIN_SYNC_MODE=upload
EOF

chmod 600 "$ENV_FILE"
touch "$STATE_DIR/${PROFILE}_processed_hammerhead_activities.json"
if [[ ! -s "$STATE_DIR/${PROFILE}_processed_hammerhead_activities.json" ]]; then
  printf '{\n  "processed": []\n}\n' > "$STATE_DIR/${PROFILE}_processed_hammerhead_activities.json"
fi

echo
echo "Profil utworzony: $ENV_FILE"
echo "Token nie został wypisany."
echo
echo "Następne kroki:"
echo "1. Zaloguj Garmin tego użytkownika do: $GARMIN_TOKEN_BASE/$PROFILE"
echo "2. Sprawdź profil:"
echo "   $APP_DIR/scripts/profile_status.sh $PROFILE"
echo "3. Wykonaj dry-run:"
echo "   $APP_DIR/.venv/bin/python $APP_DIR/qbot-hammerhead-sync --profile $PROFILE --dry-run"
echo "4. Dopiero po udanym dry-run zostaw cron/upload aktywny."
