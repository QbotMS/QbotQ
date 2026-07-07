from __future__ import annotations

"""FITMODEL -- cp_v3: prog CP (+ W') z krzywej mocy 1Hz, kotwica + dryf CTL.

FILOZOFIA (ustalona z uzytkownikiem 2026-07-07, wszystko na zywych danych):

  * Prog NIE liczy sie ze sredniej calej jazdy (zjazdy/coasting rozcienczaja).
    Liczy sie z NAJLEPSZYCH dlugich okien mocy (10 min) z jazd 1Hz.
  * W' (rezerwa beztlenowa) liczone ODDZIELNIE z krotkich okien (para 120/600s),
    mediana z mocnych dni. Krotkie strzaly to wskaznik W', NIE progu -- nie wolno
    ich mieszac do CP (zawyzylyby prog).
  * CP-kandydat pojedynczej jazdy = b600 - W'/600  (najlepsze 10 min oczyszczone
    o zmierzone W' -> czysty prog tlenowy).
  * Miedzy "gorkami" (mocnymi odczytami) CP porusza sie WYLACZNIE dryfem CTL(XSS):
    malo jezdze -> CTL spada -> CP maleje; jezdze tyle samo -> trzyma; wiecej -> rosnie.
    (k W na 1 pkt CTL, domyslnie skalibrowane z kotwic ~0.66).
  * KOTWICA (regula B, jednostronna): nowa jazda przesuwa poziom TYLKO gdy jej
    CP-kandydat lezy POWYZEJ biezacej krzywej dryfu (wzgledem CTL, nie w liczbach
    bezwzglednych). Slabsza jazda = "nie jechalem na maksa" -> ignoruj. W dol
    schodzi sie wylacznie dryfem CTL, nigdy pojedyncza slaba jazda.

Zrodla (WSZYSTKO w bazie -- patrz CONTEXT.md sekcja Dane):
  * 1Hz: qbot_v2.activity_record (ts, power_w) per external_id.
  * CTL:  qbot_v2.fitmodel_daily.ctl_xss (liczone krokiem training_load; cp_v3
          MUSI biec PO training_load w daily_job).

Pisze do fitmodel_daily.cp_v3_w oraz .wprime_v3_kj. Nie rusza innych kolumn.
Model NIEZALEZNY od Xerta (Xert tylko benchmark).
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect, _coerce_date

# --- parametry modelu ---
HISTORY_START = date(2025, 1, 1)   # od kiedy jest 1Hz w bazie
# CTL to srednia kroczaca ~42d -- na poczatku szeregu jest sztucznie niska ("zimny
# start"). Nie wolno kotwiczyc na nienasyconym CTL, bo dryf od CTL~9 zawyza cala
# krzywa. Kotwicowanie zaczyna sie dopiero po rozbiegu.
CTL_WARMUP_DAYS = 60
ANCHOR_START = HISTORY_START + timedelta(days=CTL_WARMUP_DAYS)
WIN_SHORT = 120                    # krotkie okno do W' (s)
WIN_LONG = 600                     # dlugie okno do CP (s)
MIN_SAMPLES = 700                  # min. dlugosc jazdy 1Hz, by liczyc okno 600s
K_DRIFT = 0.66                     # W na 1 pkt CTL (dryf miedzy kotwicami)
DECAY_W_PER_DAY = 0.15            # zanik kotwicy (jak Xert): bez treningu prog
                                  # opada; dryf CTL kompensuje gdy jezdzisz.
                                  # Skalibrowane: przy tym 20.06 staje sie kotwica
                                  # (stara z 2025 zdaza zaniknac) i CP dzis ~239.
ANCHOR_MARGIN_W = 0.5              # jazda musi przebic krzywa o tyle, by byc kotwica
WPRIME_MIN_KJ, WPRIME_MAX_KJ = 3.0, 40.0   # sanity dla par okien
TAIL_WRITE_DAYS = 200


def _rolling_max(power: list, win: int) -> float | None:
    """Najlepsza srednia moc w oknie 'win' sekund (okno kroczace po 1Hz)."""
    n = len(power)
    if n < win:
        return None
    ps = [0.0] * (n + 1)
    for i, p in enumerate(power):
        ps[i + 1] = ps[i] + (p if p is not None else 0.0)
    best = 0.0
    for i in range(0, n - win + 1):
        s = (ps[i + win] - ps[i]) / win
        if s > best:
            best = s
    return best


def _fetch_rides(cur, since: date) -> list[tuple]:
    cur.execute(
        """
        SELECT external_id, MIN(ts)::date AS d
        FROM qbot_v2.activity_record
        WHERE ts::date >= %s
        GROUP BY external_id
        ORDER BY d
        """,
        (since,),
    )
    return cur.fetchall()


def _ride_windows(cur, external_id: str) -> tuple[float | None, float | None]:
    cur.execute(
        "SELECT power_w FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY ts",
        (external_id,),
    )
    pw = [r[0] for r in cur.fetchall()]
    if len(pw) < MIN_SAMPLES:
        return None, None
    return _rolling_max(pw, WIN_SHORT), _rolling_max(pw, WIN_LONG)


def _estimate_wprime(per_ride: list[dict]) -> float:
    """W' = mediana z par (120,600) na dniach gdzie krotkie > dlugie."""
    vals = []
    for r in per_ride:
        s, l = r["b_short"], r["b_long"]
        if s and l and s > l:
            wp = (s - l) / (1.0 / WIN_SHORT - 1.0 / WIN_LONG)
            if WPRIME_MIN_KJ * 1000 < wp < WPRIME_MAX_KJ * 1000:
                vals.append(wp / 1000.0)
    if not vals:
        return 10.0
    return round(median(vals), 1)


