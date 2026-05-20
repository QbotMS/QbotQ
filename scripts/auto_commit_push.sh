#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/qbot/app"
LOCK_FILE="/tmp/qbot_git_auto_commit.lock"

cd "$APP_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Is) auto-commit already running"
  exit 0
fi

if ! git diff --quiet || ! git diff --cached --quiet || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
  git add -A

  if git diff --cached --quiet; then
    echo "$(date -Is) no staged changes after git add"
    exit 0
  fi

  git commit -m "Auto snapshot $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
  echo "$(date -Is) auto snapshot pushed"
else
  echo "$(date -Is) no changes"
fi
