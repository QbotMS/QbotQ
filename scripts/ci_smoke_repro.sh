#!/bin/bash
# Odtworzenie CI (GitHub Actions smoke.yml) na serwerze: czysta kopia repo z HEAD + swiezy venv z requirements.txt.
# Wynik: /opt/qbot/artifacts/ci_smoke_repro.txt
set -u
OUT=/opt/qbot/artifacts/ci_smoke_repro.txt
W=/tmp/ci_smoke_repro
rm -rf "$W" && mkdir -p "$W"
{
  echo "== $(date) =="
  git -c safe.directory=/opt/qbot/app -C /opt/qbot/app archive HEAD | tar -x -C "$W"
  cd "$W"
  # jak na GitHubie: /opt/qbot/app tam nie istnieje -> importy z kopii, nie z zywego drzewa
  sed -i "s#sys.path.insert(0, \"/opt/qbot/app\")#sys.path.insert(0, \"$W\")#" scripts/qbot_smoke_tests.py
  python3 -m venv .ci && . .ci/bin/activate
  python -m pip install -q --upgrade pip
  python -m pip install -q -r requirements.txt
  echo "== py_compile =="
  python -m py_compile qbot_coach.py daily_report.py email_template.py ride_report.py weekly_review.py scripts/qbot_smoke_tests.py && echo OK
  echo "== smoke =="
  PGHOST=/nonexistent timeout 300 python -m scripts.qbot_smoke_tests
  echo "== kod wyjscia: $? =="
} > "$OUT" 2>&1
echo "gotowe: $OUT"
