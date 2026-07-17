"""qbot-web - publiczny serwis HTML (Faza 1: statyczna strona + proste API tras)."""
import os
import json
import math
import urllib.request
import psycopg
from psycopg.rows import dict_row
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
import re as _re_email
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
import qbot_config as _cfg

WEB_ROOT = os.environ.get("QBOT_WEB_ROOT", "/opt/qbot/web/public")
HOST = os.environ.get("QBOT_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("QBOT_WEB_PORT", "30181"))
VALHALLA_ROUTE = "https://valhalla1.openstreetmap.de/route"
VALHALLA_TRACE_ATTRIBUTES = "https://valhalla1.openstreetmap.de/trace_attributes"
RISKY_GAP_MERGE_KM = 0.2  # ryzykowne odcinki oddzielone krotszym "dobrym" proseckiem laczymy w jeden
MIN_RISKY_SEGMENT_KM = 0.2  # ponizej tej dlugosci NIE zglaszamy jako osobny alert (szum/mikro-fragmenty)
VALHALLA_RISKY_SURFACES = {"dirt", "path", "impassable"}
VALHALLA_GOOD_SURFACES = {"paved_smooth", "paved", "compacted", "gravel"}
DEFAULT_ANCHOR_BUFFER_KM = 0.3  # jak daleko cofamy punkty startu/konca objazdu w dobra nawierzchnie
ESCALATION_BUFFERS_KM = [0.3, 1.0, 2.0, 3.0]  # promienie probkowania - patrz UWAGA #6 nizej
REPLACED_LENGTH_MAX_RATIO = 1.15  # kandydat nie moze byc dluzszy niz 115% dlugosci ZASTEPOWANEGO oryginalnego odcinka (miedzy kotwicami) - "na potrzeby sprawdzenia" wg ustalen 2026-07-01
# UWAGA architektoniczna (2026-07-01, wersja 4 - reguła "A wygrywa"):
# Eskalacja do 0.75/1.5/3km zostala WYCOFANA. Dowod (trasa 55798129, segment 4):
# przy szerokim buforze objazd porzucal fragmenty trasy, ktorych System A
# (route_surface_layer, tagi OSM) NIGDY nie oznaczyl jako ryzykowne, bo System B
# (wewnetrzny model nawierzchni Valhalli) ocenial te same "dobre" fragmenty jako
# w duzej mierze "dirt" (zweryfikowane trace_attributes: 60% dirt na odcinku,
# ktory System A klasyfikuje w 53% jako jawnie otagowany OSM z realnym dirt=1%).
# Rozjazd dwoch niezaleznych systemow oceny nawierzchni oznacza, ze pozwalanie
# Valhalli szukac szeroko = pozwalanie jej przepisywac trase wg INNEGO kanonu
# niz ten, ktory napedza raport i alerty. Zasada: objazd wolno ruszac WYLACZNIE
# w obrebie strefy, ktora System A oznaczyl jako ryzykowna - reszta trasy
# przypieta na sztywno. Stad tylko jeden, minimalny bufor (0.3km) - czysto
# techniczny margines do zaczepienia geometrii, nie przestrzen poszukiwan.
# Konsekwencja: czesc odcinkow, ktore wczesniej "udalo sie naprawic" dzieki
# szerokiemu buforowi (np. segmenty 4, 5, 17 na trasie testowej), wroca do
# statusu "brak realnej alternatywy" - swiadomy kompromis: mniej "sukcesow",
# ale zaden z nich nie bedzie fałszywy.
#
# UWAGA #5 (2026-07-01, korekta po feedbacku): calkowite wylaczenie eskalacji
# okazalo sie za bardzo zachowawcze - odcinek ktory mial oczywisty, bliski
# asfalt (dawny segment 17/18, 67.05-68.35km) przestal go w ogole probowac
# znalezc, bo asfalt byl osiagalny dopiero przy buforze 1.0km (0.3km: 80% dirt,
# 1.0km: 70% paved_smooth).
#
# UWAGA #6 (2026-07-01, "nie tepe jak pruski kapral"): sztywny sufit promienia
# (1.0km) to wciaz slepe zgadywanie - albo trafi w tym limicie, albo poddaje sie
# bez wzgledu na to jak blisko sukcesu bylo. WRACAMY do szerokiego zakresu
# probkowania (0.3/1.0/2.0/3.0km) bez zadnego limitu dlugosci per-kandydat.
#
# UWAGA #7 (2026-07-01, doprecyzowanie): probowano dodac limit proporcji
# dlugosci (candidate_km vs replaced_km) i zostal COFNIETY - nieporozumienie.
# Uzytkownik jasno: dlugi objazd (nawet 10km) jest OK, jesli prowadzi dobra
# nawierzchnia - jedyny akceptowalny cap to calkowita dlugosc CALEJ TRASY
# (nie pojedynczego kandydata), i to jest osobne, PRZYSZLE zadanie, nie teraz.
# Dzis jedynym kryterium akceptacji kandydata jest still_risky=False.
# replaced_km jest nadal zwracane w odpowiedzi (przejrzystosc - ile oryginalnej
# trasy miedzy kotwicami dany kandydat obejmuje), ale NIE wplywa na wybor ani
# na flage no_real_alternative. Stala REPLACED_LENGTH_MAX_RATIO ponizej NIE
# jest juz uzywana w logice - zostawiona jako udokumentowany, swiadomy false
# start na wypadek gdyby przyszly cap-na-cala-trase mial z niej korzystac.

app = FastAPI(title="qbot-web", docs_url=None, redoc_url=None)


def _webauth_load():
    """Wczytuje uzytkownikow i wartosc do podpisu ciasteczka z .env.webauth."""
    users = {}
    sign_val = ""
    try:
        for _line in open("/opt/qbot/app/" + "." + "env" + ".webauth"):
            if "=" in _line and not _line.startswith("#"):
                _k, _, _v = _line.strip().partition("=")
                if _k == "WEBAUTH_USERS":
                    for _pair in _v.split(","):
                        _pair = _pair.strip()
                        if ":" in _pair:
                            _u, _p = _pair.split(":", 1)
                            users[_u] = _p
                elif _k == "WEBAUTH_TOKEN":
                    sign_val = _v
    except Exception:
        pass
    return users, sign_val


def _webauth_cookie_make(username, sign_val):
    import hmac as _hmac, hashlib as _hashlib, time as _time
    expiry = int(_time.time()) + 365 * 24 * 3600
    msg = username + ":" + str(expiry)
    digest = _hmac.new(sign_val.encode(), msg.encode(), _hashlib.sha256).hexdigest()
    return msg + ":" + digest, expiry


def _webauth_cookie_valid(cookie_value, sign_val, users):
    import hmac as _hmac, hashlib as _hashlib, time as _time
    if not cookie_value or not sign_val:
        return False
    parts = cookie_value.split(":")
    if len(parts) != 3:
        return False
    username, expiry_s, digest = parts
    try:
        expiry = int(expiry_s)
    except ValueError:
        return False
    if _time.time() > expiry:
        return False
    if username not in users:
        return False
    expected = _hmac.new(sign_val.encode(), (username + ":" + expiry_s).encode(), _hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, digest)


_LOGIN_PAGE_CSS = (
    "body{font-family:-apple-system,system-ui,sans-serif;background:#0f1115;color:#e8e8e8;"
    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
    "form{background:#1a1d24;padding:2rem 2.5rem;border-radius:12px;"
    "box-shadow:0 8px 30px rgba(0,0,0,.4);width:280px}"
    "h1{font-size:1.1rem;margin:0 0 1.2rem;color:#9fd3ff}"
    "label{display:block;font-size:.8rem;color:#aaa;margin:.6rem 0 .2rem}"
    "input{width:100%;padding:.55rem .6rem;border-radius:6px;border:1px solid #333;"
    "background:#0f1115;color:#eee;box-sizing:border-box;font-size:1rem}"
    "button{margin-top:1.2rem;width:100%;padding:.6rem;border:0;border-radius:6px;"
    "background:#3b82f6;color:#fff;font-size:1rem;cursor:pointer}"
    "button:hover{background:#2563eb}"
    ".err{color:#ff8080;font-size:.82rem;margin-top:.8rem}"
)


def _no_cache_static(resp, path):
    """Statyki labu (html/js/css) maja byc zawsze swieze - wymus rewalidacje,
    zeby przegladarka nie trzymala starego raportu/skryptu po deployu."""
    try:
        if path == "/" or path.endswith((".html", ".js", ".css")):
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    except Exception:
        pass
    return resp


@app.middleware("http")
async def _webauth_guard(request, call_next):
    """Logowanie formularzem + dlugotrwale ciasteczko sesji (365 dni), oprocz /healthz i /login.
    Dane logowania: /opt/qbot/app/.env.webauth
    klucze: WEBAUTH_USERS=login:haslo,login2:haslo2 ; WEBAUTH_TOKEN=<wartosc do podpisu>
    """
    if request.url.path in ("/healthz", "/login", "/favicon.ico", "/favicon.svg"):
        return await call_next(request)

    users, sign_val = _webauth_load()
    if not users:
        return _no_cache_static(await call_next(request), request.url.path)

    cookie_value = request.cookies.get("qbot_session", "")
    if _webauth_cookie_valid(cookie_value, sign_val, users):
        return _no_cache_static(await call_next(request), request.url.path)

    if request.url.path.startswith("/api/"):
        return Response(status_code=401, content="unauthorized")

    from urllib.parse import quote
    next_url = quote(str(request.url.path), safe="")
    return Response(status_code=303, headers={"Location": "/login?next=" + next_url})


@app.get("/login", response_class=HTMLResponse)
async def _login_form(next: str = "/", err: int = 0):
    safe_next = next if next.startswith("/") else "/"
    err_html = '<div class="err">Zle dane logowania. Sprobuj ponownie.</div>' if err else ""
    return HTMLResponse(
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<link rel="icon" type="image/svg+xml" href="/favicon.svg"><link rel="alternate icon" href="/favicon.ico"><title>QBot Lab - logowanie</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<style>' + _LOGIN_PAGE_CSS + '</style></head><body>'
        '<form method="post" action="/login" autocomplete="on">'
        '<h1>QBot Lab</h1>'
        '<label for="u">Login</label>'
        '<input id="u" name="username" type="text" autocomplete="username" required autofocus>'
        '<label for="p">Haslo</label>'
        '<input id="p" name="password" type="password" autocomplete="current-password" required>'
        '<input type="hidden" name="next" value="' + safe_next + '">'
        '<button type="submit">Zaloguj</button>'
        + err_html +
        '</form></body></html>'
    )


@app.post("/login")
async def _login_submit(request: Request):
    raw = (await request.body()).decode("utf-8", errors="replace")
    from urllib.parse import parse_qs
    fields = parse_qs(raw)
    username = fields.get("username", [""])[0]
    password = fields.get("password", [""])[0]
    next_path = fields.get("next", ["/"])[0]
    if not next_path.startswith("/"):
        next_path = "/"

    users, sign_val = _webauth_load()
    import hmac as _hmac
    from urllib.parse import quote as _quote
    ok = bool(sign_val) and username in users and _hmac.compare_digest(users[username], password)
    if not ok:
        return Response(
            status_code=303,
            headers={"Location": "/login?err=1&next=" + _quote(next_path, safe="")},
        )

    cookie_value, expiry = _webauth_cookie_make(username, sign_val)
    resp = Response(status_code=303, headers={"Location": next_path})
    resp.set_cookie(
        "qbot_session", cookie_value,
        max_age=365 * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return resp


def _env():
    env = {}
    for ef in ["/opt/qbot/app/.env", "/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"]:
        try:
            for line in open(ef):
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k] = v
        except Exception:
            pass
    return env


def _db_conn():
    e = _env()
    return psycopg.connect(
        host=os.getenv("PGHOST", e.get("PGHOST", "127.0.0.1")),
        port=os.getenv("PGPORT", e.get("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", e.get("PGDATABASE", "qbot")),
        user=os.getenv("PGUSER", e.get("PGUSER", "qbot")),
        password=os.getenv("PGPASSWORD", e.get("PGPASSWORD", "")),
        row_factory=dict_row,
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/routes/ready")
def routes_ready():
    """Trasy z routes store, dla ktorych etap nawierzchni jest w pelni policzony (Wariant A)."""
    conn = _db_conn()
    try:
        rows = conn.execute(
            """
            SELECT route_id, distance_m, name, finished_at FROM (
                SELECT DISTINCT ON (rb.route_id) rb.route_id, rb.distance_m,
                       a.metadata_json->>'route_name' AS name,
                       j.finished_at
                FROM qbot_v2.route_base rb
                JOIN qbot_v2.route_precompute_jobs j
                    ON j.route_base_id = rb.route_base_id
                   AND j.job_type = 'route_surface'
                   AND j.status = 'complete'
                LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id
                ORDER BY rb.route_id, j.finished_at DESC
            ) t ORDER BY finished_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return {
        "routes": [
            {
                "route_id": r["route_id"],
                "name": r.get("name") or f"Trasa {r['route_id']}",
                "distance_km": round((r["distance_m"] or 0) / 1000, 1),
            }
            for r in rows
        ]
    }


@app.get("/api/routes/{route_id}/geometry")
def route_geometry(route_id: str):
    """Przebieg trasy (lat/lon) z route_axis_segments, do narysowania na mapie."""
    conn = _db_conn()
    try:
        base = conn.execute(
            """
            SELECT rb.route_base_id, rb.distance_m,
                   a.metadata_json->>'route_name' AS name
            FROM qbot_v2.route_base rb
            LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id
            WHERE rb.route_id = %s
            ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1
            """,
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        segs = conn.execute(
            """
            SELECT segment_index, segment_geojson
            FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s
            ORDER BY segment_index
            """,
            (base["route_base_id"],),
        ).fetchall()
    finally:
        conn.close()

    coords: list[list[float]] = []
    for s in segs:
        geo = s["segment_geojson"] or {}
        for pt in geo.get("coordinates", []):
            lon, lat = pt[0], pt[1]
            latlon = [round(lat, 6), round(lon, 6)]
            if not coords or coords[-1] != latlon:
                coords.append(latlon)

    return {
        "route_id": route_id,
        "name": base.get("name") or f"Trasa {route_id}",
        "distance_km": round((base["distance_m"] or 0) / 1000, 1),
        "coordinates": coords,
    }


def _haversine_m(lat1, lon1, lat2, lon2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


@app.get("/api/noclegi")
def api_noclegi(lat: float, lon: float, radius_m: int = 3000):
    """Noclegi w promieniu — Google Places (to samo zrodlo co POI trasy)."""
    try:
        from qbot3.artifacts.route_analyzer import (
            _route_poi_v2_google_search_nearby as _g_nearby,
            _route_poi_v2_google_api_key as _g_key,
        )
    except Exception as e:
        return {"status": "ERROR", "error": "integracja niedostepna: " + str(e)[:120], "items": []}
    gkey = _g_key()
    if not gkey:
        return {"status": "NO_KEY", "error": "brak klucza w srodowisku qbot-web", "items": []}
    lodging_types = ["hotel", "motel", "bed_and_breakfast", "guest_house", "hostel",
                     "resort_hotel", "extended_stay_hotel", "campground", "cottage", "farmstay"]
    try:
        places = _g_nearby(float(lat), float(lon), radius_m=float(radius_m),
                           api_key=gkey, included_types=lodging_types)
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:160], "items": []}
    items = []
    for pl in places:
        loc = pl.get("location") or {}
        plat, plon = loc.get("latitude"), loc.get("longitude")
        if plat is None or plon is None:
            continue
        items.append({
            "name": (pl.get("displayName") or {}).get("text") or "(bez nazwy)",
            "type": (pl.get("primaryTypeDisplayName") or {}).get("text") or "",
            "rating": pl.get("rating"),
            "ratings": pl.get("userRatingCount"),
            "lat": plat, "lon": plon,
            "dist_m": round(_haversine_m(float(lat), float(lon), float(plat), float(plon))),
        })
    items.sort(key=lambda x: x["dist_m"])
    return {"status": "OK", "count": len(items), "radius_m": radius_m, "items": items}


@app.get("/api/planer/opis")
def api_planer_opis(route_id: str, rebuild: int = 0):
    """Opis-tlo trasy dla Planera wyprawy (cache w qbot_v2.planer_route_opis;
    rebuild=1 wymusza regeneracje, inwalidacja po geometry_hash)."""
    try:
        from qbot3.routes.planer_opis import build_opis
    except Exception as e:
        return {"status": "ERROR", "error": "modul niedostepny: " + str(e)[:120]}
    try:
        data = build_opis(route_id, rebuild=bool(rebuild))
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:200]}
    if isinstance(data, dict) and data.get("error"):
        return {"status": "ERROR", "error": data.get("error"), "detail": data.get("raw")}
    return {"status": "OK", **data}


@app.post("/api/planer/opis-dni")
async def api_planer_opis_dni(request: Request):
    """Opis LLM per dzien wg podzialu. Body: {route_id, cuts:[km,...], rebuild?}."""
    try:
        body = await request.json()
    except Exception:
        return {"status": "ERROR", "error": "bledny JSON w body"}
    rid = body.get("route_id")
    cuts = body.get("cuts") or []
    rebuild = bool(body.get("rebuild"))
    if not rid:
        return {"status": "ERROR", "error": "brak route_id"}
    try:
        from qbot3.routes.planer_opis import build_opis_dni
    except Exception as e:
        return {"status": "ERROR", "error": "modul niedostepny: " + str(e)[:120]}
    try:
        data = build_opis_dni(rid, cuts, rebuild=rebuild)
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:200]}
    if isinstance(data, dict) and data.get("error"):
        return {"status": "ERROR", "error": data.get("error")}
    return data


def _tile_poly_bounds(x, y, z=14):
    n = 2 ** z
    lon_w = x / n * 360.0 - 180.0
    lon_e = (x + 1) / n * 360.0 - 180.0
    lat_n = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_s = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lat_s, lon_w, lat_n, lon_e  # SW, NE


@app.get("/api/routes/{route_id}/tiles")
def route_tiles(route_id: str, margin: int = 3):
    """Kafle z14 na trasie (new/keep) + pas otoczki owned wzgledem StatsHunters."""
    from tools.tile_store import fetch_tiles, get_tile_set, _latlon_to_tile
    g = route_geometry(route_id)
    coords = g["coordinates"]
    if not coords:
        return {"route_id": route_id, "zoom": 14, "margin": margin,
                "counts": {"route": 0, "new": 0, "keep": 0, "owned_total": 0},
                "tile_error": None, "tiles": []}
    rt = set()
    for i in range(len(coords) - 1):
        (la1, lo1), (la2, lo2) = coords[i], coords[i + 1]
        steps = max(1, int(math.hypot(la2 - la1, lo2 - lo1) / 0.0008))
        for s in range(steps + 1):
            t = s / steps
            rt.add(_latlon_to_tile(la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t, 14))
    share = os.getenv("STATSHUNTERS_SHARE_ID", _env().get("STATSHUNTERS_SHARE_ID", ""))
    owned, tile_err = set(), None
    if share:
        td = fetch_tiles(share)
        tile_err = td.get("_error")
        owned = get_tile_set(td.get("tiles", []))
    else:
        tile_err = "brak STATSHUNTERS_SHARE_ID"
    border = set()
    for (x, y) in rt:
        for dx in range(-margin, margin + 1):
            for dy in range(-margin, margin + 1):
                c = (x + dx, y + dy)
                if c not in rt:
                    border.add(c)

    def feat(x, y, status):
        s, w, n, e = _tile_poly_bounds(x, y, 14)
        return {"x": x, "y": y, "status": status, "bounds": [[s, w], [n, e]]}

    tiles = [feat(x, y, "new" if (x, y) not in owned else "keep") for (x, y) in rt]
    tiles += [feat(x, y, "owned" if (x, y) in owned else "empty") for (x, y) in border]
    return {"route_id": route_id, "zoom": 14, "margin": margin,
            "counts": {"route": len(rt),
                       "new": sum(1 for t in tiles if t["status"] == "new"),
                       "keep": sum(1 for t in tiles if t["status"] == "keep"),
                       "owned_total": len(owned)},
            "tile_error": tile_err, "tiles": tiles}


_PROBLEM_SURFACES = {"ground", "grass", "sand", "unknown", "unpaved"}
_OK_STATUSES = {"GOOD", "GOOD_INFERRED"}


def _load_surface_buckets(conn, route_base_id: int) -> list[dict]:
    """Odcinki nawierzchni (km_from/km_to z surface_meta_json) posortowane po km.

    UWAGA architektoniczna (2026-07-01): route_axis_segments (50m, ~1423 wierszy)
    i route_surface_layer (OSM way-segmenty, ~76 wierszy) maja NIEZALEZNA numeracje
    segment_index - to NIE jest ten sam podzial trasy. Jedyny wspolny klucz to
    kilometraz, dlatego dopasowanie idzie po km_from/km_to, nigdy po segment_index.
    """
    rows = conn.execute(
        """
        SELECT surface, highway, tracktype, coverage_status, confidence, surface_meta_json
        FROM qbot_v2.route_surface_layer
        WHERE route_base_id = %s
        ORDER BY segment_index
        """,
        (route_base_id,),
    ).fetchall()
    buckets = []
    for r in rows:
        meta = r.get("surface_meta_json") or {}
        try:
            km_from = float(meta.get("km_from"))
            km_to = float(meta.get("km_to"))
        except (TypeError, ValueError):
            continue
        surface = (r.get("surface") or "unknown").lower()
        coverage = r.get("coverage_status")
        highway = r.get("highway")
        tracktype = r.get("tracktype")
        # UWAGA (2026-07-01, regula "przyzwoity grade"): dla drog typu "track"
        # tracktype grade1-4 ZAWSZE wygrywa nad wywnioskowana etykieta "surface"
        # (ground/grass) - dowod na trasie testowej: 3 odcinki mialy jawny tag
        # tracktype=grade4 (przyzwoita, srednia droga gruntowa), a mimo to
        # wpadaly do "ryzykowne" tylko dlatego, ze surface wyszlo jako ground/
        # grass. Ryzykowne zostaje wylacznie: brak tracktype (None) LUB grade5.
        # Dla drog innych niz "track" (gdzie tracktype nie ma zastosowania)
        # zasada bez zmian - decyduje surface + coverage_status jak dotychczas.
        if highway == "track" and tracktype in {"grade1", "grade2", "grade3", "grade4"}:
            risky = False
        else:
            risky = surface in _PROBLEM_SURFACES or coverage not in _OK_STATUSES
        buckets.append({
            "km_from": km_from,
            "km_to": km_to,
            "risky": risky,
            "surface": surface,
            "surface_raw": meta.get("surface_raw") or surface,
            "coverage_status": coverage,
            "confidence": r.get("confidence"),
            "explanation": meta.get("explanation") or "",
            "highway": highway,
            "tracktype": tracktype,
            "surface_category": meta.get("surface_category"),
            "surface_category_label": meta.get("surface_category_label"),
            "surface_category_reason": meta.get("surface_category_reason"),
        })
    buckets.sort(key=lambda b: b["km_from"])
    return buckets


def _bucket_for_km(buckets: list[dict], km_mid: float) -> dict | None:
    for b in buckets:
        if b["km_from"] <= km_mid < b["km_to"]:
            return b
    return None


_SURFACE_LABEL_PL = {
    "asphalt": "asfalt",
    "paved": "nawierzchnia utwardzona",
    "paved_smooth": "gladki asfalt",
    "concrete": "beton",
    "paving_stones": "kostka brukowa",
    "compacted": "ubita nawierzchnia (dobra)",
    "gravel": "zwir",
    "fine_gravel": "drobny zwir",
    "dirt": "ubita ziemia / droga gruntowa",
    "ground": "goly grunt",
    "grass": "trawa",
    "sand": "piasek",
    "mixed": "nawierzchnia mieszana",
    "unpaved": "nieutwardzona",
    "path": "waska sciezka",
    "impassable": "nieprzejezdna",
    "unknown": "nieznana nawierzchnia",
}


def _surface_label_pl(surface: str | None) -> str:
    if not surface:
        return "nieznana nawierzchnia"
    return _SURFACE_LABEL_PL.get(surface.lower(), surface)


def _human_reason(b: dict | None) -> str:
    """Tlumaczy techniczny opis nawierzchni (tagi OSM, heurystyki) na zdanie
    po polsku - zbudowane na bazie realnych wzorcow explanation wystepujacych
    w danych (sprawdzone zapytaniem do route_surface_layer, nie zgadywane)."""
    if b is None:
        return "Brak danych o nawierzchni dla tego miejsca - z ostroznosci uznane za ryzykowne."
    surface = b.get("surface_raw") or b.get("surface") or "unknown"
    label = _surface_label_pl(surface)
    explanation = (b.get("explanation") or "").strip()
    confidence = b.get("confidence") or "brak"
    conf_pl = {"low": "niska", "medium": "srednia", "high": "wysoka"}.get(confidence, confidence)

    if "explicit OSM surface tag" in explanation:
        base = f"Nawierzchnia wprost oznaczona w danych OSM jako: {label}."
    elif "highway=track without surface/tracktype" in explanation:
        base = "Droga gruntowa (lesna/polna) bez podanej w OSM informacji o nawierzchni."
    elif "highway=path without surface" in explanation:
        base = "Waska sciezka bez podanej w OSM informacji o nawierzchni."
    elif "tracktype=grade5" in explanation:
        base = "Najgorsza klasa drogi gruntowej (grade 5) - zwykle blotnista, trawiasta lub piaszczysta."
    elif "tracktype=grade4" in explanation:
        base = "Slaba klasa drogi gruntowej (grade 4) - ziemia, trawa lub luzna nawierzchnia."
    elif "tracktype=grade3" in explanation:
        base = "Srednia klasa drogi gruntowej (grade 3) - zwykle zwir lub ubita ziemia."
    else:
        base = f"Nawierzchnia: {label}."

    if "sand_loose_ground_possible" in explanation:
        base += " W tej okolicy dodatkowo mozliwy piasek lub luzny grunt (wniosek z geologii terenu, nie z samego OSM)."

    return f"{base} Pewnosc oceny: {conf_pl}."


def _weighted_breakdown_pl(buckets: list[dict], km_from: float, km_to: float) -> list[dict]:
    """Rozklad nawierzchni ORYGINALNEGO odcinka [km_from, km_to] wazony dlugoscia
    nakladania sie z bucketami nawierzchni - do porownania z kandydatem."""
    totals: dict[str, float] = {}
    total_len = 0.0
    for b in buckets:
        overlap = min(km_to, b["km_to"]) - max(km_from, b["km_from"])
        if overlap <= 0:
            continue
        label = _surface_label_pl(b.get("surface_raw") or b.get("surface"))
        totals[label] = totals.get(label, 0.0) + overlap
        total_len += overlap
    if total_len <= 0:
        return []
    breakdown = sorted(
        [{"surface": k, "pct": round(v / total_len * 100)} for k, v in totals.items()],
        key=lambda x: -x["pct"],
    )
    return breakdown


def _describe_bucket(b: dict | None) -> str:
    if b is None:
        return "Brak dopasowanych danych OSM dla tego odcinka — traktowane jako ryzykowne z ostrożności."
    surface = b.get("surface_raw") or b.get("surface") or "nieznana"
    coverage = b.get("coverage_status") or "brak statusu"
    confidence = b.get("confidence") or "brak"
    explanation = b.get("explanation") or ""
    parts = [f"Nawierzchnia: {surface}", f"pokrycie danych: {coverage}", f"pewność: {confidence}"]
    if explanation:
        parts.append(explanation)
    return " · ".join(parts)


def _merge_close_risky(runs: list[dict], gap_km: float = RISKY_GAP_MERGE_KM) -> list[dict]:
    """Laczy sasiednie odcinki ryzykowne rozdzielone krotkim "dobrym" proseczkiem
    (< gap_km) w jeden odcinek - unika zasypywania tabeli mikro-fragmentami,
    ktore w praktyce jada sie jako jedno miejsce."""
    result: list[dict] = []
    i = 0
    n = len(runs)
    while i < n:
        run = runs[i]
        if not run["risky"]:
            result.append(run)
            i += 1
            continue
        merged_coords = list(run["coordinates"])
        km_to = run["km_to"]
        reasons = [run["reason"]] if run.get("reason") else []
        i += 1
        while (
            i + 1 < n
            and not runs[i]["risky"]
            and (runs[i]["km_to"] - runs[i]["km_from"]) < gap_km
            and runs[i + 1]["risky"]
        ):
            gap_run = runs[i]
            next_run = runs[i + 1]
            merged_coords += gap_run["coordinates"][1:] + next_run["coordinates"][1:]
            km_to = next_run["km_to"]
            if next_run.get("reason") and next_run["reason"] not in reasons:
                reasons.append(next_run["reason"])
            i += 2
        result.append({
            "risky": True,
            "km_from": run["km_from"],
            "km_to": km_to,
            "coordinates": merged_coords,
            "reason": " | ".join(reasons) if reasons else None,
        })
    return result


@app.get("/api/routes/{route_id}/surface-segments")
def route_surface_segments(route_id: str):
    """Trasa pocieta na ciagle odcinki dobra/ryzykowna wg nawierzchni, z uzasadnieniem
    i numeracja odcinkow ryzykownych (segment_no), po zlaczeniu bardzo bliskich."""
    conn = _db_conn()
    try:
        base = conn.execute(
            """
            SELECT rb.route_base_id, rb.distance_m,
                   a.metadata_json->>'route_name' AS name
            FROM qbot_v2.route_base rb
            LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id
            WHERE rb.route_id = %s
            ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1
            """,
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")

        axis_rows = conn.execute(
            """
            SELECT segment_index, km_from, km_to, segment_geojson
            FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s
            ORDER BY segment_index
            """,
            (base["route_base_id"],),
        ).fetchall()
        buckets = _load_surface_buckets(conn, base["route_base_id"])
    finally:
        conn.close()

    runs: list[dict] = []
    current_risky = None
    current_coords: list[list[float]] = []
    current_km_from = None
    current_km_to = None
    current_bucket_hits: dict[int, int] = {}
    bucket_by_id = {id(b): b for b in buckets}

    def _flush():
        if not current_coords:
            return
        rep_bucket = None
        if current_bucket_hits:
            best_id = max(current_bucket_hits, key=current_bucket_hits.get)
            rep_bucket = bucket_by_id.get(best_id)
        runs.append({
            "coordinates": current_coords,
            "risky": current_risky,
            "km_from": round(current_km_from, 2),
            "km_to": round(current_km_to, 2),
            "reason": _human_reason(rep_bucket) if current_risky else None,
        })

    for row in axis_rows:
        km_from = float(row["km_from"])
        km_to = float(row["km_to"])
        km_mid = (km_from + km_to) / 2.0
        bucket = _bucket_for_km(buckets, km_mid)
        risky = bucket["risky"] if bucket is not None else True
        geo = row["segment_geojson"] or {}
        seg_coords = [[round(pt[1], 6), round(pt[0], 6)] for pt in geo.get("coordinates", [])]
        if not seg_coords:
            continue
        if risky != current_risky:
            _flush()
            current_coords = [current_coords[-1]] if current_coords else []
            current_risky = risky
            current_km_from = km_from
            current_bucket_hits = {}
        current_coords.extend(seg_coords)
        current_km_to = km_to
        if bucket is not None:
            current_bucket_hits[id(bucket)] = current_bucket_hits.get(id(bucket), 0) + 1
    _flush()

    runs = _merge_close_risky(runs)

    # UWAGA (2026-07-01): odcinki ryzykowne krotsze niz MIN_RISKY_SEGMENT_KM (200m)
    # NIE sa zglaszane jako osobny alert - to szum (np. widziano 50m, 100m, 150m
    # fragmenty na trasie testowej), ktorego rowerzysta praktycznie nie zauwaza,
    # a ktory zasmieca tabele i generuje bezsensowne proby objazdu. Trafiaja z
    # powrotem do puli "dobra nawierzchnia" (nie usuwamy geometrii z mapy).
    filtered_runs = []
    for r in runs:
        if r["risky"] and (r["km_to"] - r["km_from"]) < MIN_RISKY_SEGMENT_KM:
            r = dict(r)
            r["risky"] = False
        filtered_runs.append(r)
    runs = filtered_runs

    segment_no = 1
    for r in runs:
        if r["risky"]:
            r["segment_no"] = segment_no
            segment_no += 1
            r["original_breakdown"] = _weighted_breakdown_pl(buckets, r["km_from"], r["km_to"])
        else:
            r["segment_no"] = None
            r["original_breakdown"] = None

    return {
        "route_id": route_id,
        "name": base.get("name") or f"Trasa {route_id}",
        "distance_km": round((base["distance_m"] or 0) / 1000, 1),
        "segments": runs,
    }


def _coalesce_categories(buckets: list[dict]) -> list[dict]:
    """Scala sasiednie bucket-y o tej samej surface_category w ciagle odcinki (wstazka 5-kat.)."""
    runs: list[dict] = []
    for b in buckets:
        cat = b.get("surface_category")
        if runs and runs[-1]["category"] == cat:
            runs[-1]["km_to"] = b["km_to"]
            runs[-1]["_surfs"].append(b.get("surface"))
        else:
            runs.append({
                "category": cat,
                "label": b.get("surface_category_label"),
                "km_from": b["km_from"],
                "km_to": b["km_to"],
                "reason": b.get("surface_category_reason"),
                "_surfs": [b.get("surface")],
            })
    for r in runs:
        surfs = [x for x in r.pop("_surfs") if x]
        r["dominant_surface"] = max(set(surfs), key=surfs.count) if surfs else None
        r["km_from"] = round(r["km_from"], 2)
        r["km_to"] = round(r["km_to"], 2)
    return runs


@app.get("/api/routes/{route_id}/surface-categories")
def route_surface_categories(route_id: str):
    """Nawierzchnia jako 5 kategorii (surface_category z route_surface_layer, model 2026-07-03).

    Zrodlo: route_surface_layer.surface_meta_json (pole surface_category liczone przez
    route_surface_category_store, przebieg DB->DB). Zwraca wstazke (scalone odcinki
    tej samej kategorii) + surowe bucket-y + histogram. Addytywny wzgledem
    /surface-segments (ryzyko binarne) - ten nie jest ruszany."""
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT rb.route_base_id, rb.distance_m, "
            "a.metadata_json->>'route_name' AS name "
            "FROM qbot_v2.route_base rb "
            "LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id "
            "WHERE rb.route_id = %s ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1",
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        buckets = _load_surface_buckets(conn, base["route_base_id"])
    finally:
        conn.close()

    ribbon = _coalesce_categories(buckets)
    histogram: dict[int, float] = {}
    for b in buckets:
        cat = b.get("surface_category")
        if cat is None:
            continue
        histogram[cat] = round(histogram.get(cat, 0.0) + (b["km_to"] - b["km_from"]), 2)
    has_cat = any(b.get("surface_category") is not None for b in buckets)
    return {
        "route_id": route_id,
        "name": base.get("name") or f"Trasa {route_id}",
        "distance_km": round((base["distance_m"] or 0) / 1000, 1),
        "has_category": has_cat,
        "ribbon": ribbon,
        "km_by_category": histogram,
        "segments": [
            {
                "km_from": b["km_from"], "km_to": b["km_to"],
                "category": b.get("surface_category"),
                "label": b.get("surface_category_label"),
                "reason": b.get("surface_category_reason"),
                "surface": b.get("surface"),
            }
            for b in buckets
        ],
    }


def _decode_valhalla_polyline(encoded: str, precision: int = 6) -> list[list[float]]:
    """Fallback: Valhalla czasem zwraca shape jako zakodowany polyline (string)
    mimo zadania shape_format=geojson - trzeba obsluzyc oba warianty (identyczna
    logika co w tools/route_generator.py::_decode_polyline / _parse_track)."""
    inv = 1.0 / 10**precision
    decoded = []
    lat = lon = 0
    i = 0
    while i < len(encoded):
        shift = result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lat += (~(result >> 1) if (result & 1) else (result >> 1))
        shift = result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lon += (~(result >> 1) if (result & 1) else (result >> 1))
        decoded.append([lat * inv, lon * inv])
    return decoded


def _valhalla_alternative(origin: list[float], destination: list[float]) -> dict:
    """Wywoluje publiczna Valhalle (bicycle/Cross) z mocnym unikaniem zlej nawierzchni."""
    payload = {
        "locations": [
            {"lat": origin[0], "lon": origin[1]},
            {"lat": destination[0], "lon": destination[1]},
        ],
        "costing": "bicycle",
        "costing_options": {"bicycle": {
            "bicycle_type": "Cross",
            "use_roads": 0.7,
            "use_hills": 0.5,
            "avoid_bad_surfaces": 0.9,
        }},
        "directions_options": {"units": "km"},
        "shape_format": "geojson",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(VALHALLA_ROUTE, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    shape = result["trip"]["legs"][0]["shape"]
    if isinstance(shape, str):
        coords = _decode_valhalla_polyline(shape)
    else:
        coords = [[c[1], c[0]] for c in shape["coordinates"]]
    distance_km = result["trip"]["summary"]["length"]
    return {"coordinates": coords, "distance_km": round(distance_km, 2)}


def _valhalla_surface_confidence(coordinates: list[list[float]]) -> dict:
    """Sprawdza realna nawierzchnie objazdu przez Valhalla trace_attributes
    (map-matching do krawedzi grafu OSM, ktorego uzywa sam routing) - zamiast
    zgadywac pewnosc, pytamy ten sam graf, ktory wyznaczyl objazd. Osobne API
    od Overpass (unikamy znanego throttlingu Overpass z wczesniejszych prob)."""
    payload = {
        "shape": [{"lat": lat, "lon": lon} for lat, lon in coordinates],
        "costing": "bicycle",
        "shape_match": "map_snap",
        "filters": {"attributes": ["edge.surface", "edge.length"], "action": "include"},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(VALHALLA_TRACE_ATTRIBUTES, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    edges = result.get("edges") or []
    by_surface: dict[str, float] = {}
    total = 0.0
    for e in edges:
        surface = e.get("surface") or "unknown"
        length = float(e.get("length") or 0.0)
        by_surface[surface] = by_surface.get(surface, 0.0) + length
        total += length
    if total <= 0:
        return {"available": False, "still_risky": None, "risky_pct": None, "note": "Brak dopasowanych krawedzi grafu dla objazdu."}
    breakdown = sorted(
        [{"surface": s, "surface_pl": _surface_label_pl(s), "pct": round(l / total * 100)} for s, l in by_surface.items()],
        key=lambda x: -x["pct"],
    )
    dominant = breakdown[0]["surface"]
    risky_pct = sum(b["pct"] for b in breakdown if b["surface"] in VALHALLA_RISKY_SURFACES)
    still_risky = risky_pct >= 50 or dominant in VALHALLA_RISKY_SURFACES
    return {
        "available": True,
        "breakdown": breakdown,
        "dominant": dominant,
        "dominant_pct": breakdown[0]["pct"],
        "risky_pct": risky_pct,
        "still_risky": still_risky,
        "note": "Wg klasyfikacji nawierzchni Valhalli/OSM dla objazdu — inna skala niz reszta raportu, traktuj orientacyjnie.",
    }


def _anchor_point(conn, route_base_id: int, target_km: float, *, side: str) -> list[float] | None:
    """Znajduje punkt geometrii najblizszy zadanemu kilometrowi.
    side='before' -> szukamy segmentu konczacego sie <= target_km, bierzemy JEGO OSTATNI punkt
    side='after'  -> szukamy segmentu zaczynajacego sie >= target_km, bierzemy JEGO PIERWSZY punkt
    """
    if side == "before":
        row = conn.execute(
            """
            SELECT segment_geojson FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s AND km_to <= %s
            ORDER BY km_to DESC LIMIT 1
            """,
            (route_base_id, target_km),
        ).fetchone()
        idx = -1
    else:
        row = conn.execute(
            """
            SELECT segment_geojson FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s AND km_from >= %s
            ORDER BY km_from ASC LIMIT 1
            """,
            (route_base_id, target_km),
        ).fetchone()
        idx = 0
    if not row:
        return None
    geo = row["segment_geojson"] or {}
    coords = geo.get("coordinates", [])
    if not coords:
        return None
    pt = coords[idx]
    return [pt[1], pt[0]]


@app.get("/api/routes/{route_id}/segments/candidate")
def route_segment_candidate(
    route_id: str,
    km_from: float,
    km_to: float,
    buffer_km: float | None = Query(default=None),
):
    """Proponuje objazd dla wskazanego odcinka [km_from, km_to] przez publiczna Valhalle,
    wraz z informacja o pewnosci nawierzchni objazdu (trace_attributes).

    UWAGA architektoniczna (2026-07-01, wersja 3 - progresywne probkowanie):
    Test na trasie testowej 55798129 wykazal, ze pojedynczy staly bufor 0.3km
    czesto nie wystarcza - trasa ta zostala CELOWO ulozona po niepewnych drogach
    (zbieranie kwadratow StatsHunters), wiec trudnosc jest realna i oczekiwana.
    Zamiast jednego stalego bufora probkujemy PROGRESYWNIE rosnace promienie
    (ESCALATION_BUFFERS_KM) i zatrzymujemy sie na pierwszym, ktory daje dobra
    nawierzchnie (still_risky=False); jesli zaden nie wystarczy, zwracamy
    NAJLEPSZY znaleziony wariant (najnizszy risky_pct) z jawna informacja
    do jakiego promienia szukano - zamiast cichego "brak" po jednej probie.

    UWAGA #4 (2026-07-01, korekta use_roads): pierwotny test parametrow byl
    robiony TYLKO na waskim buforze 0.3km, gdzie zadna prawdziwa droga nie byla
    fizycznie osiagalna - stad blednie wygladalo, ze use_roads "nic nie zmienia".
    Przy szerszym buforze (1.5km+), gdzie realna droga asfaltowa BYLA w zasiegu,
    okazalo sie ze use_roads=0.3 aktywnie ODCIAGAL routing od tej drogi w strone
    sciezek/duktow (Valhalla: nizsze use_roads = preferuj sciezki nad drogami).
    Podniesienie do use_roads=0.7 znalazlo te sama widoczna na mapie droge
    asfaltowa (np. segment 17: 67% dirt -> 75% paved_smooth przy tym samym
    buforze 1.5km), bez pogorszenia wczesniej dzialajacych przypadkow.

    Jesli wywolujacy jawnie poda buffer_km, escalacja jest pomijana (uzywany
    jest dokladnie ten jeden bufor) - przydatne do debugowania/testow.
    """
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT route_base_id, distance_m FROM qbot_v2.route_base WHERE route_id = %s ORDER BY route_modified_at DESC NULLS LAST LIMIT 1",
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        route_max_km = (base["distance_m"] or 0) / 1000.0
        route_base_id = base["route_base_id"]

        buffers_to_try = [buffer_km] if buffer_km is not None else ESCALATION_BUFFERS_KM

        best = None
        tried_km: list[float] = []
        anchors_missing = False
        last_error: str | None = None
        for buf in buffers_to_try:
            anchor_from_km = max(0.0, km_from - buf)
            anchor_to_km = min(route_max_km, km_to + buf) if route_max_km else km_to + buf
            origin = _anchor_point(conn, route_base_id, anchor_from_km, side="before")
            destination = _anchor_point(conn, route_base_id, anchor_to_km, side="after")
            if not origin or not destination:
                anchors_missing = True
                continue
            tried_km.append(buf)
            try:
                candidate = _valhalla_alternative(origin, destination)
                confidence = _valhalla_surface_confidence(candidate["coordinates"])
            except Exception as exc:
                # UWAGA (2026-07-01): rozroznij "nie ma punktow zakotwiczenia" (problem
                # danych) od "publiczna Valhalla nie odpowiada/zwraca blad" (przejsciowa
                # awaria zewnetrznej uslugi, poza nasza kontrola) - wczesniej oba przypadki
                # dawaly ten sam mylacy komunikat "nie znaleziono punktow zakotwiczenia".
                last_error = str(exc)
                continue

            # UWAGA (2026-07-01, cofniete po wyjasnieniu): limit proporcji dlugosci
            # per-kandydat byl nieporozumieniem - uzytkownik akceptuje dlugie objazdy
            # (nawet 10km) jesli prowadza dobra nawierzchnia. replaced_km zostaje
            # jako informacja (przejrzystosc), ale NIE bierze udzialu w ocenie/
            # odrzucaniu kandydata. Ograniczenie calkowitej dlugosci TRASY (nie
            # pojedynczego kandydata) to osobne, przyszle zadanie - nie teraz.
            replaced_km = round(anchor_to_km - anchor_from_km, 2)
            still_risky = confidence.get("still_risky")

            risky_pct = confidence.get("risky_pct")
            score = risky_pct if risky_pct is not None else 100
            entry = {
                "buffer_km": buf,
                "anchor_from_km": round(anchor_from_km, 2),
                "anchor_to_km": round(anchor_to_km, 2),
                "replaced_km": replaced_km,
                "candidate": candidate,
                "confidence": confidence,
                "score": score,
            }
            if best is None or score < best["score"]:
                best = entry
            if still_risky is False:
                break  # znaleziono dobra nawierzchnie, koniec eskalacji
    finally:
        conn.close()

    if best is None:
        if last_error and not anchors_missing:
            raise HTTPException(
                status_code=503,
                detail=f"Publiczna Valhalla (silnik routingu) jest chwilowo niedostepna lub zwraca blad - sprobuj ponownie za chwile. Szczegol: {last_error}",
            )
        raise HTTPException(status_code=404, detail="Nie znaleziono punktow zakotwiczenia dla tego odcinka")

    candidate = best["candidate"]
    confidence = best["confidence"]
    original_km = round(km_to - km_from, 2)
    delta_km = round(candidate["distance_km"] - original_km, 2)
    still_risky = confidence.get("still_risky")

    return {
        "route_id": route_id,
        "km_from": km_from,
        "km_to": km_to,
        "buffer_km_used": best["buffer_km"],
        "escalation_tried_km": tried_km,
        "anchor_from_km": best["anchor_from_km"],
        "anchor_to_km": best["anchor_to_km"],
        "replaced_km": best["replaced_km"],
        "original_km": original_km,
        "candidate_km": candidate["distance_km"],
        "delta_km": delta_km,
        "coordinates": candidate["coordinates"],
        "confidence": confidence,
        "no_real_alternative": bool(still_risky),
    }



import re as _re
import html as _htmlmod


def _kanon_inline(s: str) -> str:
    s = _htmlmod.escape(s)
    s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = _re.sub(r"_(.+?)_", r"<em>\1</em>", s)
    return s


def _kanon_md_to_html(md: str) -> str:
    lines = md.split("\n")
    out, i, n = [], 0, len(md.split("\n"))

    def is_row(l):
        return l.strip().startswith("|")

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    while i < n:
        l = lines[i]
        s = l.strip()
        if s == "<!--RAW-->":
            i += 1
            raw = []
            while i < n and lines[i].strip() != "<!--/RAW-->":
                raw.append(lines[i]); i += 1
            i += 1
            out.append("\n".join(raw))
            continue
        if is_row(l):
            block = []
            while i < n and is_row(lines[i]):
                block.append(lines[i])
                i += 1
            header = cells(block[0])
            data = block[1:]
            if data:
                probe = data[0].replace("|", "").replace(":", "").replace("-", "").replace(" ", "")
                if probe == "":
                    data = data[1:]
            t = ["<table><thead><tr>"]
            t += [f"<th>{_kanon_inline(c)}</th>" for c in header]
            t.append("</tr></thead><tbody>")
            for r in data:
                t.append("<tr>" + "".join(f"<td>{_kanon_inline(c)}</td>" for c in cells(r)) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue
        if s.startswith("### "):
            out.append(f"<h3>{_kanon_inline(s[4:])}</h3>"); i += 1; continue
        if s.startswith("## "):
            out.append(f"<h2>{_kanon_inline(s[3:])}</h2>"); i += 1; continue
        if s.startswith("# "):
            out.append(f"<h1>{_kanon_inline(s[2:])}</h1>"); i += 1; continue
        if s.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(f"<li>{_kanon_inline(lines[i].strip()[2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if s == "":
            i += 1; continue
        out.append(f"<p>{_kanon_inline(s)}</p>"); i += 1
    return "\n".join(out)


_KANON_PAGE = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raport kanoniczny __RID__</title>
<style>
:root{color-scheme:light dark}
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:920px;margin:0 auto;padding:16px;line-height:1.45}
h1{font-size:1.5rem;border-bottom:2px solid #888;padding-bottom:6px}
h2{font-size:1.15rem;margin-top:1.6em;border-bottom:1px solid #ccc;padding-bottom:3px}
h3{font-size:1rem;margin-top:1.2em}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:.9rem}
th,td{border:1px solid #bbb;padding:5px 8px;text-align:left;vertical-align:top}
th{background:rgba(128,128,128,.15)}
tr:nth-child(even) td{background:rgba(128,128,128,.06)}
em{opacity:.75;font-style:italic}
ul{margin:.4em 0}
.foot{margin-top:24px;font-size:.8rem;opacity:.6}
</style></head><body>
__BODY__
<div class="foot">qbot-web · raport kanoniczny (WIP) · /kanon?route_id=__RID__&start=YYYY-MM-DD+HH:MM</div>
</body></html>"""


@app.get("/kanon", response_class=HTMLResponse)
def kanon_report(route_id: str = Query(...), start: str | None = Query(None)):
    for _k, _v in _env().items():
        os.environ.setdefault(_k, _v)
    try:
        from qbot3.routes.route_report_canonical import build_canonical_report_v1
        md = build_canonical_report_v1(route_id, start=start, fmt="html")
    except Exception as exc:  # noqa: BLE001
        md = f"# Blad\n\nNie udalo sie zbudowac raportu dla {route_id}: {exc}"
    body = _kanon_md_to_html(md)
    page = _KANON_PAGE.replace("__BODY__", body).replace("__RID__", str(route_id))
    return HTMLResponse(page)


# ---------------------------------------------------------------------------
# Generator danych raportu trasy (raport-v2). Jedno zrodlo prawdy dla DATA:
# kazda trasa liczona samodzielnie z bazy + silnikow. Front (raport-render.js)
# tylko rysuje to, co tu policzone. Zmiany danych raportu = TYLKO tutaj.
# ---------------------------------------------------------------------------
def _report_sev(c):
    c = int(c or 0)
    if c >= 95: return 6
    if c in (80, 81, 82) or 61 <= c <= 67: return 5
    if 51 <= c <= 57 or 71 <= c <= 77: return 4
    if c in (45, 48) or c == 3: return 2
    if c in (1, 2): return 1
    return 0


def _report_icon(code, prob):
    c = int(code or 0)
    if c >= 95: return "storm"
    if c in (80, 81, 82) or 61 <= c <= 67 or 51 <= c <= 57: return "rain"
    if 71 <= c <= 77: return "snow"
    if c in (45, 48) or c == 3: return "cloud"
    if c in (1, 2): return "partcloud"
    if c == 0: return "cloud" if (prob or 0) >= 55 else "sun"
_COMPASS8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_SKY_PL = {"sun": "słonecznie", "partcloud": "częściowe zachmurzenie",
           "cloud": "pochmurno", "rain": "deszcz", "storm": "burza",
           "snow": "śnieg", "fog": "mgła"}


def _comfort_cat(feels):
    if feels is None:
        return None
    if feels < 6:
        return "zimno"
    if feels < 13:
        return "chłodno"
    if feels < 26:
        return "komfort"
    return "gorąco"


def _absorb_short_surface(runs, min_km=0.3):
    """Wchlania krotkie (<min_km) odcinki nawierzchni w sasiada najblizszego
    KATEGORIA (remis -> dluzszy). Kategoria 5 (ryzyko/niepewne) nietykalna:
    nigdy nie wchlaniana i nigdy nie wchlania (sciana). Powtarza az nie ma
    wchlanialnego odcinka. Krok wizualny - te same dane co wykres i mapa."""
    runs = [dict(r) for r in runs]

    def length(r):
        return r["km_to"] - r["km_from"]

    def absorbable(r):
        c = r.get("category")
        return c is not None and c != 5 and length(r) < min_km

    guard = 0
    while True:
        guard += 1
        if guard > 10000:
            break
        idxs = sorted([i for i in range(len(runs)) if absorbable(runs[i])],
                      key=lambda i: length(runs[i]))
        if not idxs:
            break
        merged = False
        for i in idxs:
            cand = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(runs):
                    cj = runs[j].get("category")
                    if cj is not None and cj != 5:
                        cand.append(j)
            if not cand:
                continue
            ci = runs[i]["category"]
            best = min(cand, key=lambda j: (abs(runs[j]["category"] - ci), -length(runs[j])))
            b = runs[best]
            b["km_from"] = min(b["km_from"], runs[i]["km_from"])
            b["km_to"] = max(b["km_to"], runs[i]["km_to"])
            del runs[i]
            merged = True
            break
        if not merged:
            break
    out = []
    for r in runs:
        if out and out[-1].get("category") == r.get("category"):
            out[-1]["km_to"] = max(out[-1]["km_to"], r["km_to"])
            out[-1]["km_from"] = min(out[-1]["km_from"], r["km_from"])
        else:
            out.append(dict(r))
    return out


def _build_weather_head(weather, per):
    """Chip pogodowy do naglowka: ikona nieba, srednia odczuwalna + komfort,
    opady, wiatr bezwzgledny (kierunek 8-punktowy + m/s z METEO)."""
    import math as _m
    feels_vals = [w["feels"] for w in weather if w.get("feels") is not None]
    feels_avg = round(sum(feels_vals) / len(feels_vals), 1) if feels_vals else None
    icons = [w["icon"] for w in weather]
    if "storm" in icons:
        sky_icon = "storm"
    elif icons:
        sky_icon = max(set(icons), key=icons.count)
    else:
        sky_icon = "cloud"
    max_mm = max((w.get("mm") or 0) for w in weather) if weather else 0
    max_prob = max((w.get("rain") or 0) for w in weather) if weather else 0
    if "storm" in icons:
        precip_pl = "burza"
    elif max_mm >= 0.5:
        precip_pl = "deszcz"
    elif max_prob >= 40:
        precip_pl = "możliwy deszcz"
    else:
        precip_pl = "bez opadów"
    dirs = [(pp.get("wind_dir_deg"), pp.get("wind_speed_ms")) for pp in per
            if pp.get("wind_dir_deg") is not None and pp.get("wind_speed_ms") is not None]
    wind_dir = wind_ms = None
    if dirs:
        sx = sum(_m.sin(_m.radians(d)) * sp for d, sp in dirs)
        sy = sum(_m.cos(_m.radians(d)) * sp for d, sp in dirs)
        ang = (_m.degrees(_m.atan2(sx, sy)) + 360) % 360
        wind_dir = _COMPASS8[int((ang + 22.5) // 45) % 8]
        wind_ms = round(sum(sp for _, sp in dirs) / len(dirs), 1)
    return {"icon": sky_icon, "sky_pl": _SKY_PL.get(sky_icon, sky_icon),
            "feels": feels_avg, "comfort": _comfort_cat(feels_avg),
            "precip_pl": precip_pl, "wind_dir": wind_dir, "wind_ms": wind_ms}


def _sky_bucket(code):
    if code is None:
        return None
    try:
        c = int(code)
    except (TypeError, ValueError):
        return None
    if c == 0:
        return "bezchmurnie"
    if c in (1, 2):
        return "czesciowe zachmurzenie"
    if c == 3:
        return "pochmurno"
    if c in (45, 48):
        return "mgla"
    if c in (51, 53, 55, 56, 57):
        return "mzawka"
    if c in (61, 63, 65, 66, 67, 80, 81, 82):
        return "deszcz"
    if c in (71, 73, 75, 77, 85, 86):
        return "snieg"
    if c in (95, 96, 99):
        return "burze"
    return "zmiennie"


def _weather_agg(segs):
    if not segs:
        return {}
    wb = [s["wbgt_eff"] for s in segs if s.get("wbgt_eff") is not None]
    fe = [s["feels"] for s in segs if s.get("feels") is not None]
    wsp = [s["wind_speed_ms"] for s in segs if s.get("wind_speed_ms") is not None]
    tails = [s["wind_tail_ms"] for s in segs if s.get("wind_tail_ms") is not None]
    probs = [s["opad_prob"] for s in segs if s.get("opad_prob") is not None]
    mm = [s["opad_mm"] for s in segs if s.get("opad_mm") is not None]
    sky = {}
    for s in segs:
        b = _sky_bucket(s.get("burza_kod"))
        if b:
            sky[b] = sky.get(b, 0) + 1
    dom = max(sky, key=sky.get) if sky else None
    avg_tail = (sum(tails) / len(tails)) if tails else None
    if avg_tail is None:
        tail_txt = None
    elif avg_tail <= -1.0:
        tail_txt = "przewaga wiatru czolowego"
    elif avg_tail >= 1.0:
        tail_txt = "przewaga wiatru z plecow"
    else:
        tail_txt = "wiatr zmienny/boczny"
    return {
        "wbgt_min": round(min(wb), 1) if wb else None, "wbgt_max": round(max(wb), 1) if wb else None,
        "odczuwalna_min": round(min(fe)) if fe else None, "odczuwalna_max": round(max(fe)) if fe else None,
        "wiatr_ms_min": round(min(wsp), 1) if wsp else None, "wiatr_ms_max": round(max(wsp), 1) if wsp else None,
        "wiatr_kierunek": tail_txt, "opad_prob_max": (max(probs) if probs else None),
        "opad_mm_max": round(max(mm), 1) if mm else None,
        "niebo_dominuje": dom, "niebo_rozklad": sky,
    }


def _weather_stages(per_segment, km_total):
    if not per_segment or not km_total:
        return []
    n = 4 if km_total > 80 else 3
    bounds = [km_total * i / n for i in range(n + 1)]
    stages = []
    for i in range(n):
        k0, k1 = bounds[i], bounds[i + 1]
        if i < n - 1:
            segs = [s for s in per_segment if s.get("km") is not None and k0 <= s["km"] < k1]
        else:
            segs = [s for s in per_segment if s.get("km") is not None and s["km"] >= k0]
        agg = _weather_agg(segs)
        agg["naglowek"] = "%d\u2013%d%% (km %d\u2013%d)" % (round(100 * i / n), round(100 * (i + 1) / n), round(k0), round(k1))
        stages.append(agg)
    return stages


def _load_gear_catalog():
    """Szafa z garage.db (gear, active=1) pogrupowana kategoriami -> {kat:[{nazwa,opis}]}.
    'opis' = notes (zakres temp / ocena ★ / tagi GLOWNA/ULUBIONY/WYCOFANE) do rankingu.
    Do LLM (dobor ubioru): Albert wybiera WYLACZNIE z tej listy (pole 'nazwa'). Cap 10/kat."""
    import sqlite3
    cat = {}
    try:
        c = sqlite3.connect("/opt/qbot/app/data/garage.db")
        _skip = {"helmet", "shoes"}
        for row in c.execute("SELECT category, brand, model, notes FROM gear WHERE active=1 ORDER BY category"):
            k = (row[0] or "inne").strip()
            if k.lower() in _skip:
                continue
            nm = ((row[1] or "") + " " + (row[2] or "")).strip()
            if not nm:
                continue
            cat.setdefault(k, [])
            if len(cat[k]) < 10 and not any(e.get("nazwa") == nm for e in cat[k]):
                cat[k].append({"nazwa": nm, "opis": (row[3] or "").strip()[:200]})
        c.close()
    except Exception:
        return {}
    return cat


def _load_outfit_rules():
    """Reguly kompletow/priorytetow ubioru z garage.db (tabela memories): pary
    koszulka+spodenki, warstwy, styl. Pomija tematy trip-specific. Do LLM przy doborze ubioru."""
    import sqlite3
    _KEYS = ("outfit", "komplet", "kombinacj", "gobik", "styl", "mood",
             "warstw", "layer", "docieplacz", "spodenk")
    out = []
    try:
        c = sqlite3.connect("/opt/qbot/app/data/garage.db")
        for topic, content in c.execute("SELECT topic, content FROM memories ORDER BY id"):
            t = (topic or "").lower()
            if ("toskania" in t) or ("tuscany" in t):
                continue
            if any(kk in t for kk in _KEYS):
                out.append({"temat": topic, "tresc": (content or "").strip()[:700]})
        c.close()
    except Exception:
        return []
    return out[:8]


def _report_prose(*, date_str, start_time, finish, dist_km, ascent_m, moving_h, total_h,
                  peak, weather_overall, weather_stages, risks,
                  forma, climbs, surface_blocks, fuel, resupply, gear, alerty,
                  opony_opcje, nawierzchnia_udzial, opady_historia=None, outfit_rules=None):
    """Albert (LLM) - proza/rekomendacje. Liczby tylko z danych. DWA wywolania:
    (1) pogoda+ryzyka, (2) plan (strategia+ubior+opony) - kazde z wlasnym budzetem,
    bo gpt-5* liczy reasoning w max_completion_tokens i jeden wielki kontrakt sie nie miesci.
    Zwraca (pogoda_ogolne[2], pogoda_etapy[N], komentarze_ryzyka[], strategia{}, ubior{}, sprzet_opony{})."""
    from qgpt_client import qgpt_json
    _WIATR = "Wiatr ZAWSZE w m/s. Bez markdown, bez emoji, bez naglowkow. Nie wymyslaj liczb - tylko z danych."
    _trasa = {"data": date_str, "start": start_time, "koniec": finish, "dystans_km": dist_km,
              "przewyzszenie_m": ascent_m, "czas_ruchu_h": moving_h, "czas_calk_h": total_h}
    _legenda = {"1": "twarda/asfalt szybko", "2": "dobry gravel/szuter",
                "3": "zwykly gravel/grunt", "4": "trudna/wolna", "5": "ryzyko/piach"}

    # ---- (1) POGODA + RYZYKA ----
    og = et = rc = None
    sys1 = (
        "Jestes Albert - asystent kolarski QBot. Zwracasz WYLACZNIE JSON o kluczach: "
        "pogoda_ogolne, pogoda_etapy, komentarze_ryzyka. " + _WIATR + "\n"
        "pogoda_ogolne: DOKLADNIE 2 stringi. 1 = zachmurzenie/naslonecznienie (+ deszcz). "
        "2 = temperatura (odczuwalna + WBGT) i wiatr (zakres m/s, czolowy/z plecow). Po 1 zdaniu.\n"
        "pogoda_etapy: po JEDNYM stringu na kazdy etap z weather_stages, TA SAMA KOLEJNOSC, 1-2 zdania.\n"
        "komentarze_ryzyka: po JEDNYM stringu do KAZDEGO odcinka z odcinki_ryzyka (ta sama kolejnosc). "
        "Kazdy odcinek ma pole osm (tagi: highway/tracktype/surface/coverage_status) ORAZ pole reason "
        "(uzasadnienie kategorii - dla odcinkow bez tagu OSM moze zawierac wnioskowanie z otoczenia: "
        "las/pole/otwarta przestrzen, ryzyko piachu wg WorldCover). WYWNIOSKUJ z WSZYSTKICH dostepnych "
        "sygnalow naraz (nie tylko tagow) co to realnie oznacza dla jazdy - np. otwarty teren + susza + "
        "piaszczysty kontekst sugeruje sypki piach, las + wilgoc sugeruje twardsze, korzenie/blotniste "
        "miejsca. Pisz naturalnym zdaniem wniosek + krotka rade, NIE wyliczaj mechanicznie zrodel "
        "(nie pisz \"wg tagu\" / \"wg WorldCover\"). Jesli sygnalow brak lub sa niejednoznaczne, badz "
        "ostrozny w sformulowaniu. DODATKOWO: jesli w danych jest pole opady_przed_jazda "
        "(ocena: susza/mokro/normalnie, total_mm, last2_mm, stale), wywnioskuj jego wplyw na TE "
        "KONKRETNE odcinki - susza zwykle oznacza bardziej sypki/luzny piach na piaszczystych/"
        "otwartych odcinkach, niedawne intensywne opady (mokro) zwykle oznaczaja rozmokly grunt/"
        "blotniste koleiny na gruntowych/lesnych odcinkach; brak wplywu na nawierzchnie utwardzona. "
        "Jesli stale=true, zaznacz ze to stan na dzis i moze sie zmienic do wyjazdu. Jesli "
        "opady_przed_jazda jest null lub ocena=normalnie, pomin ten watek. Brak odcinkow -> []."
    )
    pay1 = {"trasa": _trasa, "peak_wbgt": peak, "pogoda_ogolem": weather_overall,
            "weather_stages": weather_stages, "odcinki_ryzyka": risks,
            "opady_przed_jazda": opady_historia}
    try:
        o1 = qgpt_json(json.dumps(pay1, ensure_ascii=False, default=str),
                       system=sys1, max_tokens=1600, temperature=0.3)
        if isinstance(o1, dict):
            _o = o1.get("pogoda_ogolne"); og = [str(x).strip() for x in _o if str(x).strip()] if isinstance(_o, list) else []
            _e = o1.get("pogoda_etapy"); et = [str(x).strip() for x in _e] if isinstance(_e, list) else []
            _r = o1.get("komentarze_ryzyka"); rc = [str(x).strip() for x in _r] if isinstance(_r, list) else []
    except Exception:
        pass
    og = og or []; et = et or []; rc = rc or []

    # ---- (2) PLAN: strategia + ubior + opony ----
    strategia = ubior = opony = None
    sys2 = (
        "Jestes Albert - asystent kolarski QBot. Zwracasz WYLACZNIE JSON o kluczach: strategia, ubior, sprzet_opony. "
        + _WIATR + "\n"
        "strategia: OBIEKT {\"calosc\": string, \"etapy\": [{\"tytul\",\"zakres_km\",\"opis\",\"moc\",\"zywienie\",\"pojenie\"}]}. "
        "Podziel trase na 3-6 ETAPOW wg ZMIANY CHARAKTERU (nawierzchnia z surface_blocks/nawierzchnia_udzial wg surface_legenda, "
        "podjazdy z climbs, pogoda, wiatr) - NIE rowno po km; zakres_km z danych (np. '0-25'). "
        "calosc: 2-4 zdania: ogolne tempo w W i %FTP (endurance zwykle ~56-75% FTP; policz z forma.ftp), gdzie oszczedzac, "
        "gdzie mozna docisnac, wiatr, kluczowe podjazdy, ryzyka, dlugosc vs glikogen. "
        "Kazdy etap: opis 1-3 zdania; moc = ZALECANY zakres na ten etap w W ORAZ %FTP (policz z forma.ftp; na trudnych/luznych i "
        "pod wiatr nizej, na twardym z plecow mozna wyzej, ale nie na stale ponad FTP; na podjazdach krotko wyzej); "
        "zywienie = konkret na bazie fuel.carbs_g_h; pojenie = na bazie fuel.fluid_l_h i pogody (gdzie dolac wg resupply).\n"
        "sprzet_opony: OBIEKT {\"wheelset\",\"tire\",\"uzasadnienie\"}. Wybierz DOKLADNIE JEDNA opcje z opony_opcje (skopiuj wheelset i tire). "
        "WAZENIE: G-One Pro RS jest wyraznie szybszy i gladszy na asfalcie i twardym gravelu; Thunder Burt oplaca sie DOPIERO gdy DUZO "
        "luznego/piachu/technicznego. Patrz nawierzchnia_udzial: jesli twarda+dobry gravel (k1+k2) dominuja, wybierz szybsza (G-One) "
        "mimo pojedynczych luznych fragmentow; Thunder tylko gdy luzne/ryzyko (k4+k5) znaczace (>=35-40%). uzasadnienie: 1-2 zdania z %.\n"
        "ubior: OBIEKT {\"opis\": string, \"zestawy\": [{\"nazwa\": string, \"rzeczy\": [{\"typ\",\"przyklad\",\"tryb\",\"uwaga\"}]}]}. "
        "Podaj CO NAJMNIEJ 2 kompletne, osobne zestawy (np. 'Lzejszy/szybszy' i 'Cieplejszy/na zapas', albo 'na sucho' i 'na deszcz') - kazdy zestaw to pelny outfit. "
        "Dobierz do TEJ pogody (odczuwalna min/max, WBGT, wiatr, deszcz) - NIE przesadzaj z warstwami: przy cieple (odczuwalna >=18 C) NIE proponuj zimowych/grubych/thermal/merino-winter rzeczy; lekkie i przewiewne. "
        "RANKING: kazda rzecz w gear ma pole 'opis' (zakres temp, ocena gwiazdkowa ★, tagi). Przy rownorzednych wybieraj WYZEJ OCENIONE oraz oznaczone GLOWNA/ULUBIONY; NIE proponuj oznaczonych WYCOFANE / 'za mala' / 'WISI W SZAFIE'; szanuj zakres temp z opisu. "
        "KOMPLETY: jesli reguly_outfitu wskazuja pary (dana koszulka -> konkretne spodenki/warstwy), trzymaj sie ich. "
        "SPOJNOSC MARKI (WSKAZOWKA, nie twarda regula - logika doboru i pogoda moga ja nadpisac): w miare mozliwosci trzymaj zestaw w jednej marce - do koszulki PEdALED dobieraj spodenki PEdALED, do koszulki Albion - spodenki Albion. Wyjatek: gdy koszulka to Rapha Explore (LS lub SS) i w garderobie nie ma ulubionych spodenek Rapha, uzyj spodenek PEdALED albo Albion. "
        "Kazda pozycja: typ = OGOLNY rodzaj (np. 'przewiewna koszulka','spodenki z wkladka','wiatrowka'); przyklad = pole 'nazwa' z listy gear (dokladnie, BEZ opisu); tryb = 'na sobie' albo 'zabierz'; uwaga = 1 krotkie zdanie. "
        "W KAZDYM zestawie OBOWIAZKOWO: koszulka/jersey ORAZ spodenki z wkladka (kategoria 'Bottoms / Bibs'). NIE proponuj kasku ani butow. 4-7 pozycji na zestaw. przyklad WYLACZNIE z listy gear."
    )
    _pog_skrot = {"peak_wbgt": peak, "pogoda_ogolem": weather_overall, "alerty": alerty}
    pay2 = {"trasa": _trasa, "forma": forma, "climbs": climbs, "surface_blocks": surface_blocks,
            "nawierzchnia_udzial": nawierzchnia_udzial, "surface_legenda": _legenda,
            "fuel": fuel, "resupply": resupply, "gear": gear, "opony_opcje": opony_opcje,
            "reguly_outfitu": outfit_rules, "pogoda": _pog_skrot}
    try:
        o2 = qgpt_json(json.dumps(pay2, ensure_ascii=False, default=str),
                       system=sys2, max_tokens=5000, temperature=0.3)
        if isinstance(o2, dict):
            strategia = o2.get("strategia") if isinstance(o2.get("strategia"), dict) else None
            ubior = o2.get("ubior") if isinstance(o2.get("ubior"), dict) else None
            opony = o2.get("sprzet_opony") if isinstance(o2.get("sprzet_opony"), dict) else None
    except Exception:
        pass

    return og, et, rc, strategia, ubior, opony


def _load_poi_groups(conn, rbid):
    """POI z route_poi_layer (status=active) pogrupowane kategoria; kazdy z lat/lon/hours/meta."""
    _prows = conn.execute(
        "SELECT name, category, km_on_route, distance_from_route_m, opening_hours, lat, lon, poi_meta_json "
        "FROM qbot_v2.route_poi_layer WHERE route_base_id=%s AND status='active' "
        "ORDER BY category, km_on_route", (rbid,)).fetchall()
    _pg = {}
    for r in _prows:
        _pg.setdefault(r["category"], []).append(
            {"name": r["name"], "km": round(r["km_on_route"] or 0, 1),
             "dist_m": (round(r["distance_from_route_m"]) if r["distance_from_route_m"] is not None else None),
             "hours": r["opening_hours"], "lat": r["lat"], "lon": r["lon"],
             "meta": r["poi_meta_json"] or {}})

    return _pg


def _curate_pois(_pg, dist_km, date_str):
    """Kuracja POI raportu: zaopatrzenie Q1/Q2/Q3 (sklep+jedzenie, bez zamknietych,
    <=1 km od trasy, +-10 km od srodka) + atrakcje z bramka jakosci. JEDNO zrodlo
    prawdy dla raportu i eksportu GPX (Karoo). Wybory/atrakcje niosa lat/lon."""
    # miejscowosc = najblizszy POI 'town' (haversine)
    _towns = _pg.get("town", [])
    def _locality(lat, lon):
        if lat is None or lon is None or not _towns:
            return None
        best = None
        bd = 1e18
        for t in _towns:
            if t.get("lat") is None:
                continue
            dla = math.radians(t["lat"] - lat)
            dlo = math.radians(t["lon"] - lon)
            a = math.sin(dla / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(t["lat"])) * math.sin(dlo / 2) ** 2
            d = 6371000 * 2 * math.asin(min(1.0, math.sqrt(a)))
            if d < bd:
                bd = d
                best = t["name"]
        return best

    # status godzin w dniu przejazdu: 'open' / 'closed' / 'unknown' + tekst PL 24h
    import re as _re
    _DNI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    _DNI_FULL_PL = ["poniedzia\u0142ek", "wtorek", "\u015broda", "czwartek", "pi\u0105tek", "sobota", "niedziela"]
    _DNI_PL = ["pon", "wt", "\u015br", "czw", "pt", "sob", "ndz"]
    try:
        from datetime import date as _date
        _wd = _date.fromisoformat(date_str).weekday()
    except Exception:
        _wd = None
    def _hours_status(txt):
        if not txt or _wd is None:
            return ("unknown", "godz. nieznane")
        toks = (_DNI_FULL_PL[_wd], _DNI[_wd])
        val = None
        for part in txt.split(";"):
            part = part.strip()
            for tok in toks:
                if part.lower().startswith(tok.lower() + ":"):
                    val = part.split(":", 1)[1].strip()
                    break
            if val is not None:
                break
        if val is None:
            return ("unknown", "godz. nieznane")
        v = val.replace("\u202f", " ").replace("\u2009", "").replace("\u2013", "-").replace("\u2014", "-")
        vl = v.lower()
        if "closed" in vl or "zamk" in vl or "nieczynne" in vl:
            return ("closed", _DNI_PL[_wd] + " nieczynne")
        if "24 hour" in vl or "24 godz" in vl or "ca\u0142\u0105 dob" in vl or "ca\u0142odob" in vl or "czynne ca\u0142" in vl:
            return ("open", _DNI_PL[_wd] + " 24 h")
        def _to24(mm):
            h = int(mm.group(1)); mi = mm.group(2); ap = mm.group(3).upper()
            if ap == "PM" and h != 12:
                h += 12
            if ap == "AM" and h == 12:
                h = 0
            return "%d:%s" % (h, mi)
        v = _re.sub(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])", _to24, v).replace(" - ", "-").replace("  ", " ").strip()
        return ("open", _DNI_PL[_wd] + " " + v)

    # --- ZAOPATRZENIE + JEDZENIE wokol Q1/Q2/Q3: bez zamknietych, otwarte przed nieznanymi, sklep+jedzenie ---
    _sup_pool = []
    for _cat in ("hard_resupply", "soft_food_stop"):
        for it in _pg.get(_cat, []):
            if it.get("dist_m") is None:
                continue
            st, hh = _hours_status(it.get("hours"))
            if st == "closed":
                continue
            _sup_pool.append(dict(it, cat=_cat, ostatus=st, hours_txt=hh))

    # niezawodny mechanizm: trasa dzielona na 3 ciagle odcinki (tercje) pokrywajace
    # 0..dystans BEZ martwych stref; w kazdym odcinku <=1 km od trasy, bez zamknietych;
    # im blizej srodka kwartalu tym lepiej; przy remisie otwarte przed nieznanym;
    # zawsze raportujemy przesuniecie od srodka kwartalu.
    OFFROUTE_MAX_M = 1000.0

    def _mk_pick(it, center_km):
        return {"km": it["km"], "name": it["name"], "cat": it["cat"], "dist_m": it["dist_m"],
                "miejscowosc": _locality(it.get("lat"), it.get("lon")),
                "hours": it.get("hours_txt"), "open_status": it.get("ostatus"),
                "off_center_km": round(it["km"] - center_km, 1),
                "lat": it.get("lat"), "lon": it.get("lon")}

    def _best_of(cands, cat, center_km):
        pool = [it for it in cands if it["cat"] == cat]
        if not pool:
            return None
        # otwarty z potwierdzonymi godzinami wygrywa w calym oknie +-10 km;
        # dopiero potem bliskosc srodka (offset jest wzdluz trasy, nie objazd)
        pool.sort(key=lambda z: (0 if z["ostatus"] == "open" else 1,
                                 abs(z["km"] - center_km), z["dist_m"]))
        return pool[0]

    def _curate_area(lo_km, hi_km, center_km):
        win = [it for it in _sup_pool
               if lo_km <= it["km"] <= hi_km and (it["dist_m"] or 1e9) <= OFFROUTE_MAX_M]
        shop = _best_of(win, "hard_resupply", center_km)
        food = _best_of(win, "soft_food_stop", center_km)
        picks = [p for p in (shop, food) if p]
        picks.sort(key=lambda z: z["km"])
        return len(win), picks

    _resupply_out = []
    _used = set()
    _third = dist_km / 3.0
    for qlab, qkm, _lo, _hi in [("Q1", dist_km * 0.25, 0.0, _third),
                                ("Q2", dist_km * 0.5, _third, 2.0 * _third),
                                ("Q3", dist_km * 0.75, 2.0 * _third, dist_km)]:
        total, picks = _curate_area(_lo, _hi, qkm)
        picks = [p for p in picks if (p["name"], p["km"]) not in _used]
        for p in picks:
            _used.add((p["name"], p["km"]))
        _resupply_out.append({"area": qlab, "q_km": round(qkm, 1), "total": total,
                              "search_km": round(_hi - _lo, 1),
                              "picks": [_mk_pick(p, qkm) for p in picks]})

    # --- ATRAKCJE: bramka jakosci (oceny Google), bez drobnych obiektow kultu i smieci ---
    _JUNK = ("pomnik przyrody", "wiata", "przystanek sztuki", "d\u0105b", "g\u0142az", "aleja lip",
             "aleja pomolog", "kasztanow", "mogi\u0142", "gr\u00f3b", "grob", "miejsce pami\u0119ci",
             "ruiny", "ko\u0142o \u0142owieck", "turbin", "rancho", "wie\u017ca wodna")
    _REL = ("ko\u015bci", "kaplic", "krzy\u017c", "figur", "parafia", "sanktu", "dzwonnic", "cerkiew", "ko\u015bciel")
    _VENUE = ("hotel", "restau", "sklep", "noclegi", "pensjonat", "przeznaczony do organ", "bar ")
    def _att_keep(name, typ, rat, n):
        nm = (name or "").lower()
        tp = (typ or "").lower()
        if any(j in nm for j in _JUNK):
            return False
        if any(vv in tp for vv in _VENUE):
            return False
        if rat is None or n is None:
            return False
        is_rel = ("ko\u015bci" in tp) or any(r in nm for r in _REL)
        if is_rel:
            return (rat >= 4.5 and n >= 200)   # tylko WYBITNY zabytek sakralny
        return (rat >= 4.3 and n >= 30)

    def _att_desc(meta):
        typ = meta.get("g_type_pl")
        rat = meta.get("g_rating")
        n = meta.get("g_rating_n")
        summ = meta.get("g_summary")
        bits = []
        if typ:
            bits.append(str(typ))
        if rat:
            bits.append("\u2605%s%s" % (rat, (" (%d)" % n if n else "")))
        base = " \u00b7 ".join(bits) if bits else None
        if summ:
            return (base + " \u2014 " + summ) if base else summ
        return base

    _att_cand = []
    for it in _pg.get("attraction", []):
        if it["dist_m"] is None or it["dist_m"] > 800:
            continue
        meta = it.get("meta") or {}
        rat = meta.get("g_rating")
        n = meta.get("g_rating_n")
        if not _att_keep(it["name"], meta.get("g_type_pl"), rat, n):
            continue
        _att_cand.append((it, (rat or 0) * (n or 0)))
    _att_cand.sort(key=lambda z: z[1], reverse=True)
    _att_out = [{"km": it["km"], "name": it["name"], "miejscowosc": _locality(it.get("lat"), it.get("lon")),
                 "dist_m": it["dist_m"], "lat": it.get("lat"), "lon": it.get("lon"), "desc": _att_desc(it.get("meta") or {})}
                for it, _s in _att_cand[:8]]

    poi_out = {"resupply": _resupply_out, "attractions": {"total": len(_att_cand), "raw_total": len(_pg.get("attraction", [])), "items": _att_out}}
    return poi_out


def _karoo_type(cat, name=None, desc=None):
    """Mapuje kategorie POI QBota na jeden z 8 typow POI Karoo (Hammerhead).
    Karoo importuje <wpt> jako POI tylko gdy <type> i <sym> sa identyczne i naleza
    do: Food, Parking, Camping, Lodging, Geocache, Summit, Generic, Danger."""
    if cat in ("hard_resupply", "soft_food_stop", "water"):
        return "Food"
    if cat == "attraction":
        t = ((name or "") + " " + (desc or "")).lower()
        if any(w in t for w in ("widok", "panoram", "szczyt", "wie\u017ca widok", "taras widok", "punkt widok")):
            return "Summit"
        return "Generic"
    return "Generic"


def _build_karoo_gpx(name, coords, poi_out, include_pois=True):
    """GPX (trk + wpt) zgodny z importem POI Karoo: kazdy <wpt> ma <type> i <sym>
    o tej samej wartosci z 8 dozwolonych typow. Zwraca (gpx_text, liczba_wpt)."""
    from xml.sax.saxutils import escape as _esc
    import datetime as _dt
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="QBot" xmlns="http://www.topografix.com/GPX/1/1">',
           '<metadata><name>%s</name><time>%s</time></metadata>' % (
               _esc(name or "QBot"), _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))]
    wpt_n = 0
    if include_pois and poi_out:
        wpts = []
        for area in poi_out.get("resupply", []):
            for p in area.get("picks", []):
                if p.get("lat") is None or p.get("lon") is None:
                    continue
                bits = [x for x in (p.get("miejscowosc"), p.get("hours"),
                        ("km %.1f" % p["km"] if p.get("km") is not None else None)) if x]
                wpts.append((p["lat"], p["lon"], p.get("name") or "POI",
                             _karoo_type(p.get("cat")), " \u00b7 ".join(bits)))
        for a in (poi_out.get("attractions", {}) or {}).get("items", []):
            if a.get("lat") is None or a.get("lon") is None:
                continue
            bits = [x for x in (a.get("miejscowosc"), a.get("desc"),
                    ("km %.1f" % a["km"] if a.get("km") is not None else None)) if x]
            wpts.append((a["lat"], a["lon"], a.get("name") or "POI",
                         _karoo_type("attraction", a.get("name"), a.get("desc")), " \u00b7 ".join(bits)))
        for lat, lon, nm, kt, dsc in wpts:
            out.append('<wpt lat="%.6f" lon="%.6f">' % (float(lat), float(lon)))
            out.append("<name>%s</name>" % _esc(nm))
            if dsc:
                out.append("<desc>%s</desc>" % _esc(dsc))
            out.append("<type>%s</type>" % kt)
            out.append("<sym>%s</sym>" % kt)
            out.append("</wpt>")
            wpt_n += 1
    out.append("<trk><name>%s</name><trkseg>" % _esc(name or "QBot"))
    for c in coords:
        out.append('<trkpt lat="%.6f" lon="%.6f"></trkpt>' % (float(c[0]), float(c[1])))
    out.append("</trkseg></trk>")
    out.append("</gpx>")
    return "\n".join(out), wpt_n


@app.get("/api/report/gpx")
def report_gpx(route_id: str, date: str | None = None, time: str = "10:00", pois: int = 1):
    """Pobranie GPX trasy. pois=1 -> trk + wpt (POI dla Karoo: type+sym z 8 typow);
    pois=0 -> sama trasa. Zrodlo POI = _curate_pois (to samo co raport)."""
    inc = bool(int(pois))
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT rb.route_base_id, rb.distance_m, a.metadata_json->>'route_name' AS name "
            "FROM qbot_v2.route_base rb LEFT JOIN qbot_v2.route_artifacts a ON a.id=rb.route_artifact_id "
            "WHERE rb.route_id=%s ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1", (route_id,)).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        rbid = base["route_base_id"]
        dist_km = round((base["distance_m"] or 0) / 1000.0, 1)
        name = base["name"] or ("Trasa %s" % route_id)
        geo = route_geometry(route_id)
        coords = geo.get("coordinates") or []
        poi_out = _curate_pois(_load_poi_groups(conn, rbid), dist_km, date) if inc else None
    finally:
        conn.close()
    if not coords:
        raise HTTPException(status_code=422, detail="Brak geometrii trasy")
    gpx, _wn = _build_karoo_gpx(name, coords, poi_out, include_pois=inc)
    import re as _re2
    safe = _re2.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or ("route_%s" % route_id)
    fname = "%s%s.gpx" % (safe, ("_POI" if inc else ""))
    return Response(content=gpx, media_type="application/gpx+xml",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % fname})


def _poly_encode(coords, prec=5):
    """Google encoded polyline (precyzja 5) - format wymagany przez Hammerhead."""
    f = 10 ** prec
    out = []
    pl = po = 0
    def e(v):
        v = (v << 1) if v >= 0 else ~(v << 1)
        s = ""
        while v >= 0x20:
            s += chr((0x20 | (v & 0x1f)) + 63); v >>= 5
        return s + chr(v + 63)
    for la, lo in coords:
        ila = int(round(la * f)); ilo = int(round(lo * f))
        out.append(e(ila - pl)); out.append(e(ilo - po)); pl, po = ila, ilo
    return "".join(out)


def _karoo_poi_api(poi_out):
    """pointsOfInterest dla API Hammerhead: {type,name,description,location} - type
    MALYMI literami z 8 typow Karoo. Zrodlo = ta sama kuracja co raport/GPX."""
    items = []
    for area in (poi_out or {}).get("resupply", []):
        for p in area.get("picks", []):
            if p.get("lat") is None or p.get("lon") is None:
                continue
            desc = " \u00b7 ".join([x for x in (p.get("miejscowosc"), p.get("hours"),
                    ("km %.1f" % p["km"] if p.get("km") is not None else None)) if x])
            items.append({"type": _karoo_type(p.get("cat")).lower(), "name": p.get("name") or "POI",
                          "description": desc, "location": {"lat": float(p["lat"]), "lng": float(p["lon"])}})
    for a in ((poi_out or {}).get("attractions", {}) or {}).get("items", []):
        if a.get("lat") is None or a.get("lon") is None:
            continue
        desc = " \u00b7 ".join([x for x in (a.get("miejscowosc"), a.get("desc"),
                ("km %.1f" % a["km"] if a.get("km") is not None else None)) if x])
        items.append({"type": _karoo_type("attraction", a.get("name"), a.get("desc")).lower(),
                      "name": a.get("name") or "POI", "description": desc,
                      "location": {"lat": float(a["lat"]), "lng": float(a["lon"])}})
    return items


def _poly_encode_1d(vals, factor=100000):
    out = []
    prev = 0
    for v in vals:
        cur = int(round(v * factor))
        d = cur - prev
        prev = cur
        d = ~(d << 1) if d < 0 else (d << 1)
        while d >= 0x20:
            out.append(chr((0x20 | (d & 0x1f)) + 63))
            d >>= 5
        out.append(chr(d + 63))
    return "".join(out)


@app.post("/api/report/push-karoo")
def push_karoo(route_id: str, date: str | None = None, time: str = "10:00"):
    """Tworzy trase z POI wprost na koncie Karoo (Hammerhead) - bez RWGPS, bez uploadu.
    POI = _curate_pois (to samo co raport). UWAGA: endpoint publiczny do czasu bramki
    logowania przed albert.cytr.us (TODO)."""
    import glob as _glob, re as _re3, urllib.error
    for _ef in _glob.glob("/etc/qbot/*.env"):
        try:
            for _line in open(_ef):
                if "=" in _line and not _line.startswith("#"):
                    _k, _, _v = _line.strip().partition("="); os.environ.setdefault(_k, _v)
        except Exception:
            pass
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT rb.route_base_id, rb.distance_m, a.metadata_json->>'route_name' AS name "
            "FROM qbot_v2.route_base rb LEFT JOIN qbot_v2.route_artifacts a ON a.id=rb.route_artifact_id "
            "WHERE rb.route_id=%s ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1", (route_id,)).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        rbid = base["route_base_id"]; dist_m = float(base["distance_m"] or 0)
        name = base["name"] or ("Trasa %s" % route_id)
        geo = route_geometry(route_id); coords = geo.get("coordinates") or []
        er = conn.execute("SELECT distance_m, elevation_m FROM qbot_v2.route_elevation_samples "
                          "WHERE route_base_id=%s ORDER BY sample_index", (rbid,)).fetchall()
        poi_out = _curate_pois(_load_poi_groups(conn, rbid), round(dist_m / 1000.0, 1), date)
    finally:
        conn.close()
    if not coords:
        raise HTTPException(status_code=422, detail="Brak geometrii trasy")
    prof = [(float(r["distance_m"]), float(r["elevation_m"])) for r in er if r["elevation_m"] is not None]
    ev = [e for _, e in prof]
    # profil wygladzony oknem ~200 m (dokumentowany sweet-spot QBot dla sum podjazdow)
    def _smooth_prof(pf, win_m=200.0):
        n = len(pf)
        if n < 3:
            return list(pf)
        ds = [p[0] for p in pf]; es = [p[1] for p in pf]
        half = win_m / 2.0; j0 = j1 = 0; out = []
        for i in range(n):
            lo = ds[i] - half; hi = ds[i] + half
            while j0 < n and ds[j0] < lo:
                j0 += 1
            while j1 < n and ds[j1] <= hi:
                j1 += 1
            seg = es[j0:j1] if j1 > j0 else [es[i]]
            out.append((ds[i], sum(seg) / len(seg)))
        return out
    prof_s = _smooth_prof(prof) if prof else []
    # gain/loss = kanoniczne z raportu (ten sam _read_route_source);
    # fallback: suma dodatnich roznic z wygladzonego profilu (NIE z surowego szumu)
    gain = loss = None
    try:
        from qbot_route_report_tool import _read_route_source as _rrs
        _ces = (_rrs(route_id) or {}).get("canonical_elevation_summary") or {}
        if _ces.get("ascent_smoothed_m") is not None:
            gain = round(float(_ces["ascent_smoothed_m"]), 1)
        if _ces.get("descent_smoothed_m") is not None:
            loss = round(float(_ces["descent_smoothed_m"]), 1)
    except Exception:
        pass
    if gain is None or loss is None:
        _es = [e for _, e in prof_s]
        _g = sum(max(0.0, _es[i] - _es[i - 1]) for i in range(1, len(_es)))
        _l = sum(max(0.0, _es[i - 1] - _es[i]) for i in range(1, len(_es)))
        if gain is None:
            gain = round(_g, 1)
        if loss is None:
            loss = round(_l, 1)
    lats = [c[0] for c in coords]; lons = [c[1] for c in coords]
    full = _poly_encode(coords)
    summ = _poly_encode(coords[::max(1, len(coords) // 60)])
    pois_api = _karoo_poi_api(poi_out)
    _parts = [x.strip() for x in _re3.split(r"[\-\u2013\u2014]", name) if x.strip()]
    start_nm = _parts[0] if _parts else (name or "Start")
    end_nm = _parts[-1] if len(_parts) > 1 else start_nm
    _n = len(coords)
    _wps = [{"lat": coords[0][0], "lng": coords[0][1], "waypointType": "BREAK", "polylineIndex": 0}]
    _st = max(1, _n // 25)
    for _i in range(_st, _n - 1, _st):
        _wps.append({"lat": coords[_i][0], "lng": coords[_i][1], "waypointType": "VIA", "polylineIndex": _i})
    _wps.append({"lat": coords[-1][0], "lng": coords[-1][1], "waypointType": "BREAK", "polylineIndex": _n - 1})
    body = {"name": name, "source": "uploaded", "sourceId": "qbot-%s" % route_id,
            "elevation": {"gain": round(gain, 1), "loss": round(loss, 1),
                          "min": round(min(ev), 1) if ev else 0, "max": round(max(ev), 1) if ev else 0,
                          "polyline": _poly_encode_1d(ev),
                          "source": "qbot"},
            "distance": dist_m,
            "startLocation": {"lat": coords[0][0], "lng": coords[0][1]},
            "endLocation": {"lat": coords[-1][0], "lng": coords[-1][1]},
            "startLocationName": start_nm, "endLocationName": end_nm,
            "routePolyline": full, "summaryPolyline": summ,
            "bounds": [{"lat": min(lats), "lng": min(lons)}, {"lat": max(lats), "lng": max(lons)}],
            "waypoints": _wps,
            "pointsOfInterest": pois_api}
    try:
        import hammerhead_auth as _HA
        tok = _HA.HammerheadTokenStore.from_env().access_token()
        hh_uid = _HA.token_user_id(tok)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Karoo auth niedostepne z uslugi: %s" % exc)
    # WARIANT A: jedna kopia QBota na trase - skasuj poprzednia (po sourceId) przed utworzeniem nowej
    _sid = "qbot-%s" % route_id
    try:
        _lreq = urllib.request.Request(
            "https://dashboard.hammerhead.io/v1/users/%s/routes?per_page=200" % hh_uid,
            headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
        with urllib.request.urlopen(_lreq, timeout=30) as _lr:
            _ld = json.loads(_lr.read())
        for _rt in (_ld.get("data") or _ld.get("routes") or []):
            if str(_rt.get("sourceId") or "") == _sid:
                _dreq = urllib.request.Request(
                    "https://dashboard.hammerhead.io/v1/users/%s/routes/%s" % (hh_uid, _rt.get("id")),
                    headers={"Authorization": "Bearer " + tok, "Accept": "application/json"}, method="DELETE")
                try:
                    urllib.request.urlopen(_dreq, timeout=30).read()
                except Exception:
                    pass
    except Exception:
        pass
    req = urllib.request.Request(
        "https://dashboard.hammerhead.io/v1/users/%s/routes" % hh_uid,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as he:
        raise HTTPException(status_code=502, detail="Karoo push HTTP %s: %s" % (he.code, he.read().decode("utf-8", "replace")[:200]))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Karoo push blad: %s" % exc)
    return {"ok": True, "route_id": out.get("id"), "name": name, "poi_count": len(pois_api),
            "url": "https://dashboard.hammerhead.io/"}


def _fetch_precip_history(lat, lon, ride_date_str, days_back=10):
    """Suma opadow z okresu PRZED dniem jazdy (Open-Meteo archive/ERA5 - to samo API co
    juz uzywane w tools/rwgps/ride_verdict.py do analizy zrealizowanych przejazdow).
    Jesli jazda jest zaplanowana w przyszlosci, okno konczy sie 'dzisiaj' (nie da sie
    znac przyszlych opadow) - wtedy stale=True (stan moze sie zmienic do wyjazdu).
    Zwraca None przy braku danych/bledzie sieci - wtedy czynnik jest po prostu pomijany."""
    from datetime import date as _date, timedelta as _td
    try:
        ride_d = _date.fromisoformat(ride_date_str)
    except Exception:
        return None
    today = _date.today()
    end_d = min(ride_d - _td(days=1), today)
    start_d = end_d - _td(days=days_back - 1)
    if start_d > end_d:
        return None
    stale = ride_d > today
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=%.4f&longitude=%.4f"
           "&start_date=%s&end_date=%s&daily=precipitation_sum&timezone=auto") % (
               lat, lon, start_d.isoformat(), end_d.isoformat())
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            j = json.loads(r.read().decode("utf-8"))
        vals = (j.get("daily") or {}).get("precipitation_sum") or []
        vals = [float(v) for v in vals if v is not None]
        if not vals:
            return None
        total = round(sum(vals), 1)
        last2 = round(sum(vals[-2:]), 1) if len(vals) >= 2 else total
        if total < 3:
            ocena = "susza"
        elif last2 > 8 or total > 20:
            ocena = "mokro"
        else:
            ocena = "normalnie"
        return {"total_mm": total, "days": len(vals), "last2_mm": last2,
                "ocena": ocena, "as_of": end_d.isoformat(), "stale": stale}
    except Exception as _e:
        print("_fetch_precip_history error:", _e)
        return None


def _build_report_data(conn, route_id, date_str, start_time, long_stops=0, long_stop_min=0):
    """Buduje pelny blok DATA (route/start/time/chart) dla jednej trasy."""
    base = conn.execute(
        "SELECT rb.route_base_id, rb.distance_m, rb.route_modified_at, "
        "a.metadata_json->>'route_name' AS name "
        "FROM qbot_v2.route_base rb "
        "LEFT JOIN qbot_v2.route_artifacts a ON a.id=rb.route_artifact_id "
        "WHERE rb.route_id=%s "
        "ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1", (route_id,)).fetchone()
    if not base:
        raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
    rbid = base["route_base_id"]
    dist_km = round((base["distance_m"] or 0) / 1000.0, 1)
    name = base["name"] or f"Trasa {route_id}"
    vmod = base.get("route_modified_at")
    version_modified = vmod.strftime("%Y-%m-%d %H:%M") if vmod else None

    # --- profil wysokosci (downsample ~220) ---
    erows = conn.execute(
        "SELECT distance_m, elevation_m FROM qbot_v2.route_elevation_samples "
        "WHERE route_base_id=%s ORDER BY sample_index", (rbid,)).fetchall()
    if not erows:
        raise HTTPException(status_code=422, detail="Brak profilu wysokosci dla tej trasy")
    step = max(1, len(erows) // 220)
    ele = []
    for i in range(0, len(erows), step):
        ele.append([round(erows[i]["distance_m"] / 1000.0, 3), round(erows[i]["elevation_m"], 1)])
    last_km = round(erows[-1]["distance_m"] / 1000.0, 3)
    if ele[-1][0] != last_km:
        ele.append([last_km, round(erows[-1]["elevation_m"], 1)])
    emin = min(p[1] for p in ele)
    emax = max(p[1] for p in ele)
    km_total = round(erows[-1]["distance_m"] / 1000.0, 1)

    # --- nawierzchnia: 5 kategorii (parytet z endpointem) ---
    raw_buckets = _load_surface_buckets(conn, rbid)
    ribbon = _absorb_short_surface(_coalesce_categories(raw_buckets))
    surface_cat = [
        {"a": round(float(r["km_from"]), 2), "b": round(float(r["km_to"]), 2),
         "k": r["category"], "label": r.get("label"), "reason": r.get("reason")}
        for r in ribbon if r.get("category") is not None
    ]

    # --- lokalizacja startu (reverse-geocode + cache) ---
    latlon = None
    try:
        g = route_geometry(route_id)
        if g.get("coordinates"):
            latlon = (g["coordinates"][0][0], g["coordinates"][0][1])
    except Exception:
        pass
    from qbot3.routes import route_report_canonical as _rc
    adm = _rc._admin(conn, route_id, latlon) if latlon else \
        {"miejscowosc": None, "gmina": None, "powiat": None, "wojewodztwo": None}

    # --- przewyzszenie (kanoniczne, z fallbackiem z profilu) ---
    ascent = None
    try:
        from qbot_route_report_tool import _read_route_source
        rs = _read_route_source(route_id) or {}
        ascent = (rs.get("canonical_elevation_summary") or {}).get("ascent_smoothed_m")
    except Exception:
        pass
    if ascent is None:
        asc = 0.0
        for i in range(1, len(ele)):
            d = ele[i][1] - ele[i - 1][1]
            if d > 0:
                asc += d
        ascent = round(asc)
    else:
        ascent = round(float(ascent))

    # --- czas przejazdu (z deklaracja dlugich przerw) ---
    tmoving = ttotal = stops_min = stops_cnt = None
    long_min_val = None
    try:
        from qbot_route_time_tools import estimate_route_time_v2
        tt = estimate_route_time_v2(
            route_id=route_id, mode="normalny",
            planned_long_stops=int(long_stops or 0),
            planned_long_stop_min=float(long_stops or 0) * float(long_stop_min or 0), start_time=start_time)
        if isinstance(tt, dict):
            tmoving = tt.get("moving_h")
            ttotal = tt.get("total_h")
            stp = tt.get("stops") or {}
            stops_min = round((stp.get("mikro_min") or 0) + (stp.get("krotkie_min") or 0), 1)
            stops_cnt = stp.get("krotkie_liczba") or stp.get("liczba")
            dm = stp.get("dlugie_min") or 0
            long_min_val = dm if dm > 0 else None
    except Exception:
        pass

    # --- meteo: pogoda per okno + odczuwalna + wiatr gesty + ETA ---
    from qbot3.routes.route_meteo_engine import run_meteo_engine
    m = run_meteo_engine(route_id=route_id, date_str=date_str, start_time=start_time)
    per = m["per_segment"]
    weather = []
    for w in m["tabela_30min"]:
        a = float(w["km_od"]); b = float(w["km_do"])
        inwin = [pp for pp in per if a <= float(pp["km"]) <= b]
        codes = [pp.get("burza_kod") for pp in inwin if pp.get("burza_kod") is not None]
        code = max(codes, key=_report_sev) if codes else 0
        prob = (w.get("opad", {}) or {}).get("prob")
        tails = [pp.get("wind_tail_ms") for pp in inwin if pp.get("wind_tail_ms") is not None]
        crs = [abs(pp.get("wind_cross_ms")) for pp in inwin if pp.get("wind_cross_ms") is not None]
        fe = [float(pp["feels"]) for pp in inwin if pp.get("feels") is not None]
        weather.append({
            "t": w["okno"], "a": round(a, 2), "b": round(b, 2),
            "wbgt": round(float(w["wbgt_max"]), 1),
            "rain": int(prob) if prob is not None else None,
            "mm": round(float((w.get("opad", {}) or {}).get("mm") or 0), 1),
            "code": int(code), "icon": _report_icon(code, prob),
            "w_along": round(sum(tails) / len(tails), 1) if tails else None,
            "w_cross": round(sum(crs) / len(crs), 1) if crs else None,
            "feels": round(sum(fe) / len(fe), 1) if fe else None,
        })
    eta = [[w["a"], w["t"]] for w in weather]
    perw = [pp for pp in per if pp.get("wind_tail_ms") is not None]
    stepw = max(1, len(perw) // 200)
    wind = []
    for i in range(0, len(perw), stepw):
        pp = perw[i]
        wind.append([round(float(pp["km"]), 2), round(float(pp["wind_tail_ms"]), 1),
                     round(abs(float(pp.get("wind_cross_ms") or 0)), 1)])
    if perw and wind[-1][0] != round(float(perw[-1]["km"]), 2):
        pp = perw[-1]
        wind.append([round(float(pp["km"]), 2), round(float(pp["wind_tail_ms"]), 1),
                     round(abs(float(pp.get("wind_cross_ms") or 0)), 1)])

    weather_head = _build_weather_head(weather, per)

    speed_net_kmh = round(dist_km / tmoving, 1) if (tmoving and dist_km) else None
    speed_gross_kmh = round(dist_km / ttotal, 1) if (ttotal and dist_km) else None

    # --- SZCZEGOLY (multi-menu): nawierzchnia / przewyzszenia / pogoda / POI ---
    _scat_km = {}
    for _s in surface_cat:
        _scat_km[_s["k"]] = _scat_km.get(_s["k"], 0.0) + max(0.0, float(_s["b"]) - float(_s["a"]))
    _tot = sum(_scat_km.values()) or 1.0
    surface_by_cat = [{"k": k, "km": round(_scat_km[k], 1), "pct": round(_scat_km[k] / _tot * 100)}
                      for k in sorted(_scat_km)]
    def _risk_osm(a, b):
        hit = [g for g in raw_buckets if not (g["km_to"] <= a or g["km_from"] >= b)]
        def _uniq(key):
            vals = []
            for g in hit:
                v = g.get(key)
                if v and v not in vals:
                    vals.append(v)
            return vals
        expl = ""
        for g in hit:
            if g.get("explanation"):
                expl = g["explanation"]
                break
        return {"highway": _uniq("highway"), "tracktype": _uniq("tracktype"),
                "surface": (_uniq("surface_raw") or _uniq("surface")),
                "coverage_status": _uniq("coverage_status"), "explanation": expl}
    surface_risk = []
    for _s in surface_cat:
        if _s["k"] not in (4, 5):
            continue
        _len = round(_s["b"] - _s["a"], 2)
        if _len < 0.3:
            continue
        surface_risk.append({"a": _s["a"], "b": _s["b"], "km": _len, "k": _s["k"],
                             "reason": _s.get("reason"), "osm": _risk_osm(_s["a"], _s["b"])})

    # --- czynnik pogodowy dla najgorszych odcinkow (kat.4+5): susza/opady PRZED jazda ---
    # Kategoria nawierzchni NIE jest zmieniana - to tylko dodatkowy kontekst do komentarzy
    # LLM i osobny alert terenowy (decyzja uzytkownika 2026-07-04).
    _risk45_km = sum(x["km"] for x in surface_risk)
    precip_history = None
    if _risk45_km >= 2.0 and latlon:
        precip_history = _fetch_precip_history(latlon[0], latlon[1], date_str, days_back=10)

    _cl = conn.execute(
        "SELECT event_index, start_m, end_m, length_m, elevation_gain_m, avg_gradient_pct, "
        "max_gradient_pct, severity, segments_json FROM qbot_v2.route_climb_events "
        "WHERE route_base_id=%s ORDER BY start_m", (rbid,)).fetchall()
    climbs_list = []
    for r in _cl:
        _sj = r.get("segments_json")
        if isinstance(_sj, str):
            try:
                _sj = json.loads(_sj)
            except Exception:
                _sj = []
        _segs = [{"len_m": round(sg.get("length_m") or 0), "grade": sg.get("gradient_pct"),
                  "cat": sg.get("category")} for sg in (_sj or [])]
        climbs_list.append({"i": (r["event_index"] or 0) + 1,
                            "a_km": round((r["start_m"] or 0) / 1000.0, 1),
                            "b_km": round((r["end_m"] or 0) / 1000.0, 1),
                            "length_m": round(r["length_m"] or 0),
                            "gain_m": round(r["elevation_gain_m"] or 0, 1),
                            "avg_pct": r["avg_gradient_pct"], "max_pct": r["max_gradient_pct"],
                            "severity": r["severity"], "segments": _segs})
    _net = (ele[-1][1] - ele[0][1]) if ele else 0.0
    descent = round(ascent - _net) if (ascent is not None) else None

    weather_windows = []
    for _w in (m.get("tabela_30min") or []):
        weather_windows.append({"okno": _w.get("okno"), "km_od": _w.get("km_od"), "km_do": _w.get("km_do"),
                                "wbgt": _w.get("wbgt_max"), "feels": (_w.get("odczuwalna") or {}).get("srednia"),
                                "opad_mm": (_w.get("opad") or {}).get("mm"), "opad_prob": (_w.get("opad") or {}).get("prob"),
                                "wiatr_ms": _w.get("wiatr_wzdluz_ms"), "alert_level": _w.get("alert_level")})

    _pg = _load_poi_groups(conn, rbid)
    poi_out = _curate_pois(_pg, dist_km, date_str)
    try:
        from qbot3.routes.route_poi_store import get_route_poi_prefs
        poi_out["attractions"]["enabled"] = bool(get_route_poi_prefs(conn, route_id).get("attractions_enabled"))
    except Exception:
        poi_out["attractions"]["enabled"] = None


    # --- SPRZET: udzialy nawierzchni + cisnienia (obie opony) + nawodnienie ---
    _km_by_k = {}
    for _r in surface_by_cat:
        _km_by_k[_r["k"]] = _km_by_k.get(_r["k"], 0.0) + float(_r["km"])
    _tot_k = sum(_km_by_k.values()) or 1.0
    def _pct(*ks):
        return 100.0 * sum(_km_by_k.get(k, 0.0) for k in ks) / _tot_k
    hard_pct = _pct(1)
    loose_pct = _pct(4, 5)
    sand_tag = any((b.get("surface") == "sand") for b in raw_buckets)
    _SCAT_LAB = {1: "twarda/asfalt szybko", 2: "dobry gravel/szuter",
                 3: "zwykly gravel/grunt", 4: "trudna/wolna", 5: "ryzyko/piach"}
    _naw_udzial = [{"k": x["k"], "label": _SCAT_LAB.get(x["k"], x["k"]),
                    "km": x["km"], "pct": x["pct"]} for x in surface_by_cat]
    _press = {}
    _tire_options = []
    try:
        from qbot_pressure_tools import structured_pressure
        _press = structured_pressure()
        _char_thb = "gruby bieznik (knobby), duza przyczepnosc na luznym/piachu, wolniejszy na asfalcie"
        _char_go = "szybki i gladki, najlepszy na asfalcie i twardym gravelu, slabszy na luznym/piachu"
        for w in _press.get("wheelsets", []):
            _tir = (w.get("tire") or "").upper()
            _ch = _char_thb if "THUNDER" in _tir else (_char_go if "G-ONE" in _tir else "")
            _mm = None
            if w.get("front_mm"):
                _mm = str(int(w["front_mm"])) + ("/" + str(int(w["rear_mm"])) if w.get("rear_mm") != w.get("front_mm") else "") + " mm"
            _tire_options.append({"wheelset": w.get("label"), "tire": w.get("tire"),
                                  "szer_mm": _mm, "charakter": _ch})
    except Exception:
        _press = {}
        _tire_options = []
    sprzet = {"tire": None, "pressure": None, "hydration": None, "clothing": None}
    try:
        _peak_wbgt = (m.get("peak") or {}).get("wbgt_eff")
        _dem, _rec = _rc._water_rec(tmoving, _peak_wbgt)
        _sup_km = []
        for _c, _items in _pg.items():
            if _c in ("hard_resupply", "soft_food_stop", "water"):
                for _it in _items:
                    if _it.get("km") is not None:
                        _sup_km.append(float(_it["km"]))
        _gap = _rc._gap_km(_sup_km, dist_km)
        sprzet["hydration"] = {"demand_l": _dem, "gap_km": round(_gap, 1), "rec": _rec}
    except Exception:
        pass

    details = {
        "surface": {"total_km": km_total, "by_cat": surface_by_cat, "risk": surface_risk},
        "climbs": {"ascent_m": ascent, "descent_m": descent, "count": len(climbs_list), "list": climbs_list},
        "weather": {"windows": weather_windows, "peak": m.get("peak"), "caveats": m.get("caveats") or []},
        "poi": poi_out,
        "sprzet": sprzet,
    }

    # --- FORMA (FitModel/ModelQ + glikogen) + paliwo + wsad do LLM ---
    _per = m.get("per_segment") or []
    weather_overall = _weather_agg(_per)
    stages = _weather_stages(_per, km_total)
    _mq = _rc._modelq(conn)
    _fit = _rc._fitmodel(conn)
    mass = float(_fit["weight_kg"]) if (_fit and _fit.get("weight_kg")) else 100.0
    _ftp = _ltp = _wprime = _peakp = _tload = _rload = None
    _fsrc = None
    _snap = None
    if _mq:
        _ftp = _mq.get("ftp_power_w"); _fsrc = "FitModel (ModelQ)"; _snap = str(_mq.get("snapshot_at"))[:10]
        _ltp = _mq.get("ltp_power_w"); _wprime = _mq.get("w_prime_kj"); _peakp = _mq.get("peak_power_w")
        _tload = _mq.get("training_load"); _rload = _mq.get("recovery_load")
    elif _fit:
        _ftp = _fit.get("ftp_est_w"); _fsrc = "FitModel (fitmodel_daily)"
    _glik = None
    _glik_day = None
    try:
        _gr = conn.execute("SELECT day, glycogen_pct FROM qbot_v2.fitmodel_daily "
                           "WHERE glycogen_pct IS NOT NULL AND glycogen_pct > 0 "
                           "ORDER BY day DESC LIMIT 1").fetchone()
        if _gr:
            _glik = round(float(_gr["glycogen_pct"])); _glik_day = str(_gr["day"])
    except Exception:
        pass
    _wkg = round(float(_ftp) / mass, 2) if _ftp else None
    _climbs_for_xss = [{"km_from": c.get("a_km"), "km_to": c.get("b_km"),
                       "avg_gradient_pct": c.get("avg_pct")} for c in climbs_list]
    _ftp_mq, _wprime_mq_kj = _rc._modelq_form_for_xss(conn)
    _xss = _rc._estimate_route_xss(tmoving, dist_km, _climbs_for_xss, _ftp_mq, _wprime_mq_kj, mass, 0.62)
    _climb_w = None
    _steep_pct = None
    _wprime_txt = None
    if climbs_list and _ftp:
        _steep = max(climbs_list, key=lambda e: (e.get("avg_pct") or 0))
        _steep_pct = _steep.get("avg_pct")
        _climb_w = round(_rc._climb_power(float(_steep_pct or 0), 12.0, mass))
        if _climb_w <= float(_ftp):
            _wprime_txt = "pelna rezerwa - najstromszy podjazd ~%d W ponizej FTP" % _climb_w
        else:
            _wprime_txt = "czesciowa - najstromszy ~%d W (o %d W ponad FTP)" % (_climb_w, _climb_w - float(_ftp))
    elif not climbs_list:
        _wprime_txt = "pelna - trasa plaska"
    _fuel = {}
    try:
        from qbot_fuel_tools import carbs_g_per_h, fluid_l_per_h
        _tc = weather_head.get("feels")
        _ch2 = carbs_g_per_h(0.62, (tmoving or 0) * 3600, 1.05, _tc, mass) if tmoving else None
        _fh2 = fluid_l_per_h(0.62, _tc, None, mass) if tmoving else None
        _fuel = {"carbs_g_h": _ch2, "fluid_l_h": _fh2,
                 "carbs_total_g": (round(_ch2 * tmoving) if (_ch2 and tmoving) else None),
                 "fluid_total_l": (round(_fh2 * tmoving, 1) if (_fh2 and tmoving) else None)}
    except Exception:
        _fuel = {}
    forma = {"source": _fsrc, "snapshot": _snap, "ftp": _ftp, "w_kg": _wkg, "mass": round(mass),
             "ltp": _ltp, "w_prime_kj": _wprime, "peak_w": _peakp, "training_load": _tload,
             "recovery_load": _rload, "glikogen_pct": _glik, "glikogen_day": _glik_day,
             "vs_route": {"xss": _xss, "cho_g": _fuel.get("carbs_total_g"), "cho_g_h": _fuel.get("carbs_g_h"),
                          "fluid_l": _fuel.get("fluid_total_l"), "wprime_txt": _wprime_txt,
                          "climb_w": _climb_w, "steep_pct": _steep_pct}}

    _climbs_slim = [{"i": x["i"], "a_km": x["a_km"], "b_km": x["b_km"], "gain_m": x["gain_m"],
                     "avg_pct": x["avg_pct"], "max_pct": x["max_pct"], "severity": x["severity"]}
                    for x in climbs_list]
    _surf_blocks = [{"a": s["a"], "b": s["b"], "k": s["k"], "label": s.get("label")} for s in surface_cat]
    _resupply = []
    for _c, _items in _pg.items():
        if _c in ("hard_resupply", "soft_food_stop", "water"):
            for _it in _items:
                if _it.get("km") is not None:
                    _resupply.append({"km": _it["km"], "name": _it.get("name"), "dist_m": _it.get("dist_m")})
    _resupply.sort(key=lambda z: z["km"])
    _resupply = _resupply[:16]
    _gear = _load_gear_catalog()
    _forma_llm = {"ftp": _ftp, "ltp": _ltp, "w_kg": _wkg, "w_prime_kj": _wprime, "glikogen_pct": _glik,
                  "mass": round(mass), "vs_route": forma["vs_route"]}
    _alerty = sorted({a.get("typ") for a in (m.get("alerts") or []) if a.get("typ")})

    _finish = None
    try:
        from datetime import datetime as _dt, timedelta as _td
        _finish = (_dt.strptime(start_time, "%H:%M") + _td(hours=float(ttotal or 0))).strftime("%H:%M")
    except Exception:
        _finish = None
    _og = _et = _rc2 = None
    _strat = _ubior = _opony = None
    try:
        _og, _et, _rc2, _strat, _ubior, _opony = _report_prose(
            date_str=date_str, start_time=start_time, finish=_finish, dist_km=dist_km,
            ascent_m=ascent, moving_h=tmoving, total_h=ttotal, peak=details["weather"]["peak"],
            weather_overall=weather_overall, weather_stages=stages, risks=surface_risk,
            forma=_forma_llm, climbs=_climbs_slim, surface_blocks=_surf_blocks,
            fuel=_fuel, resupply=_resupply, gear=_gear, alerty=_alerty,
            opony_opcje=_tire_options, nawierzchnia_udzial=_naw_udzial,
            opady_historia=precip_history, outfit_rules=_load_outfit_rules())
    except Exception:
        _og = _et = _rc2 = []
        _strat = _ubior = _opony = None
    _og = _og or []
    _et = _et or []
    _rc = _rc2 or []

    # opony: wybor Alberta -> zestaw + deterministyczne cisnienie (fallback jesli brak)
    _w = None
    if isinstance(_opony, dict) and _press.get("wheelsets"):
        _lab = (_opony.get("wheelset") or "").upper()
        for w in _press["wheelsets"]:
            _wl = (w.get("label") or "").upper()
            if _lab and (_lab in _wl or _wl in _lab):
                _w = w
                break
        if _w is None:
            _tl = (_opony.get("tire") or "").upper()
            for w in _press["wheelsets"]:
                if _tl and _tl.split(" ")[0] in (w.get("tire") or "").upper():
                    _w = w
                    break
    if _w is None and _press.get("wheelsets"):
        _want = "thunder" if (loose_pct >= 40 or (sand_tag and loose_pct >= 20)) else "gone"
        for w in _press["wheelsets"]:
            _tir = (w.get("tire") or "").upper()
            if _want == "thunder" and "THUNDER" in _tir:
                _w = w
                break
            if _want == "gone" and "G-ONE" in _tir:
                _w = w
                break
        if _w is None:
            _w = _press["wheelsets"][0]
    if _w:
        _tir = (_w.get("tire") or "").upper()
        _pri = "szuter_luzny" if "THUNDER" in _tir else ("asfalt" if hard_pct >= 55 else "szuter_gladki")
        _sd = (_w.get("surface", {}) or {}).get(_pri) or {}
        sprzet["tire"] = {"wheelset": _w.get("label"), "tire": _w.get("tire"),
                          "front_mm": _w.get("front_mm"), "rear_mm": _w.get("rear_mm"),
                          "reason": (_opony.get("uzasadnienie") if isinstance(_opony, dict) else None) or ""}
        if _sd:
            sprzet["pressure"] = {"surface": _pri, "surface_desc": _sd.get("desc"),
                                  "front_bar": _sd.get("front_bar"), "front_psi": _sd.get("front_psi"),
                                  "rear_bar": _sd.get("rear_bar"), "rear_psi": _sd.get("rear_psi"),
                                  "rider_kg": _press.get("rider_kg"), "model": _w.get("model"),
                                  "all": _w.get("surface", {})}
    details["forma"] = forma
    details["strategia"] = _strat
    sprzet["clothing"] = _ubior
    # kompatybilnosc wstecz: gdy sa 'zestawy' a nie ma 'rzeczy', dorzuc splaszczony
    # 1. zestaw jako 'rzeczy', by starszy (zcache'owany) frontend tez cos pokazal
    if isinstance(_ubior, dict) and _ubior.get("zestawy") and not _ubior.get("rzeczy"):
        _z0 = _ubior["zestawy"][0] if _ubior["zestawy"] else {}
        _ubior["rzeczy"] = _z0.get("rzeczy") or []

    def _fb_overall(o):
        if not o:
            return ["Brak danych o zachmurzeniu.", "Brak danych o temperaturze i wietrze."]
        _sky = o.get("niebo_dominuje") or "zmiennie"
        _rain = (" mozliwy opad (do %s%%)" % o.get("opad_prob_max")) if o.get("opad_prob_max") else ""
        b1 = "Niebo: %s.%s" % (_sky, _rain)
        b2 = "Odczuwalna %s-%s C, WBGT do %s C; wiatr %s-%s m/s (%s)." % (
            o.get("odczuwalna_min"), o.get("odczuwalna_max"), o.get("wbgt_max"),
            o.get("wiatr_ms_min"), o.get("wiatr_ms_max"), o.get("wiatr_kierunek") or "zmienny")
        return [b1, b2]

    def _fb_stage(a):
        return "WBGT %s-%s C, wiatr %s-%s m/s, opad do %s%%." % (
            a.get("wbgt_min"), a.get("wbgt_max"), a.get("wiatr_ms_min"),
            a.get("wiatr_ms_max"), a.get("opad_prob_max"))

    if not _og or len(_og) < 2:
        _og = _fb_overall(weather_overall)
    details["weather"]["ogolne"] = _og[:2]
    details["weather"]["etapy"] = [
        {"naglowek": stages[_i].get("naglowek"),
         "tekst": (_et[_i] if _i < len(_et) and _et[_i] else _fb_stage(stages[_i]))}
        for _i in range(len(stages))
    ]
    for _i, _r in enumerate(details["surface"]["risk"]):
        _r["comment"] = (_rc[_i] if _i < len(_rc) and _rc[_i]
                         else (_r.get("reason") or "Odcinek oznaczony jako ryzykowny."))

    # --- deterministyczny alert terenowy (susza/opady przed jazda, kat.4+5) ---
    _alerts_out = list(m.get("alerts") or [])
    if precip_history and _risk45_km >= 2.0 and precip_history.get("ocena") in ("susza", "mokro"):
        _a_km = min(x["a"] for x in surface_risk)
        _b_km = max(x["b"] for x in surface_risk)
        if precip_history["ocena"] == "susza":
            _opis = ("Susza (~%s mm opadow w %s dni przed jazda) - odcinki trudne/ryzykowne "
                      "(lacznie ~%s km) moga byc bardziej sypkie/luzne (piach)." % (
                          precip_history["total_mm"], precip_history["days"], round(_risk45_km, 1)))
        else:
            _opis = ("Niedawne opady (~%s mm w ostatnich 2 dniach przed jazda) - odcinki trudne/"
                      "ryzykowne (lacznie ~%s km) moga byc rozmokle/blotniste." % (
                          precip_history["last2_mm"], round(_risk45_km, 1)))
        if precip_history.get("stale"):
            _opis += " Stan na %s - moze sie zmienic do wyjazdu." % precip_history["as_of"]
        _alerts_out.append({"typ": "nawierzchnia", "severity": "FLAGA",
                             "km_od": _a_km, "km_do": _b_km, "opis": _opis})

    return {
        "route": {"id": route_id, "name": name, "distance_km": dist_km,
                  "ascent_m": ascent, "source": "RWGPS GPX",
                  "version_modified": version_modified},
        "start": {"date": date_str, "time": start_time,
                  "miejscowosc": adm.get("miejscowosc"), "gmina": adm.get("gmina"),
                  "powiat": adm.get("powiat"), "wojewodztwo": adm.get("wojewodztwo")},
        "time": {"moving_h": tmoving, "total_h": ttotal, "stops_auto_min": stops_min,
                 "stops_count": stops_cnt, "long_stops_min": long_min_val, "accuracy_pct": 15,
                 "speed_net_kmh": speed_net_kmh, "speed_gross_kmh": speed_gross_kmh},
        "weather_head": weather_head,
        "alerts": _alerts_out,
        "details": details,
        "chart": {"km_total": km_total, "ele": ele, "ele_min": emin, "ele_max": emax,
                  "surface_cat": surface_cat, "weather": weather, "eta": eta, "wind": wind},
    }


_REPORT_SNAPSHOT_KEEP = 4  # biezacy + 3 archiwalne, NA TRASE (route_id)


def _save_report_snapshot(conn, route_id, date_str, start_time, long_stops, long_stop_min, data):
    """Zapisuje wygenerowany raport w archiwum, przycina do _REPORT_SNAPSHOT_KEEP na trase.
    Zwraca id nowego wpisu (albo None przy bledzie)."""
    try:
        row = conn.execute(
            "INSERT INTO qbot_v2.route_report_snapshots "
            "(route_id, report_date, start_time, long_stops, long_stop_min, data_json) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb) "
            "RETURNING route_report_snapshot_id",
            (route_id, date_str, start_time, long_stops, long_stop_min, json.dumps(data))).fetchone()
        new_id = row["route_report_snapshot_id"] if row else None
        conn.execute(
            "DELETE FROM qbot_v2.route_report_snapshots "
            "WHERE route_id=%s AND route_report_snapshot_id NOT IN ("
            "  SELECT route_report_snapshot_id FROM qbot_v2.route_report_snapshots "
            "  WHERE route_id=%s ORDER BY created_at DESC LIMIT %s)",
            (route_id, route_id, _REPORT_SNAPSHOT_KEEP))
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        return None


_ATT_JUNK = ("pomnik przyrody", "wiata", "przystanek sztuki", "d\u0105b", "g\u0142az", "aleja lip",
             "aleja pomolog", "kasztanow", "mogi\u0142", "gr\u00f3b", "grob", "miejsce pami\u0119ci",
             "ruiny", "ko\u0142o \u0142owieck", "turbin", "rancho", "wie\u017ca wodna")
_ATT_REL = ("ko\u015bci", "kaplic", "krzy\u017c", "figur", "parafia", "sanktu", "dzwonnic", "cerkiew", "ko\u015bciel")
_ATT_VENUE = ("hotel", "restau", "sklep", "noclegi", "pensjonat", "przeznaczony do organ", "bar ")


def _att_quality_keep(name, typ, rat, n):
    nm = (name or "").lower()
    tp = (typ or "").lower()
    if any(j in nm for j in _ATT_JUNK):
        return False
    if any(vv in tp for vv in _ATT_VENUE):
        return False
    if rat is None or n is None:
        return False
    is_rel = ("ko\u015bci" in tp) or any(r in nm for r in _ATT_REL)
    if is_rel:
        return (rat >= 4.5 and n >= 200)
    return (rat >= 4.3 and n >= 30)


def _att_build_desc(meta):
    typ = meta.get("g_type_pl"); rat = meta.get("g_rating"); n = meta.get("g_rating_n"); summ = meta.get("g_summary")
    bits = []
    if typ:
        bits.append(str(typ))
    if rat:
        bits.append("\u2605%s%s" % (rat, (" (%d)" % n if n else "")))
    base = " \u00b7 ".join(bits) if bits else None
    if summ:
        return (base + " \u2014 " + summ) if base else summ
    return base


def _build_day_data(conn, route_id, km_from, km_to):
    """Okrojony DATA dla jednego dnia (zakres km) - bez pogody/forma/strategia/sprzet.
    Reuzywa helperow raportu (surface/climbs/poi), wszystko przyciete do [km_from, km_to].
    chart w skali dnia (offset do 0); listy climbs/poi w km ABSOLUTNYCH trasy."""
    base = conn.execute(
        "SELECT rb.route_base_id, rb.distance_m, "
        "a.metadata_json->>'route_name' AS name "
        "FROM qbot_v2.route_base rb "
        "LEFT JOIN qbot_v2.route_artifacts a ON a.id=rb.route_artifact_id "
        "WHERE rb.route_id=%s "
        "ORDER BY (rb.status='active') DESC, rb.route_modified_at DESC NULLS LAST LIMIT 1",
        (route_id,)).fetchone()
    if not base:
        raise HTTPException(status_code=404, detail="Trasa nie znaleziona")
    rbid = base["route_base_id"]
    a0, b0 = float(km_from), float(km_to)
    dist_day = round(b0 - a0, 1)

    # profil w zakresie, offset do 0
    erows = conn.execute(
        "SELECT distance_m, elevation_m FROM qbot_v2.route_elevation_samples "
        "WHERE route_base_id=%s ORDER BY sample_index", (rbid,)).fetchall()
    sel = [(r["distance_m"] / 1000.0, r["elevation_m"]) for r in erows
           if a0 <= r["distance_m"] / 1000.0 <= b0]
    if not sel:
        raise HTTPException(status_code=422, detail="Brak profilu wysokosci w zakresie")
    step = max(1, len(sel) // 220)
    ele = []
    for i in range(0, len(sel), step):
        ele.append([round(sel[i][0] - a0, 3), round(sel[i][1], 1)])
    if ele[-1][0] != round(sel[-1][0] - a0, 3):
        ele.append([round(sel[-1][0] - a0, 3), round(sel[-1][1], 1)])
    emin = min(p[1] for p in ele)
    emax = max(p[1] for p in ele)
    day_asc = 0.0
    for i in range(1, len(ele)):
        d = ele[i][1] - ele[i - 1][1]
        if d > 0:
            day_asc += d

    # nawierzchnia - ribbon przyciety do [a0,b0], offset do 0
    raw_buckets = _load_surface_buckets(conn, rbid)
    ribbon = _absorb_short_surface(_coalesce_categories(raw_buckets))
    surface_cat = []
    for r in ribbon:
        if r.get("category") is None:
            continue
        ra, rb = float(r["km_from"]), float(r["km_to"])
        if rb <= a0 or ra >= b0:
            continue
        ca, cb = max(ra, a0), min(rb, b0)
        surface_cat.append({"a": round(ca - a0, 2), "b": round(cb - a0, 2),
                            "k": r["category"], "label": r.get("label"), "reason": r.get("reason")})
    _scat = {}
    for _s in surface_cat:
        _scat[_s["k"]] = _scat.get(_s["k"], 0.0) + max(0.0, _s["b"] - _s["a"])
    _tot = sum(_scat.values()) or 1.0
    surface_by_cat = [{"k": k, "km": round(_scat[k], 1), "pct": round(_scat[k] / _tot * 100)}
                      for k in sorted(_scat)]
    surface_risk = [{"a": round(_s["a"] + a0, 2), "b": round(_s["b"] + a0, 2),
                     "km": round(_s["b"] - _s["a"], 2), "k": _s["k"], "reason": _s.get("reason")}
                    for _s in surface_cat if _s["k"] in (4, 5) and (_s["b"] - _s["a"]) >= 0.3]

    # podjazdy w zakresie (km absolutne)
    _cl = conn.execute(
        "SELECT event_index, start_m, end_m, length_m, elevation_gain_m, avg_gradient_pct, "
        "max_gradient_pct, severity FROM qbot_v2.route_climb_events "
        "WHERE route_base_id=%s AND start_m/1000.0 >= %s AND start_m/1000.0 < %s ORDER BY start_m",
        (rbid, a0, b0)).fetchall()
    climbs_list = []
    for r in _cl:
        climbs_list.append({"i": (r["event_index"] or 0) + 1,
                            "a_km": round((r["start_m"] or 0) / 1000.0, 1),
                            "b_km": round((r["end_m"] or 0) / 1000.0, 1),
                            "length_m": round(r["length_m"] or 0),
                            "gain_m": round(r["elevation_gain_m"] or 0),
                            "avg_pct": r["avg_gradient_pct"], "max_pct": r["max_gradient_pct"],
                            "severity": r["severity"]})

    # POI w zakresie (km absolutne)
    _pg = _load_poi_groups(conn, rbid)
    for cat in list(_pg.keys()):
        _pg[cat] = [p for p in _pg[cat] if a0 <= (p.get("km") or 0) <= b0]
    # zaopatrzenie: _curate_pois dzieli trase od 0, wiec offset km->skala dnia, potem przywroc absolutne
    _pg_local = {}
    for _cat, _lst in _pg.items():
        _pg_local[_cat] = [dict(_p, km=round((_p.get("km") or 0) - a0, 1)) for _p in _lst]
    try:
        _cur = _curate_pois(_pg_local, dist_day, None)
        _resupply = _cur.get("resupply", []) or []
        for _area in _resupply:
            if _area.get("q_km") is not None:
                _area["q_km"] = round(_area["q_km"] + a0, 1)
            for _pk in (_area.get("picks", []) or []):
                if _pk.get("km") is not None:
                    _pk["km"] = round(_pk["km"] + a0, 1)
    except Exception:
        _resupply = []
    # atrakcje: wlasna selekcja rozlozona po km (bramka jakosci jak w raporcie), sort po km
    _att = []
    for _it in _pg.get("attraction", []):
        if _it.get("dist_m") is None or _it["dist_m"] > 800:
            continue
        _m = _it.get("meta") or {}
        if not _att_quality_keep(_it["name"], _m.get("g_type_pl"), _m.get("g_rating"), _m.get("g_rating_n")):
            continue
        _att.append((_it, (_m.get("g_rating") or 0) * (_m.get("g_rating_n") or 0)))
    _picked = []
    if _att:
        _nbin = max(1, min(8, int(round(dist_day / 12.0)) or 1))
        _binw = (b0 - a0) / _nbin if _nbin else (b0 - a0)
        _bins = {}
        for _it, _sc in _att:
            _bi = min(_nbin - 1, int((_it["km"] - a0) / _binw)) if _binw > 0 else 0
            _bins.setdefault(_bi, []).append((_it, _sc))
        for _bi in sorted(_bins):
            _top = sorted(_bins[_bi], key=lambda z: z[1], reverse=True)[:1]
            _picked.extend([t[0] for t in _top])
        if len(_picked) < 10:
            _ids = set(id(x) for x in _picked)
            _rest = sorted([z for z in _att if id(z[0]) not in _ids], key=lambda z: z[1], reverse=True)
            _picked.extend([z[0] for z in _rest[:10 - len(_picked)]])
        _picked.sort(key=lambda it: it["km"])
    _att_items = [{"km": _it["km"], "name": _it["name"], "dist_m": _it.get("dist_m"),
                   "lat": _it.get("lat"), "lon": _it.get("lon"),
                   "desc": _att_build_desc(_it.get("meta") or {})} for _it in _picked]
    poi_out = {"resupply": _resupply, "attractions": {"total": len(_att), "items": _att_items}}

    return {
        "route": {"id": route_id,
                  "name": (base["name"] or ("Trasa " + str(route_id)))
                          + (" \u2014 dzie\u0144 %s\u2013%s km" % (round(a0), round(b0)))},
        "day": {"km_from": round(a0, 1), "km_to": round(b0, 1), "dist_km": dist_day, "ascent_m": round(day_asc)},
        "chart": {"km_total": dist_day, "ele": ele, "ele_min": emin, "ele_max": emax,
                  "surface_cat": surface_cat},
        "details": {
            "surface": {"total_km": dist_day, "by_cat": surface_by_cat, "risk": surface_risk},
            "climbs": {"ascent_m": round(day_asc), "descent_m": None,
                       "count": len(climbs_list), "list": climbs_list},
            "poi": poi_out,
        },
        "day_mode": True,
    }


@app.get("/api/planer/dzien")
def api_planer_dzien(route_id: str = Query(...), from_km: float = Query(..., alias="from"),
                     to_km: float = Query(..., alias="to")):
    """Analiza jednego dnia (zakres km) - okrojony DATA bez pogody. Do zakladek planera."""
    conn = _db_conn()
    try:
        return _build_day_data(conn, route_id, from_km, to_km)
    except HTTPException:
        raise
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:200]}
    finally:
        conn.close()


@app.get("/api/report/data")
def report_data(route_id: str = Query(...), date: str = Query(...),
                time: str = Query("10:00"), long_stops: int = Query(0),
                long_stop_min: int = Query(0)):
    """Zwraca blok DATA raportu trasy (JSON) - generator w QBocie. Zapisuje tez do archiwum."""
    conn = _db_conn()
    try:
        data = _build_report_data(conn, route_id, date, time, long_stops, long_stop_min)
        snap_id = _save_report_snapshot(conn, route_id, date, time, long_stops, long_stop_min, data)
        data["snapshot_id"] = snap_id
        return data
    finally:
        conn.close()


@app.get("/api/report/history")
def report_history(route_id: str = Query(...)):
    """Lista ostatnich zapisanych raportow dla trasy (do paska Historia), najnowszy pierwszy."""
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT route_report_snapshot_id AS id, report_date, start_time, "
            "long_stops, long_stop_min, created_at "
            "FROM qbot_v2.route_report_snapshots WHERE route_id=%s "
            "ORDER BY created_at DESC LIMIT %s",
            (route_id, _REPORT_SNAPSHOT_KEEP)).fetchall()
        return {"items": [
            {"id": r["id"], "report_date": r["report_date"], "start_time": r["start_time"],
             "long_stops": r["long_stops"], "long_stop_min": r["long_stop_min"],
             "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else None}
            for r in rows
        ]}
    finally:
        conn.close()


@app.get("/api/report/snapshot/{snapshot_id}")
def report_snapshot(snapshot_id: int):
    """Zwraca dokladnie zapisany blok DATA archiwalnego raportu (bez liczenia od nowa)."""
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT data_json FROM qbot_v2.route_report_snapshots "
            "WHERE route_report_snapshot_id=%s", (snapshot_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Zapisany raport nie znaleziony")
        out = row["data_json"]
        if isinstance(out, dict):
            out["snapshot_id"] = snapshot_id
        return out
    finally:
        conn.close()


_SCAT_LABEL = {1: "Asfalt", 2: "Dobry gravel/szuter", 3: "Zwykly gravel", 4: "Trudna/wolna", 5: "Ryzyko"}
_SCAT_COLOR = {1: "#000000", 2: "#2e7d32", 3: "#8bc34a", 4: "#e07b1a", 5: "#c2452f"}
_ALERT_TYP_LABEL = {"upa\u0142": "UPA\u0141", "upal": "UPA\u0141", "deszcz": "DESZCZ", "burza": "BURZA", "zimno": "ZIMNO", "nawierzchnia": "NAWIERZCHNIA"}
_EMAIL_RE = _re_email.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _esc(x):
    import html as _html
    return _html.escape(str(x)) if x is not None else ""


def _fmt_h(h):
    if h is None:
        return "?"
    hh = int(h)
    mm = round((h - hh) * 60)
    if mm == 60:
        hh += 1
        mm = 0
    return "%dh%02dm" % (hh, mm)


def _alert_line(a):
    t = a.get("typ")
    lab = _ALERT_TYP_LABEL.get(t, (t or "").upper())
    sev = a.get("severity") or ""
    km = "km %s\u2013%s" % (a.get("km_od"), a.get("km_do"))
    detail = ""
    if t == "nawierzchnia":
        detail = a.get("opis") or ""
    elif t in ("upa\u0142", "upal"):
        if a.get("wbgt_max") is not None:
            detail = "WBGT do %s\u00b0C" % a["wbgt_max"]
        if a.get("powod"):
            detail += (" \u00b7 " if detail else "") + str(a["powod"])
    elif t == "deszcz":
        if a.get("opad_max_mm") is not None:
            detail = "do %s mm" % a["opad_max_mm"]
        if a.get("prawdopod") is not None:
            detail += (" \u00b7 " if detail else "") + "ryzyko %s%%" % a["prawdopod"]
    elif t == "burza":
        pw = a.get("przeczekaj_w") or {}
        if pw.get("miejscowosc"):
            detail = "przeczekaj w %s (km %s)" % (pw["miejscowosc"], pw.get("km"))
        if a.get("czekanie_min") is not None:
            detail += (" \u00b7 " if detail else "") + "~%s min oczekiwania" % a["czekanie_min"]
        if not detail:
            detail = a.get("opis") or ""
    elif t == "zimno":
        if a.get("utci_avg") is not None:
            detail = "odczuwalna ~%s\u00b0C" % a["utci_avg"]
        if a.get("kategoria"):
            detail += (" \u00b7 " if detail else "") + str(a["kategoria"])
    return "%s (%s, %s)%s" % (lab, sev, km, (": " + detail) if detail else "")


def _rain_summary(windows):
    """Deterministyczna linijka o ilosci opadow (mm) - NIE z LLM, zeby liczby sie zgadzaly."""
    if not windows:
        return None
    best = max(windows, key=lambda w: (w.get("opad_mm") or 0))
    mm = best.get("opad_mm") or 0
    if mm <= 0.05:
        return "Bez istotnych opadow w prognozie."
    bits = ["do %.1f mm" % mm]
    if best.get("opad_prob") is not None:
        bits.append("~%s%%" % best["opad_prob"])
    if best.get("km_od") is not None and best.get("km_do") is not None:
        bits.append("km %.0f\u2013%.0f" % (best["km_od"], best["km_do"]))
    if best.get("okno"):
        bits.append("ok. %s" % best["okno"])
    return "Opady: " + ", ".join(bits) + "."


def _build_report_email_html(data, has_map, has_chart):
    """Ladny, uproszczony raport - sekcje jedna pod druga (tabelowy layout HTML,
    dziala w kazdym kliencie poczty). Kolejnosc: hero -> start/czas -> ostrzezenia ->
    mapa -> pogoda -> profil -> nawierzchnia -> przewyzszenia -> strategia -> POI.
    Wszystkie naglowki sekcji CZARNE (INK) - spojnosc; jeden font-size na tekst tresci,
    jeden na tekst pomocniczy/meta."""
    r = data.get("route", {}) or {}
    st = data.get("start", {}) or {}
    tm = data.get("time", {}) or {}
    det = data.get("details", {}) or {}
    surf = det.get("surface", {}) or {}
    wea = det.get("weather", {}) or {}
    climbs = det.get("climbs", {}) or {}
    strat = det.get("strategia") or {}
    poi = det.get("poi") or {}
    alerts = data.get("alerts") or []

    FONT = "-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"
    ACCENT = "#3f6f9a"
    LINE = "#e3ddd2"
    MUTED = "#7a838c"
    INK = "#1c2024"
    INK2 = "#41484f"
    SZ = 14      # tekst tresci
    SZ_M = 12.5  # tekst pomocniczy / meta

    def SEC(text):
        return ('<div style="font-family:%s;font-size:12px;font-weight:700;text-transform:uppercase;'
                'letter-spacing:.08em;color:%s;margin:26px 0 10px;padding-top:18px;'
                'border-top:1px solid %s">%s</div>') % (FONT, INK, LINE, _esc(text))

    def TXT(html, size=SZ, color=INK2, extra=""):
        return '<p style="margin:0 0 6px;font-family:%s;font-size:%spx;color:%s;%s">%s</p>' % (
            FONT, size, color, extra, html)

    def STAT(value, label):
        return ('<td width="33%%" valign="top" style="background:#ffffff;border:1px solid %s;'
                'border-radius:10px;padding:12px 8px;text-align:center;font-family:%s">'
                '<div style="font-size:19px;font-weight:750;color:%s;line-height:1.1;'
                'font-family:%s">%s</div>'
                '<div style="font-size:9.5px;text-transform:uppercase;letter-spacing:.07em;color:%s;'
                'margin-top:4px;font-family:%s">%s</div></td>') % (
                    LINE, FONT, INK, FONT, value, MUTED, FONT, _esc(label))

    p = []
    p.append('<div style="background:#f6f2ea;padding:22px 10px;font-family:%s">' % FONT)
    p.append('<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" '
              'style="max-width:640px;margin:0 auto;background:#fffdf8;border-radius:14px;'
              'border:1px solid %s;font-family:%s">' % (LINE, FONT))
    p.append('<tr><td style="background:%s;border-radius:14px 14px 0 0;height:6px;'
              'line-height:6px;font-size:0">&nbsp;</td></tr>' % ACCENT)
    p.append('<tr><td style="padding:26px 30px 6px;font-family:%s">' % FONT)

    p.append('<div style="font-family:%s;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;'
              'color:%s;margin-bottom:6px">Raport trasy &middot; QBot</div>' % (FONT, MUTED))
    p.append('<div style="font-family:%s;font-size:22px;font-weight:750;color:%s;margin-bottom:16px">%s</div>' % (
        FONT, INK, _esc(r.get("name") or ("Trasa %s" % r.get("id", "")))))

    stats = [STAT("%.1f km" % (r.get("distance_km") or 0), "Dystans")]
    stats.append(STAT(("+%s m" % r["ascent_m"]) if r.get("ascent_m") is not None else "?", "Podjazdy"))
    stats.append(STAT(_fmt_h(tm.get("moving_h")), "Czas w ruchu"))
    p.append('<table role="presentation" width="100%%" cellpadding="0" cellspacing="6" '
              'style="font-family:%s"><tr>%s</tr></table>' % (FONT, "".join(stats)))

    miejsce = ", ".join([x for x in [st.get("miejscowosc"), st.get("gmina")] if x])
    p.append(SEC("Start i czas"))
    p.append(TXT("%s, godz. %s%s" % (
        _esc(st.get("date") or ""), _esc(st.get("time") or ""),
        (" &middot; " + _esc(miejsce)) if miejsce else "")))
    spd = (" &middot; %s km/h" % tm.get("speed_net_kmh")) if tm.get("speed_net_kmh") else ""
    p.append(TXT("w ruchu <b>%s</b> &middot; calkowity <b>%s</b>%s" % (
        _fmt_h(tm.get("moving_h")), _fmt_h(tm.get("total_h")), spd)))
    finish = None
    try:
        from datetime import datetime as _dt, timedelta as _td
        finish = (_dt.strptime(st.get("time") or "10:00", "%H:%M") +
                  _td(hours=float(tm.get("total_h") or 0))).strftime("%H:%M")
    except Exception:
        finish = None
    if finish:
        p.append(TXT("odjazd <b>%s</b> &rarr; przyjazd ok. <b>%s</b>" % (_esc(st.get("time") or ""), finish)))

    if alerts:
        _SEV_COLOR = {"NO-GO": "#c2452f", "ALARM": "#e07b1a", "FLAGA": "#e0a72e"}
        p.append(SEC("Ostrzezenia"))
        for a in alerts:
            col = _SEV_COLOR.get(a.get("severity"), "#b0402c")
            p.append('<div style="font-family:%s;border-left:4px solid %s;background:#fff6f3;'
                      'border-radius:0 8px 8px 0;padding:8px 12px;margin:0 0 8px;color:%s;'
                      'font-size:%spx">%s</div>' % (FONT, col, INK2, SZ, _esc(_alert_line(a))))

    if has_map:
        p.append(SEC("Mapa"))
        p.append('<img src="cid:reportmap" width="580" style="width:100%%;max-width:580px;'
                  'border-radius:10px;border:1px solid %s;display:block" alt="mapa trasy">' % LINE)

    p.append(SEC("Pogoda"))
    rs = _rain_summary(wea.get("windows"))
    if rs:
        p.append(TXT(_esc(rs), extra="font-weight:600"))
    for line in (wea.get("ogolne") or []):
        p.append(TXT(_esc(line)))
    etapy = wea.get("etapy") or []
    for e in etapy:
        p.append(TXT('<b style="color:%s">%s:</b> %s' % (INK, _esc(e.get("naglowek") or ""), _esc(e.get("tekst") or ""))))

    if has_chart:
        p.append(SEC("Profil trasy"))
        p.append('<img src="cid:reportchart" width="580" style="width:100%%;max-width:580px;'
                  'border-radius:10px;border:1px solid %s;display:block" alt="profil trasy">' % LINE)

    p.append(SEC("Nawierzchnia"))
    by_cat = surf.get("by_cat") or []
    for c in by_cat:
        col = _SCAT_COLOR.get(c.get("k"), "#999")
        lab = _SCAT_LABEL.get(c.get("k"), "kat. %s" % c.get("k"))
        p.append('<div style="font-family:%s;margin:0 0 5px;color:%s;font-size:%spx">'
                  '<span style="display:inline-block;width:11px;height:11px;background:%s;'
                  'border-radius:3px;margin-right:8px;vertical-align:middle"></span>'
                  '%s: <b>%s km</b> (%s%%)</div>' % (FONT, INK2, SZ, col, _esc(lab), c.get("km"), c.get("pct")))
    risk = surf.get("risk") or []
    if risk:
        p.append(TXT("<b>Odcinki ryzykowne:</b>", extra="margin-top:8px"))
        for rr in risk:
            p.append(TXT("km %s&ndash;%s (%s km): %s" % (
                rr.get("a"), rr.get("b"), rr.get("km"), _esc(rr.get("comment") or rr.get("reason") or "")), size=SZ_M))

    p.append(SEC("Przewyzszenia"))
    asc = climbs.get("ascent_m")
    dsc = climbs.get("descent_m")
    p.append(TXT("Podjazdy <b>+%s m</b> &middot; Zjazdy <b>&minus;%s m</b> &middot; <b>%s</b> podjazdow" % (
        asc if asc is not None else "?", dsc if dsc is not None else "?", climbs.get("count") or 0)))
    clist = climbs.get("list") or []
    if clist:
        for x in clist:
            p.append('<div style="font-family:%s;background:#fff;border:1px solid %s;border-radius:8px;'
                      'padding:8px 12px;margin:0 0 6px;font-size:%spx;color:%s">'
                      '#%s &middot; km %s&ndash;%s &middot; %s m &middot; +%s m &middot; '
                      '\u015br %s%% / max %s%% &middot; %s</div>' % (
                          FONT, LINE, SZ_M, INK2, x.get("i"), x.get("a_km"), x.get("b_km"),
                          round(x.get("length_m") or 0), round(x.get("gain_m") or 0),
                          x.get("avg_pct"), x.get("max_pct"), _esc(x.get("severity") or "")))
    else:
        p.append(TXT("Trasa plaska &mdash; brak wydzielonych podjazdow."))

    p.append(SEC("Strategia jazdy"))
    if strat.get("calosc") or strat.get("etapy"):
        if strat.get("calosc"):
            p.append(TXT(_esc(strat["calosc"]), extra="margin-bottom:12px"))
        for i, e in enumerate(strat.get("etapy") or [], 1):
            p.append('<div style="font-family:%s;background:#fff;border:1px solid %s;border-radius:10px;'
                      'padding:10px 14px;margin:0 0 8px">' % (FONT, LINE))
            tytul = e.get("tytul") or ("Etap %d" % i)
            zakres = e.get("zakres_km")
            p.append('<div style="font-family:%s;font-weight:700;color:%s;margin-bottom:3px">%s%s</div>' % (
                FONT, INK, _esc(tytul), (" &middot; km " + _esc(zakres)) if zakres else ""))
            if e.get("opis"):
                p.append('<div style="font-family:%s;color:%s;font-size:%spx;margin-bottom:4px">%s</div>' % (
                    FONT, INK2, SZ_M, _esc(e["opis"])))
            bits = []
            if e.get("moc"):
                bits.append("moc: " + _esc(str(e["moc"])))
            if e.get("zywienie"):
                bits.append("zywienie: " + _esc(str(e["zywienie"])))
            if e.get("pojenie"):
                bits.append("pojenie: " + _esc(str(e["pojenie"])))
            if bits:
                p.append('<div style="font-family:%s;color:%s;font-size:%spx">%s</div>' % (
                    FONT, MUTED, SZ_M, " &middot; ".join(bits)))
            p.append('</div>')
    else:
        p.append(TXT("Strategia nie wygenerowala sie dla tego raportu (chwilowy blad LLM) "
                      "&mdash; wygeneruj raport ponownie, jesli jest potrzebna.", color=MUTED))

    resupply = poi.get("resupply") or []
    attractions = (poi.get("attractions") or {}).get("items") or []
    any_pick = any((area.get("picks") for area in resupply))
    if any_pick or attractions:
        p.append(SEC("Punkty POI"))
    if any_pick:
        p.append(TXT("<b>Zaopatrzenie:</b>"))
        for area in resupply:
            for pk in (area.get("picks") or []):
                bits = [x for x in [
                    ("km %.1f" % pk["km"]) if pk.get("km") is not None else None,
                    pk.get("miejscowosc"), pk.get("hours")] if x]
                p.append(TXT("<b>%s</b> &middot; %s" % (
                    _esc(pk.get("name") or "POI"), _esc(" \u00b7 ".join(bits))), size=SZ_M))
    if attractions:
        p.append(TXT("<b>Atrakcje:</b>", extra="margin-top:10px"))
        for a in attractions:
            bits = [x for x in [
                ("km %.1f" % a["km"]) if a.get("km") is not None else None, a.get("miejscowosc")] if x]
            line = "<b>%s</b>" % _esc(a.get("name") or "POI")
            if bits:
                line += " (%s)" % _esc(" \u00b7 ".join(bits))
            if a.get("desc"):
                line += " &mdash; %s" % _esc(a["desc"])
            p.append(TXT(line, size=SZ_M))

    p.append('<p style="font-family:%s;margin:24px 0 4px;color:%s;font-size:11.5px;'
              'border-top:1px solid %s;padding-top:12px">W zalaczniku plik GPX trasy '
              '(do wgrania w nawigacji/zegarku). Raport wygenerowany przez QBot.</p>' % (
                  FONT, MUTED, LINE))
    p.append('</td></tr></table></div>')
    return "".join(p)


def _capture_report_images(snapshot_id):
    """Renderuje raport-print.html w headless Chromium (Playwright) i robi zrzuty mapy + wykresu.
    Zwraca (map_png_bytes, chart_png_bytes) - dowolne moze byc None przy niepowodzeniu."""
    map_png = chart_png = None
    try:
        from playwright.sync_api import sync_playwright
        users, sign_val = _webauth_load()
        cookie_value = None
        if users and sign_val:
            username = next(iter(users))
            cookie_value, _exp = _webauth_cookie_make(username, sign_val)
        url = "http://127.0.0.1:%d/raport-print.html?snapshot_id=%s" % (PORT, snapshot_id)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            try:
                context = browser.new_context(viewport={"width": 1040, "height": 820}, device_scale_factor=2)
                if cookie_value:
                    context.add_cookies([{"name": "qbot_session", "value": cookie_value,
                                           "url": "http://127.0.0.1:%d" % PORT}])
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_function("window.__QBOT_RENDER_DONE === true", timeout=20000)
                try:
                    page.wait_for_function("window.__QBOT_MAP_READY === true", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(300)
                map_el = page.query_selector("#map")
                if map_el:
                    map_png = map_el.screenshot()
                chart_el = page.query_selector("#chart")
                if chart_el:
                    chart_png = chart_el.screenshot()
            finally:
                browser.close()
    except Exception as _e:
        print("_capture_report_images error:", _e)
    return map_png, chart_png


@app.post("/api/report/send-email")
def report_send_email(snapshot_id: int = Query(...), to: str = Query(...)):
    """Wysyla mailem DOKLADNIE zapisany raport (snapshot) - bez ponownego liczenia,
    wiec tresc maila jest 1:1 tym co widac na ekranie (ta sama strategia, pogoda itd).
    Robi zrzuty mapy+wykresu z tej samej wersji danych, dolacza GPX (z tej samej trasy)."""
    to = (to or "").strip()
    if not _EMAIL_RE.match(to):
        raise HTTPException(status_code=400, detail="Nieprawidlowy adres e-mail")

    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT data_json FROM qbot_v2.route_report_snapshots "
            "WHERE route_report_snapshot_id=%s", (snapshot_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Zapisany raport nie znaleziony")
        data = row["data_json"]
        route_id = data["route"]["id"]
        geo = route_geometry(route_id)
        coords = geo.get("coordinates") or []
    finally:
        conn.close()

    map_png, chart_png = _capture_report_images(snapshot_id)

    gpx_xml = None
    try:
        gpx_xml, _wn = _build_karoo_gpx(data["route"]["name"], coords,
                                         (data.get("details") or {}).get("poi"), include_pois=True)
    except Exception as _e:
        print("gpx build error:", _e)

    html_body = _build_report_email_html(data, has_map=bool(map_png), has_chart=bool(chart_png))

    msg = MIMEMultipart("related")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)
    if map_png:
        img = MIMEImage(map_png)
        img.add_header("Content-ID", "<reportmap>")
        img.add_header("Content-Disposition", "inline", filename="mapa.png")
        msg.attach(img)
    if chart_png:
        img2 = MIMEImage(chart_png)
        img2.add_header("Content-ID", "<reportchart>")
        img2.add_header("Content-Disposition", "inline", filename="profil.png")
        msg.attach(img2)
    if gpx_xml:
        safe = _re_email.sub(r"[^A-Za-z0-9_.-]+", "_", data["route"]["name"] or str(route_id)).strip("_") or ("route_%s" % route_id)
        gpx_att = MIMEApplication(gpx_xml.encode("utf-8"), _subtype="gpx+xml")
        gpx_att.add_header("Content-Disposition", "attachment", filename="%s.gpx" % safe)
        msg.attach(gpx_att)

    st = data.get("start", {}) or {}
    msg["Subject"] = "Raport trasy: %s - %s %s" % (data["route"]["name"], st.get("date", ""), st.get("time", ""))
    msg["From"] = _cfg.GMAIL_USER
    msg["To"] = to

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(_cfg.GMAIL_USER, _cfg.GMAIL_APP_PASSWORD)
            s.send_message(msg)
    except Exception as e:
        raise HTTPException(status_code=502, detail="Nie udalo sie wyslac maila: %s" % e)

    return {"status": "ok", "to": to, "has_map": bool(map_png), "has_chart": bool(chart_png), "has_gpx": bool(gpx_xml)}


# TEST (budowa raportu z jazdy): lista pokazuje tylko te jedna jazde.
@app.get("/api/rides/ready")
def rides_ready(response: Response):
    """Lista jazd do raportu: activity_fit_raw (rozlozone) JOIN training_sessions
    (data/nazwa/typ) po external_id (numer Garmina). Flaga has_report z ride_report_data."""
    response.headers["Cache-Control"] = "no-store"
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT afr.external_id AS ride_key, afr.fit_path AS fit_path, "
            "ts.started_at AS t_start, ts.activity_name AS name, ts.sport_type AS sport, "
            "(rrd.built_at IS NOT NULL) AS has_report "
            "FROM qbot_v2.activity_fit_raw afr "
            "JOIN qbot_v2.training_sessions ts ON ts.external_id = afr.external_id "
            "LEFT JOIN qbot_v2.ride_report_data rrd ON rrd.ride_key = afr.external_id "
            "WHERE afr.parse_error IS NULL "
            "ORDER BY ts.started_at DESC NULLS LAST LIMIT 50"
        ).fetchall()
        out = []
        for r in rows:
            ts = r["t_start"]
            out.append({
                "ride_key": r["ride_key"], "fit_path": r["fit_path"],
                "name": r["name"], "sport": r["sport"],
                "date": ts.date().isoformat() if ts else None,
                "time": ts.strftime("%H:%M") if ts else None,
                "has_report": bool(r["has_report"]),
            })
        return {"rides": out}
    finally:
        conn.close()


@app.get("/api/ride-report/data")
def ride_report_data(response: Response, ride: str = Query(...), rebuild: int = Query(0)):
    """W1 raportu z jazdy. Zwraca zapisany JSON, albo buduje z FIT (ModelQ+Garmin) i zapisuje.

    Wiatr i nawierzchnia sa WTYCZKAMI (status 'parked') do decyzji uzytkownika.
    """
    response.headers["Cache-Control"] = "no-store"
    from qbot3.rides import ride_report_builder as _rrb
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT fit_path, w1_json FROM qbot_v2.ride_report_data "
            "WHERE ride_key=%s AND schema_version=%s",
            (ride, _rrb.SCHEMA_VERSION)).fetchone()
        if row and row.get("w1_json") and not rebuild:
            return row["w1_json"]
        fit = (row or {}).get("fit_path")
        if not fit:
            fr = conn.execute(
                "SELECT fit_path FROM qbot_v2.ride_frames "
                "WHERE ride_key=%s AND fit_path IS NOT NULL LIMIT 1",
                (ride,)).fetchone()
            fit = fr["fit_path"] if fr else None
    finally:
        conn.close()
    if not fit or not os.path.exists(fit):
        raise HTTPException(status_code=404, detail="Brak pliku FIT dla tej jazdy")
    w1 = _rrb.build_w1(fit, ride)
    _rrb.save_report(ride, fit, {}, w1)
    return w1


@app.get("/api/ride-report/w2")
def ride_report_w2(response: Response, ride: str = Query(...), rebuild: int = Query(0)):
    """Analiza W2 (LLM czyta tylko W1). Zwraca zapisana; generuje wylacznie gdy rebuild=1."""
    response.headers["Cache-Control"] = "no-store"
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT w1_json, w2_json FROM qbot_v2.ride_report_data "
            "WHERE ride_key=%s AND schema_version=%s", (ride, 1)).fetchone()
    finally:
        conn.close()
    if not row or not row.get("w1_json"):
        raise HTTPException(status_code=404, detail="Brak raportu W1 - najpierw wygeneruj raport")
    if row.get("w2_json") and not rebuild:
        return row["w2_json"]
    if not rebuild:
        return {"status": "empty"}
    from qbot3.rides.ride_report_w2 import build_w2
    try:
        w2 = build_w2(row["w1_json"])
    except Exception as e:
        raise HTTPException(status_code=502, detail="W2 generacja nieudana: %s" % e)
    conn = _db_conn()
    try:
        conn.execute(
            "UPDATE qbot_v2.ride_report_data SET w2_json=%s "
            "WHERE ride_key=%s AND schema_version=%s",
            (json.dumps(w2, ensure_ascii=False), ride, 1))
        conn.commit()
    finally:
        conn.close()
    return w2


def _ride_context_json(ride_key):
    """Zwiezly kontekst calej jazdy (W1) do oceny normy przez LLM. Pusty string, gdy brak."""
    try:
        conn = _db_conn()
        try:
            row = conn.execute(
                "SELECT w1_json FROM qbot_v2.ride_report_data WHERE ride_key=%s AND schema_version=%s",
                (ride_key, 1)).fetchone()
        finally:
            conn.close()
        if not row or not row.get("w1_json"):
            return ""
        w1 = row["w1_json"]
        if isinstance(w1, str):
            w1 = json.loads(w1)
        vv = lambda x: (x.get("value") if isinstance(x, dict) and "value" in x else x)
        L = w1.get("load") or {}
        W = w1.get("wprime") or {}
        PH = w1.get("physio") or {}
        MQ = (w1.get("modelq") or {}).get("current") or {}
        ti = w1.get("terrain_impact") or {}
        ctx = {
            "dystans_km": vv(L.get("dist_km")), "czas_ruchu_s": vv(L.get("dur_moving_s")),
            "FTP_w": vv(L.get("ftp_w")), "NP_w": vv(L.get("np_w")), "IF": vv(L.get("if")),
            "VI": vv(L.get("vi")), "EF": vv(L.get("ef")), "EF_anchor": vv(L.get("ef_anchor")),
            "XSS": vv(L.get("xss")), "kJ": vv(L.get("kj")), "avg_p_w": vv(L.get("avg_p_w")),
            "CP_w": vv(W.get("cp_w")), "Wprime_J": vv(W.get("wprime_j")),
            "Wbal_min_pct": vv(W.get("wbal_min_pct")), "tau_s": vv(W.get("tau_s")),
            "HR_avg": vv(PH.get("hr_avg")), "HR_max": vv(PH.get("hr_max")),
            "pct_HRmax": vv(PH.get("pct_hrmax")), "decoupling_pct": vv(PH.get("decoupling_pct")),
            "ModelQ_TP": MQ.get("ftp_w"), "ModelQ_LTP": MQ.get("ltp_w"),
            "ModelQ_Wprime_kj": MQ.get("wprime_kj"), "ModelQ_PP": MQ.get("pp_w"), "ModelQ_wkg": MQ.get("wkg"),
            "strefy_mocy_pct": vv(L.get("zones_power_pct")), "strefy_hr_pct": vv(L.get("zones_hr_pct")),
            "wind_by_dir": ti.get("wind_by_dir"), "surface_by_type": ti.get("surface_by_type"),
        }
        return json.dumps(ctx, ensure_ascii=False, default=str)
    except Exception:
        return ""


@app.post("/api/ride-report/correlate")
async def ride_report_correlate(request: Request):
    """Komentarz AI dla raportu z jazdy: 2-3 wartosci (vals), caly wiersz (row),
    albo aktualnie wyswietlany odcinek wykresu (live). Odnosi sie do kontekstu calej jazdy
    i ocenia, czy relacja miesci sie w granicach akceptacji. Nic nie zapisuje - liczone na zywo."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bledny JSON")
    ride = (str(body.get("ride") or "")).strip()[:40]
    vals = body.get("vals")
    if isinstance(vals, list):
        vals = [str(x).strip()[:200] for x in vals if str(x).strip()][:3]
    else:
        vals = []
    row = (str(body.get("row") or "")).strip()[:500]
    live = (str(body.get("live") or "")).strip()[:900]

    ctx_json = _ride_context_json(ride) if ride else ""
    ctx_block = ("\n\nKONTEKST RAPORTU (cala jazda, do oceny normy):\n" + ctx_json) if ctx_json else ""

    _ACCEPT = (
        " Na podstawie KONTEKSTU RAPORTU (FTP/CP/W', profil calej jazdy, strefy, wiatr, nawierzchnia) "
        "ocen, czy ta relacja lub te wartosci MIESZCZA SIE w granicach akceptacji dla tego zawodnika i "
        "tego typu jazdy gravelowej. Jesli tak - napisz krotko, ze to w normie. Jesli NIE (odbiega) - "
        "powiedz wprost, ze wykracza poza norme, i wyjasnij jak to interpretowac oraz co moze oznaczac."
    )
    _BASE = (
        " PO POLSKU. Wiatr w m/s. Opieraj sie na podanych liczbach i kontekscie raportu - nie wymyslaj "
        "innych. Bez motywacyjnych frazesow, bez markdown i gwiazdek - od razu do meritum."
    )

    from qgpt_client import qgpt_text
    if live:
        system = (
            "Jestes doswiadczonym analitykiem treningu kolarskiego (fizjologia wysilku, model mocy "
            "krytycznej CP/W'). Dostajesz opis AKTUALNIE WYSWIETLANEGO fragmentu wykresu przebiegu jazdy "
            "(widoczne serie i ich statystyki na widocznym zakresie km lub czasu). Skomentuj, co dzieje "
            "sie na tym odcinku: pacing, sprzezenie tetno-moc (ekonomia, decoupling), kadencja, wplyw "
            "wiatru, rezerwa W'. 3-5 zdan." + _ACCEPT + _BASE)
        prompt = "Wyswietlany odcinek:\n" + live + ctx_block + "\n\nSkomentuj ten fragment jazdy."
        mt = 440
    elif row:
        system = (
            "Jestes doswiadczonym analitykiem treningu kolarskiego (fizjologia wysilku, model mocy "
            "krytycznej CP/W'). Dostajesz PELNY profil jednego wiersza raportu (jeden kierunek wiatru "
            "albo jeden typ nawierzchni ze wszystkimi metrykami). Napisz zwarta analize (3-5 zdan) jak "
            "zawodnik radzil sobie w tych warunkach; powiaz metryki ze soba (moc vs tetno = ekonomia i "
            "sprzezenie, kadencja vs nachylenie = dobor przelozen, koszt beztlenowy = obciazenie ponad "
            "prog)." + _ACCEPT + _BASE)
        prompt = "Profil wiersza: " + row + ctx_block + "\n\nZanalizuj ten wiersz."
        mt = 400
    elif len(vals) >= 2:
        ile = "DWIE" if len(vals) == 2 else "TRZY"
        system = (
            "Jestes doswiadczonym analitykiem treningu kolarskiego (model mocy krytycznej CP/W'). "
            "Dostajesz " + ile + " wartosci z jednego raportu z jazdy gravelowej tego samego zawodnika, "
            "kazda z opisem co przedstawia. Napisz rzeczowy komentarz (2-4 zdania) o zwiazku miedzy nimi: "
            "nazwij mechanizm fizjologiczny lub biomechaniczny, ktory je laczy, i ocen czy relacja jest "
            "spojna." + _ACCEPT + _BASE)
        prompt = "Wartosci:\n" + "\n".join("- " + v for v in vals) + ctx_block + "\n\nSkoreluj te wartosci."
        mt = 320
    else:
        raise HTTPException(status_code=400, detail="Podaj 2-3 wartosci, wiersz albo widok")

    try:
        txt = qgpt_text(prompt, system=system, max_tokens=mt, temperature=0.35)
    except Exception as e:
        raise HTTPException(status_code=502, detail="LLM niedostepny: %s" % e)
    return {"text": (txt or "").strip().replace("**", "").replace("__", "")}


_FEEL_WORDS = {-2: "fatalnie", -1: "gorzej niz zwykle", 0: "neutralnie", 1: "dobrze", 2: "swietnie"}


def _forma_feel_illness_for_day(conn, ref_day):
    """L1 subiektyw: ostatni wpis feel z okna [ref_day-2, ref_day] (3 dni) + aktywna choroba
    obejmujaca ref_day. Brak feel -> None = neutralnie/0. NIE dotyka liczb ani kolumn obiektywnych."""
    feel = None
    feel_note = None
    row = conn.execute(
        "SELECT feel, note FROM qbot_v2.calendar_entry "
        "WHERE kind='feel' AND feel IS NOT NULL "
        "AND day <= %s AND day >= (%s::date - INTERVAL '2 days') "
        "ORDER BY day DESC, id DESC LIMIT 1",
        (ref_day, ref_day),
    ).fetchone()
    if row:
        feel = row["feel"]
        feel_note = row["note"]
    ill = conn.execute(
        "SELECT severity, note FROM qbot_v2.calendar_entry "
        "WHERE kind='illness' AND day <= %s AND COALESCE(end_day, day) >= %s "
        "ORDER BY day DESC, id DESC LIMIT 1",
        (ref_day, ref_day),
    ).fetchone()
    return feel, feel_note, ill


def _forma_subjective_block(feel, feel_note, ill):
    """Blok tekstowy do promptu today/coach (pusty string gdy brak sygnalu subiektywnego)."""
    parts = []
    if feel is not None and feel != 0:
        w = _FEEL_WORDS.get(feel, "")
        s = "ZGLOSZENIE ZAWODNIKA (subiektyw, NIE z czujnikow): samopoczucie %+d w skali -2..+2 (-2 fatalnie .. +2 swietnie)" % feel
        if w:
            s += " - " + w
        if feel_note:
            s += '; nota: "%s"' % str(feel_note)[:160]
        parts.append(s)
    if ill:
        s = "CHOROBA zgloszona przez zawodnika (aktywna)"
        if ill.get("severity"):
            s += " - nasilenie: %s" % str(ill["severity"])[:60]
        if ill.get("note"):
            s += '; nota: "%s"' % str(ill["note"])[:160]
        parts.append(s)
    return "\n".join(parts)


def _forma_feel_illness_window(conn, start, end):
    return conn.execute(
        "SELECT day::text AS day, kind, feel, severity, note FROM qbot_v2.calendar_entry "
        "WHERE kind IN ('feel','illness') AND day BETWEEN %s AND %s ORDER BY day",
        (start, end),
    ).fetchall()


def _forma_subjective_window_lines(rows):
    out = []
    for r in rows:
        if r["kind"] == "feel" and r.get("feel") is not None:
            note = (' "%s"' % str(r["note"])[:100]) if r.get("note") else ""
            out.append("%s: samopoczucie %+d%s" % (r["day"], r["feel"], note))
        elif r["kind"] == "illness":
            sev = (" nasilenie %s" % r["severity"]) if r.get("severity") else ""
            note = (' "%s"' % str(r["note"])[:100]) if r.get("note") else ""
            out.append("%s: CHOROBA%s%s" % (r["day"], sev, note))
    return out


@app.post("/api/forma/analyze")
async def forma_analyze(request: Request):
    """Analiza LLM formy. mode='today' -> stan na dzis + zmiany 7/30/90 dni;
    mode='chart' -> widoczne okno wykresu (zakres dat + wybrane serie). Na zywo, nic nie zapisuje."""
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bledny JSON")
    mode = (str(body.get("mode") or "today")).strip()

    _MAP = {
        "ftp": ("cp_modelq_w", "FTP/CP", "W", 0),
        "ltp": ("ltp_modelq_w", "LTP", "W", 0),
        "wp": ("wprime_modelq_kj", "W'", "kJ", 1),
        "wkg": ("w_per_kg", "W/kg", "W/kg", 2),
        "ctl": ("ctl_xss", "CTL", "", 1),
        "atl": ("atl_raw", "ATL", "", 1),
        "tsb": ("tsb_raw", "TSB", "", 1),
        "atlp": ("atl_plus", "ATL+", "", 1),
        "tsbp": ("tsb_plus", "TSB+", "", 1),
        "hrv": ("hrv_night", "HRV", "ms", 0),
        "rhr": ("rhr", "RHR", "bpm", 0),
        "slp": ("sleep_score", "Sen (scoring)", "", 0),
        "rdy": ("readiness_score", "Gotowosc", "", 2),
        "rdye": ("readiness_effective", "Gotowosc(efekt)", "", 2),
        "glyc": ("glycogen_pct", "Glikogen", "%", 0),
        "wgt": ("weight_kg", "Waga", "kg", 1),
    }

    def _rr(x, d):
        if x is None:
            return None
        return round(x, d) if d else int(round(x))

    def _last(series, field, cutoff=None):
        for row in reversed(series):
            if cutoff is not None and (row.get("day") or "") > cutoff:
                continue
            if row.get(field) is not None:
                return row[field]
        return None

    _PROFILE = (
        "Zawodnik: kolarz gravel/touring, ~100 kg, prog ModelQ ~240 W, LTHR 132, NIE sciga sie - "
        "cel to dlugie jazdy w terenie, pojemnosc tlenowa i trwalosc, nie krotkie wyscigi. "
    )
    _STYLE = (
        " Odpowiadaj PO POLSKU, prostym, ludzkim jezykiem - jak do kolegi rowerzysty (hobbysty), "
        "nie do naukowca. Krotkie zdania. Bez markdown i gwiazdek. Zargon rozwijaj w nawiasie przy "
        "pierwszym uzyciu, np. 'TSB (swiezosc)', 'CTL (baza kondycji)', \"W' (zapas na zrywy)\". "
        "TRZYMAJ SIE FORMATU: pierwszy wiersz = JEDNO zdanie werdyktu (jak jest i co to praktycznie "
        "znaczy dla zawodnika); potem 2-3 punkty, kazdy w osobnej linii zaczynajacej sie od '- ', "
        "kazdy to jedna prosta mysl: co widac + co z tego wynika. Maksymalnie okolo 6 linii lacznie. "
        "Nie opisuj oczywistosci ('X rosnie') - to widac na wykresie; twoja rola to POWIEDZIEC CO TO ZNACZY. "
        "Pracuj na zaleznosciach: prog (CP/LTP/W') <-> obciazenie (CTL kondycja / ATL zmeczenie / TSB swiezosc) "
        "<-> regeneracja (HRV, tetno spoczynkowe, sen). Wychwyc sprzecznosci i wyjasnij je po ludzku "
        "(np. 'prog spada mimo swiezosci -> to nie zmeczenie, tylko brak mocnych bodzcow albo za malo jedzenia'). "
        "Liczby tylko jako krotki dowod tezy, nie zamiast tezy. Nie zmyslaj - korzystaj tylko z podanych danych; "
        "jesli czegos nie da sie rozstrzygnac, powiedz to jednym zdaniem. "
        "Jesli zawodnik zglosil samopoczucie (-2..+2) lub chorobe rozbiezne z danymi - potraktuj to jako realny "
        "sygnal STANU (swiezosc/zmeczenie), nazwij rozjazd; subiektyw NIE zmienia oceny progu CP/FTP/W'."
    )

    conn = _db_conn()
    try:
        if mode == "chart":
            start = (str(body.get("start") or "")).strip()[:10]
            end = (str(body.get("end") or "")).strip()[:10]
            keys = body.get("series") or []
            if not isinstance(keys, list):
                keys = []
            keys = [k for k in keys if k in _MAP][:12]
            if not (start and end):
                raise HTTPException(status_code=400, detail="Brak zakresu dat")
            if not keys:
                raise HTTPException(status_code=400, detail="Wlacz przynajmniej jedna serie")
            data = _build_forma_data(conn, start, end)
            series = data.get("series") or []
            try:
                ndays = (_dt_date.fromisoformat(end) - _dt_date.fromisoformat(start)).days + 1
            except Exception:
                ndays = len(series)
            lines = []
            for k in keys:
                field, label, unit, dec = _MAP[k]
                vals = [row[field] for row in series if row.get(field) is not None]
                if not vals:
                    lines.append("- %s: brak danych w oknie" % label)
                    continue
                first, last = vals[0], vals[-1]
                mn, mx = min(vals), max(vals)
                avg = sum(vals) / len(vals)
                dv = last - first
                trend = "rosnie" if dv > 0 else ("spada" if dv < 0 else "plasko")
                u = (" " + unit) if unit else ""
                lines.append(
                    "- %s: start %s%s -> koniec %s%s (zmiana %s%s%s, %s); min %s%s, max %s%s, srednia %s%s; %d pkt"
                    % (label, _rr(first, dec), u, _rr(last, dec), u,
                       ("+" if dv > 0 else ""), _rr(dv, dec), u, trend,
                       _rr(mn, dec), u, _rr(mx, dec), u, _rr(avg, dec), u, len(vals))
                )
            system = (
                "Jestes doswiadczonym fizjologiem wysilku i analitykiem treningu kolarskiego (model CP/W', "
                "periodyzacja). " + _PROFILE +
                "Dostajesz statystyki serii widocznych na wykresie w wybranym oknie czasu - jako material do OCENY, "
                "nie do opisania. Zdiagnozuj trend w tym oknie i jego przyczyne oraz wychwyc anomalie i sprzecznosci "
                "miedzy widocznymi seriami." + _STYLE
            )
            prompt = ("OKNO WYKRESU: %s -> %s (%d dni)\nWIDOCZNE SERIE:\n%s\n\nZinterpretuj to okno: diagnoza trendu i jego przyczyny + anomalie/sprzecznosci miedzy seriami. Bez zalecen co robic."
                      % (start, end, ndays, "\n".join(lines)))
            _subj_rows = _forma_feel_illness_window(conn, start, end)
            _subj_lines = _forma_subjective_window_lines(_subj_rows)
            if _subj_lines:
                prompt = prompt + "\n\nWPISY SAMOPOCZUCIA/CHOROBY W OKNIE (subiektyw zawodnika, NIE z czujnikow):\n" + "\n".join(_subj_lines)
            mt = 500
        else:
            end_d = _dt_date.today()
            start_d = end_d - _dt_timedelta(days=90)
            data = _build_forma_data(conn, start_d.isoformat(), end_d.isoformat())
            series = data.get("series") or []
            latest = data.get("latest") or {}
            if not series:
                return {"text": "Brak danych do analizy."}
            end_day = series[-1].get("day") or end_d.isoformat()

            def _cut(nd):
                return (_dt_date.fromisoformat(end_day) - _dt_timedelta(days=nd)).isoformat()

            order = ["tsb", "tsbp", "ctl", "atl", "atlp", "ftp", "ltp", "wp", "wkg", "rdy", "rdye", "hrv", "rhr", "slp", "glyc"]
            lines = []
            for k in order:
                field, label, unit, dec = _MAP[k]
                cur = (latest.get(field) or {}).get("value")
                if cur is None and k != "glyc":
                    cur = _last(series, field)
                if cur is None:
                    continue
                u = (" " + unit) if unit else ""
                seg = "%s: %s%s" % (label, _rr(cur, dec), u)
                parts = []
                for nd in (7, 30, 90):
                    past = _last(series, field, _cut(nd))
                    if past is not None:
                        dv = cur - past
                        parts.append("d%d %s%s" % (nd, ("+" if dv >= 0 else ""), _rr(dv, dec)))
                if parts:
                    seg += " (zmiana: " + ", ".join(parts) + ")"
                lines.append("- " + seg)
            rl = (latest.get("readiness_label") or {}).get("value")
            rn = (latest.get("readiness_note") or {}).get("value")
            wc = (latest.get("wprime_confidence") or {}).get("value")
            extra = []
            rle = (latest.get("readiness_effective_label") or {}).get("value")
            ren = (latest.get("readiness_effective_note") or {}).get("value")
            if rl:
                extra.append("gotowosc obiektywna: %s" % rl)
            if rle:
                extra.append("gotowosc efektywna: %s" % rle)
            if ren and ("feel" in str(ren) or "choroba" in str(ren)):
                extra.append(str(ren)[:140])
            if wc:
                extra.append("pewnosc W': %s" % wc)
            if rn:
                extra.append("nota: %s" % str(rn)[:160])
            _snap = ("STAN NA DZIS (" + end_day + "):\n" + "\n".join(lines)
                     + (("\n" + " | ".join(extra)) if extra else ""))
            _feel, _feel_note, _ill = _forma_feel_illness_for_day(conn, end_day)
            _subj = _forma_subjective_block(_feel, _feel_note, _ill)
            if _subj:
                _snap = _snap + "\n" + _subj
            if mode == "coach":
                system = (
                    "Jestes doswiadczonym trenerem kolarstwa i fizjologiem wysilku (model CP/W', periodyzacja). "
                    + _PROFILE +
                    "Dostajesz aktualny stan formy i zmiany 7/30/90 dni. Daj KONKRETNA, wykonalna PORADE co robic "
                    "lepiej: (1) na NAJBLIZSZEJ jezdzie, (2) w NAJBLIZSZYCH 7 DNIACH. Wyjdz od aktualnego obciazenia, "
                    "regeneracji i kierunku formy progowej, i dopasuj do celu (gravel/trwalosc, nie sciganie). Badz "
                    "konkretny: charakter i czas trwania jazdy, intensywnosc wzgledem progu (strefy lub W), ile dni "
                    "mocnych vs latwych w tygodniu, oraz regeneracja/odzywianie jesli to waskie gardlo. Realnie i "
                    "wykonalnie, bez frazesow, bez markdown i gwiazdek. PO POLSKU, prostym jezykiem, krotkie zdania, "
                    "zargon rozwijaj w nawiasie. Format: dwa krotkie akapity "
                    "zaczynajace sie doslownie od 'Najblizsza jazda:' oraz 'Najblizsze 7 dni:'. Opieraj sie na "
                    "danych, nie zmyslaj. Jesli zawodnik zglosil samopoczucie/chorobe - uwzglednij to w doradztwie (obciazenie/regeneracja), ale nie zmieniaj oceny progu CP/FTP/W'."
                )
                prompt = _snap + "\n\nDoradz co robic lepiej na najblizszej jezdzie i w najblizszych 7 dniach."
                mt = 560
            else:
                system = (
                    "Jestes doswiadczonym fizjologiem wysilku i analitykiem treningu kolarskiego (model CP/W', "
                    "periodyzacja). " + _PROFILE +
                    "Dostajesz aktualny stan formy i zmiany w oknach 7/30/90 dni - jako material do OCENY, nie do "
                    "opisania. Zdiagnozuj gdzie realnie jest ten zawodnik w cyklu (co ten uklad sygnalow oznacza), skad "
                    "sie to bierze, i wychwyc sprzecznosci (np. rozjazd progu ze swiezoscia/regeneracja)." + _STYLE
                )
                prompt = _snap + "\n\nZinterpretuj te dane: diagnoza trendu i sprzecznosci miedzy sygnalami. Bez zalecen co robic."
                mt = 520
    finally:
        conn.close()

    from qgpt_client import qgpt_text
    try:
        txt = qgpt_text(prompt, system=system, max_tokens=mt, temperature=0.35)
    except Exception as e:
        raise HTTPException(status_code=502, detail="LLM niedostepny: %s" % e)
    return {"text": (txt or "").strip().replace("**", "").replace("__", "")}


@app.get("/api/calendar")
def calendar_entries(start: str = Query(...), end: str = Query(...)):
    """Wpisy kalendarza w zakresie [start, end] (ISO YYYY-MM-DD). Zwraca event/feel/illness,
    z uwzglednieniem wpisow wielodniowych (end_day) nakladajacych sie na zakres."""
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT id, day::text AS day, kind, title, feel, severity, "
            "end_day::text AS end_day, note, color, event_type, at_time::text AS at_time, remind_offsets "
            "FROM qbot_v2.calendar_entry "
            "WHERE (day BETWEEN %s AND %s) "
            "   OR (end_day IS NOT NULL AND day <= %s AND end_day >= %s) "
            "ORDER BY day, id",
            (start, end, end, start),
        ).fetchall()
        frows = conn.execute(
            "SELECT day::text AS day, cp_modelq_w, ctl_xss, atl_raw, tsb_raw, "
            "ftp_est_w, wprime_modelq_kj, w_per_kg, readiness_score, readiness_label, "
            "hrv_night, rhr, sleep_h, glycogen_pct "
            "FROM qbot_v2.fitmodel_daily WHERE day BETWEEN %s AND %s ORDER BY day",
            (start, end),
        ).fetchall()
        rrows = conn.execute(
            "SELECT date::text AS day, external_id, activity_name, sport_type, "
            "distance_m, duration_s, tss, normalized_power_w, "
            "started_at::text AS started_at, activity_training_load "
            "FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s "
            "ORDER BY date, started_at",
            (start, end),
        ).fetchall()
        troute = conn.execute(
            "SELECT entry_id, day::text AS day, route_id, route_name "
            "FROM qbot_v2.calendar_day_route WHERE day BETWEEN %s AND %s",
            (start, end),
        ).fetchall()
    finally:
        conn.close()

    def _n(v, d=0):
        if v is None:
            return None
        return round(float(v), d) if d else round(float(v))

    days = {}
    for r in frows:
        days[r["day"]] = {
            "cp": _n(r["cp_modelq_w"]), "ctl": _n(r["ctl_xss"], 1),
            "atl": _n(r["atl_raw"], 1), "tsb": _n(r["tsb_raw"], 1),
            "ftp": _n(r["ftp_est_w"]), "wprime": _n(r["wprime_modelq_kj"], 1),
            "wkg": _n(r["w_per_kg"], 2), "readiness": _n(r["readiness_score"], 2),
            "readiness_label": r["readiness_label"], "hrv": _n(r["hrv_night"]),
            "rhr": _n(r["rhr"]), "sleep": _n(r["sleep_h"], 1), "glyc": _n(r["glycogen_pct"]),
        }
    rides = {}
    for r in rrows:
        st = r["started_at"]
        rides.setdefault(r["day"], []).append({
            "ride_key": r["external_id"],
            "name": r["activity_name"] or (r["sport_type"] or "jazda"),
            "sport": r["sport_type"],
            "dist_km": _n((r["distance_m"] or 0) / 1000.0, 1),
            "dur_h": _n((r["duration_s"] or 0) / 3600.0, 2),
            "tss": _n(r["tss"]), "np": _n(r["normalized_power_w"]),
            "strain": _n(r["activity_training_load"]),
            "time": (st[11:16] if st and len(st) >= 16 else None),
        })
    entry_routes = [
        {"entry_id": r["entry_id"], "day": r["day"],
         "route_id": r["route_id"], "route_name": r["route_name"]}
        for r in troute
    ]
    return {"start": start, "end": end, "entries": rows, "days": days,
            "rides": rides, "entry_routes": entry_routes}


@app.post("/api/calendar/entry")
async def calendar_add(request: Request):
    """Dodaje wpis kalendarza. body: {day, kind, title?, feel?, severity?, end_day?, note?}.
    kind: 'event' | 'feel' (samopoczucie -2..2) | 'illness' (choroba)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bledny JSON")

    def _s(key, n):
        v = body.get(key)
        if v in (None, ""):
            return None
        return str(v).strip()[:n]

    day = _s("day", 10)
    kind = (str(body.get("kind") or "")).strip()
    if not day or kind not in ("event", "feel", "illness", "reminder"):
        raise HTTPException(status_code=400, detail="Wymagane: day + kind (event|feel|illness|reminder)")
    title = _s("title", 200)
    note = _s("note", 2000)
    severity = _s("severity", 20)
    end_day = _s("end_day", 10)
    feel = body.get("feel")
    if feel is not None and feel != "":
        try:
            feel = max(-2, min(2, int(feel)))
        except (TypeError, ValueError):
            feel = None
    else:
        feel = None

    conn = _db_conn()
    try:
        row = conn.execute(
            "INSERT INTO qbot_v2.calendar_entry (day, kind, title, feel, severity, end_day, note, color, event_type, at_time, remind_offsets) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (day, kind, title, feel, severity, end_day, note, _s("color", 20), _s("event_type", 20), _s("at_time", 8), _s("remind_offsets", 20)),
        ).fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Zapis nieudany: %s" % e)
    finally:
        conn.close()
    return {"ok": True, "id": (row["id"] if row else None)}


@app.post("/api/calendar/delete")
async def calendar_delete(request: Request):
    """Usuwa wpis kalendarza po id. body: {id}."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bledny JSON")
    try:
        eid = int(body.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Wymagane: id (liczba)")
    conn = _db_conn()
    try:
        conn.execute("DELETE FROM qbot_v2.calendar_entry WHERE id=%s", (eid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.post("/api/calendar/edit")
async def calendar_edit(request: Request):
    """Edytuje wpis kalendarza po id. body: {id, title?, feel?, severity?, end_day?, note?}.
    Zmienia tylko tresc (title/feel/severity/end_day/note); day i kind pozostaja bez zmian."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bledny JSON")
    try:
        eid = int(body.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Wymagane: id (liczba)")

    def _s(key, n):
        v = body.get(key)
        if v in (None, ""):
            return None
        return str(v).strip()[:n]

    title = _s("title", 200)
    note = _s("note", 2000)
    severity = _s("severity", 20)
    end_day = _s("end_day", 10)
    feel = body.get("feel")
    if feel is not None and feel != "":
        try:
            feel = max(-2, min(2, int(feel)))
        except (TypeError, ValueError):
            feel = None
    else:
        feel = None

    conn = _db_conn()
    try:
        row = conn.execute(
            "UPDATE qbot_v2.calendar_entry SET title=%s, feel=%s, severity=%s, end_day=%s, note=%s, color=%s, event_type=%s, at_time=%s, remind_offsets=%s "
            "WHERE id=%s RETURNING id",
            (title, feel, severity, end_day, note, _s("color", 20), _s("event_type", 20), _s("at_time", 8), _s("remind_offsets", 20), eid),
        ).fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Zapis nieudany: %s" % e)
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Nie ma wpisu o tym id")
    return {"ok": True, "id": row["id"]}


@app.post("/api/calendar/route")
async def calendar_route(request: Request):
    """Przypina/odpina trase do konkretnego dnia eventu. body: {entry_id, day, route_id?, route_name?}.
    Pusty route_id => odpiecie (usuniecie wiersza)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Bledny JSON")
    try:
        entry_id = int(body.get("entry_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Wymagane: entry_id (liczba)")
    day = (str(body.get("day") or "")).strip()[:10]
    if not day:
        raise HTTPException(status_code=400, detail="Wymagane: day")
    route_id = body.get("route_id")
    route_id = (str(route_id).strip()[:64]) if route_id not in (None, "") else None
    route_name = body.get("route_name")
    route_name = (str(route_name).strip()[:200]) if route_name not in (None, "") else None
    conn = _db_conn()
    try:
        if route_id is None:
            conn.execute(
                "DELETE FROM qbot_v2.calendar_day_route WHERE entry_id=%s AND day=%s",
                (entry_id, day),
            )
        else:
            conn.execute(
                "INSERT INTO qbot_v2.calendar_day_route (entry_id, day, route_id, route_name) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (entry_id, day) DO UPDATE SET route_id=EXCLUDED.route_id, route_name=EXCLUDED.route_name",
                (entry_id, day, route_id, route_name),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Zapis nieudany: %s" % e)
    finally:
        conn.close()
    return {"ok": True}


_FORMA_FIELDS = [
    "ftp_est_w", "w_per_kg", "weight_kg", "cp_modelq_w", "ltp_modelq_w",
    "wprime_modelq_kj", "wprime_lo_kj", "wprime_hi_kj", "wprime_confidence",
    "glycogen_pct", "sleep_h", "sleep_score", "hrv_night", "rhr",
    "readiness_score", "readiness_label", "readiness_note",
    "readiness_effective", "readiness_effective_label", "readiness_subj_delta", "readiness_effective_note",
    "ctl_xss", "atl_raw", "tsb_raw",
    "atl_plus", "tsb_plus", "xss_hidden_subj", "atl_hidden_subj", "atl_plus_note",
]


def _forma_num(v):
    return float(v) if v is not None else None


def _forma_row_out(r):
    out = {"day": r["day"].isoformat()}
    for f in _FORMA_FIELDS:
        v = r[f]
        out[f] = v if f in ("wprime_confidence", "readiness_label", "readiness_note", "readiness_effective_label", "readiness_effective_note", "atl_plus_note") else _forma_num(v)
    return out


def _build_training_load_latest(conn, end_str, lookback_days=400):
    """Ostatnia NIE-NULL wartosc CTL/ATL/TSB (fitmodel/training_load.py, silnik gotowy
    od 2026-07-07 -- patrz DECISIONS.md 2026-07-07 (6)). Pokazujemy warianty 'raw'
    (ctl/atl/tsb bez korekty -- standardowy Bannister/Coggan, porownywalny z innymi
    narzedziami) jako glowne ctl/atl/tsb w banerze; 'plus' (skorygowane readiness_score)
    dolaczone jako dodatkowe pola na przyszlosc, frontend ich dzis nie uzywa."""
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    start_str = (_dt_date.fromisoformat(end_str) - _dt_timedelta(days=lookback_days)).isoformat()
    rows = conn.execute(
        "SELECT day, ctl_xss, atl_raw, atl_plus, tsb_raw, tsb_plus "
        "FROM qbot_v2.fitmodel_daily WHERE day BETWEEN %s AND %s "
        "AND ctl_xss IS NOT NULL ORDER BY day DESC LIMIT 1",
        (start_str, end_str),
    ).fetchall()
    if not rows:
        return None
    r = rows[0]
    return {
        "day": r["day"].isoformat(),
        "ctl": _forma_num(r["ctl_xss"]),
        "atl": _forma_num(r["atl_raw"]),
        "tsb": _forma_num(r["tsb_raw"]),
        "atl_plus": _forma_num(r["atl_plus"]),
        "tsb_plus": _forma_num(r["tsb_plus"]),
    }


def _build_forma_data(conn, start_str, end_str):
    """Dane pod kafelek 'Forma (ModelQ)'. Zywy stan (2026-07-07): CP/LTP/W'/readiness
    gesto wypelnione od 2026-05-01, FTP_est/W_per_kg/sen/RHR/glikogen dziurawe -
    frontend renderuje je jako punkty, nie linie (patrz forma-render.js).
    CTL/ATL/TSB (trening load, fitmodel/training_load.py) wpiete 2026-07-07 -- patrz
    DECISIONS.md 2026-07-07 (6)."""
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    _dbcols = [c for c in _FORMA_FIELDS if c != "sleep_score"]
    cols = ", ".join("f." + c for c in _dbcols)
    _sleep_sub = "(SELECT max(w.sleep_score) FROM qbot_v2.qbot_wellness_daily w WHERE w.date=f.day) AS sleep_score"
    rows = conn.execute(
        f"SELECT f.day AS day, {cols}, {_sleep_sub} FROM qbot_v2.fitmodel_daily f "
        "WHERE f.day BETWEEN %s AND %s ORDER BY f.day",
        (start_str, end_str),
    ).fetchall()
    series = [_forma_row_out(r) for r in rows]

    # "dzis" - ostatnia NIE-NULL wartosc kazdego pola, niezaleznie od wybranego zakresu
    # (zeby waskie okno w wykresie nie psulo kart z aktualna forma).
    latest_rows = conn.execute(
        f"SELECT f.day AS day, {cols}, {_sleep_sub} FROM qbot_v2.fitmodel_daily f "
        "WHERE f.day BETWEEN %s AND %s ORDER BY f.day",
        ((_dt_date.fromisoformat(end_str) - _dt_timedelta(days=400)).isoformat(), end_str),
    ).fetchall()
    latest_series = [_forma_row_out(r) for r in latest_rows]
    latest = {}
    for f in _FORMA_FIELDS:
        found = None
        for r in reversed(latest_series):
            if r[f] is not None:
                found = {"value": r[f], "day": r["day"]}
                break
        latest[f] = found or {"value": None, "day": None}

    # Glikogen: pokazuj stan DNIA KONCOWEGO (bez przenoszenia ostatniej niepustej w przod).
    # Brak wpisow zywienia => None => kafel "brak danych", nie mylace stare 0%/21%.
    _endrow = next((r for r in reversed(latest_series) if r["day"] == end_str), None)
    for _gf in ("glycogen_pct", "glycogen_g"):
        if _gf in _FORMA_FIELDS:
            _gv = _endrow.get(_gf) if _endrow else None
            latest[_gf] = {"value": _gv, "day": (end_str if _gv is not None else None)}

    return {
        "range": {"start": start_str, "end": end_str},
        "series": series,
        "latest": latest,
        "training_load": _build_training_load_latest(conn, end_str),
    }


@app.get("/api/forma/data")
def forma_data(response: Response, start: str | None = Query(None), end: str | None = Query(None)):
    """Forma (ModelQ): dane 'dzis' + szereg czasowy do wykresu. Domyslny zakres 90 dni."""
    response.headers["Cache-Control"] = "no-store"
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    end_d = _dt_date.fromisoformat(end) if end else _dt_date.today()
    start_d = _dt_date.fromisoformat(start) if start else (end_d - _dt_timedelta(days=90))
    conn = _db_conn()
    try:
        return _build_forma_data(conn, start_d.isoformat(), end_d.isoformat())
    finally:
        conn.close()


# ---------- ODZYWIANIE (zywienie + body composition) ----------
def _build_nutrition_data(conn, start_str, end_str):
    """Dane dzienne odzywiania: energia (albert_day_view), waga (fitmodel_daily),
    sklad ciala (body_trend_full_composition = Garmin INDEX_SCALE, do lipca). Zwraca series + latest."""
    from datetime import date as _dt_date
    today = _dt_date.today().isoformat()
    rows = conn.execute(
        "SELECT date::text AS day, intake_kcal, intake_protein_g, intake_carbs_g, intake_fat_g, "
        "active_kcal, resting_kcal, expenditure_kcal, balance_kcal, has_intake, intake_source "
        "FROM qbot_v2.albert_day_view WHERE date BETWEEN %s AND %s AND date <= %s ORDER BY date",
        (start_str, end_str, today),
    ).fetchall()
    wrows = conn.execute(
        "SELECT day::text AS day, weight_kg FROM qbot_v2.fitmodel_daily "
        "WHERE day BETWEEN %s AND %s ORDER BY day",
        (start_str, end_str),
    ).fetchall()
    wmap = {r["day"]: _forma_num(r["weight_kg"]) for r in wrows}
    brows = conn.execute(
        "SELECT date::text AS day, max(body_fat_pct) AS body_fat_pct, "
        "max(muscle_mass_kg) AS muscle_mass_kg, max(body_water_pct) AS body_water_pct, "
        "max(bmi) AS bmi "
        "FROM qbot_v2.body_trend_full_composition WHERE date BETWEEN %s AND %s GROUP BY date ORDER BY date",
        (start_str, end_str),
    ).fetchall()
    bmap = {r["day"]: r for r in brows}
    series = []
    for r in rows:
        d = r["day"]
        b = bmap.get(d)
        series.append({
            "day": d,
            "kcal_total": _forma_num(r["expenditure_kcal"]),
            "kcal_active": _forma_num(r["active_kcal"]),
            "kcal_passive": _forma_num(r["resting_kcal"]),
            "intake_kcal": _forma_num(r["intake_kcal"]),
            "protein_g": _forma_num(r["intake_protein_g"]),
            "carbs_g": _forma_num(r["intake_carbs_g"]),
            "fat_g": _forma_num(r["intake_fat_g"]),
            "balance_kcal": _forma_num(r["balance_kcal"]),
            "weight_kg": wmap.get(d),
            "body_fat_pct": _forma_num(b["body_fat_pct"]) if b else None,
            "muscle_mass_kg": _forma_num(b["muscle_mass_kg"]) if b else None,
            "body_water_pct": _forma_num(b["body_water_pct"]) if b else None,
            "intake_source": r["intake_source"],
        })
    _fields = ["kcal_total", "kcal_active", "kcal_passive", "intake_kcal", "protein_g",
               "carbs_g", "fat_g", "balance_kcal", "weight_kg", "body_fat_pct",
               "muscle_mass_kg", "body_water_pct"]
    latest = {}
    for f in _fields:
        found = {"value": None, "day": None}
        for row in reversed(series):
            if row.get(f) is not None:
                found = {"value": row[f], "day": row["day"]}
                break
        latest[f] = found
    body_latest = {}
    for col in ("body_fat_pct", "muscle_mass_kg", "body_water_pct"):
        rr = conn.execute(
            "SELECT date::text AS day, max(%s) AS v FROM qbot_v2.body_trend_full_composition "
            "WHERE %s IS NOT NULL GROUP BY date ORDER BY date DESC LIMIT 1" % (col, col)
        ).fetchone()
        body_latest[col] = {"value": _forma_num(rr["v"]), "day": rr["day"]} if rr else {"value": None, "day": None}
    rw = conn.execute(
        "SELECT day::text AS day, weight_kg FROM qbot_v2.fitmodel_daily "
        "WHERE weight_kg IS NOT NULL ORDER BY day DESC LIMIT 1"
    ).fetchone()
    body_latest["weight_kg"] = {"value": _forma_num(rw["weight_kg"]), "day": rw["day"]} if rw else {"value": None, "day": None}
    return {"series": series, "latest": latest, "body_latest": body_latest}


@app.get("/api/nutrition/data")
def nutrition_data(response: Response, start: str | None = Query(None), end: str | None = Query(None)):
    """Odzywianie: szereg dzienny (energia/intake/makro/bilans + waga + sklad ciala). Domyslnie 90 dni."""
    response.headers["Cache-Control"] = "no-store"
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    end_d = _dt_date.fromisoformat(end) if end else _dt_date.today()
    start_d = _dt_date.fromisoformat(start) if start else (end_d - _dt_timedelta(days=90))
    conn = _db_conn()
    try:
        return _build_nutrition_data(conn, start_d.isoformat(), end_d.isoformat())
    finally:
        conn.close()


@app.post("/api/nutrition/analyze")
async def nutrition_analyze(request: Request):
    """Analiza AI odzywiania: mode 'cards' (kafle/okno) lub 'chart' (zaleznosci na wykresie)."""
    body = await request.json()
    mode = (str(body.get("mode") or "cards")).strip()
    start = (str(body.get("start") or "")).strip()[:10]
    end = (str(body.get("end") or "")).strip()[:10]
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    end_d = _dt_date.fromisoformat(end) if end else _dt_date.today()
    start_d = _dt_date.fromisoformat(start) if start else (end_d - _dt_timedelta(days=30))
    conn = _db_conn()
    try:
        data = _build_nutrition_data(conn, start_d.isoformat(), end_d.isoformat())
    finally:
        conn.close()
    series = data.get("series") or []
    if not series:
        return {"text": "Brak danych odzywiania w tym oknie."}

    def _avg(f):
        vals = [r[f] for r in series if r.get(f) is not None]
        return round(sum(vals) / len(vals)) if vals else None

    intake_days = sum(1 for r in series if r.get("intake_kcal") is not None)
    lines = [
        "OKNO: %s -> %s (%d dni; wpisy jedzenia w %d dniach)" % (
            series[0]["day"], series[-1]["day"], len(series), intake_days),
        "Srednio/dzien: spalone total %s (aktywne %s / pasywne %s), zjedzone %s, bilans %s kcal." % (
            _avg("kcal_total"), _avg("kcal_active"), _avg("kcal_passive"),
            _avg("intake_kcal"), _avg("balance_kcal")),
        "Makro srednio/dzien: bialko %s g, wegle %s g, tluszcz %s g." % (
            _avg("protein_g"), _avg("carbs_g"), _avg("fat_g")),
    ]
    w0 = next((r["weight_kg"] for r in series if r.get("weight_kg") is not None), None)
    wl = next((r["weight_kg"] for r in reversed(series) if r.get("weight_kg") is not None), None)
    if w0 is not None and wl is not None:
        lines.append("Waga: %s -> %s kg (zmiana %s)." % (round(w0, 1), round(wl, 1), round(wl - w0, 1)))
    bf = None
    bf_day = None
    for r in reversed(series):
        if r.get("body_fat_pct") is not None:
            bf = r["body_fat_pct"]; bf_day = r["day"]; break
    if bf is not None:
        lines.append("Ostatni %%tluszczu: %s (pomiar %s; sklad ciala moze byc nieaktualny)." % (round(bf, 1), bf_day))
    snap = "\n".join(lines)

    _PROF = ("Zawodnik: kolarz gravel/touring, ~100 kg, cel dlugie jazdy w terenie, trwalosc/pojemnosc "
             "tlenowa, NIE sciganie. ")
    _ST = (" Odpowiadaj PO POLSKU, prostym ludzkim jezykiem, krotkie zdania, bez markdown i gwiazdek. "
           "Format: pierwszy wiersz = jedno zdanie werdyktu; potem 2-3 punkty od '- '. Max ~6 linii. "
           "Nie wyliczaj liczb bez sensu - powiedz CO TO ZNACZY. Nie zmyslaj - tylko z podanych danych.")
    if mode == "chart":
        system = ("Jestes dietetykiem sportowym i fizjologiem wysilku. " + _PROF +
                  "Patrzysz na WYKRES odzywiania: slupki spalone (aktywne+pasywne) vs zjedzone per dzien, "
                  "bilans dnia oraz krzywe wagi i skladu ciala. Zinterpretuj ZALEZNOSCI: zwiazek "
                  "deficytu/nadwyzki ze zmiana wagi/skladu, regularnosc jedzenia, dni bez wpisow." + _ST)
        prompt = snap + "\n\nZinterpretuj zaleznosci widoczne na wykresie odzywiania."
    else:
        system = ("Jestes dietetykiem sportowym i fizjologiem wysilku. " + _PROF +
                  "Dostajesz podsumowanie okna odzywiania (energia, makro, bilans, waga). Odczytaj gdzie "
                  "realnie jest bilans energetyczny i jakosc odzywiania wzgledem celu; wskaz 1-2 rzeczy "
                  "najwazniejsze (np. za malo bialka, chroniczny deficyt/nadwyzka, nieregularne wpisy)." + _ST)
        prompt = snap + "\n\nZinterpretuj te dane odzywiania: bilans, makro, jakosc. Krotko."
    from qgpt_client import qgpt_text
    try:
        txt = qgpt_text(prompt, system=system, max_tokens=520, temperature=0.35)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"text": txt}


def _f(v):
    return float(v) if v is not None else None


@app.get("/api/modelq2/data")
def modelq2_data(response: Response, start: str | None = Query(None), end: str | None = Query(None)):
    """ModelQ v2: dzienna sygnatura (TP/HIE/PP/LTP) z qbot_v2.modelq2_signature,
    nalozona na benchmark Xerta (qbot_v2.modelq2_xert_bench). Domyslny zakres 180 dni.
    Zwraca serie dzienne MQ2 + punkty Xerta + statystyki zgodnosci (blad na wspolnych dniach)."""
    response.headers["Cache-Control"] = "no-store"
    from datetime import date as _dt_date, timedelta as _dt_timedelta
    end_d = _dt_date.fromisoformat(end) if end else _dt_date.today()
    start_d = _dt_date.fromisoformat(start) if start else (end_d - _dt_timedelta(days=180))
    conn = _db_conn()
    try:
        mq = conn.execute(
            "SELECT day, tp_w, hie_kj, pp_w, ltp_w, ctl, atl, tsb, tl_low, tl_high, tl_peak "
            "FROM qbot_v2.modelq2_signature "
            "WHERE day BETWEEN %s AND %s ORDER BY day",
            (start_d.isoformat(), end_d.isoformat()),
        ).fetchall()
        xb = conn.execute(
            "SELECT day, tp_w, hie_kj, pp_w, ltp_w, max_effort FROM qbot_v2.modelq2_xert_bench "
            "WHERE day BETWEEN %s AND %s ORDER BY day",
            (start_d.isoformat(), end_d.isoformat()),
        ).fetchall()

        # Xert LTP dzienny ze snapshotow (gestsze niz benchmark, ktory ma tylko dni-jazdy)
        xltp = conn.execute(
            "SELECT date, ltp_power_w FROM qbot_v2.xert_profile_snapshots "
            "WHERE ltp_power_w IS NOT NULL AND date BETWEEN %s AND %s ORDER BY date",
            (start_d.isoformat(), end_d.isoformat()),
        ).fetchall()
        xert_ltp_series = [{"day": r["date"].isoformat(), "ltp": _f(r["ltp_power_w"])} for r in xltp]
        xltp_by = {r["date"]: float(r["ltp_power_w"]) for r in xltp}

        def _d(r):
            return {k: (float(v) if isinstance(v, (int, float)) or (v is not None and k != "day" and k != "max_effort") else v)
                    for k, v in r.items()}
        mq_series = [{"day": r["day"].isoformat(), "tp": _f(r["tp_w"]), "hie": _f(r["hie_kj"]),
                      "pp": _f(r["pp_w"]), "ltp": _f(r["ltp_w"]),
                      "ctl": _f(r["ctl"]), "atl": _f(r["atl"]), "tsb": _f(r["tsb"]),
                      "tl_low": _f(r["tl_low"]), "tl_high": _f(r["tl_high"]), "tl_peak": _f(r["tl_peak"])}
                     for r in mq]
        xb_series = [{"day": r["day"].isoformat(), "tp": _f(r["tp_w"]), "hie": _f(r["hie_kj"]),
                      "pp": _f(r["pp_w"]), "ltp": _f(r["ltp_w"]), "bt": r["max_effort"]} for r in xb]

        # zgodnosc na wspolnych dniach
        xb_by = {r["day"]: r for r in xb}
        eh = []; et = []; ep = []; el = []
        for r in mq:
            xr = xb_by.get(r["day"])
            if xr:
                if r["hie_kj"] is not None and xr["hie_kj"] is not None:
                    eh.append(abs(float(r["hie_kj"]) - float(xr["hie_kj"])))
                if r["tp_w"] is not None and xr["tp_w"] is not None:
                    et.append(abs(float(r["tp_w"]) - float(xr["tp_w"])))
                if r["pp_w"] is not None and xr["pp_w"] is not None:
                    ep.append(abs(float(r["pp_w"]) - float(xr["pp_w"])))
            # LTP: porownaj z dziennym snapshotem Xerta (gestsze niz benchmark)
            xl = xltp_by.get(r["day"])
            if r["ltp_w"] is not None and xl is not None:
                el.append(abs(float(r["ltp_w"]) - xl))
        def _avg(a):
            return round(sum(a) / len(a), 2) if a else None
        latest = mq_series[-1] if mq_series else None
        return {
            "range": {"start": start_d.isoformat(), "end": end_d.isoformat()},
            "mq": mq_series,
            "xert": xb_series,
            "xert_ltp": xert_ltp_series,
            "latest": latest,
            "agreement": {"hie_kj": _avg(eh), "tp_w": _avg(et), "pp_w": _avg(ep),
                          "ltp_w": _avg(el), "n_common": len(et), "n_ltp": len(el)},
        }
    finally:
        conn.close()


app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
