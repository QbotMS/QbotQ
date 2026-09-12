"""Szacowanie biegu z predkosci i kadencji dla rowerow bez czujnika biegow (mechaniczny naped). DECISIONS 2026-09-12.

Dla kazdego rekordu z kadencja 50-110 i predkoscia > 2 m/s: rozwiniecie = v*60/cad [m/obr];
kandydaci = obwod * przod / zab; wybieramy najblizszy, jesli blad < 7%. Wynik -> activity_record.gear_rear_est
(1 = najlzejszy = najwiekszy zab, zgodnie z kanonem gear_rear_num). ride_drivetrain: cassette_source='physics_est'.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

# profile rowerow bez czujnika biegow (nazwa z qbot_v2.bike_sensor)
BIKE_GEARING = {
    "Canyon Grand Canyon": {"front_t": 36, "cassette_code": "11-50", "cogs": [11, 13, 15, 17, 19, 22, 25, 28, 32, 36, 42, 50],
                            "circumference_m": 2.300, "label": "36T"},  # 29x2.4 Wicked Will ~ 2.30 m
}


def _conn():
    from fitmodel.api import _db_connect
    return _db_connect()


def ensure_schema(conn):
    cur = conn.cursor()
    cur.execute("ALTER TABLE qbot_v2.activity_record ADD COLUMN IF NOT EXISTS gear_rear_est smallint")
    for name, g in BIKE_GEARING.items():
        cur.execute("INSERT INTO qbot_v2.gear_cassette(code, label, cogs) VALUES(%s,%s,%s) ON CONFLICT (code) DO NOTHING",
                    (g["cassette_code"], "SRAM PG-1210 Eagle 11-50T 12s", g["cogs"]))
    conn.commit()


def estimate_ride(conn, external_id: str, bike: str) -> dict:
    g = BIKE_GEARING.get(bike)
    if not g:
        return {"ok": False, "reason": "brak profilu napedu dla roweru %s" % bike}
    ensure_schema(conn)
    cogs = g["cogs"]; n = len(cogs); circ = g["circumference_m"]; front = g["front_t"]
    dev = [circ * front / c for c in cogs]            # rozwiniecie per zab
    cur = conn.cursor()
    cur.execute("SELECT sec, speed_mps, cadence_rpm FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (external_id,))
    rows = cur.fetchall()
    upd = []; hit = 0; tot = 0
    for sec, v, cad in rows:
        est = None
        if v is not None and cad is not None and 50 <= cad <= 110 and v > 2.0:
            tot += 1
            d = v * 60.0 / cad
            j = min(range(n), key=lambda i: abs(dev[i] - d))
            if abs(dev[j] - d) / dev[j] <= 0.07:
                est = n - j           # j=0 -> 11T (najciezszy) -> pozycja n; j=n-1 -> 50T -> pozycja 1
                hit += 1
        upd.append((est, external_id, sec))
    cur.executemany("UPDATE qbot_v2.activity_record SET gear_rear_est=%s WHERE external_id=%s AND sec=%s", upd)
    conf = round(100.0 * hit / tot, 1) if tot else 0.0
    cur.execute("SELECT min(ts)::date FROM qbot_v2.activity_record WHERE external_id=%s", (external_id,))
    day = cur.fetchone()[0]
    cur.execute("""INSERT INTO qbot_v2.ride_drivetrain(external_id, day, chainring_t, chainring_label, cassette_code, cassette_source,
                     circumference_m, positions, flag, note, computed_at)
                   VALUES(%s,%s,%s,%s,%s,'physics_est',%s,%s,%s,%s,now())
                   ON CONFLICT (external_id) DO UPDATE SET day=EXCLUDED.day, chainring_t=EXCLUDED.chainring_t, chainring_label=EXCLUDED.chainring_label,
                     cassette_code=EXCLUDED.cassette_code, cassette_source='physics_est', circumference_m=EXCLUDED.circumference_m,
                     positions=EXCLUDED.positions, flag=EXCLUDED.flag, note=EXCLUDED.note, computed_at=now()""",
                (external_id, day, front, g["label"], g["cassette_code"], circ, n,
                 "ok" if conf >= 70 else "uwaga", "biegi szacowane z predkosci/kadencji (%s), dopasowano %s%% probek z pedalowaniem" % (bike, conf)))
    conn.commit()
    return {"ok": True, "bike": bike, "matched_pct": conf, "records": len(rows), "pedaling": tot}


def estimate_if_needed(conn, external_id: str) -> dict | None:
    """Rower bez AXS z profilem -> szacuj. Rower z czujnikiem -> nic (build_drivetrain robi swoje)."""
    from qbot3.rides.activity_devices import bike_for_ride
    b = bike_for_ride(conn, external_id)
    if b.get("has_axs") or not b.get("bike") or b["bike"] not in BIKE_GEARING:
        return None
    return estimate_ride(conn, external_id, b["bike"])
