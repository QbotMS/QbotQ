from __future__ import annotations

"""Dzienny dopis Xerta do qbot_v2.modelq2_xert_bench (TYLKO benchmark, 2026-10-07).

Zrodlo: qbot_v2.xert_profile_snapshots (cron Xerta, 1 wiersz/dzien).
Cel:    qbot_v2.modelq2_xert_bench (wykres ModelQ vs Xert na /api/modelq2/data,
        blok "benchmark_xert" w raporcie z jazdy).

IZOLACJA (decyzja Michala 2026-10-07): Xert wpada do tabeli porownawczej, ale NIE
wplywa na parametry ModelQ. Zaden modul fitmodel/modelq2/* ani readiness nie czyta
tej tabeli; scripts/mq2_backfill.py czyta ja wylacznie do 2026-07-06 (historyczny
import CSV). Pilnuje tego tests/test_xert_isolation.py.

Historyczne wiersze (import CSV z lipca, do 2026-07-06) NIE sa nadpisywane:
ON CONFLICT DO NOTHING. Po 2026-10-04 Xert jest uznany za skazony (DECISIONS.md) --
dane ida do tabeli jako surowe porownanie, bez interpretacji.
"""

FROZEN_CSV_UNTIL = "2026-07-06"


def run_daily_xert_bench(conn, days_back: int = 14) -> dict:
    """Dopisz brakujace dni (ostatnie days_back) ze snapshotow Xerta. Idempotentne."""
    sql = """
        INSERT INTO qbot_v2.modelq2_xert_bench (day, tp_w, hie_kj, pp_w, ltp_w, max_effort, imported_at)
        SELECT DISTINCT ON (s.date)
               s.date,
               round(s.ftp_power_w::numeric, 0),
               round(s.w_prime_kj::numeric, 1),
               round(s.peak_power_w::numeric, 0),
               s.ltp_power_w,
               NULL,
               now()
        FROM qbot_v2.xert_profile_snapshots s
        WHERE s.date > %s::date
          AND s.date >= CURRENT_DATE - %s
          AND s.ftp_power_w IS NOT NULL
        ORDER BY s.date, s.imported_at DESC
        ON CONFLICT (day) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.execute(sql, (FROZEN_CSV_UNTIL, int(days_back)))
        n = cur.rowcount
    conn.commit()
    return {"inserted": n, "days_back": days_back}


def backfill_since_csv(conn) -> dict:
    """Jednorazowo: wszystkie dni od konca importu CSV do dzis."""
    from datetime import date
    days = (date.today() - date.fromisoformat(FROZEN_CSV_UNTIL)).days + 1
    return run_daily_xert_bench(conn, days_back=days)


if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.ftp_resolver import _db_connect
    c = _db_connect()
    try:
        if "--backfill" in sys.argv:
            print(backfill_since_csv(c))
        else:
            print(run_daily_xert_bench(c))
    finally:
        c.close()
