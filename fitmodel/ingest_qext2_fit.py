from __future__ import annotations

"""FITMODEL -- lekki, czesty ingest FIT -> fitmodel_segment + fitmodel_qext2_ride.

Osobny od daily_job.py (ktory leci raz dziennie o 4:45 i robi cala reszte
pipeline'u -- xert_bench/week_planner nie maja sensu czesciej). Tu TYLKO
ingest_all_new, zeby Strona B (developer fields QExt2) i segmenty EF byly
widoczne wkrotce po jezdzie, a nie dopiero nastepnego dnia rano.

Cron: co 30 min, cale dnia (tania operacja -- pomija jazdy juz w bazie).
Patrz DECISIONS.md 2026-07-06 "Strona B -- brak automatycznego triggera".
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect

FIT_DIR = "/opt/qbot/app/outgoing/michal/hammerhead_originals"


def main() -> None:
    from fitmodel.fit_ingest import ingest_all_new
    t0 = time.time()
    conn = _db_connect()
    try:
        result = ingest_all_new(FIT_DIR, conn)
    finally:
        conn.close()
    dt = time.time() - t0
    print(f"ingest_qext2_fit ({dt:.1f}s) -> {result}")


if __name__ == "__main__":
    main()
