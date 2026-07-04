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


@app.middleware("http")
async def _webauth_guard(request, call_next):
    """Logowanie formularzem + dlugotrwale ciasteczko sesji (365 dni), oprocz /healthz i /login.
    Dane logowania: /opt/qbot/app/.env.webauth
    klucze: WEBAUTH_USERS=login:haslo,login2:haslo2 ; WEBAUTH_TOKEN=<wartosc do podpisu>
    """
    if request.url.path in ("/healthz", "/login"):
        return await call_next(request)

    users, sign_val = _webauth_load()
    if not users:
        return await call_next(request)

    cookie_value = request.cookies.get("qbot_session", "")
    if _webauth_cookie_valid(cookie_value, sign_val, users):
        return await call_next(request)

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
        '<title>QBot Lab - logowanie</title>'
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
    """Szafa z garage.db (gear, active=1) pogrupowana kategoriami -> {kat:[marka model,...]}.
    Do LLM (dobor ubioru): Albert wybiera WYLACZNIE z tej listy. Cap 10/kat."""
    import sqlite3
    cat = {}
    try:
        c = sqlite3.connect("/opt/qbot/app/data/garage.db")
        _skip = {"helmet", "shoes"}
        for row in c.execute("SELECT category, brand, model FROM gear WHERE active=1 ORDER BY category"):
            k = (row[0] or "inne").strip()
            if k.lower() in _skip:
                continue
            nm = ((row[1] or "") + " " + (row[2] or "")).strip()
            if not nm:
                continue
            cat.setdefault(k, [])
            if nm not in cat[k] and len(cat[k]) < 10:
                cat[k].append(nm)
        c.close()
    except Exception:
        return {}
    return cat


