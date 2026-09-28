# -*- coding: utf-8 -*-
"""Strava -> QBot (2026-09-28): polaczenie OAuth, lista aktywnosci i ZDJECIA z jazd (do wizytowki START).

Przeplyw:
  1. Michal zaklada aplikacje API na strava.com/settings/api (Callback Domain = albert.cytr.us)
  2. na /strava.html wpisuje Client ID + Client Secret (POST /api/strava/config) - sekret NIE trafia do czatu/repo
  3. "Polacz ze Strava" -> GET /api/strava/connect -> Strava (scope read,activity:read_all) -> GET /api/strava/callback
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
SCOPE = "read,activity:read_all"
LIMIT_15, LIMIT_DAY = 90, 900          # zapas wzgledem limitow Stravy (100 / 1000)

_SYNC = {"running": False, "phase": None, "done": 0, "photos": 0, "error": None, "started": None, "finished": None, "note": None}
_LOCK = threading.Lock()


def ensure_tables(c) -> None:
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
                               a.get("total_photo_count") or 0, rk, json.dumps({k: a.get(k) for k in ("start_latlng", "end_latlng", "total_elevation_gain", "moving_time", "location_country")})))
                    _SYNC["done"] += 1
                conn.commit()
                if _over_limit(usage):
                    _SYNC["note"] = "limit Stravy - reszta przy następnym pobieraniu (za ok. 15 min)"
                    return
                page += 1
            _SYNC["phase"] = "zdjęcia"
            c.execute("SELECT strava_id, ride_key, start_date FROM qbot_v2.strava_activity WHERE total_photo_count > 0 AND photos_synced_at IS NULL ORDER BY start_date DESC")
            todo = [dict(r) if hasattr(r, "keys") else {"strava_id": r[0], "ride_key": r[1], "start_date": r[2]} for r in c.fetchall()]
            for t in todo:
                tok = _token(c)
                photos, usage = _http("GET", API + "/activities/%d/photos" % t["strava_id"], {"size": 2048, "photo_sources": "true"}, tok)
                for p in photos or []:
                    uid = str(p.get("unique_id") or p.get("id"))
                    url = (p.get("urls") or {}).get("2048") or next(iter((p.get("urls") or {}).values()), None)
                    if not uid or not url or p.get("type") not in (None, 1, "1") and p.get("video_url"):
                        continue
                    fn = "%s.jpg" % uid.replace("/", "_")
                    path = os.path.join(PHOTO_DIR, fn)
                    if not os.path.exists(path):
                        try:
                            with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
                                f.write(r.read())
                        except Exception as e:
                            print("[strava] zdjecie %s: %s" % (uid, e)); continue
                    ll = p.get("location") or [None, None]
                    sz = (p.get("sizes") or {}).get("2048") or [None, None]
                    day = str(t["start_date"])[:10]
                    c.execute("""INSERT INTO qbot_v2.strava_photo (unique_id, strava_activity_id, ride_key, day, caption, lat, lon, taken_at, width, height, file, src_url)
                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (unique_id) DO UPDATE SET caption=EXCLUDED.caption, ride_key=EXCLUDED.ride_key""",
                              (uid, t["strava_id"], t["ride_key"], day, p.get("caption") or None, ll[0] if ll else None, ll[1] if ll else None,
                               p.get("created_at"), sz[0], sz[1], fn, url))
                    _SYNC["photos"] += 1
                c.execute("UPDATE qbot_v2.strava_activity SET photos_synced_at=now() WHERE strava_id=%s", (t["strava_id"],))
                conn.commit()
                if _over_limit(usage):
                    _SYNC["note"] = "limit Stravy - reszta zdjęć przy następnym pobieraniu (za ok. 15 min)"
                    return
            _SYNC["note"] = "gotowe"
        finally:
            conn.close()
    except Exception as e:
        _SYNC["error"] = str(e)[:300]
        print("[strava] sync: %s" % e)
    finally:
        _SYNC.update(running=False, finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def build_router(db_conn: Callable, current_user: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/strava")

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

    return r
