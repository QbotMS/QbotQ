"""Przebieg rowerow (licznik). DECYZJA 2026-10-01 (Michal).

Stan licznika = baza (km ustalone recznie na dany moment) + suma km jazd przypisanych do roweru
PO tym momencie. Rower jazdy rozpoznaje bike_for_ride (czujniki z FIT, qbot3/rides/activity_devices.py).
Bazy 2026-10-01: Grizl 9791 km i Monster (Grand Canyon) 353 km od chwili ustalenia; Grail 0 km od 01.10 00:00.
Jazdy bez listy czujnikow (bike=None) nie sa liczone -- zwracane jako 'unassigned' do kontroli.
Tabela qbot_v2.bike_odometer: garage_bike_id (id w garazu SQLite), sensor_bike (nazwa z bike_sensor).
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.bike_odometer(
  garage_bike_id int PRIMARY KEY, sensor_bike text NOT NULL, baseline_km numeric NOT NULL,
  baseline_at timestamptz NOT NULL, note text, set_at timestamptz DEFAULT now());
"""

_SQL_RIDES = """
SELECT DISTINCT ON (external_id) external_id, started_at, distance_m, duration_s
FROM qbot_v2.training_sessions
WHERE sport_type = 'cycling' AND external_id IS NOT NULL AND started_at >= %s
ORDER BY external_id, imported_at DESC
"""


def _conn():
    from fitmodel.api import _db_connect
    return _db_connect()


def ensure_tables(conn):
    conn.cursor().execute(DDL); conn.commit()


def odometers(conn=None) -> dict:
    """{garage_bike_id: {km, baseline_km, baseline_at, rides, hours, added_km, last_ride}, '_unassigned': n}"""
    own = conn is None
    conn = conn or _conn()
    try:
        from qbot3.rides.activity_devices import bike_for_ride
        ensure_tables(conn)
        cur = conn.cursor()
        cur.execute("SELECT garage_bike_id, sensor_bike, baseline_km, baseline_at FROM qbot_v2.bike_odometer")
        rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
        if not rows:
            return {}
        out = {}
        by_name = {}
        for gid, name, bkm, bat in rows:
            out[int(gid)] = {"sensor_bike": name, "baseline_km": float(bkm), "baseline_at": bat.isoformat(),
                             "added_km": 0.0, "rides": 0, "hours": 0.0, "last_ride": None, "_at": bat}
            by_name[name] = int(gid)
        start = min(v["_at"] for v in out.values())
        cur.execute(_SQL_RIDES, (start,))
        rides = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
        unassigned = 0
        for eid, st, dist, dur in rides:
            b = bike_for_ride(conn, eid).get("bike")
            gid = by_name.get(b)
            if gid is None:
                unassigned += 1
                continue
            o = out[gid]
            if st is None or st < o["_at"]:
                continue
            o["added_km"] += (dist or 0) / 1000.0
            o["hours"] += (dur or 0) / 3600.0
            o["rides"] += 1
            if o["last_ride"] is None or st.isoformat() > o["last_ride"]:
                o["last_ride"] = st.isoformat()
        for o in out.values():
            o.pop("_at")
            o["added_km"] = round(o["added_km"], 1)
            o["hours"] = round(o["hours"], 1)
            o["km"] = round(o["baseline_km"] + o["added_km"], 1)
        out["_unassigned"] = unassigned
        return out
    finally:
        if own:
            conn.close()


def set_baseline(garage_bike_id: int, sensor_bike: str, km: float, at=None, note=None, conn=None):
    own = conn is None
    conn = conn or _conn()
    try:
        ensure_tables(conn)
        conn.cursor().execute(
            """INSERT INTO qbot_v2.bike_odometer(garage_bike_id, sensor_bike, baseline_km, baseline_at, note)
               VALUES(%s,%s,%s,COALESCE(%s, now()),%s)
               ON CONFLICT (garage_bike_id) DO UPDATE SET sensor_bike=EXCLUDED.sensor_bike,
                 baseline_km=EXCLUDED.baseline_km, baseline_at=EXCLUDED.baseline_at, note=EXCLUDED.note, set_at=now()""",
            (int(garage_bike_id), sensor_bike, float(km), at, note))
        conn.commit()
    finally:
        if own:
            conn.close()
