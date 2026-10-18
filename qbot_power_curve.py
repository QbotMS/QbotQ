"""Krzywa mocy (MMP = najlepsza srednia moc dla danego czasu) per jazda, liczona z danych 1 Hz.

2026-10-18. Zrodlo: qbot_v2.activity_record.power_w po CZASIE jazdy (kolumna sec): przerwy auto-pauzy
Karoo wypelniane zerami -- okno 1 h obejmuje postoj, jak w Garmin Connect (zgodnosc 5 s..20 min co do wata).
Wynik w qbot_v2.ride_power_curve (jedna krzywa na jazde: durs[] s, watts[] W). Jazda bez miernika mocy
-> puste tablice (zapisane, zeby nie liczyc w kolko). Jazda bez rekordow 1 Hz -> nie zapisywana
(doliczy sie, gdy ingest dojdzie). Uzywane przez /api/power/curve (qbot_web.py) i
scripts/power_curve_backfill.py.
"""
from __future__ import annotations

DURS = [1, 2, 3, 5, 8, 10, 12, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, 900,
        1200, 1800, 2700, 3600, 5400, 7200, 10800, 14400, 18000, 21600, 25200, 28800]
BIKE = ["cycling", "gravel_cycling"]

DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.ride_power_curve (
    external_id  text PRIMARY KEY,
    ride_date    date,
    durs         int[] NOT NULL,
    watts        int[] NOT NULL,
    n_samples    int,
    computed_at  timestamptz NOT NULL DEFAULT now()
)
"""


def _g(row, i, k):
    return row[k] if isinstance(row, dict) else row[i]


def compute_curve(powers):
    """Lista mocy 1 Hz -> (durs, watts). Brak odczytu = 0 W (jak toczenie)."""
    import numpy as np
    p = np.asarray([0.0 if v is None else float(v) for v in powers], dtype=np.float64)
    n = len(p)
    cs = np.concatenate(([0.0], np.cumsum(p)))
    durs, watts = [], []
    for d in DURS:
        if d > n:
            break
        durs.append(d)
        watts.append(int(round(float(np.max(cs[d:] - cs[:-d])) / d)))
    return durs, watts


def ensure_curves(conn, rides, limit=None, force=False):
    """rides: [(external_id, date)]. Dolicza brakujace krzywe. Zwraca (policzone, pozostale_brakujace)."""
    cur = conn.cursor()
    cur.execute(DDL)
    ids = [r[0] for r in rides]
    have = set()
    if ids:
        cur.execute("SELECT external_id FROM qbot_v2.ride_power_curve WHERE external_id = ANY(%s)", (ids,))
        have = {_g(r, 0, "external_id") for r in cur.fetchall()}
    todo = [r for r in rides if force or r[0] not in have]
    done = 0
    for eid, day in todo:
        if limit is not None and done >= limit:
            break
        cur.execute("SELECT sec, power_w FROM qbot_v2.activity_record WHERE external_id = %s ORDER BY sec", (eid,))
        rec = [(_g(r, 0, "sec"), _g(r, 1, "power_w")) for r in cur.fetchall()]
        if not rec:
            continue
        s0 = rec[0][0]
        pw = [0] * (rec[-1][0] - s0 + 1)   # os czasu; przerwy = 0 W
        for sec, w in rec:
            pw[sec - s0] = w or 0
        durs, watts = compute_curve(pw) if any(v for v in pw if v) else ([], [])
        cur.execute(
            "INSERT INTO qbot_v2.ride_power_curve (external_id, ride_date, durs, watts, n_samples, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, now()) ON CONFLICT (external_id) DO UPDATE SET "
            "ride_date = EXCLUDED.ride_date, durs = EXCLUDED.durs, watts = EXCLUDED.watts, "
            "n_samples = EXCLUDED.n_samples, computed_at = now()",
            (eid, day, durs, watts, len(pw)))
        conn.commit()
        done += 1
    return done, max(0, len(todo) - done)


def envelope(conn, start, end):
    """Najlepsza moc dla kazdego czasu z jazd w okresie (W i W/kg, z data i nazwa jazdy rekordu).
    W/kg: waga z qbot_v2.fitmodel_daily z dnia jazdy lub ostatnia wczesniejsza."""
    cur = conn.cursor()
    cur.execute(
        "SELECT t.external_id, t.date, t.activity_name, c.durs, c.watts, "
        "(SELECT f.weight_kg FROM qbot_v2.fitmodel_daily f WHERE f.day <= t.date AND f.weight_kg IS NOT NULL "
        " ORDER BY f.day DESC LIMIT 1) AS kg "
        "FROM qbot_v2.training_sessions t JOIN qbot_v2.ride_power_curve c USING (external_id) "
        "WHERE t.date BETWEEN %s AND %s AND t.sport_type = ANY(%s)",
        (start, end, BIKE))
    best_w, best_k, n = {}, {}, 0
    for r in cur.fetchall():
        durs, watts = _g(r, 3, "durs") or [], _g(r, 4, "watts") or []
        if not durs:
            continue
        n += 1
        day = str(_g(r, 1, "date"))
        name = _g(r, 2, "activity_name")
        kg = _g(r, 5, "kg")
        for d, w in zip(durs, watts):
            if d not in best_w or w > best_w[d][0]:
                best_w[d] = (w, day, name)
            if kg:
                v = w / float(kg)
                if d not in best_k or v > best_k[d][0]:
                    best_k[d] = (v, day, name)
    pts = []
    for d in sorted(best_w):
        w = best_w[d]
        k = best_k.get(d)
        pts.append({"s": d, "w": w[0], "w_date": w[1], "w_name": w[2],
                    "wkg": round(k[0], 2) if k else None, "wkg_date": k[1] if k else None,
                    "wkg_name": k[2] if k else None})
    return {"points": pts, "rides": n}
