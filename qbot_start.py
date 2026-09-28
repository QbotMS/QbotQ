# -*- coding: utf-8 -*-
"""START - wizytowka QBota (2026-09-28, kierunek C "Galeria w ruchu").
GET /api/start/card -> zdjecia ze Stravy (qbot_v2.strava_photo), miejsca jazd roku (training_sessions + pierwszy punkt
activity_record, grupowane do regionow ze slownika), najblizszy start (Kalendarz), cele A/B (trainer_goal)."""
from __future__ import annotations

import math
from datetime import date
from typing import Callable

from fastapi import APIRouter, HTTPException, Request

HOME = (52.23, 21.01)
# slownik regionow (srodek, promien km) - etykiety mapy; jazda trafia do najblizszego w promieniu
REGIONS = [
    ("Warszawa", 52.23, 21.01, 45), ("Mazowsze", 52.3, 20.6, 110), ("Podlasie", 53.1, 22.6, 90), ("Suwalszczyzna", 54.1, 23.0, 60),
    ("Mazury", 53.9, 21.8, 80), ("Kujawy", 52.7, 19.0, 70), ("Pomorze", 53.9, 18.2, 110), ("Bory Tucholskie", 53.6, 17.9, 45),
    ("Łódzkie", 51.8, 19.6, 70), ("Świętokrzyskie", 51.0, 20.7, 60), ("Małopolska", 50.1, 19.9, 75), ("Opolszczyzna", 50.5, 17.6, 70),
    ("Dolny Śląsk", 51.1, 16.0, 90), ("Lubelskie", 51.2, 22.6, 80), ("Toskania", 43.3, 11.0, 130), ("Sycylia", 37.4, 14.3, 180),
]


def _km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _region(lat, lon):
    best = None
    for n, la, lo, r in REGIONS:
        d = _km(lat, lon, la, lo)
        if d <= r and (best is None or d < best[1]):
            best = (n, d)
    return best[0] if best else None


def build_router(db_conn: Callable, current_user: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/start")

    @r.get("/card")
    def card(request: Request, year: int = 0):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        y = year or date.today().year
        conn = db_conn()
        try:
            c = conn.cursor()
            photos = []
            try:
                c.execute("""SELECT p.unique_id, p.day::text AS day, p.width, p.height, p.file, p.ride_key, a.name AS title,
                                    round(a.distance_m/1000.0) AS km, a.strava_id, (a.raw->'start_latlng') AS ll
                             FROM qbot_v2.strava_photo p JOIN qbot_v2.strava_activity a ON a.strava_id = p.strava_activity_id
                             WHERE NOT p.hidden ORDER BY p.day DESC""")
                for x in c.fetchall():
                    x = dict(x); ll = x.pop("ll") or []
                    x["region"] = _region(ll[0], ll[1]) if len(ll) == 2 else None
                    fn = x.pop("file"); x["url"] = "/strava/" + fn; x["url_m"] = "/strava/m/" + fn; x["url_t"] = "/strava/t/" + fn; x["km"] = int(x["km"] or 0)
                    photos.append(x)
            except Exception:
                conn.rollback()
            c.execute("""SELECT DISTINCT ON (t.external_id) t.external_id, t.date, t.distance_m, a.lat, a.lon
                         FROM qbot_v2.training_sessions t JOIN qbot_v2.activity_record a ON a.external_id = t.external_id
                         WHERE t.date BETWEEN %s AND %s AND t.sport_type ILIKE '%%cycl%%' AND a.lat IS NOT NULL
                         ORDER BY t.external_id, a.sec""", (date(y, 1, 1), date(y, 12, 31)))
            reg = {}
            for x in c.fetchall():
                n = _region(float(x["lat"]), float(x["lon"])) or "inne"
                g = reg.setdefault(n, {"name": n, "rides": 0, "km": 0.0, "lat": 0.0, "lon": 0.0, "first": None, "last": None})
                g["rides"] += 1; g["km"] += float(x["distance_m"] or 0) / 1000.0
                g["lat"] += float(x["lat"]); g["lon"] += float(x["lon"])
                d = str(x["date"]); g["first"] = min(g["first"] or d, d); g["last"] = max(g["last"] or d, d)
            regions = []
            for g in reg.values():
                if g["name"] == "inne":
                    continue
                g["lat"] /= g["rides"]; g["lon"] /= g["rides"]; g["km"] = int(round(g["km"]))
                g["home"] = g["name"] in ("Warszawa", "Mazowsze")
                g["away_km"] = int(_km(HOME[0], HOME[1], g["lat"], g["lon"]))
                regions.append(g)
            regions.sort(key=lambda g: g["first"])
            countries = sorted({("Włochy" if g["name"] in ("Toskania", "Sycylia") else "Polska") for g in regions})
            c.execute("""SELECT title, day::text AS day, end_day::text AS end_day FROM qbot_v2.calendar_entry
                         WHERE kind = 'event' AND day >= current_date AND ((end_day IS NOT NULL AND end_day > day) OR event_type = 'wyprawa')
                         ORDER BY day LIMIT 1""")
            nx = c.fetchone()
            c.execute("""SELECT name, kind, priority, date_from::text AS date_from, date_to::text AS date_to FROM qbot_v2.trainer_goal
                         WHERE status = 'active' AND kind = 'trip' AND COALESCE(date_to, date_from) >= current_date ORDER BY date_from""")
            goals = [dict(g) for g in c.fetchall()]
            c.execute("""SELECT count(*) AS n, round(sum(distance_m)/1000) AS km FROM qbot_v2.training_sessions
                         WHERE date BETWEEN %s AND %s AND sport_type ILIKE '%%cycl%%'""", (date(y, 1, 1), date(y, 12, 31)))
            tot = dict(c.fetchone())
            return {"year": y, "photos": photos, "regions": regions, "countries": countries,
                    "totals": {"rides": int(tot["n"] or 0), "km": int(tot["km"] or 0)},
                    "next": dict(nx) if nx else None,
                    "goals_a": [g for g in goals if g["priority"] == "A"], "goals_b": [g for g in goals if g["priority"] != "A"]}
        finally:
            conn.close()

    return r
