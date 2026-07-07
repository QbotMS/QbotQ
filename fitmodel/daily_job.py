from __future__ import annotations

"""FITMODEL -- dzienny orkiestrator pipeline'u.

Uruchamia po kolei, z ODPORNOSCIA WARSTWOWA (awaria jednego kroku nie blokuje
reszty -- spec sek. 1): ingest nowych FIT -> resolver (fitmodel_daily) ->
CP/W' z krzywej mocy -> glikogen -> tagowanie nawierzchni (+kalibracja) ->
ride_buckets -> benchmark Xert.

Kazdy krok ma wlasny try/except i raport czasu. Jedno wspolne polaczenie DB.
Wpiety w cron (codziennie). Log: /opt/qbot/logs/fitmodel_daily.log
"""

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect

FIT_DIR = "/opt/qbot/app/outgoing/michal/hammerhead_originals"


def _step(name, fn):
    t0 = time.time()
    try:
        result = fn()
        dt = time.time() - t0
        print(f"[OK ] {name} ({dt:.1f}s) -> {result}")
        return True
    except Exception as exc:
        dt = time.time() - t0
        print(f"[ERR] {name} ({dt:.1f}s): {exc}")
        traceback.print_exc()
        return False


def main() -> None:
    print(f"=== FITMODEL daily {datetime.now().isoformat(timespec='seconds')} ===")
    conn = _db_connect()
    try:
        # 1. Ingest nowych jazd -> fitmodel_segment
        def _ingest():
            from fitmodel.fit_ingest import ingest_all_new
            return ingest_all_new(FIT_DIR, conn)
        _step("ingest_fit", _ingest)

        # 2. Resolver FTP_est -> fitmodel_daily
        def _resolver():
            from fitmodel.ftp_resolver import run_weekly_job
            return run_weekly_job(conn)
        _step("ftp_resolver", _resolver)

        # 2b. CP/W' z krzywej mocy (Garmin MMP, training_sessions) -> fitmodel_daily
        def _cp_wprime():
            from fitmodel.cp_wprime import run_daily
            return run_daily(conn, dry_run=False)
        _step("cp_wprime", _cp_wprime)

        # 2c. Wskaznik gotowosci (HRV+RHR+sen, baseline 60d) -> fitmodel_daily
        def _readiness():
            from fitmodel.readiness import save_readiness
            return save_readiness(conn)
        _step("readiness", _readiness)

        # 2d. Krok 3 -- W'bal tick-po-ticku dla nowych jazd -> fitmodel_wbal_ride
        def _wbal_replay():
            from fitmodel.wbal_replay import run_for_new_rides
            return run_for_new_rides()
        _step("wbal_replay", _wbal_replay)

        # 2e. CTL/ATL/TSB z XSS (raw + plus skorygowany o readiness_score) -> fitmodel_daily
        def _training_load():
            from datetime import date
            from fitmodel.training_load import compute_and_store
            return compute_and_store(conn, date(2025, 5, 1), date.today())
        _step("training_load", _training_load)

        # 3. Glikogen -> fitmodel_daily
        def _glyco():
            from fitmodel.glycogen import update_glycogen_in_daily
            return update_glycogen_in_daily(conn, FIT_DIR, days=30)
        _step("glycogen", _glyco)

        # 4. Tagowanie nawierzchni nowych segmentow + kalibracja (cache OSM)
        def _surface():
            from fitmodel.surface_tag import tag_segments, calibrate
            res = tag_segments(conn, only_untagged=True, use_cache=True, dry_run=False)
            tagged = sum(1 for r in res if r["dominant"])
            rep = calibrate(conn, dry_run=False)
            return {"nowe_otagowane": tagged, "kalibracja_update": rep["updated"]}
        _step("surface_tag", _surface)

        # 5. Ride buckets nowych jazd -> fitmodel_ride_buckets
        def _buckets():
            from fitmodel.ride_buckets import process_rides
            res = process_rides(conn, only_new=True, dry_run=False)
            return {"nowe_jazdy": len(res)}
        _step("ride_buckets", _buckets)

        # 6. Benchmark Xert (UPSERT biezacy tydzien; FTP vs TP + CP vs LTP + W' vs HIE)
        def _xert():
            from fitmodel.xert_bench import run_weekly_benchmark
            return run_weekly_benchmark(conn, dry_run=False)
        _step("xert_bench", _xert)

        # 7. Plan tygodnia (tryb=PROPOZYCJA do zatwierdzenia) -> fitmodel_week_plan
        def _plan():
            from fitmodel.week_planner import build_plan, upsert_plan
            p = build_plan(conn)
            upsert_plan(conn, p)
            return {"week": p["week"], "mode": p["mode"],
                    "budget_h": p["time_budget_h"], "feasible": p["feasible"]}
        _step("week_planner", _plan)
    finally:
        conn.close()
    print("=== koniec ===")


if __name__ == "__main__":
    main()
