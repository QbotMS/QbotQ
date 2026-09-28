# -*- coding: utf-8 -*-
"""START - wizytowka QBota (2026-09-28).
GET  /api/start/card        -> zdjecia (wybrane), regiony roku, WYPRAWY SEZONU, najblizszy start, cele A/B
POST /api/start/trip-story  -> opis wyprawy (AI z faktow, zapamietany; {key, text} = reczna poprawka)
GET/POST /api/ride/companions -> "z kim jechalem" dla jazdy (podpowiedzi: zaproszenia z RSVP + liczba osob ze Stravy)
Wyprawa = jazdy poza domem (> AWAY_KM) w tym samym regionie, przerwa miedzy etapami <= 3 dni, >= 2 rozne dni i (>= 3 dni lub >= 250 km)."""
from __future__ import annotations

import json
import math
import re
from datetime import date
from typing import Callable

from fastapi import APIRouter, HTTPException, Request

HOME = (52.23, 21.01)
AWAY_KM = 80.0
REGIONS = [
    ("Warszawa", 52.23, 21.01, 45), ("Mazowsze", 52.3, 20.6, 110), ("Podlasie", 53.1, 22.6, 90), ("Suwalszczyzna", 54.1, 23.0, 60),
    ("Mazury", 53.9, 21.8, 80), ("Kujawy", 52.7, 19.0, 70), ("Pomorze", 53.9, 18.2, 110), ("Bory Tucholskie", 53.6, 17.9, 45),
    ("Łódzkie", 51.8, 19.6, 70), ("Świętokrzyskie", 51.0, 20.7, 60), ("Małopolska", 50.1, 19.9, 75), ("Opolszczyzna", 50.5, 17.6, 70),
    ("Dolny Śląsk", 51.1, 16.0, 90), ("Lubelskie", 51.2, 22.6, 80), ("Toskania", 43.3, 11.0, 130), ("Sycylia", 37.4, 14.3, 180),
]
MON = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"]
_EMO = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF\uFE0F]")
_OK_RSVP = ("yes", "accepted", "confirmed", "tak", "going")


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


def _clean(s):
    return re.sub(r"\s+", " ", _EMO.sub("", s or "")).strip()


def _trip_name(names, region, d0):
    """Wspolny poczatek nazw etapow ze Stravy ('Tuscany Trail E01 ...' -> 'Tuscany Trail'), inaczej region + miesiac."""
    ws = [_clean(n).split() for n in names if n]
    pre = []
    if len(ws) >= 2:
        for tup in zip(*ws):
            if all(t.lower() == tup[0].lower() for t in tup):
                pre.append(tup[0])
            else:
                break
    nm = " ".join(pre).strip(" -–·:")
    nm = re.sub(r"\s+(E|D|Etap|Dzień)\s*\d*$", "", nm, flags=re.I).strip(" -–·:")
    if len(nm) < 4:
        nm = "%s · %s" % (region, ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień",
                                   "październik", "listopad", "grudzień"][d0.month - 1])
    return nm


def _ensure(c):
    c.execute("CREATE TABLE IF NOT EXISTS qbot_v2.ride_companion (ride_key text PRIMARY KEY, names text[] NOT NULL DEFAULT '{}', updated_at timestamptz DEFAULT now())")
    c.execute("CREATE TABLE IF NOT EXISTS qbot_v2.trip_story (key text PRIMARY KEY, text text, edited boolean DEFAULT false, facts jsonb, updated_at timestamptz DEFAULT now())")


_ENSURED = False


