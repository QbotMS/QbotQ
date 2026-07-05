from __future__ import annotations

"""FITMODEL E7 -- tygodniowy benchmark wlasnych estymatorow vs Xert.

Spec: FITMODEL_SPEC.md sek. 9 / FITMODEL_CLI_TASKS.md E7.
Zasada: dane Xerta JUZ w QBocie (qbot_v2.xert_profile_snapshots), nie z API,
nie recznie. To porownanie dwoch estymatorow, nie estymatora z prawda.

Dwie osobne pary (koncepcyjnie rozne metryki Xerta):
- ftp_est_w (FitModel, ~1h prog) vs xert_tp_w (Xert Threshold Power, ~1h prog)
- ltp_modelq_w (FitModel LTP, asymptota trwala z dlugich okien) vs ltp_xert_w
  (Xert Long Term Power) -- ZWERYFIKOWANE 2026-07-04: 192.9 vs 192.9 W, niemal
  identyczne. Od Kroku 1 (2026-07-05) zrodlem jest ltp_modelq_w, NIE cp_modelq_w
  (ktore od Kroku 1 = prawdziwe CP z krotkich okien, benchmarkowane przez ftp_est).
  Kolumna bench cp_modelq_w zachowuje historyczna nazwe, ale trzyma LTP ModelQ
- wprime_modelq_kj (FitModel, z krzywej mocy) vs hie_xert_kj (Xert High Intensity
  Energy, ich odpowiednik W') -- oczekiwana wieksza rozbieznosc, inne modele
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


def _latest_cp_wprime(db_conn, as_of: date) -> tuple[date | None, float | None, float | None]:
    """Najswiezszy NIEPUSTY ltp_modelq_w (LTP) + wprime_modelq_kj z fitmodel_daily na dzien <= as_of.

    Od Kroku 1 porownujemy LTP-do-LTP (ltp_modelq_w vs Xert LTP); prawdziwe CP
    (cp_modelq_w, krotkie okna) benchmarkuje ftp_est_w vs xert_tp_w.
    """
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT day, ltp_modelq_w, wprime_modelq_kj
            FROM qbot_v2.fitmodel_daily
            WHERE ltp_modelq_w IS NOT NULL
              AND day <= %s
            ORDER BY day DESC
            LIMIT 1
            """,
            (as_of,),
        )
        row = cur.fetchone()
    if not row:
        return None, None, None
    return row[0], float(row[1]), (float(row[2]) if row[2] is not None else None)


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


