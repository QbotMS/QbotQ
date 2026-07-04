from __future__ import annotations

"""FITMODEL -- CP/W' z krzywej mocy (MMP) wykonanych jazd.

Zrodlo: qbot_v2.training_sessions.mmp_*_w (Garmin API, maxAvgPower_N, juz
pobierane co 15 min przez import_garmin_training.py -- zero nowych wywolan API).

Metoda: envelope (najlepsza wartosc per duracja w oknie, NIE z jednej jazdy)
-> model 2-parametrowy Monod-Scherrer P(t) = W'/t + CP, linearyzowany jako
Work(t) = P(t)*t = CP*t + W' -> regresja liniowa najmniejszych kwadratow.

Duracje 300/600/1200/1800 s (5/10/20/30 min) -- zakres gdzie model CP jest
wiarygodny (krotsze <2min zaklamuje beztlenowe, dluzsze >30-40min zaklamuje
zmeczenie/tankowanie). Prog: min. 3 z 4 duracji obecne w oknie, inaczej None+reason
(przy turystyce czesto brak wysilkow maksymalnych -- nie zgadujemy).

UWAGA (uczciwie): to sa najlepsze fragmenty ZWYKLYCH jazd, nie testy maksymalne.
Moze to nieco zanizac realne CP/W'. Traktowac jako estymator, nie pomiar.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect, _coerce_date

DURATIONS = (300, 600, 1200, 1800)
MIN_POINTS = 3
WINDOW_DAYS = 90


def _envelope_curve(db_conn, as_of: date, window_days: int) -> tuple[dict[int, float], int]:
    """Najlepsza (max) wartosc mmp_{d}_w w oknie [as_of-window_days, as_of], per duracja.

    Envelope = najlepszy fragment SPOSROD WIELU jazd, nie pojedyncza jazda --
    tak buduje sie realna krzywa mocy w oknie czasowym.
    """
    cols = ",".join(f"max(mmp_{d}_w)" for d in DURATIONS)
    with db_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {cols}, count(*)
            FROM qbot_v2.training_sessions
            WHERE date >= %s AND date <= %s
              AND (sport_type IS NULL OR sport_type NOT LIKE %s)
            """,
            (as_of - timedelta(days=window_days), as_of, "%virtual%"),
        )
        row = cur.fetchone()
    n_rides = row[-1] or 0
    curve = {d: float(v) for d, v in zip(DURATIONS, row[:-1]) if v is not None}
    return curve, n_rides


def _fit_cp_wprime(curve: dict[int, float]) -> tuple[float | None, float | None, float | None]:
    """Regresja Work(t) = CP*t + W' na punktach envelope. Zwraca (cp_w, wprime_j, r2)."""
    pts = sorted(curve.items())
    n = len(pts)
    if n < MIN_POINTS:
        return None, None, None

    ts = [float(t) for t, _ in pts]
    ws = [p * t for t, p in pts]  # Work = Power * time

    mean_t = sum(ts) / n
    mean_w = sum(ws) / n
    sxx = sum((t - mean_t) ** 2 for t in ts)
    sxy = sum((t - mean_t) * (w - mean_w) for t, w in zip(ts, ws))
    if sxx == 0:
        return None, None, None

    cp = sxy / sxx
    wprime = mean_w - cp * mean_t

    ss_tot = sum((w - mean_w) ** 2 for w in ws)
    if ss_tot == 0:
        r2 = None
    else:
        ss_res = sum((w - (cp * t + wprime)) ** 2 for t, w in zip(ts, ws))
        r2 = 1 - ss_res / ss_tot

    return cp, wprime, r2


def compute_cp_wprime(db_conn, as_of: date | None = None, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """Policz CP/W' na dzien as_of (bez zapisu)."""
    as_of = _coerce_date(as_of)
    curve, n_rides = _envelope_curve(db_conn, as_of, window_days)

    if len(curve) < MIN_POINTS:
        have = sorted(curve.keys())
        return {
            "day": as_of,
            "cp_modelq_w": None,
            "wprime_modelq_kj": None,
            "cp_wprime_r2": None,
            "cp_wprime_note": (
                f"za malo wysilkow maksymalnych w oknie {window_days}d "
                f"(mam {len(curve)}/{len(DURATIONS)} duracji: {have}, min={MIN_POINTS}, n_jazd={n_rides})"
            ),
        }

    cp, wprime_j, r2 = _fit_cp_wprime(curve)
    if cp is None or cp <= 0 or wprime_j is None or wprime_j <= 0:
        return {
            "day": as_of,
            "cp_modelq_w": None,
            "wprime_modelq_kj": None,
            "cp_wprime_r2": round(r2, 3) if r2 is not None else None,
            "cp_wprime_note": f"fit niewiarygodny (cp={cp}, wprime_j={wprime_j}) -- odrzucony",
        }

    note = (
        f"okno {window_days}d, {len(curve)} duracji {sorted(curve.keys())}, "
        f"n_jazd={n_rides}, r2={round(r2, 3) if r2 is not None else 'n/a'} "
        f"-- z najlepszych fragmentow zwyklych jazd, nie testow maksymalnych"
    )

    return {
        "day": as_of,
        "cp_modelq_w": round(cp, 1),
        "wprime_modelq_kj": round(wprime_j / 1000.0, 2),
        "cp_wprime_r2": round(r2, 3) if r2 is not None else None,
        "cp_wprime_note": note,
    }


def upsert_into_daily(db_conn, row: dict[str, Any]) -> None:
    """Zapisz cp/wprime do istniejacego (lub nowego) wiersza fitmodel_daily.day."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_daily (day, cp_modelq_w, wprime_modelq_kj, cp_wprime_r2, cp_wprime_note)
            VALUES (%(day)s, %(cp_modelq_w)s, %(wprime_modelq_kj)s, %(cp_wprime_r2)s, %(cp_wprime_note)s)
            ON CONFLICT (day) DO UPDATE SET
                cp_modelq_w = EXCLUDED.cp_modelq_w,
                wprime_modelq_kj = EXCLUDED.wprime_modelq_kj,
                cp_wprime_r2 = EXCLUDED.cp_wprime_r2,
                cp_wprime_note = EXCLUDED.cp_wprime_note
            """,
            row,
        )
    db_conn.commit()


def run_daily(db_conn, as_of: date | None = None, window_days: int = WINDOW_DAYS, dry_run: bool = False) -> dict[str, Any]:
    row = compute_cp_wprime(db_conn, as_of, window_days)
    if not dry_run:
        upsert_into_daily(db_conn, row)
    return row


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FITMODEL CP/W' z krzywej mocy (MMP)")
    parser.add_argument("--as-of", default=None, help="data odniesienia YYYY-MM-DD (domyslnie dzis)")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = _db_connect()
    try:
        row = run_daily(conn, as_of=args.as_of, window_days=args.window_days, dry_run=args.dry_run)
        print("DRY-RUN (bez zapisu):" if args.dry_run else "ZAPISANO:")
        for k, v in row.items():
            print(f"  {k} = {v}")
    finally:
        conn.close()
