"""Odswiezenie lokalnej bazy drog OSM (cron: pon. 04:20, uzytkownik qbot) z powiadomieniem.

Kroki: osm_extract_fetch --run -> osm_local_build --run -> osm_landmarks_build --run.
Na koniec ZAWSZE wiadomosc na Telegram (sukces z liczbami albo blad z koncowka logu),
bo od 05.10.2026 do 19.10.2026 cron cicho padal (brak uprawnien qbot do /opt/qbot/data/osm,
wynik crona odrzucany - "No MTA"). Sesja router-1910, 19.10.2026.
Uzycie: .venv/bin/python3 scripts/osm_refresh_run.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

APP = Path("/opt/qbot/app")
PY = str(APP / ".venv/bin/python3")
STEPS = [
    ("pobranie mapy Polski", "scripts/osm_extract_fetch.py", "/opt/qbot/artifacts/osm_extract_fetch.log"),
    ("baza drog", "scripts/osm_local_build.py", "/opt/qbot/artifacts/osm_local_build.log"),
    ("baza punktow orientacyjnych", "scripts/osm_landmarks_build.py", "/opt/qbot/artifacts/osm_landmarks_build.log"),
]


def _tail(path: str, n: int = 6) -> str:
    try:
        return "\n".join(Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except Exception as exc:  # noqa: BLE001
        return f"(brak logu: {exc})"


def _telegram(text: str) -> None:
    try:
        sys.path.insert(0, str(APP))
        import httpx
        import qbot_config as cfg
        httpx.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                   json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text[:4000]}, timeout=15)
    except Exception as exc:  # noqa: BLE001
        print(f"Telegram niewyslany: {exc}", file=sys.stderr)


def main() -> int:
    t0 = time.time()
    for label, script, log in STEPS:
        r = subprocess.run([PY, script, "--run"], cwd=str(APP), capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip().splitlines()[-6:]
            _telegram(f"QBot: odswiezanie bazy drog OSM NIEUDANE na kroku '{label}' (kod {r.returncode}).\n"
                      + "\n".join(err) + f"\n--- log:\n{_tail(log)}")
            return r.returncode
    mins = round((time.time() - t0) / 60)
    _telegram(f"QBot: baza drog OSM odswiezona ({mins} min).\n{_tail(STEPS[1][2], 1)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
