from __future__ import annotations

"""FITMODEL E7 -- tygodniowy benchmark FTP_est (dane wlasne) vs Xert TP.

Spec: FITMODEL_SPEC.md sek. 9 / FITMODEL_CLI_TASKS.md E7.
Zasada: xert_tp z danych Xerta JUZ w QBocie (qbot_v2.xert_profile_snapshots),
nie z API, nie recznie. To porownanie dwoch estymatorow, nie estymatora z prawda.
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

from fitmodel.ftp_resolver import _db_connect, _coerce_date


def _week_monday(value: date) -> date:
    """Poniedzialek tygodnia ISO dla podanej daty (klucz wiersza benchmarku)."""
    return value - timedelta(days=value.weekday())


def _latest_ftp_est(db_conn, as_of: date) -> tuple[date | None, float | None]:
    """Najswiezszy NIEPUSTY ftp_est_w z fitmodel_daily na dzien <= as_of."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT day, ftp_est_w
            FROM qbot_v2.fitmodel_daily
            WHERE ftp_est_w IS NOT NULL
              AND day <= %s
            ORDER BY day DESC
            LIMIT 1
            """,
            (as_of,),
        )
        row = cur.fetchone()
    if not row:
        return None, None
    return row[0], float(row[1])


def _latest_xert_tp(db_conn, as_of: date) -> tuple[date | None, float | None]:
    """Najswiezszy Xert TP (ftp_power_w) ze snapshotow na dzien <= as_of."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT snapshot_at::date, ftp_power_w
            FROM qbot_v2.xert_profile_snapshots
            WHERE ftp_power_w IS NOT NULL
              AND snapshot_at::date <= %s
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (as_of,),
        )
        row = cur.fetchone()
    if not row:
        return None, None
    return row[0], float(row[1])


def compute_benchmark(db_conn, as_of: date | None = None) -> dict[str, Any]:
    """Policz wiersz benchmarku na tydzien zawierajacy as_of (bez zapisu)."""
    as_of = _coerce_date(as_of)
    week = _week_monday(as_of)

    ftp_day, ftp_est_w = _latest_ftp_est(db_conn, as_of)
    xert_day, xert_tp_w = _latest_xert_tp(db_conn, as_of)

    delta_w = None
    if ftp_est_w is not None and xert_tp_w is not None:
        delta_w = round(ftp_est_w - xert_tp_w, 1)

    note_bits = []
    if ftp_day is not None:
        note_bits.append(f"ftp_est z {ftp_day.isoformat()}")
    else:
        note_bits.append("brak ftp_est")
    if xert_day is not None:
        note_bits.append(f"xert_tp z {xert_day.isoformat()}")
    else:
        note_bits.append("brak xert_tp")
    note = "; ".join(note_bits)

    return {
        "week": week,
        "ftp_est_w": round(ftp_est_w, 1) if ftp_est_w is not None else None,
        "xert_tp_w": round(xert_tp_w, 1) if xert_tp_w is not None else None,
        "delta_w": delta_w,
        "xert_breakthrough": None,  # brak rzetelnego sygnalu breakthrough z danych w QBocie
        "note": note,
    }


def upsert_benchmark(db_conn, row: dict[str, Any]) -> None:
    """UPSERT wiersza po kluczu week (idempotentne na tydzien)."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_xert_bench
                (week, ftp_est_w, xert_tp_w, delta_w, xert_breakthrough, note)
            VALUES (%(week)s, %(ftp_est_w)s, %(xert_tp_w)s, %(delta_w)s,
                    %(xert_breakthrough)s, %(note)s)
            ON CONFLICT (week) DO UPDATE SET
                ftp_est_w = EXCLUDED.ftp_est_w,
                xert_tp_w = EXCLUDED.xert_tp_w,
                delta_w = EXCLUDED.delta_w,
                xert_breakthrough = EXCLUDED.xert_breakthrough,
                note = EXCLUDED.note
            """,
            row,
        )
    db_conn.commit()


def run_weekly_benchmark(db_conn, as_of: date | None = None, dry_run: bool = False) -> dict[str, Any]:
    row = compute_benchmark(db_conn, as_of)
    if not dry_run:
        upsert_benchmark(db_conn, row)
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FITMODEL E7 benchmark Xert")
    parser.add_argument("--as-of", default=None, help="data odniesienia YYYY-MM-DD (domyslnie dzis)")
    parser.add_argument("--dry-run", action="store_true", help="policz i wypisz, bez zapisu do DB")
    args = parser.parse_args()

    conn = _db_connect()
    try:
        row = run_weekly_benchmark(conn, as_of=args.as_of, dry_run=args.dry_run)
        print("DRY-RUN (bez zapisu):" if args.dry_run else "ZAPISANO:")
        for k, v in row.items():
            print(f"  {k} = {v}")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT week, ftp_est_w, xert_tp_w, delta_w, xert_breakthrough, note "
                "FROM qbot_v2.fitmodel_xert_bench ORDER BY week DESC LIMIT 5"
            )
            print("fitmodel_xert_bench (ostatnie):")
            for r in cur.fetchall():
                print("  ", r)
    finally:
        conn.close()