def _latest_xert_ltp_hie(db_conn, as_of: date) -> tuple[date | None, float | None, float | None]:
    """Najswiezszy Xert LTP (ltp_power_w) i HIE (w_prime_kj) ze snapshotow na dzien <= as_of."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT snapshot_at::date, ltp_power_w, w_prime_kj
            FROM qbot_v2.xert_profile_snapshots
            WHERE snapshot_at::date <= %s
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (as_of,),
        )
        row = cur.fetchone()
    if not row:
        return None, None, None
    return row[0], (float(row[1]) if row[1] is not None else None), (float(row[2]) if row[2] is not None else None)


def compute_benchmark(db_conn, as_of: date | None = None) -> dict[str, Any]:
    """Policz wiersz benchmarku na tydzien zawierajacy as_of (bez zapisu)."""
    as_of = _coerce_date(as_of)
    week = _week_monday(as_of)

    ftp_day, ftp_est_w = _latest_ftp_est(db_conn, as_of)
    xert_day, xert_tp_w = _latest_xert_tp(db_conn, as_of)
    cp_day, cp_modelq_w, wprime_modelq_kj = _latest_cp_wprime(db_conn, as_of)
    xert2_day, ltp_xert_w, hie_xert_kj = _latest_xert_ltp_hie(db_conn, as_of)

    delta_w = None
    if ftp_est_w is not None and xert_tp_w is not None:
        delta_w = round(ftp_est_w - xert_tp_w, 1)

    delta_cp_w = None
    if cp_modelq_w is not None and ltp_xert_w is not None:
        delta_cp_w = round(cp_modelq_w - ltp_xert_w, 1)

    delta_wprime_kj = None
    if wprime_modelq_kj is not None and hie_xert_kj is not None:
        delta_wprime_kj = round(wprime_modelq_kj - hie_xert_kj, 2)

    note_bits = []
    note_bits.append(f"ftp_est z {ftp_day.isoformat()}" if ftp_day else "brak ftp_est")
    note_bits.append(f"xert_tp z {xert_day.isoformat()}" if xert_day else "brak xert_tp")
    note_bits.append(f"ltp_modelq z {cp_day.isoformat()}" if cp_day else "brak ltp_modelq")
    note_bits.append(f"xert_ltp/hie z {xert2_day.isoformat()}" if xert2_day else "brak xert_ltp/hie")
    note = "; ".join(note_bits)

    return {
        "week": week,
        "ftp_est_w": round(ftp_est_w, 1) if ftp_est_w is not None else None,
        "xert_tp_w": round(xert_tp_w, 1) if xert_tp_w is not None else None,
        "delta_w": delta_w,
        "xert_breakthrough": None,  # brak rzetelnego sygnalu breakthrough z danych w QBocie
        "cp_modelq_w": round(cp_modelq_w, 1) if cp_modelq_w is not None else None,
        "ltp_xert_w": round(ltp_xert_w, 1) if ltp_xert_w is not None else None,
        "delta_cp_w": delta_cp_w,
        "wprime_modelq_kj": round(wprime_modelq_kj, 2) if wprime_modelq_kj is not None else None,
        "hie_xert_kj": round(hie_xert_kj, 2) if hie_xert_kj is not None else None,
        "delta_wprime_kj": delta_wprime_kj,
        "note": note,
    }


def upsert_benchmark(db_conn, row: dict[str, Any]) -> None:
    """UPSERT wiersza po kluczu week (idempotentne na tydzien)."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_xert_bench
                (week, ftp_est_w, xert_tp_w, delta_w, xert_breakthrough, note,
                 cp_modelq_w, ltp_xert_w, delta_cp_w,
                 wprime_modelq_kj, hie_xert_kj, delta_wprime_kj)
            VALUES (%(week)s, %(ftp_est_w)s, %(xert_tp_w)s, %(delta_w)s,
                    %(xert_breakthrough)s, %(note)s,
                    %(cp_modelq_w)s, %(ltp_xert_w)s, %(delta_cp_w)s,
                    %(wprime_modelq_kj)s, %(hie_xert_kj)s, %(delta_wprime_kj)s)
            ON CONFLICT (week) DO UPDATE SET
                ftp_est_w = EXCLUDED.ftp_est_w,
                xert_tp_w = EXCLUDED.xert_tp_w,
                delta_w = EXCLUDED.delta_w,
                xert_breakthrough = EXCLUDED.xert_breakthrough,
                note = EXCLUDED.note,
                cp_modelq_w = EXCLUDED.cp_modelq_w,
                ltp_xert_w = EXCLUDED.ltp_xert_w,
                delta_cp_w = EXCLUDED.delta_cp_w,
                wprime_modelq_kj = EXCLUDED.wprime_modelq_kj,
                hie_xert_kj = EXCLUDED.hie_xert_kj,
                delta_wprime_kj = EXCLUDED.delta_wprime_kj
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
                "SELECT week, ftp_est_w, xert_tp_w, delta_w, cp_modelq_w, ltp_xert_w, "
                "delta_cp_w, wprime_modelq_kj, hie_xert_kj, delta_wprime_kj "
                "FROM qbot_v2.fitmodel_xert_bench ORDER BY week DESC LIMIT 5"
            )
            print("fitmodel_xert_bench (ostatnie):")
            for r in cur.fetchall():
                print("  ", r)
    finally:
        conn.close()