def _trips(c, y: int, photos: list) -> list:
    c.execute("""SELECT t.external_id AS rk, t.date, t.distance_m, t.elevation_m, t.duration_s, t.activity_name, p.lat, p.lon,
                        sa.name AS sname, (sa.raw->>'athlete_count')::int AS ac, rc.names AS comp
                 FROM qbot_v2.training_sessions t
                 JOIN LATERAL (SELECT r.lat, r.lon FROM qbot_v2.activity_record r WHERE r.external_id = t.external_id AND r.lat IS NOT NULL ORDER BY r.sec LIMIT 1) p ON true
                 LEFT JOIN qbot_v2.strava_activity sa ON sa.ride_key = t.external_id
                 LEFT JOIN qbot_v2.ride_companion rc ON rc.ride_key = t.external_id
                 WHERE t.date BETWEEN %s AND %s AND t.sport_type ILIKE '%%cycl%%' ORDER BY t.date, t.started_at""", (date(y, 1, 1), date(y, 12, 31)))
    rows = [dict(r) for r in c.fetchall()]
    groups, cur = [], None
    for r in rows:
        lat, lon = float(r["lat"]), float(r["lon"])
        if _km(HOME[0], HOME[1], lat, lon) <= AWAY_KM:
            continue
        reg = _region(lat, lon) or "inne"
        if cur and cur["region"] == reg and (r["date"] - cur["rides"][-1]["date"]).days <= 4:   # do 3 dni przerwy (dni odpoczynku)
            cur["rides"].append(r)
        else:
            cur = {"region": reg, "rides": [r]}; groups.append(cur)
    story = {}
    c.execute("SELECT key, text, edited FROM qbot_v2.trip_story")
    for s in c.fetchall():
        story[s["key"]] = s
    ph_by_rk = {}
    for p in photos:
        if p.get("ride_key"):
            ph_by_rk.setdefault(p["ride_key"], []).append(p)
    trips = []
    for g in groups:
        R = g["rides"]; days = sorted({r["date"] for r in R})
        km_tot = sum(float(r["distance_m"] or 0) for r in R) / 1000.0
        if len(days) < 2 or not ((days[-1] - days[0]).days + 1 >= 3 or km_tot >= 250):   # tylko duze wyprawy
            continue
        d0, d1 = days[0], days[-1]
        key = "%s_%s" % (d0.isoformat(), g["region"])
        comp = sorted({n for r in R for n in (r["comp"] or [])})
        ph = [p for r in R for p in ph_by_rk.get(r["rk"], [])]
        trips.append({
            "key": key, "name": _trip_name([r["sname"] for r in R], g["region"], d0), "region": g["region"],
            "from": d0.isoformat(), "to": d1.isoformat(), "days": (d1 - d0).days + 1, "stages": len(R),
            "km": int(round(sum(float(r["distance_m"] or 0) for r in R) / 1000)), "up_m": int(round(sum(float(r["elevation_m"] or 0) for r in R))),
            "moving_h": round(sum(float(r["duration_s"] or 0) for r in R) / 3600.0, 1),
            "longest_km": int(round(max(float(r["distance_m"] or 0) for r in R) / 1000)),
            "people": max([int(r["ac"] or 1) for r in R] or [1]), "companions": comp,
            "rides": [{"ride_key": r["rk"], "date": r["date"].isoformat(), "name": _clean(r["sname"] or r["activity_name"]),
                       "km": int(round(float(r["distance_m"] or 0) / 1000)), "up_m": int(round(float(r["elevation_m"] or 0)))} for r in R],
            "photos": ph, "story": (story.get(key) or {}).get("text"), "story_edited": bool((story.get(key) or {}).get("edited")),
        })
    return trips


STORY_SYS = ("Piszesz krotki opis wyprawy rowerowej (gravel/bikepacking) na osobista strone-wizytowke kolarza. Polski, prosty, "
             "3-4 zdania, konkretnie i z lekkim wyczuciem klimatu, bez przesady i bez wymyslania faktow. Uzywaj WYLACZNIE podanych faktow "
             "(daty, dni, etapy, km, metry w gore, czas, nazwy etapow, osoby). Jesli nie ma imion towarzyszy - nie wymyslaj ich; mozesz napisac "
             "'we dwoch' gdy liczba osob = 2. Nie podawaj liczb, ktorych nie ma w faktach. NIE wnioskuj z nazw etapow, gdzie byl start, "
             "meta ani przez jakie miejsca prowadzila trasa - nazwy etapow mozesz najwyzej przytoczyc doslownie. Nie tlumacz nazwy wyprawy. "
             "Zwroc WYLACZNIE JSON {\"opis\": \"...\"}.")