def compute_series(db_conn, end_day=None) -> dict:
    """Zwraca {day: (cp_v3_w, wprime_kj)} od pierwszej jazdy do end_day."""
    end_day = _coerce_date(end_day)
    cur = db_conn.cursor()

    rides = _fetch_rides(cur, HISTORY_START)
    if not rides:
        return {}

    # okna per jazda
    per_ride = []
    for eid, d in rides:
        b_short, b_long = _ride_windows(cur, eid)
        if b_long:
            per_ride.append({"d": d, "b_short": b_short, "b_long": b_long})
    if not per_ride:
        return {}

    # W' globalne + CP-kandydat per jazda (najlepsza jazda dnia)
    wprime_kj = _estimate_wprime(per_ride)
    wprime_w = wprime_kj * 1000.0
    ride_cp: dict[date, float] = {}
    for r in per_ride:
        cp = r["b_long"] - wprime_w / WIN_LONG
        if r["d"] not in ride_cp or cp > ride_cp[r["d"]]:
            ride_cp[r["d"]] = cp

    # CTL dzienne
    cur.execute(
        """SELECT day, ctl_xss FROM qbot_v2.fitmodel_daily
           WHERE day >= %s AND ctl_xss IS NOT NULL ORDER BY day""",
        (HISTORY_START,),
    )
    ctl = {row[0]: float(row[1]) for row in cur.fetchall()}
    if not ctl:
        return {}

    # dzien po dniu: dryf CTL + regula B (kotwica tylko powyzej krzywej)
    eligible = [d for d in ride_cp if d >= ANCHOR_START]
    if not eligible:
        return {}
    first_day = min(eligible)
    cp_a = ride_cp[first_day]
    ctl_a = ctl.get(first_day, ctl[min(ctl)])
    anchor_day = first_day
    series: dict[date, tuple] = {}
    for day in sorted(ctl):
        if day < first_day or day > end_day:
            continue
        age = (day - anchor_day).days
        # zanik z wiekiem kotwicy (w dol) + dryf CTL (w gore gdy jezdzisz)
        cp_pred = cp_a - DECAY_W_PER_DAY * age + K_DRIFT * (ctl[day] - ctl_a)
        if day in ride_cp and ride_cp[day] > cp_pred + ANCHOR_MARGIN_W:
            # jazda przebila (juz oslabiona zanikiem) krzywa -> nowa kotwica
            cp_a = ride_cp[day]
            ctl_a = ctl[day]
            anchor_day = day
            cp_pred = cp_a
        series[day] = (round(cp_pred, 1), wprime_kj)
    return series


def write_series(db_conn, series: dict, only_from: date | None = None) -> int:
    if not series:
        return 0
    items = sorted(series.items())
    if only_from is not None:
        items = [(d, v) for d, v in items if d >= only_from]
    with db_conn.cursor() as cur:
        for d, (cp, wp) in items:
            cur.execute(
                """
                INSERT INTO qbot_v2.fitmodel_daily (day, cp_v3_w, wprime_v3_kj)
                VALUES (%s, %s, %s)
                ON CONFLICT (day) DO UPDATE
                SET cp_v3_w = EXCLUDED.cp_v3_w,
                    wprime_v3_kj = EXCLUDED.wprime_v3_kj
                """,
                (d, cp, wp),
            )
    db_conn.commit()
    return len(items)


def run_backfill(db_conn, end_day=None) -> dict:
    series = compute_series(db_conn, end_day)
    n = write_series(db_conn, series)
    last = max(series) if series else None
    return {
        "days_written": n,
        "last_day": last.isoformat() if last else None,
        "cp_v3_w": series[last][0] if last else None,
        "wprime_v3_kj": series[last][1] if last else None,
    }


def run_daily(db_conn, as_of=None) -> dict:
    end_day = _coerce_date(as_of)
    series = compute_series(db_conn, end_day)
    only_from = end_day - timedelta(days=TAIL_WRITE_DAYS)
    n = write_series(db_conn, series, only_from=only_from)
    # raportuj ostatni POLICZONY dzien (moze byc < end_day, gdy brak CTL na dzis)
    last = max(series) if series else None
    val = series.get(last) if last else None
    return {"written": n, "last_day": last.isoformat() if last else None,
            "cp_v3_w": val[0] if val else None,
            "wprime_v3_kj": val[1] if val else None}


if __name__ == "__main__":
    conn = _db_connect()
    try:
        print(run_backfill(conn))
    finally:
        conn.close()
