from __future__ import annotations

"""Kotwica W' z drogi -- WARTOSC (Wariant b). Uzupelnia wprime_anchor.py (ktory
ustawia tylko PEWNOSC). Patrz docs/TODO.md [W-PRIME-KOTWICA-B].

Dla kazdego zdarzenia W'bal=0% z QExt2 (qbot_v2.fitmodel_qext2_ride) liczymy
replay_deficit (fitmodel/wbal_replay.py) -- szczyt nieograniczonego deficytu na
strumieniu 1 Hz tej jazdy = PEWNA DOLNA GRANICA realnego W' tego dnia.

Kluczowa obserwacja (zweryfikowana na zywo 2026-07-20):
  - Jesli balans schodzi PONIZEJ zera -> model (W' dnia) NIE tlumaczy jazdy ->
    to twardy dowod, ze W' bylo wieksze (np. 06.07: docisk na finiszu -> -9 kJ ->
    W' >= 29.5 kJ, mimo ze MQ2 mial 20.5).
  - Jesli balans nie schodzi pod zero -> dolna granica jest ponizej MQ2 = nie
    wnosi (dlugie "1302 s na zerze" to artefakt za niskiego W' NA KAROO, nie
    dowod na serwerze -- to naprawia repoint W' na Karoo).

Zapis: kolumny fitmodel_daily.wprime_road_kj (+ wprime_road_note). NIE zmienia
wprime_modelq_kj (MQ2 liczy swoje). Konsument (Karoo/raport) bierze
max(wprime_modelq_kj, wprime_road_kj) -- osobny krok (repoint). Reguladolna
granica: laczymy przez MAX (nie srednia -- usrednianie dolnych granic je obniza).

Wpiete jako krok "wprime_road" w fitmodel/daily_job.py (po wprime_anchor).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.api import _db_connect
from fitmodel.wbal_replay import replay_deficit

WINDOW_DAYS = 42     # jak dlugo dolna granica z drogi obowiazuje (pamiec formy ~6 tyg)
MIN_ZERO_S = 10      # odsiej pojedyncze glitche czujnika (min. sekund na W'bal=0)


def ensure_columns(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE qbot_v2.fitmodel_daily "
            "ADD COLUMN IF NOT EXISTS wprime_road_kj numeric"
        )
        cur.execute(
            "ALTER TABLE qbot_v2.fitmodel_daily "
            "ADD COLUMN IF NOT EXISTS wprime_road_note text"
        )
    conn.commit()


def _clean_event_rides(conn, min_zero_s: int) -> list[str]:
    """ride_id zdarzen W'bal=0 (>= min_zero_s). replay_deficit sam odsieje te bez
    strumienia 1 Hz (duplikaty/natywne ID Karoo -> NO_DATA), wiec dedup jest
    automatyczny: liczbe wnosza tylko jazdy z activity_record."""
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT ride_id FROM qbot_v2.fitmodel_qext2_ride "
        "WHERE wbal_zero_seconds >= %s",
        (min_zero_s,),
    )
    return [r[0] for r in cur.fetchall()]


def compute_road_wprime(conn=None, window_days: int = WINDOW_DAYS,
                        min_zero_s: int = MIN_ZERO_S) -> dict:
    """Policz wprime_road_kj dla kazdego dnia fitmodel_daily jako MAX dolnej granicy
    W' z czystych zdarzen W'bal=0 w oknie [day-window, day]. Nie rusza wprime_modelq_kj."""
    own = conn is None
    if own:
        conn = _db_connect()
    ensure_columns(conn)

    # 1) dolna granica per zdarzenie (tylko te z danymi 1 Hz)
    events = []  # (ride_date, wprime_lower_kj, ride_id, base_kj)
    for ride_id in _clean_event_rides(conn, min_zero_s):
        res = replay_deficit(ride_id, verbose=False)
        if res.get("status") != "OK":
            continue
        from datetime import date as _date
        y, m, d = (int(x) for x in res["ride_date"].split("-"))
        events.append((_date(y, m, d), float(res["wprime_lower_kj"]),
                       ride_id, float(res["wprime_base_kj"])))

    # 2) dla kazdego dnia -- max granica z okna
    cur = conn.cursor()
    cur.execute("SELECT day FROM qbot_v2.fitmodel_daily ORDER BY day")
    days = [r[0] for r in cur.fetchall()]

    n_set = 0
    n_above_mq2 = 0
    for day in days:
        best = None  # (lower_kj, ride_date, ride_id)
        for edate, lower_kj, ride_id, base_kj in events:
            if edate <= day and (day - edate).days <= window_days:
                if best is None or lower_kj > best[0]:
                    best = (lower_kj, edate, ride_id)
        if best is None:
            continue
        lower_kj, edate, ride_id = best
        note = "dolna granica z drogi: W'>=%.1f kJ (jazda %s, %s)" % (
            lower_kj, edate.isoformat(), ride_id)
        cur.execute(
            "UPDATE qbot_v2.fitmodel_daily SET wprime_road_kj=%s, wprime_road_note=%s "
            "WHERE day=%s",
            (round(lower_kj, 2), note, day),
        )
        n_set += 1
    conn.commit()

    # ile dni gdzie road > MQ2 (czyli realnie podniesie W' u konsumenta)
    cur.execute(
        "SELECT COUNT(*) FROM qbot_v2.fitmodel_daily "
        "WHERE wprime_road_kj IS NOT NULL AND wprime_modelq_kj IS NOT NULL "
        "AND wprime_road_kj > wprime_modelq_kj"
    )
    n_above_mq2 = cur.fetchone()[0]

    if own:
        conn.close()
    return {"events_with_data": len(events), "days_set": n_set,
            "days_road_gt_mq2": n_above_mq2}


if __name__ == "__main__":
    print(compute_road_wprime())
