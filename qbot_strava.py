# -*- coding: utf-8 -*-
"""Strava -> QBot (2026-09-28): polaczenie OAuth, lista aktywnosci i ZDJECIA z jazd (do wizytowki START).

Przeplyw:
  1. Michal zaklada aplikacje API na strava.com/settings/api (Callback Domain = albert.cytr.us)
  2. na /strava.html wpisuje Client ID + Client Secret (POST /api/strava/config) - sekret NIE trafia do czatu/repo
  3. "Polacz ze Strava" -> GET /api/strava/connect -> Strava (scope read,activity:read_all,activity:write,profile:read_all) -> GET /api/strava/callback
  4. "Pobierz zdjecia" -> POST /api/strava/sync (watek w tle, wznawialny, pilnuje limitow Stravy 100/15 min, 1000/dzien)
Zdjecia: /opt/qbot/web/public/strava/<unique_id>.jpg (statyk za brama logowania), metadane w qbot_v2.strava_photo,
dopasowanie do jazdy QBota po czasie startu (+-15 min) -> ride_key (= training_sessions.external_id).
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

API = "https://www.strava.com/api/v3"
PHOTO_DIR = "/opt/qbot/web/public/strava"
PHOTO_URL = "/strava/"
DEFAULT_BASE = os.environ.get("STRAVA_REDIRECT_BASE", "https://albert.cytr.us")
SCOPE = "read,activity:read_all,activity:write,profile:read_all"   # 2026-10-09: zapis roweru i opisu (qbot_strava_publish)
LIMIT_15, LIMIT_DAY = 90, 900          # zapas wzgledem limitow Stravy (100 / 1000)
# dobor zdjec (decyzja Michala 2026-09-28): NIE wszystkie. Na start ~40 z najlepszych jazd (wyjazdy + dlugie),
# potem po 2-3 zdjecia z kazdej nowej jazdy.
HOME = (52.23, 21.01)
AWAY_KM, LONG_KM = 80.0, 90.0
BACKFILL_MIN, BACKFILL_CAP, PER_RIDE_BACKFILL = 30, 40, 2
MIN_RIDE_KM = 30   # 2026-09-28: kandydaci tylko z jazd >= 30 km (decyzja Michala)
AUTO_FROM = "2026-09-28"   # automat (run_auto) tylko dla jazd od konca kalibracji - starszych nie dokladamy bez oceny
INCR_RIDES, PER_RIDE_INCR = 3, 3


def make_thumbs(path):
    """Lekkie wersje zdjecia dla START: m/ = 1600 px (pokaz), t/ = 720 px (kolaz, tasma). JPEG q82."""
    try:
        from PIL import Image, ImageOps
        d, fn = os.path.split(path)
        for sub, w in (("m", 1600), ("t", 720)):
            out = os.path.join(d, sub, fn)
            if os.path.exists(out):
                continue
            os.makedirs(os.path.join(d, sub), exist_ok=True)
            im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            im.thumbnail((w, w * 2))
            im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    except Exception as e:
        print("[strava] miniatura %s: %s" % (path, e))


def _km_from_home(lat, lon):
    import math
    if lat is None or lon is None:
        return 0.0
    p1, p2 = math.radians(HOME[0]), math.radians(lat)
    dl, dp = math.radians(lon - HOME[1]), p2 - p1
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))

_SYNC = {"running": False, "phase": None, "done": 0, "photos": 0, "error": None, "started": None, "finished": None, "note": None}
_LOCK = threading.Lock()


_TABLES_OK = False


def ensure_tables(c) -> None:
    """Raz na proces (2026-09-28): ALTER TABLE bierze blokade wylaczna - wolane przy kazdym zapytaniu
    (odswiezanie /zdjecia.html co 4 s) zakleszczalo sie z INSERT-ami rundy kalibracji."""
    global _TABLES_OK
    if _TABLES_OK:
        return
    _ensure_tables(c)
    _TABLES_OK = True


def _ensure_tables(c) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.strava_auth (
        id int PRIMARY KEY DEFAULT 1, client_id text, client_secret text, access_token text, refresh_token text,
        expires_at bigint, athlete_id bigint, athlete_name text, scope text, updated_at timestamptz DEFAULT now())""")
    c.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.strava_activity (
        strava_id bigint PRIMARY KEY, start_date timestamptz, name text, sport_type text, distance_m real,
        total_photo_count int, ride_key text, photos_synced_at timestamptz, raw jsonb, updated_at timestamptz DEFAULT now())""")
    c.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.strava_photo (
        unique_id text PRIMARY KEY, strava_activity_id bigint REFERENCES qbot_v2.strava_activity(strava_id) ON DELETE CASCADE,
        ride_key text, day date, caption text, lat double precision, lon double precision, taken_at timestamptz,
        width int, height int, file text, src_url text, hidden boolean DEFAULT false, created_at timestamptz DEFAULT now())""")
    c.execute("CREATE INDEX IF NOT EXISTS strava_photo_day ON qbot_v2.strava_photo(day)")
    # 2026-09-28: kalibracja gustu - status zdjecia (candidate / liked / rejected / auto), cechy, dopasowanie, runda
    for col, typ in (("status", "text DEFAULT 'candidate'"), ("feats", "jsonb"), ("score", "real"), ("round", "int"), ("rated_at", "timestamptz")):
        c.execute("ALTER TABLE qbot_v2.strava_photo ADD COLUMN IF NOT EXISTS %s %s" % (col, typ))
    c.execute("ALTER TABLE qbot_v2.strava_activity ADD COLUMN IF NOT EXISTS candidates_at timestamptz")
    c.execute("ALTER TABLE qbot_v2.strava_activity ADD COLUMN IF NOT EXISTS photos_seen int")
    c.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.strava_taste (id int PRIMARY KEY DEFAULT 1, model jsonb, rounds int DEFAULT 0, updated_at timestamptz DEFAULT now())""")


def _get(c) -> dict:
    c.execute("SELECT * FROM qbot_v2.strava_auth WHERE id=1")
    r = c.fetchone()
    return dict(r) if r else {}


def _http(method: str, url: str, data: dict | None = None, token: str | None = None, timeout: int = 30):
    body = urllib.parse.urlencode(data).encode() if (data and method == "POST") else None
    if data and method == "GET":
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(data)
    req = urllib.request.Request(url, data=body, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        usage = r.headers.get("X-RateLimit-Usage") or r.headers.get("X-ReadRateLimit-Usage")
        return json.loads(r.read().decode() or "null"), usage


def _token(c) -> str:
    a = _get(c)
    if not a.get("refresh_token"):
        raise HTTPException(status_code=409, detail="Strava niepolaczona")
    if (a.get("expires_at") or 0) > time.time() + 120:
        return a["access_token"]
    j, _ = _http("POST", "https://www.strava.com/oauth/token", {"client_id": a["client_id"], "client_secret": a["client_secret"],
                                                                "grant_type": "refresh_token", "refresh_token": a["refresh_token"]})
    c.execute("UPDATE qbot_v2.strava_auth SET access_token=%s, refresh_token=%s, expires_at=%s, updated_at=now() WHERE id=1",
              (j["access_token"], j["refresh_token"], int(j["expires_at"])))
    c.connection.commit()
    return j["access_token"]


def _over_limit(usage: str | None) -> bool:
    try:
        a, b = [int(x) for x in (usage or "0,0").split(",")[:2]]
        return a >= LIMIT_15 or b >= LIMIT_DAY
    except Exception:
        return False


def _match_ride(c, start_iso: str):
    c.execute("SELECT external_id FROM qbot_v2.training_sessions WHERE started_at BETWEEN %s::timestamptz - interval '15 minutes' "
              "AND %s::timestamptz + interval '15 minutes' ORDER BY abs(extract(epoch FROM started_at - %s::timestamptz)) LIMIT 1",
              (start_iso, start_iso, start_iso))
    r = c.fetchone()
    return (r["external_id"] if hasattr(r, "keys") else r[0]) if r else None


def run_sync(db_conn: Callable, since: str = "2025-01-01") -> None:
    """Watek: 1) lista aktywnosci od 'since' 2) zdjecia aktywnosci z photo_count>0 i bez photos_synced_at."""
    with _LOCK:
        if _SYNC["running"]:
            return
        _SYNC.update(running=True, phase="aktywności", done=0, photos=0, error=None, note=None,
                     started=datetime.now(timezone.utc).isoformat(timespec="seconds"), finished=None)
    try:
        os.makedirs(PHOTO_DIR, exist_ok=True)
        conn = db_conn()
        try:
            c = conn.cursor()
            ensure_tables(c); conn.commit()
            after = int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp())
            page = 1
            while True:
                tok = _token(c)
                acts, usage = _http("GET", API + "/athlete/activities", {"after": after, "per_page": 100, "page": page}, tok)
                if not acts:
                    break
                for a in acts:
                    rk = _match_ride(c, a["start_date"])
                    c.execute("""INSERT INTO qbot_v2.strava_activity (strava_id, start_date, name, sport_type, distance_m, total_photo_count, ride_key, raw)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (strava_id) DO UPDATE SET
                                 name=EXCLUDED.name, total_photo_count=EXCLUDED.total_photo_count, ride_key=COALESCE(EXCLUDED.ride_key, qbot_v2.strava_activity.ride_key),
                                 raw=EXCLUDED.raw, updated_at=now()""",
                              (a["id"], a["start_date"], a.get("name"), a.get("sport_type") or a.get("type"), a.get("distance"),
                               a.get("total_photo_count") or 0, rk, json.dumps({k: a.get(k) for k in ("start_latlng", "end_latlng", "total_elevation_gain", "moving_time", "location_country", "athlete_count")})))
                    _SYNC["done"] += 1
                conn.commit()
                if _over_limit(usage):
                    _SYNC["note"] = "limit Stravy - reszta przy następnym pobieraniu (za ok. 15 min)"
                    return
                page += 1
            _SYNC["phase"] = "zdjęcia"
            c.execute("SELECT count(*) AS n FROM qbot_v2.strava_photo")
            r0 = c.fetchone(); have = r0["n"] if hasattr(r0, "keys") else r0[0]
            c.execute("SELECT strava_id, ride_key, start_date, distance_m, raw FROM qbot_v2.strava_activity "
                      "WHERE total_photo_count > 0 AND photos_synced_at IS NULL ORDER BY start_date DESC")
            acts = [dict(r) if hasattr(r, "keys") else {"strava_id": r[0], "ride_key": r[1], "start_date": r[2], "distance_m": r[3], "raw": r[4]}
                    for r in c.fetchall()]
            for a_ in acts:
                raw = a_.get("raw") or {}
                if isinstance(raw, str):
                    raw = json.loads(raw)
                ll = raw.get("start_latlng") or []
                a_["away_km"] = _km_from_home(ll[0], ll[1]) if len(ll) == 2 else 0.0
                a_["region"] = ("%d,%d" % (round(ll[0]), round(ll[1]))) if len(ll) == 2 else "?"
                a_["dist_km"] = (a_.get("distance_m") or 0) / 1000.0
            if have < BACKFILL_MIN:
                # START: ~40 zdjec z NAJLEPSZYCH jazd = wyjazdy (start > 80 km od domu) i dlugie jazdy (>= 90 km),
                # po kolei z kazdego regionu (Toskania, Sycylia, Opolszczyzna...), max 2 zdjecia z jednej jazdy
                best = [x for x in acts if x["away_km"] > AWAY_KM or x["dist_km"] >= LONG_KM]
                regions = {}
                for x in sorted(best, key=lambda x: (-(x["away_km"] > AWAY_KM), -x["dist_km"])):
                    regions.setdefault("dom" if x["away_km"] <= AWAY_KM else x["region"], []).append(x)
                queue = []
                while any(regions.values()):
                    for k in list(regions):
                        if regions[k]:
                            queue.append(regions[k].pop(0))
                cap, per = BACKFILL_CAP - have, PER_RIDE_BACKFILL
            else:
                # potem: tylko NOWE jazdy (pozniejsze niz ostatnia jazda ze zdjeciami), po 2-3 zdjecia z jazdy
                c.execute("SELECT max(a.start_date) AS m FROM qbot_v2.strava_activity a WHERE EXISTS "
                          "(SELECT 1 FROM qbot_v2.strava_photo p WHERE p.strava_activity_id = a.strava_id)")
                r1 = c.fetchone(); last = r1["m"] if hasattr(r1, "keys") else r1[0]
                queue = [x for x in acts if last is None or x["start_date"] > last][:INCR_RIDES]
                cap, per = INCR_RIDES * PER_RIDE_INCR, PER_RIDE_INCR
            taken = 0
            for t in queue:
                if taken >= cap:
                    break
                tok = _token(c)
                photos, usage = _http("GET", API + "/activities/%d/photos" % t["strava_id"], {"size": 2048, "photo_sources": "true"}, tok)
                got = 0
                for p in photos or []:
                    if got >= per or taken >= cap:
                        break
                    uid = str(p.get("unique_id") or p.get("id") or "")
                    url = (p.get("urls") or {}).get("2048") or next(iter((p.get("urls") or {}).values()), None)
                    if not uid or not url or p.get("video_url"):
                        continue
                    fn = "%s.jpg" % uid.replace("/", "_")
                    path = os.path.join(PHOTO_DIR, fn)
                    if not os.path.exists(path):
                        try:
                            with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                                f.write(r.read())
                        except Exception as e:
                            print("[strava] zdjecie %s: %s" % (uid, e)); continue
                    make_thumbs(path)
                    ll = p.get("location") or [None, None]
                    sz = (p.get("sizes") or {}).get("2048") or [None, None]
                    c.execute("""INSERT INTO qbot_v2.strava_photo (unique_id, strava_activity_id, ride_key, day, caption, lat, lon, taken_at, width, height, file, src_url)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (unique_id) DO NOTHING""",
                              (uid, t["strava_id"], t["ride_key"], str(t["start_date"])[:10], p.get("caption") or None,
                               ll[0] if ll else None, ll[1] if ll else None, p.get("created_at"), sz[0], sz[1], fn, url))
                    got += 1; taken += 1; _SYNC["photos"] += 1
                c.execute("UPDATE qbot_v2.strava_activity SET photos_synced_at=now() WHERE strava_id=%s", (t["strava_id"],))
                conn.commit()
                if _over_limit(usage):
                    _SYNC["note"] = "limit Stravy - reszta przy następnym pobieraniu (za ok. 15 min)"
                    return
            # jazdy, ktorych nie wybralismy, NIE sa oznaczane - moga trafic do kolejnego doboru
            _SYNC["note"] = "gotowe"
        finally:
            conn.close()
    except Exception as e:
        _SYNC["error"] = str(e)[:300]
        print("[strava] sync: %s" % e)
    finally:
        _SYNC.update(running=False, finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _rows(c):
    return [dict(r) if hasattr(r, "keys") else r for r in c.fetchall()]


def _model(c):
    import qbot_photo_taste as PT
    c.execute("SELECT feats, status FROM qbot_v2.strava_photo WHERE status IN ('liked','rejected') AND feats IS NOT NULL")
    rows = _rows(c)
    return PT.fit([r["feats"] for r in rows], [1 if r["status"] == "liked" else 0 for r in rows])


def run_round(db_conn: Callable, n: int = 60) -> None:
    """Runda kalibracji: model z ocen -> ranking jazd -> kandydaci (>= MIN_PX) -> cechy + dopasowanie. Watek w tle."""
    import random
    import qbot_photo_taste as PT
    with _LOCK:
        if _SYNC["running"]:
            return
        _SYNC.update(running=True, phase="runda: wybór jazd", done=0, photos=0, error=None, note=None,
                     started=datetime.now(timezone.utc).isoformat(timespec="seconds"), finished=None)
    try:
        os.makedirs(PHOTO_DIR, exist_ok=True)
        conn = db_conn()
        try:
            c = conn.cursor(); ensure_tables(c); conn.commit()
            model = _model(c)
            c.execute("SELECT COALESCE(max(round),0)+1 AS r FROM qbot_v2.strava_photo"); rnd = _rows(c)[0]["r"]
            # 2026-09-28: TYLKO biezacy rok (decyzja Michala - bez zdjec z 2025)
            c.execute("SELECT strava_id, ride_key, start_date, distance_m, total_photo_count, raw FROM qbot_v2.strava_activity "
                      "WHERE total_photo_count > 0 AND candidates_at IS NULL AND photos_synced_at IS NULL "
                      "AND start_date >= date_trunc('year', now()) AND distance_m >= %s", (MIN_RIDE_KM * 1000,))
            acts = _rows(c)
            for a in acts:
                raw = a.get("raw") or {}
                raw = json.loads(raw) if isinstance(raw, str) else raw
                ll = raw.get("start_latlng") or []
                a["away"] = _km_from_home(ll[0], ll[1]) if len(ll) == 2 else 0.0
                a["dist"] = (a.get("distance_m") or 0) / 1000.0
                cf = PT.context_features(None, a["away"], a["dist"])
                a["pri"] = PT.score(model, dict(cf, ostrosc=3.0, poziome=1.0, rozdzielczosc=1.0))
            acts.sort(key=lambda a: -a["pri"])
            k = max(1, int(len(acts) * 0.75))
            order = acts[:k][: int(n / 2.2) + 1]
            rest = acts[k:] + acts[len(order):k]
            random.shuffle(rest)
            order += rest[: max(3, int(len(order) * 0.33))]    # ~25% na probe
            _SYNC["phase"] = "runda %d: kandydaci" % rnd
            got = 0
            for a in order:
                if got >= n:
                    break
                tok = _token(c)
                photos, usage = _http("GET", API + "/activities/%d/photos" % a["strava_id"], {"size": 2048, "photo_sources": "true"}, tok)
                per = 0
                for p in photos or []:
                    if per >= 3 or got >= n:
                        break
                    uid = str(p.get("unique_id") or p.get("id") or "")
                    url = (p.get("urls") or {}).get("2048")
                    sz = (p.get("sizes") or {}).get("2048") or [0, 0]
                    if not uid or not url or p.get("video_url") or max(sz or [0]) < PT.MIN_PX:
                        continue
                    c.execute("SELECT 1 FROM qbot_v2.strava_photo WHERE unique_id=%s", (uid,))
                    if c.fetchone():
                        continue
                    fn = "%s.jpg" % uid.replace("/", "_"); path = os.path.join(PHOTO_DIR, fn)
                    try:
                        with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                            f.write(r.read())
                        make_thumbs(path)
                        f_ = PT.image_features(path)
                    except Exception as e:
                        print("[strava] kandydat %s: %s" % (uid, e)); continue
                    if max(f_["w"], f_["h"]) < PT.MIN_PX:
                        continue
                    hr = None
                    try:
                        hr = datetime.fromisoformat(str(p.get("created_at_local") or p.get("created_at")).replace("Z", "+00:00")).hour
                    except Exception:
                        pass
                    f_.update(PT.context_features(hr, a["away"], a["dist"]))
                    sc = PT.score(model, f_)
                    ll = p.get("location") or [None, None]
                    c.execute("""INSERT INTO qbot_v2.strava_photo (unique_id, strava_activity_id, ride_key, day, caption, lat, lon, taken_at, width, height,
                                 file, src_url, status, feats, score, round) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'candidate',%s::jsonb,%s,%s)
                                 ON CONFLICT (unique_id) DO NOTHING""",
                              (uid, a["strava_id"], a["ride_key"], str(a["start_date"])[:10], p.get("caption") or None, ll[0] if ll else None,
                               ll[1] if ll else None, p.get("created_at"), f_["w"], f_["h"], fn, url, json.dumps(f_), sc, rnd))
                    per += 1; got += 1; _SYNC["photos"] = got
                c.execute("UPDATE qbot_v2.strava_activity SET candidates_at=now() WHERE strava_id=%s", (a["strava_id"],))
                conn.commit(); _SYNC["done"] += 1
                if _over_limit(usage):
                    _SYNC["note"] = "limit Stravy — dokończę przy następnej rundzie (za ok. 15 min)"
                    break
            c.execute("INSERT INTO qbot_v2.strava_taste (id, model, rounds) VALUES (1, %s::jsonb, 1) ON CONFLICT (id) DO UPDATE SET "
                      "model=EXCLUDED.model, rounds=qbot_v2.strava_taste.rounds+1, updated_at=now()", (json.dumps(model),))
            conn.commit()
            _SYNC["note"] = _SYNC["note"] or ("runda %d: %d nowych kandydatów" % (rnd, got))
        finally:
            conn.close()
    except Exception as e:
        _SYNC["error"] = str(e)[:300]; print("[strava] runda: %s" % e)
    finally:
        _SYNC.update(running=False, finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _dict_conn():
    """Polaczenie z wierszami-slownikami poza qbot-web (nocny daily_job)."""
    from psycopg.rows import dict_row
    from fitmodel.api import _db_connect
    c = _db_connect(); c.row_factory = dict_row
    return c


def _upsert_activity(c, a) -> None:
    rk = _match_ride(c, a["start_date"])
    c.execute("""INSERT INTO qbot_v2.strava_activity (strava_id, start_date, name, sport_type, distance_m, total_photo_count, ride_key, raw)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (strava_id) DO UPDATE SET
                 name=EXCLUDED.name, total_photo_count=EXCLUDED.total_photo_count, ride_key=COALESCE(EXCLUDED.ride_key, qbot_v2.strava_activity.ride_key),
                 raw=EXCLUDED.raw, updated_at=now()""",
              (a["id"], a["start_date"], a.get("name"), a.get("sport_type") or a.get("type"), a.get("distance"), a.get("total_photo_count") or 0, rk,
               json.dumps({k: a.get(k) for k in ("start_latlng", "end_latlng", "total_elevation_gain", "moving_time", "location_country", "athlete_count")})))


def run_auto(db_conn: Callable | None = None, per: int = 3, min_fit: float = 0.5) -> dict:
    """Po kalibracji (2026-09-28): nowe jazdy z biezacego roku >= MIN_RIDE_KM -> po maks. `per` zdjec wybranych
    NAUCZONYM gustem (dopasowanie >= min_fit) jako status 'auto' (START je pokazuje, na /zdjecia.html mozna zdjac).
    Reszta zdjec takiej jazdy nie zostaje na serwerze. Wolane w nocnym daily_job."""
    import qbot_photo_taste as PT
    conn = db_conn() if db_conn else _dict_conn()
    out = {"nowe_jazdy": 0, "przejrzane": 0, "auto": 0}
    try:
        c = conn.cursor(); ensure_tables(c); conn.commit()
        if not _get(c).get("refresh_token"):
            return {"pominiete": "Strava niepolaczona"}
        c.execute("SELECT max(start_date) AS m FROM qbot_v2.strava_activity"); m = _rows(c)[0]["m"]
        after = int((m - timedelta(days=3)).timestamp()) if m else int(datetime(datetime.now().year, 1, 1, tzinfo=timezone.utc).timestamp())
        for page in (1, 2, 3):
            acts, usage = _http("GET", API + "/athlete/activities", {"after": after, "per_page": 100, "page": page}, _token(c))
            if not acts:
                break
            for a in acts:
                _upsert_activity(c, a); out["nowe_jazdy"] += 1
            conn.commit()
            if _over_limit(usage):
                return dict(out, uwaga="limit Stravy")
        model = _model(c)
        c.execute("SELECT strava_id, ride_key, start_date, distance_m, raw, total_photo_count FROM qbot_v2.strava_activity WHERE total_photo_count > 0 "
                  "AND photos_synced_at IS NULL AND start_date >= %s AND distance_m >= %s "
                  "AND (candidates_at IS NULL OR (start_date >= now() - interval '3 days' AND total_photo_count > COALESCE(photos_seen, 0))) "
                  "ORDER BY start_date", (AUTO_FROM, MIN_RIDE_KM * 1000))
        for a in _rows(c):
            raw = a.get("raw") or {}; raw = json.loads(raw) if isinstance(raw, str) else raw
            ll = raw.get("start_latlng") or []
            away = _km_from_home(ll[0], ll[1]) if len(ll) == 2 else 0.0
            c.execute("SELECT count(*) AS n FROM qbot_v2.strava_photo WHERE strava_activity_id=%s AND status IN ('auto','liked')", (a["strava_id"],))
            have = _rows(c)[0]["n"]; left = per - have
            if left <= 0:
                c.execute("UPDATE qbot_v2.strava_activity SET candidates_at=now(), photos_seen=%s WHERE strava_id=%s", (a.get("total_photo_count"), a["strava_id"]))
                conn.commit(); continue
            photos, usage = _http("GET", API + "/activities/%d/photos" % a["strava_id"], {"size": 2048, "photo_sources": "true"}, _token(c))
            cand = []
            for p in photos or []:
                uid = str(p.get("unique_id") or p.get("id") or ""); url = (p.get("urls") or {}).get("2048")
                sz = (p.get("sizes") or {}).get("2048") or [0, 0]
                if not uid or not url or p.get("video_url") or max(sz or [0]) < PT.MIN_PX:
                    continue
                c.execute("SELECT 1 FROM qbot_v2.strava_photo WHERE unique_id=%s", (uid,))
                if c.fetchone():
                    continue
                fn = "%s.jpg" % uid.replace("/", "_"); path = os.path.join(PHOTO_DIR, fn)
                try:
                    with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                        f.write(r.read())
                    f_ = PT.image_features(path)
                except Exception as e:
                    print("[strava auto] %s: %s" % (uid, e)); continue
                hr = None
                try:
                    hr = datetime.fromisoformat(str(p.get("created_at_local") or p.get("created_at")).replace("Z", "+00:00")).hour
                except Exception:
                    pass
                f_.update(PT.context_features(hr, away, (a.get("distance_m") or 0) / 1000.0))
                cand.append((PT.score(model, f_), uid, fn, path, f_, p))
            cand.sort(key=lambda t: -t[0])
            keep = [t for t in cand if t[0] >= min_fit and max(t[4]["w"], t[4]["h"]) >= PT.MIN_PX][:left]
            if not keep and not have and cand:          # nowa jazda nie znika: gdy nic nie przekracza progu - najlepsze pasujace
                keep = cand[:1]
            for sc, uid, fn, path, f_, p in cand:
                if (sc, uid, fn, path, f_, p) in keep:
                    make_thumbs(path)
                    loc = p.get("location") or [None, None]
                    c.execute("""INSERT INTO qbot_v2.strava_photo (unique_id, strava_activity_id, ride_key, day, caption, lat, lon, taken_at, width, height,
                                 file, src_url, status, feats, score, round) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'auto',%s::jsonb,%s,NULL)
                                 ON CONFLICT (unique_id) DO NOTHING""",
                              (uid, a["strava_id"], a["ride_key"], str(a["start_date"])[:10], p.get("caption") or None, loc[0] if loc else None,
                               loc[1] if loc else None, p.get("created_at"), f_["w"], f_["h"], fn, (p.get("urls") or {}).get("2048"), json.dumps(f_), sc))
                    out["auto"] += 1
                else:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            c.execute("UPDATE qbot_v2.strava_activity SET candidates_at=now(), photos_seen=%s WHERE strava_id=%s", (a.get("total_photo_count"), a["strava_id"]))
            conn.commit(); out["przejrzane"] += 1
            if _over_limit(usage):
                out["uwaga"] = "limit Stravy - reszta nastepnej nocy"; break
        return out
    finally:
        conn.close()


_SCHED_STARTED = False


def _scheduler(db_conn: Callable) -> None:
    """2026-09-28: zdjecia z nowej jazdy tego samego dnia - run_auto co 3 h (7:00-22:00), pierwszy raz 10 min po starcie."""
    time.sleep(600)
    while True:
        try:
            if 7 <= datetime.now().hour <= 22 and not _SYNC["running"]:
                print("[strava] auto:", run_auto(db_conn))
        except Exception as e:
            print("[strava] auto blad: %s" % e)
        time.sleep(3 * 3600)


def build_router(db_conn: Callable, current_user: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/strava")
    global _SCHED_STARTED
    if not _SCHED_STARTED:
        _SCHED_STARTED = True
        threading.Thread(target=_scheduler, args=(db_conn,), daemon=True, name="strava-auto").start()
        try:   # 2026-10-09: automat roweru i opisu na Stravie (docs/STRAVA_PUBLISH.md)
            import qbot_strava_publish
            qbot_strava_publish.start_loop(db_conn)
        except Exception as e:
            print("[strava] publish start: %s" % e)

    def user_of(request: Request) -> str:
        u = current_user(request)
        if not u:
            raise HTTPException(status_code=401, detail="unauthorized")
        return u

    def run(fn):
        conn = db_conn()
        try:
            c = conn.cursor(); ensure_tables(c)
            out = fn(c); conn.commit(); return out
        finally:
            conn.close()

    def base(request: Request) -> str:
        h = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if h and not h.startswith(("127.", "localhost")):
            return "https://" + h
        return DEFAULT_BASE

    @r.get("/status")
    def status(request: Request):
        user_of(request)
        def go(c):
            a = _get(c)
            c.execute("SELECT count(*) AS n, count(*) FILTER (WHERE total_photo_count>0) AS wf FROM qbot_v2.strava_activity")
            s = c.fetchone()
            c.execute("SELECT count(*) AS n FROM qbot_v2.strava_photo"); p = c.fetchone()
            g = (lambda row, k, i: row[k] if hasattr(row, "keys") else row[i])
            return {"configured": bool(a.get("client_id") and a.get("client_secret")), "connected": bool(a.get("refresh_token")),
                    "client_id": a.get("client_id"), "athlete": a.get("athlete_name"), "scope": a.get("scope"),
                    "callback_domain": base(request).replace("https://", ""),
                    "activities": g(s, "n", 0), "with_photos": g(s, "wf", 1), "photos": g(p, "n", 0), "sync": dict(_SYNC)}
        return run(go)

    @r.post("/config")
    async def config(request: Request):
        user_of(request)
        b = await request.json()
        cid, sec = str(b.get("client_id") or "").strip(), str(b.get("client_secret") or "").strip()
        if not cid.isdigit() or len(sec) < 20:
            raise HTTPException(status_code=400, detail="Client ID to liczba, Client Secret to dlugi ciag znakow")
        def go(c):
            c.execute("INSERT INTO qbot_v2.strava_auth (id, client_id, client_secret) VALUES (1,%s,%s) ON CONFLICT (id) DO UPDATE SET "
                      "client_id=EXCLUDED.client_id, client_secret=EXCLUDED.client_secret, updated_at=now()", (cid, sec))
            return {"ok": True}
        return run(go)

    @r.get("/connect")
    def connect(request: Request):
        user_of(request)
        a = run(_get)
        if not a.get("client_id"):
            raise HTTPException(status_code=409, detail="najpierw zapisz Client ID i Client Secret")
        q = urllib.parse.urlencode({"client_id": a["client_id"], "response_type": "code", "approval_prompt": "force",
                                    "redirect_uri": base(request) + "/api/strava/callback", "scope": SCOPE})
        return RedirectResponse("https://www.strava.com/oauth/authorize?" + q)

    @r.get("/callback")
    def callback(request: Request, code: str = "", scope: str = "", error: str = ""):
        user_of(request)
        if error or not code:
            return RedirectResponse("/strava.html?err=" + urllib.parse.quote(error or "brak kodu"))
        if "activity:read_all" not in scope:
            return RedirectResponse("/strava.html?err=" + urllib.parse.quote("zaznacz dostep do prywatnych aktywnosci"))
        def go(c):
            a = _get(c)
            j, _ = _http("POST", "https://www.strava.com/oauth/token", {"client_id": a["client_id"], "client_secret": a["client_secret"],
                                                                        "code": code, "grant_type": "authorization_code"})
            ath = j.get("athlete") or {}
            c.execute("UPDATE qbot_v2.strava_auth SET access_token=%s, refresh_token=%s, expires_at=%s, athlete_id=%s, athlete_name=%s, scope=%s, updated_at=now() WHERE id=1",
                      (j["access_token"], j["refresh_token"], int(j["expires_at"]), ath.get("id"),
                       ((ath.get("firstname") or "") + " " + (ath.get("lastname") or "")).strip(), scope))
        try:
            run(go)
        except Exception as e:
            return RedirectResponse("/strava.html?err=" + urllib.parse.quote(str(e)[:120]))
        return RedirectResponse("/strava.html?ok=1")

    @r.post("/sync")
    async def sync(request: Request):
        user_of(request)
        try:
            b = await request.json()
        except Exception:
            b = {}
        since = str((b or {}).get("since") or "2025-01-01")[:10]
        if not run(_get).get("refresh_token"):
            raise HTTPException(status_code=409, detail="Strava niepolaczona")
        threading.Thread(target=run_sync, args=(db_conn, since), daemon=True).start()
        return {"started": True, "since": since}

    @r.get("/photos")
    def photos(request: Request, year: int = 0, limit: int = 200):
        user_of(request)
        def go(c):
            q = ("SELECT p.unique_id, p.day, p.caption, p.lat, p.lon, p.width, p.height, p.file, p.ride_key, a.name AS activity, a.distance_m "
                 "FROM qbot_v2.strava_photo p JOIN qbot_v2.strava_activity a ON a.strava_id=p.strava_activity_id WHERE NOT p.hidden ")
            args: list[Any] = []
            if year:
                q += "AND extract(year FROM p.day) = %s "; args.append(year)
            q += "ORDER BY p.day DESC LIMIT %s"; args.append(max(1, min(1000, limit)))
            c.execute(q, args)
            rows = [dict(x) for x in c.fetchall()]
            for x in rows:
                x["day"] = str(x["day"]); x["url"] = PHOTO_URL + x.pop("file")
            return {"photos": rows}
        return run(go)

    @r.get("/review")
    def review(request: Request):
        user_of(request)
        import qbot_photo_taste as PT
        def go(c):
            model = _model(c)
            c.execute("""SELECT p.unique_id, p.day::text AS day, p.status, p.score, p.round, p.width, p.height, p.file, p.feats,
                                a.name AS title, round(a.distance_m/1000.0) AS km
                         FROM qbot_v2.strava_photo p JOIN qbot_v2.strava_activity a ON a.strava_id=p.strava_activity_id
                         WHERE p.day >= date_trunc('year', now())::date ORDER BY p.day DESC""")
            out = {"candidate": [], "liked": [], "rejected": 0}
            for x in _rows(c):
                st = x["status"] or "candidate"
                if st == "rejected":
                    out["rejected"] += 1; continue
                f = x.pop("feats") or {}
                x["fit"] = round(PT.score(model, f) * 100) if f else None
                x["sharp_ok"] = bool(f) and float(f.get("ostrosc") or 0) >= 3.0 and max(x["width"] or 0, x["height"] or 0) >= PT.MIN_PX
                fn = x.pop("file"); x["url_t"] = "/strava/t/" + fn; x["url_m"] = "/strava/m/" + fn; x["km"] = int(x["km"] or 0)
                out["liked" if st in ("liked", "auto") else "candidate"].append(x)
            out["candidate"].sort(key=lambda x: -(x["fit"] or 0))
            out["model"] = {"learned": bool(model), "n": (model or {}).get("n", 0), "acc": (model or {}).get("acc"), "top": PT.explain(model)}
            c.execute("SELECT count(*) AS n FROM qbot_v2.strava_activity WHERE total_photo_count>0 AND candidates_at IS NULL AND photos_synced_at IS NULL "
                      "AND start_date >= date_trunc('year', now()) AND distance_m >= %s", (MIN_RIDE_KM * 1000,))
            out["left_rides"] = _rows(c)[0]["n"]
            out["sync"] = dict(_SYNC)
            return out
        return run(go)

    @r.post("/rate")
    async def rate(request: Request):
        user_of(request)
        b = await request.json()
        uid, st = str(b.get("unique_id") or ""), str(b.get("status") or "")
        if st not in ("liked", "rejected", "candidate") or not uid:
            raise HTTPException(status_code=400, detail="status: liked / rejected / candidate")
        def go(c):
            c.execute("UPDATE qbot_v2.strava_photo SET status=%s, rated_at=now() WHERE unique_id=%s RETURNING file", (st, uid))
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="brak zdjecia")
            return {"ok": True, "status": st}
        return run(go)

    @r.post("/round")
    async def new_round(request: Request):
        user_of(request)
        try:
            b = await request.json()
        except Exception:
            b = {}
        n = max(10, min(80, int((b or {}).get("n") or 60)))
        if not run(_get).get("refresh_token"):
            raise HTTPException(status_code=409, detail="Strava niepolaczona")
        threading.Thread(target=run_round, args=(db_conn, n), daemon=True).start()
        return {"started": True, "n": n}

    return r