def build_router(db_conn: Callable, current_user: Callable) -> APIRouter:
    r = APIRouter()

    def need(request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")

    def run(fn):
        global _ENSURED
        conn = db_conn()
        try:
            c = conn.cursor()
            if not _ENSURED:
                _ensure(c); conn.commit(); _ENSURED = True
            out = fn(c); conn.commit(); return out
        finally:
            conn.close()

    @r.get("/api/start/card")
    def card(request: Request, year: int = 0):
        need(request)
        y = year or date.today().year
        def go(c):
            photos = []
            try:
                c.execute("""SELECT p.unique_id, p.day::text AS day, p.width, p.height, p.file, p.ride_key, a.name AS title,
                                    round(a.distance_m/1000.0) AS km, a.strava_id, (a.raw->'start_latlng') AS ll, COALESCE(p.status,'candidate') AS status
                             FROM qbot_v2.strava_photo p JOIN qbot_v2.strava_activity a ON a.strava_id = p.strava_activity_id
                             WHERE NOT p.hidden AND COALESCE(p.status,'candidate') <> 'rejected' ORDER BY p.day DESC""")
                for x in c.fetchall():
                    x = dict(x); ll = x.pop("ll") or []
                    x["region"] = _region(ll[0], ll[1]) if len(ll) == 2 else None
                    fn = x.pop("file"); x["url"] = "/strava/" + fn; x["url_m"] = "/strava/m/" + fn; x["url_t"] = "/strava/t/" + fn
                    x["km"] = int(x["km"] or 0); x["title"] = _clean(x["title"])
                    photos.append(x)
                if any(x["status"] in ("liked", "auto") for x in photos):
                    photos = [x for x in photos if x["status"] in ("liked", "auto")]
            except Exception:
                c.connection.rollback()
            c.execute("""SELECT DISTINCT ON (t.external_id) t.external_id, t.date, t.distance_m, a.lat, a.lon
                         FROM qbot_v2.training_sessions t JOIN qbot_v2.activity_record a ON a.external_id = t.external_id
                         WHERE t.date BETWEEN %s AND %s AND t.sport_type ILIKE '%%cycl%%' AND a.lat IS NOT NULL
                         ORDER BY t.external_id, a.sec""", (date(y, 1, 1), date(y, 12, 31)))
            reg = {}
            for x in c.fetchall():
                n = _region(float(x["lat"]), float(x["lon"])) or "inne"
                g = reg.setdefault(n, {"name": n, "rides": 0, "km": 0.0, "lat": 0.0, "lon": 0.0, "first": None, "last": None})
                g["rides"] += 1; g["km"] += float(x["distance_m"] or 0) / 1000.0; g["lat"] += float(x["lat"]); g["lon"] += float(x["lon"])
                d = str(x["date"]); g["first"] = min(g["first"] or d, d); g["last"] = max(g["last"] or d, d)
            regions = []
            for g in reg.values():
                if g["name"] == "inne":
                    continue
                g["lat"] /= g["rides"]; g["lon"] /= g["rides"]; g["km"] = int(round(g["km"]))
                g["home"] = g["name"] in ("Warszawa", "Mazowsze")
                regions.append(g)
            regions.sort(key=lambda g: g["first"])
            countries = sorted({("Włochy" if g["name"] in ("Toskania", "Sycylia") else "Polska") for g in regions})
            trips = _trips(c, y, photos)
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
            return {"year": y, "photos": photos, "regions": regions, "countries": countries, "trips": trips,
                    "totals": {"rides": int(tot["n"] or 0), "km": int(tot["km"] or 0)}, "next": dict(nx) if nx else None,
                    "goals_a": [g for g in goals if g["priority"] == "A"], "goals_b": [g for g in goals if g["priority"] != "A"]}
        return run(go)

    @r.post("/api/start/trip-story")
    async def trip_story(request: Request):
        need(request)
        b = await request.json()
        key, text, regen = str(b.get("key") or ""), b.get("text"), bool(b.get("regenerate"))
        y = int((key or "0")[:4] or 0)
        def go(c):
            if text is not None:
                c.execute("INSERT INTO qbot_v2.trip_story (key, text, edited) VALUES (%s,%s,true) ON CONFLICT (key) DO UPDATE SET text=EXCLUDED.text, edited=true, updated_at=now()",
                          (key, str(text).strip()[:2000]))
                return {"key": key, "text": str(text).strip(), "edited": True}
            c.execute("SELECT text, edited FROM qbot_v2.trip_story WHERE key=%s", (key,))
            s = c.fetchone()
            if s and s["text"] and not regen:
                return {"key": key, "text": s["text"], "edited": s["edited"]}
            t = [x for x in _trips(c, y, []) if x["key"] == key]
            if not t:
                raise HTTPException(status_code=404, detail="brak wyprawy")
            t = t[0]
            facts = {k: t[k] for k in ("name", "region", "from", "to", "days", "stages", "km", "up_m", "moving_h", "longest_km", "people", "companions")}
            facts["etapy"] = [{"data": x["date"], "nazwa": x["name"], "km": x["km"], "m_w_gore": x["up_m"]} for x in t["rides"]]
            from qgpt_client import qgpt_json
            out = qgpt_json("FAKTY (JSON):\n" + json.dumps(facts, ensure_ascii=False), system=STORY_SYS, max_tokens=600, temperature=0.4)
            opis = str((out or {}).get("opis") or "").strip()
            if not opis:
                raise HTTPException(status_code=502, detail="AI nie zwrocilo opisu")
            c.execute("INSERT INTO qbot_v2.trip_story (key, text, edited, facts) VALUES (%s,%s,false,%s::jsonb) ON CONFLICT (key) DO UPDATE SET "
                      "text=EXCLUDED.text, edited=false, facts=EXCLUDED.facts, updated_at=now()", (key, opis, json.dumps(facts, ensure_ascii=False)))
            return {"key": key, "text": opis, "edited": False}
        return run(go)

    @r.get("/api/ride/companions")
    def companions_get(request: Request, ride: str):
        need(request)
        def go(c):
            c.execute("SELECT names FROM qbot_v2.ride_companion WHERE ride_key=%s", (ride,))
            x = c.fetchone()
            c.execute("SELECT date FROM qbot_v2.training_sessions WHERE external_id=%s", (ride,)); t = c.fetchone()
            sug = []
            if t:
                try:
                    c.execute("SELECT DISTINCT email, status FROM qbot_v2.ride_invite WHERE ride_date=%s AND revoked_at IS NULL", (t["date"],))
                    sug += [{"name": s["email"], "src": "zaproszenie (%s)" % s["status"]} for s in c.fetchall() if str(s["status"] or "").lower() in _OK_RSVP]
                except Exception:
                    c.connection.rollback()
            c.execute("SELECT (raw->>'athlete_count')::int AS ac FROM qbot_v2.strava_activity WHERE ride_key=%s LIMIT 1", (ride,)); a = c.fetchone()
            return {"ride": ride, "names": list((x or {}).get("names") or []), "suggestions": sug, "strava_people": (a or {}).get("ac")}
        return run(go)

    @r.post("/api/ride/companions")
    async def companions_set(request: Request):
        need(request)
        b = await request.json()
        ride = str(b.get("ride") or "")
        names = [str(n).strip()[:60] for n in (b.get("names") or []) if str(n).strip()][:12]
        if not ride:
            raise HTTPException(status_code=400, detail="brak ride")
        def go(c):
            c.execute("INSERT INTO qbot_v2.ride_companion (ride_key, names) VALUES (%s,%s) ON CONFLICT (ride_key) DO UPDATE SET names=EXCLUDED.names, updated_at=now()",
                      (ride, names))
            return {"ok": True, "ride": ride, "names": names}
        return run(go)

    return r
