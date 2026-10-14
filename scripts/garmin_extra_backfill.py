#!/usr/bin/env python3
"""[GARMIN-DANE] Etap 1: migracja schematu + dociagniecie historii pelnych danych snu/HRV.

Tylko get_sleep_data + get_hrv_data (2 zapytania/dzien), jeden klient Garmina,
przerwa miedzy dniami, wznawialny (pomija dni juz zapisane w garmin_daily_raw).
NIE rusza istniejacych kolumn snu/HRV -- tylko garmin_daily_raw + pola dodatkowe.

DLUGIE -> uruchamiac przez SSH w tle (NIE przez dev_shell_exec):
  cd /opt/qbot/app && nohup .venv/bin/python3 scripts/garmin_extra_backfill.py \\
      > /opt/qbot/artifacts/garmin_extra_backfill.txt 2>&1 &

Krotkie (mozna przez dev_shell_exec):
  .venv/bin/python3 scripts/garmin_extra_backfill.py --migrate-only
  .venv/bin/python3 scripts/garmin_extra_backfill.py --from 2026-10-13 --to 2026-10-14

Opcje: --from/--to (domyslnie: najstarszy dzien Garmina w qbot_wellness_daily .. dzis),
       --force (nadpisz dni juz zapisane), --pause 1.5 (s miedzy dniami).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(APP_DIR / ".env.local")
load_dotenv(APP_DIR / ".env")

from qbot_garmin_extra import ensure_schema, save_extra  # noqa: E402
from qbot_wellness_store import _db_conn  # noqa: E402


def _client():
    from garminconnect import Garmin
    profile = json.loads((APP_DIR / ".garmin_profile.json").read_text())
    g = Garmin("", "")
    g.client.load(str(APP_DIR / ".garmin_tokens"))
    g.display_name = profile["display_name"]
    return g


def _log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="d_from")
    p.add_argument("--to", dest="d_to")
    p.add_argument("--force", action="store_true")
    p.add_argument("--pause", type=float, default=1.5)
    p.add_argument("--migrate-only", action="store_true")
    a = p.parse_args()

    conn = _db_conn()
    ensure_schema(conn)
    _log("schemat OK (sql/garmin_extra_v1.sql)")
    if a.migrate_only:
        conn.close()
        return 0

    with conn.cursor() as cur:
        cur.execute("SELECT min(date) AS d FROM qbot_v2.qbot_wellness_daily WHERE source='garmin'")
        first = cur.fetchone()["d"]
        cur.execute("SELECT date, count(*) AS n FROM qbot_v2.garmin_daily_raw GROUP BY date")
        done = {r["date"].isoformat() for r in cur.fetchall() if r["n"] >= 2}

    d0 = date.fromisoformat(a.d_from) if a.d_from else first
    d1 = date.fromisoformat(a.d_to) if a.d_to else date.today()
    days = [(d0 + timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)]
    todo = [d for d in days if a.force or d not in done]
    _log(f"zakres {d0}..{d1}: {len(days)} dni, do pobrania {len(todo)}")

    g = _client()
    ok = skin = need = err = 0
    consecutive_err = 0
    t0 = time.time()
    for i, d in enumerate(todo, 1):
        try:
            sleep_raw = g.get_sleep_data(d)
            hrv_raw = g.get_hrv_data(d)
            with conn.cursor() as cur:
                ex = save_extra(cur, d, "garmin", sleep_raw, hrv_raw)
            conn.commit()
            ok += 1
            consecutive_err = 0
            skin += ex["skin_temp_dev_c"] is not None
            need += ex["sleep_need_min"] is not None
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            err += 1
            consecutive_err += 1
            _log(f"{d}: BLAD {str(e)[:200]}")
            if "429" in str(e) or consecutive_err >= 5:
                _log("STOP: limit Garmina lub seria bledow -- wznow pozniej (pominie zrobione dni)")
                break
            time.sleep(10)
        if i % 25 == 0 or i == len(todo):
            _log(f"[{i}/{len(todo)}] ok={ok} bledy={err} temp_skory={skin} potrzeba_snu={need} "
                 f"({time.time() - t0:.0f} s)")
        time.sleep(a.pause)

    conn.close()
    _log(f"KONIEC: ok={ok} bledy={err} dni z temp. skory={skin} z potrzeba snu={need}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
