"""Kalibracja: prognoza temperatury powietrza -> temperatura na trasie Michala (czujnik Karoo).

Dane: qbot_v2.activity_record (1 Hz) jazd z Karoo (activity_device manufacturer='tacx'), tylko jazda
(speed > 2 m/s), bez pierwszych 10 min (licznik stygnie po wyjsciu z domu); mediana godzinowa.
Prognoza: historical-forecast-api.open-meteo.com (to samo zrodlo co prognozy, w UTC).
Model: regresja liniowa roznicy (Karoo - prognoza) na cechach dostepnych w prognozie trasy:
sezon, godzina lokalna, wieczor, zachmurzenie, wiatr, wilgotnosc, temperatura, predkosc.
Walidacja: 10 grup jazd (cala jazda w jednej grupie). Wynik: data/thermal_model.json.

Uzycie: .venv/bin/python3 scripts/thermal_calibrate.py [--dry]
"""
import datetime as dt
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
import httpx
import numpy as np
from fitmodel.api import _db_connect

OUT = "/opt/qbot/app/data/thermal_model.json"
WAW, UTC = ZoneInfo("Europe/Warsaw"), dt.timezone.utc
VARS = "temperature_2m,cloud_cover,wind_speed_10m,relative_humidity_2m"
sys.path.insert(0, "/opt/qbot/app/qbot3/routes")
from ride_thermal import FEATURES, feature_vector  # noqa: E402  (jedna definicja cech dla kalibracji i uzycia)


def load():
    c = _db_connect(); cur = c.cursor()
    cur.execute("""
      SELECT a.external_id AS rk, to_char(a.ts AT TIME ZONE 'Europe/Warsaw', 'YYYY-MM-DD"T"HH24') AS h,
             percentile_cont(0.5) WITHIN GROUP (ORDER BY a.temperature_c) AS t_dev, count(*) AS n,
             avg(a.speed_mps) AS v, avg(a.lat) AS la, avg(a.lon) AS lo
      FROM qbot_v2.activity_record a
      JOIN qbot_v2.activity_device d ON d.external_id=a.external_id AND d.device_index=0 AND d.manufacturer='tacx'
      WHERE a.sec >= 600 AND a.speed_mps > 2 AND a.temperature_c IS NOT NULL AND a.lat IS NOT NULL
      GROUP BY 1, 2 HAVING count(*) >= 600""")
    rows = [r if isinstance(r, dict) else dict(zip(("rk", "h", "t_dev", "n", "v", "la", "lo"), r)) for r in cur.fetchall()]
    c.close()
    return rows


def main(dry):
    rows = load()
    rides = {}
    for r in rows:
        rides.setdefault(r["rk"], []).append(r)

    def om(rk):
        hs = rides[rk]
        la = sum(float(x["la"]) for x in hs) / len(hs); lo = sum(float(x["lo"]) for x in hs) / len(hs)
        days = sorted({x["h"][:10] for x in hs})
        for _ in range(3):
            try:
                h = httpx.get("https://historical-forecast-api.open-meteo.com/v1/forecast", params={
                    "latitude": round(la, 3), "longitude": round(lo, 3), "timezone": "GMT", "start_date": days[0],
                    "end_date": days[-1], "hourly": VARS, "wind_speed_unit": "ms"}, timeout=30).json()["hourly"]
                return rk, {t[:13]: {k: h[k][i] for k in VARS.split(",")} for i, t in enumerate(h["time"])}
            except Exception:
                time.sleep(1.5)
        return rk, None

    with ThreadPoolExecutor(6) as ex:
        wx = dict(ex.map(om, list(rides)))
    P = []
    for rk, hs in rides.items():
        w = wx.get(rk) or {}
        for x in hs:
            o = w.get(x["h"])
            if not o or any(o[k] is None for k in VARS.split(",")):
                continue
            tl = dt.datetime.strptime(x["h"], "%Y-%m-%dT%H").replace(tzinfo=UTC).astimezone(WAW)
            P.append((rk, feature_vector(tl.timetuple().tm_yday, tl.hour + 0.5, o["cloud_cover"], o["wind_speed_10m"],
                                         o["relative_humidity_2m"], o["temperature_2m"], float(x["v"]) * 3.6),
                      float(x["t_dev"]) - o["temperature_2m"]))
    ids = sorted({p[0] for p in P})
    fold = {rk: i % 10 for i, rk in enumerate(ids)}
    err = []
    for f in range(10):
        tr = [p for p in P if fold[p[0]] != f]; te = [p for p in P if fold[p[0]] == f]
        b, *_ = np.linalg.lstsq(np.array([p[1] for p in tr]), np.array([p[2] for p in tr]), rcond=None)
        err += [p[2] - float(np.dot(p[1], b)) for p in te]
    e = np.array(err)
    beta, *_ = np.linalg.lstsq(np.array([p[1] for p in P]), np.array([p[2] for p in P]), rcond=None)
    model = {"version": 1, "built_at": dt.datetime.now(WAW).isoformat(timespec="seconds"),
             "source": "Karoo (activity_record) vs Open-Meteo historical forecast", "device": "Karoo (tacx)",
             "n_hours": len(P), "n_rides": len(ids), "features": FEATURES, "coef": [round(float(x), 4) for x in beta],
             "cv": {"mae": round(float(np.mean(np.abs(e))), 2), "p05": round(float(np.percentile(e, 5)), 2),
                    "p10": round(float(np.percentile(e, 10)), 2), "p90": round(float(np.percentile(e, 90)), 2),
                    "p95": round(float(np.percentile(e, 95)), 2)}}
    print(json.dumps(model, ensure_ascii=False, indent=1))
    if not dry:
        tmp = OUT + ".tmp"
        json.dump(model, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, OUT)
        print("zapisano:", OUT)


if __name__ == "__main__":
    main("--dry" in sys.argv)