def _report_prose(*, date_str, start_time, finish, dist_km, ascent_m, moving_h, total_h,
                  peak, weather_overall, weather_stages, risks,
                  forma, climbs, surface_blocks, fuel, resupply, gear, alerty,
                  opony_opcje, nawierzchnia_udzial):
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
        "komentarze_ryzyka: po JEDNYM stringu do KAZDEGO odcinka z odcinki_ryzyka (ta sama kolejnosc): "
        "czego sie spodziewac (tagi OSM) + krotka rada. Brak odcinkow -> []."
    )
    pay1 = {"trasa": _trasa, "peak_wbgt": peak, "pogoda_ogolem": weather_overall,
            "weather_stages": weather_stages, "odcinki_ryzyka": risks}
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
        "ubior: OBIEKT {\"opis\": string, \"rzeczy\": [{\"typ\",\"przyklad\",\"tryb\",\"uwaga\"}]}. Dobierz do TEJ pogody "
        "(odczuwalna min/max, WBGT, wiatr, deszcz) - NIE przesadzaj z warstwami: przy cieple (odczuwalna >=18 C) NIE proponuj zimowych/"
        "grubych/thermal/merino-winter rzeczy; lekkie i przewiewne. Kazda pozycja: typ = OGOLNY rodzaj (np. 'przewiewna koszulka', "
        "'spodenki z wkladka', 'wiatrowka'); przyklad = KONKRETNA rzecz z listy gear (dokladna nazwa) jako propozycja; "
        "tryb = 'na sobie' albo 'zabierz' (warstwy na chlod/deszcz jako 'zabierz'); uwaga = 1 krotkie zdanie. "
        "OBOWIAZKOWO dolacz: koszulka/jersey ORAZ spodenki z wkladka (kategoria 'Bottoms / Bibs'). NIE proponuj kasku ani butow. "
        "4-7 pozycji. przyklad WYLACZNIE z listy gear."
    )
    _pog_skrot = {"peak_wbgt": peak, "pogoda_ogolem": weather_overall, "alerty": alerty}
    pay2 = {"trasa": _trasa, "forma": forma, "climbs": climbs, "surface_blocks": surface_blocks,
            "nawierzchnia_udzial": nawierzchnia_udzial, "surface_legenda": _legenda,
            "fuel": fuel, "resupply": resupply, "gear": gear, "opony_opcje": opony_opcje,
            "pogoda": _pog_skrot}
    try:
        o2 = qgpt_json(json.dumps(pay2, ensure_ascii=False, default=str),
                       system=sys2, max_tokens=4000, temperature=0.3)
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

    # niezawodny mechanizm: szukamy wzdluz trasy do +-10 km od srodka kwartalu,
    # <=1 km od trasy, bez zamknietych; im blizej srodka tym lepiej (kubelki 2 km),
    # przy remisie otwarte przed nieznanym; zawsze raportujemy przesuniecie od srodka.
    AREA_HALF_KM = 10.0
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

    def _curate_area(center_km):
        win = [it for it in _sup_pool
               if abs(it["km"] - center_km) <= AREA_HALF_KM and (it["dist_m"] or 1e9) <= OFFROUTE_MAX_M]
        shop = _best_of(win, "hard_resupply", center_km)
        food = _best_of(win, "soft_food_stop", center_km)
        picks = [p for p in (shop, food) if p]
        picks.sort(key=lambda z: z["km"])
        return len(win), picks

    _resupply_out = []
    _used = set()
    for qlab, qkm in [("Q1", dist_km * 0.25), ("Q2", dist_km * 0.5), ("Q3", dist_km * 0.75)]:
        total, picks = _curate_area(qkm)
        picks = [p for p in picks if (p["name"], p["km"]) not in _used]
        for p in picks:
            _used.add((p["name"], p["km"]))
        _resupply_out.append({"area": qlab, "q_km": round(qkm, 1), "total": total,
                              "search_km": AREA_HALF_KM,
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

    poi_out = {"resupply": _resupply_out, "attractions": {"total": len(_att_cand), "items": _att_out}}
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
        if _s["k"] != 5:
            continue
        _len = round(_s["b"] - _s["a"], 2)
        if _len < 0.3:
            continue
        surface_risk.append({"a": _s["a"], "b": _s["b"], "km": _len,
                             "reason": _s.get("reason"), "osm": _risk_osm(_s["a"], _s["b"])})

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
    _tss = round((tmoving or 0) * (0.62 ** 2) * 100) if tmoving else None
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
             "vs_route": {"tss": _tss, "cho_g": _fuel.get("carbs_total_g"), "cho_g_h": _fuel.get("carbs_g_h"),
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
            opony_opcje=_tire_options, nawierzchnia_udzial=_naw_udzial)
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
        "alerts": m.get("alerts") or [],
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


@app.get("/api/report/data")
def report_data(route_id: str = Query(...), date: str = Query(...),
                time: str = Query("10:00"), long_stops: int = Query(0),
                long_stop_min: int = Query(0)):
    """Zwraca blok DATA raportu trasy (JSON) - generator w QBocie. Zapisuje tez do archiwum."""
    conn = _db_conn()
    try:
        data = _build_report_data(conn, route_id, date, time, long_stops, long_stop_min)
        _save_report_snapshot(conn, route_id, date, time, long_stops, long_stop_min, data)
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
        return row["data_json"]
    finally:
        conn.close()


_SCAT_LABEL = {1: "Asfalt", 2: "Dobry gravel/szuter", 3: "Zwykly gravel", 4: "Trudna/wolna", 5: "Ryzyko"}
_SCAT_COLOR = {1: "#000000", 2: "#2e7d32", 3: "#8bc34a", 4: "#e07b1a", 5: "#c2452f"}
_ALERT_TYP_LABEL = {"upa\u0142": "UPA\u0141", "upal": "UPA\u0141", "deszcz": "DESZCZ", "burza": "BURZA", "zimno": "ZIMNO"}
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
    if t in ("upa\u0142", "upal"):
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


def _build_report_email_html(data, has_map, has_chart):
    """Uproszczony raport - sekcje jedna pod drugą, do maila (bez interaktywnej mapy/wykresu)."""
    r = data.get("route", {}) or {}
    st = data.get("start", {}) or {}
    tm = data.get("time", {}) or {}
    det = data.get("details", {}) or {}
    surf = det.get("surface", {}) or {}
    wea = det.get("weather", {}) or {}
    alerts = data.get("alerts") or []
    H = '<h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#7a838c;margin:22px 0 6px">'

    p = []
    p.append('<div style="font-family:-apple-system,Arial,sans-serif;color:#1c2024;max-width:640px;line-height:1.5">')
    p.append('<h1 style="font-size:22px;margin:0 0 4px">%s</h1>' % _esc(r.get("name") or ("Trasa %s" % r.get("id", ""))))
    sub = "%.1f km" % (r.get("distance_km") or 0)
    if r.get("ascent_m") is not None:
        sub += " \u00b7 %s m w g\u00f3r\u0119" % r["ascent_m"]
    if det.get("climbs", {}).get("descent_m") is not None:
        sub += " \u00b7 %s m w d\u00f3\u0142" % det["climbs"]["descent_m"]
    p.append('<p style="color:#555;margin:0 0 18px">%s</p>' % sub)

    miejsce = ", ".join([x for x in [st.get("miejscowosc"), st.get("gmina")] if x])
    p.append(H + 'Start</h2>')
    p.append('<p style="margin:0">%s, godz. %s%s</p>' % (
        _esc(st.get("date") or ""), _esc(st.get("time") or ""),
        (" \u00b7 " + _esc(miejsce)) if miejsce else ""))

    p.append(H + 'Szacowany czas</h2>')
    spd = (" \u00b7 %s km/h" % tm.get("speed_net_kmh")) if tm.get("speed_net_kmh") else ""
    p.append('<p style="margin:0">w ruchu %s \u00b7 ca\u0142kowity %s%s</p>' % (
        _fmt_h(tm.get("moving_h")), _fmt_h(tm.get("total_h")), spd))

    if has_map:
        p.append(H + 'Mapa</h2>')
        p.append('<img src="cid:reportmap" style="width:100%;max-width:600px;border-radius:8px;border:1px solid #e3ddd2" alt="mapa trasy">')

    p.append(H + 'Pogoda</h2>')
    for line in (wea.get("ogolne") or []):
        p.append('<p style="margin:0 0 4px">%s</p>' % _esc(line))
    etapy = wea.get("etapy") or []
    if etapy:
        p.append('<ul style="margin:8px 0 0;padding-left:18px">')
        for e in etapy:
            p.append('<li style="margin:0 0 4px"><b>%s:</b> %s</li>' % (_esc(e.get("naglowek") or ""), _esc(e.get("tekst") or "")))
        p.append('</ul>')

    if has_chart:
        p.append(H + 'Profil trasy</h2>')
        p.append('<img src="cid:reportchart" style="width:100%;max-width:600px;border-radius:8px;border:1px solid #e3ddd2" alt="profil trasy">')

    p.append(H + 'Nawierzchnia</h2>')
    by_cat = surf.get("by_cat") or []
    if by_cat:
        p.append('<ul style="margin:0;padding-left:0;list-style:none">')
        for c in by_cat:
            col = _SCAT_COLOR.get(c.get("k"), "#999")
            lab = _SCAT_LABEL.get(c.get("k"), "kat. %s" % c.get("k"))
            p.append('<li style="margin:0 0 4px"><span style="display:inline-block;width:10px;height:10px;'
                      'background:%s;border-radius:2px;margin-right:6px"></span>%s: %s km (%s%%)</li>' % (
                          col, _esc(lab), c.get("km"), c.get("pct")))
        p.append('</ul>')
    risk = surf.get("risk") or []
    if risk:
        p.append('<p style="margin:14px 0 4px"><b>Odcinki ryzykowne:</b></p>')
        p.append('<ul style="margin:0;padding-left:18px">')
        for rr in risk:
            p.append('<li style="margin:0 0 4px">km %s\u2013%s (%s km): %s</li>' % (
                rr.get("a"), rr.get("b"), rr.get("km"), _esc(rr.get("comment") or rr.get("reason") or "")))
        p.append('</ul>')

    if alerts:
        p.append('<h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#b0402c;margin:22px 0 6px">Ostrze\u017cenia</h2>')
        p.append('<ul style="margin:0;padding-left:18px">')
        for a in alerts:
            p.append('<li style="margin:0 0 4px">%s</li>' % _esc(_alert_line(a)))
        p.append('</ul>')

    p.append('<p style="margin:26px 0 0;color:#7a838c;font-size:12px">W za\u0142\u0105czniku plik GPX trasy (do wgrania w nawigacji/zegarku).</p>')
    p.append('</div>')
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
                context = browser.new_context(viewport={"width": 900, "height": 700})
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
def report_send_email(route_id: str = Query(...), date: str = Query(...),
                      time: str = Query("10:00"), long_stops: int = Query(0),
                      long_stop_min: int = Query(0), to: str = Query(...)):
    """Liczy raport (zapisuje do archiwum), robi zrzuty mapy+wykresu, dolacza GPX,
    wysyla uproszczony raport mailem (to samo konto co poranny raport)."""
    to = (to or "").strip()
    if not _EMAIL_RE.match(to):
        raise HTTPException(status_code=400, detail="Nieprawidlowy adres e-mail")

    conn = _db_conn()
    try:
        data = _build_report_data(conn, route_id, date, time, long_stops, long_stop_min)
        snap_id = _save_report_snapshot(conn, route_id, date, time, long_stops, long_stop_min, data)
        geo = route_geometry(route_id)
        coords = geo.get("coordinates") or []
    finally:
        conn.close()

    map_png = chart_png = None
    if snap_id:
        map_png, chart_png = _capture_report_images(snap_id)

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
        safe = _re_email.sub(r"[^A-Za-z0-9_.-]+", "_", data["route"]["name"] or route_id).strip("_") or ("route_%s" % route_id)
        gpx_att = MIMEApplication(gpx_xml.encode("utf-8"), _subtype="gpx+xml")
        gpx_att.add_header("Content-Disposition", "attachment", filename="%s.gpx" % safe)
        msg.attach(gpx_att)

    msg["Subject"] = "Raport trasy: %s - %s %s" % (data["route"]["name"], date, time)
    msg["From"] = _cfg.GMAIL_USER
    msg["To"] = to

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(_cfg.GMAIL_USER, _cfg.GMAIL_APP_PASSWORD)
            s.send_message(msg)
    except Exception as e:
        raise HTTPException(status_code=502, detail="Nie udalo sie wyslac maila: %s" % e)

    return {"status": "ok", "to": to, "has_map": bool(map_png), "has_chart": bool(chart_png), "has_gpx": bool(gpx_xml)}


app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
