from __future__ import annotations

"""FITMODEL -- CP i LTP z krzywej mocy (MMP) wykonanych jazd.

Zrodlo: qbot_v2.training_sessions.mmp_*_w (Garmin API, maxAvgPower_N, juz
pobierane co 15 min przez import_garmin_training.py -- zero nowych wywolan API).

Metoda: envelope (najlepsza wartosc per duracja w oknie, NIE z jednej jazdy)
-> model 2-parametrowy Monod-Scherrer P(t) = W'/t + CP, linearyzowany jako
Work(t) = P(t)*t = CP*t + W' -> regresja liniowa najmniejszych kwadratow.

DWA DOPASOWANIA (od Kroku 1, 2026-07-05):
- CP  z KROTKICH okien 120/300/600 s -> prawdziwe CP (~= FTP). Kolumna cp_modelq_w.
- LTP z DLUGICH  okien 300/600/1200/1800 s -> asymptota trwala (Long Term Power),
  odpowiednik Xert LTP. Kolumna ltp_modelq_w.
Wczesniej pojedyncze dlugie dopasowanie zapisywalo LTP mylnie jako cp_modelq_w
(cp_modelq_w == Xert LTP, delta ~0). Rozdzielone -- patrz DECISIONS.md 2026-07-05.

W' (wprime_modelq_kj): brany z intercepta dopasowania DLUGIEGO, bez zmian wzgledem
stanu sprzed Kroku 1. Traktowany jako NIEWIARYGODNY (submaksymalny artefakt) --
poprawne W' (null + range + confidence) to osobny Krok 2.

UWAGA (uczciwie): to sa najlepsze fragmenty ZWYKLYCH jazd, nie testy maksymalne.
Moze to nieco zanizac realne CP/LTP. Traktowac jako estymator, nie pomiar.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect, _coerce_date

CP_DURATIONS = (120, 300, 600)          # krotkie okna -> prawdziwe CP (~FTP)
LTP_DURATIONS = (300, 600, 1200, 1800)  # dlugie okna  -> LTP (asymptota trwala)
CP_MIN_POINTS = 3
LTP_MIN_POINTS = 3
WINDOW_DAYS = 90


def _envelope_curve(db_conn, as_of: date, window_days: int, durations: tuple[int, ...]) -> tuple[dict[int, float], int]:
    """Najlepsza (max) wartosc mmp_{d}_w w oknie [as_of-window_days, as_of], per duracja.

    Envelope = najlepszy fragment SPOSROD WIELU jazd, nie pojedyncza jazda --
    tak buduje sie realna krzywa mocy w oknie czasowym.
    """
    cols = ",".join(f"max(mmp_{d}_w)" for d in durations)
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
    curve = {d: float(v) for d, v in zip(durations, row[:-1]) if v is not None}
    return curve, n_rides


def _fit_model(curve: dict[int, float], min_points: int) -> tuple[float | None, float | None, float | None]:
    """Regresja Work(t) = P*t + W' na punktach envelope. Zwraca (asymptota_w, wprime_j, r2).

    asymptota_w = nachylenie (CP dla krotkich okien / LTP dla dlugich).
    """
    pts = sorted(curve.items())
    n = len(pts)
    if n < min_points:
        return None, None, None

    ts = [float(t) for t, _ in pts]
    ws = [p * t for t, p in pts]  # Work = Power * time

    mean_t = sum(ts) / n
    mean_w = sum(ws) / n
    sxx = sum((t - mean_t) ** 2 for t in ts)
    sxy = sum((t - mean_t) * (w - mean_w) for t, w in zip(ts, ws))
    if sxx == 0:
        return None, None, None

    slope = sxy / sxx           # asymptota (CP / LTP)
    wprime = mean_w - slope * mean_t

    ss_tot = sum((w - mean_w) ** 2 for w in ws)
    if ss_tot == 0:
        r2 = None
    else:
        ss_res = sum((w - (slope * t + wprime)) ** 2 for t, w in zip(ts, ws))
        r2 = 1 - ss_res / ss_tot

    return slope, wprime, r2


def compute_cp_wprime(db_conn, as_of: date | None = None, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """Policz CP (krotkie okna) i LTP (dlugie okna) na dzien as_of (bez zapisu)."""
    as_of = _coerce_date(as_of)

    out: dict[str, Any] = {
        "day": as_of,
        "cp_modelq_w": None, "cp_wprime_r2": None, "cp_wprime_note": None,
        "ltp_modelq_w": None, "ltp_modelq_r2": None, "ltp_modelq_note": None,
        "wprime_modelq_kj": None,
    }

    # --- CP: krotkie okna 120/300/600 ---
    cp_curve, cp_n = _envelope_curve(db_conn, as_of, window_days, CP_DURATIONS)
    if len(cp_curve) < CP_MIN_POINTS:
        out["cp_wprime_note"] = (
            f"za malo krotkich wysilkow w oknie {window_days}d "
            f"(mam {len(cp_curve)}/{len(CP_DURATIONS)}: {sorted(cp_curve.keys())}, min={CP_MIN_POINTS}, n_jazd={cp_n})"
        )
    else:
        cp, _cp_wp_j, cp_r2 = _fit_model(cp_curve, CP_MIN_POINTS)
        if cp is None or cp <= 0:
            out["cp_wprime_r2"] = round(cp_r2, 3) if cp_r2 is not None else None
            out["cp_wprime_note"] = f"fit CP niewiarygodny (cp={cp}) -- odrzucony"
        else:
            out["cp_modelq_w"] = round(cp, 1)
            out["cp_wprime_r2"] = round(cp_r2, 3) if cp_r2 is not None else None
            out["cp_wprime_note"] = (
                f"prawdziwe CP z krotkich okien {sorted(cp_curve.keys())}, okno {window_days}d, "
                f"n_jazd={cp_n}, r2={round(cp_r2, 3) if cp_r2 is not None else 'n/a'} "
                f"-- najlepsze fragmenty zwyklych jazd, nie testy maksymalne"
            )

    # --- LTP: dlugie okna 300/600/1200/1800 (+ W' z intercepta, niewiarygodne) ---
    ltp_curve, ltp_n = _envelope_curve(db_conn, as_of, window_days, LTP_DURATIONS)
    if len(ltp_curve) < LTP_MIN_POINTS:
        out["ltp_modelq_note"] = (
            f"za malo dlugich wysilkow w oknie {window_days}d "
            f"(mam {len(ltp_curve)}/{len(LTP_DURATIONS)}: {sorted(ltp_curve.keys())}, min={LTP_MIN_POINTS}, n_jazd={ltp_n})"
        )
    else:
        ltp, ltp_wp_j, ltp_r2 = _fit_model(ltp_curve, LTP_MIN_POINTS)
        if ltp is None or ltp <= 0:
            out["ltp_modelq_r2"] = round(ltp_r2, 3) if ltp_r2 is not None else None
            out["ltp_modelq_note"] = f"fit LTP niewiarygodny (ltp={ltp}) -- odrzucony"
        else:
            out["ltp_modelq_w"] = round(ltp, 1)
            out["ltp_modelq_r2"] = round(ltp_r2, 3) if ltp_r2 is not None else None
            out["ltp_modelq_note"] = (
                f"LTP (asymptota trwala) z dlugich okien {sorted(ltp_curve.keys())}, okno {window_days}d, "
                f"n_jazd={ltp_n}, r2={round(ltp_r2, 3) if ltp_r2 is not None else 'n/a'} "
                f"-- odpowiednik Xert LTP"
            )
            # W' -- intercept dlugiego dopasowania, bez zmian (NIEWIARYGODNY, patrz Krok 2)
            if ltp_wp_j is not None and ltp_wp_j > 0:
                out["wprime_modelq_kj"] = round(ltp_wp_j / 1000.0, 2)

    return out


def upsert_into_daily(db_conn, row: dict[str, Any]) -> None:
    """Zapisz cp/ltp/wprime do istniejacego (lub nowego) wiersza fitmodel_daily.day."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_daily
                (day, cp_modelq_w, wprime_modelq_kj, cp_wprime_r2, cp_wprime_note,
                 ltp_modelq_w, ltp_modelq_r2, ltp_modelq_note)
            VALUES
                (%(day)s, %(cp_modelq_w)s, %(wprime_modelq_kj)s, %(cp_wprime_r2)s, %(cp_wprime_note)s,
                 %(ltp_modelq_w)s, %(ltp_modelq_r2)s, %(ltp_modelq_note)s)
            ON CONFLICT (day) DO UPDATE SET
                cp_modelq_w = EXCLUDED.cp_modelq_w,
                wprime_modelq_kj = EXCLUDED.wprime_modelq_kj,
                cp_wprime_r2 = EXCLUDED.cp_wprime_r2,
                cp_wprime_note = EXCLUDED.cp_wprime_note,
                ltp_modelq_w = EXCLUDED.ltp_modelq_w,
                ltp_modelq_r2 = EXCLUDED.ltp_modelq_r2,
                ltp_modelq_note = EXCLUDED.ltp_modelq_note
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

    parser = argparse.ArgumentParser(description="FITMODEL CP (krotkie okna) i LTP (dlugie okna) z krzywej mocy (MMP)")
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
