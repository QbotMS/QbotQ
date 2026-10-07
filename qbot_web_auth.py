"""Tymczasowy dostep DEMO do qbot-web przez QR (2026-10-07). Dok.: docs/WEB_DEMO_AUTH.md

Przeplyw: komputer POST /auth/device/start -> QR + kod porownawczy; wlasciciel na telefonie
(pelna sesja qbot_session) GET /auth/device/approve?id= -> POST /auth/device/decide (CSRF);
komputer odpytuje GET /auth/device/status i po zatwierdzeniu POST /auth/device/claim
(sekret przegladarki z ciasteczka qbot_devreq) -> jedna sesja demo (ciasteczko qbot_demo).
Sesja demo: 1 h bezwzglednie, tylko odczyt wg listy dozwolonych, bez zatwierdzania urzadzen.
Unieważnianie: POST /auth/demo/logout (komputer) lub POST /api/auth/sessions/revoke (wlasciciel).
Surowe sekrety nie trafiaja do bazy ani logow (tylko sha256).
"""
import hashlib
import os
import hmac
import html
import re
import secrets
import time
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

REQ_TTL_S = 120            # waznosc QR / zadania
CLAIM_GRACE_S = 60         # ile po zatwierdzeniu (ponad TTL) komputer moze odebrac sesje
SESSION_TTL_S = 3600       # sesja demo: 1 h, bez przedluzania
SCOPE_DEMO = "read_all"    # podglad wszystkich modulow, bez zapisow
DEMO_COOKIE = "qbot_demo"
REQ_COOKIE = "qbot_devreq"
OWNER_COOKIE = "qbot_session"
MAX_PENDING = 20           # globalny limit oczekujacych zadan
POLL_MIN_INTERVAL_S = 1.0
DEMO_CACHE_S = 5.0         # krotki cache walidacji sesji demo (unieważnienie czysci cache)
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
# publiczny adres strony (QR musi prowadzic telefon na zewnetrzny HTTPS, nie na port lokalny)
PUBLIC_BASE = os.environ.get("QBOT_WEB_PUBLIC_URL", "https://albert.cytr.us")

PUBLIC_PATHS = frozenset({"/auth/device/start", "/auth/device/status", "/auth/device/claim"})

# --- polityka DEMO (tylko odczyt). Domyslnie ZAKAZ: /api/* tylko z listy ponizej.
FORBIDDEN_PARAMS = frozenset({"rebuild", "fresh", "force", "refresh", "recompute", "regen", "regenerate"})
DEMO_EXTRA_ALLOWED = frozenset({("POST", "/auth/demo/logout"), ("GET", "/auth/demo/whoami"),
                                ("HEAD", "/auth/demo/whoami")})
DEMO_BLOCKED_PAGES = frozenset({"/hammerhead-dostep", "/komoot-dostep", "/openapi.json", "/docs",
                                "/redoc", "/strava.html"})
# GET-y API dozwolone w demo ({} = jeden segment sciezki). Swiadomie POMINIETE: zaproszenia,
# adresy/grupy mailowe, RSVP, harmonogramy wysylek, towarzysze jazd (dane innych osob),
# Strava poza statusem, Komoot/Hammerhead, PDF-y, pogoda planera / noclegi / atrakcje / opis / tlo
# (AI lub platne Google przy braku cache). Nowe endpointy sa w demo ZABLOKOWANE, dopoki ktos ich tu nie doda.
DEMO_ALLOWED_API_GET = (
    "/api/prefs", "/api/config/map",
    "/api/forma/activities", "/api/forma/activity", "/api/forma/data", "/api/forma/event-prep",
    "/api/forma/season", "/api/forma/season/analyze", "/api/stats/rides", "/api/modelq2/data",
    "/api/routes/ready", "/api/routes/{}/geometry", "/api/routes/{}/spine", "/api/routes/{}/tiles",
    "/api/routes/{}/surface-segments", "/api/routes/{}/surface-categories",
    "/api/routes/{}/segments/candidate",
    "/api/report/data", "/api/report/plan", "/api/report/gpx", "/api/report/outfit",
    "/api/report/day-pack", "/api/report/day-packs", "/api/report/day-pack/status",
    "/api/report/history", "/api/report/snapshot/{}", "/api/route-intro",
    "/api/rides/ready", "/api/ride-report/data", "/api/ride-report/status", "/api/ride-report/tiles",
    "/api/ride-report/w2", "/api/ride-gear/options",
    "/api/planer/dzien", "/api/planer/dzien/gpx", "/api/planer/foto/{}", "/api/planer/termin",
    "/api/planer/wyposazenie/pogoda", "/api/planer/wyposazenie/garage-options",
    "/api/planer/wyposazenie/kategorie", "/api/planer/wyposazenie/zasady",
    "/api/planer/wyposazenie/list", "/api/planer/wyposazenie/bags", "/api/planer/wyposazenie/summary",
    "/api/planer/wyposazenie/termin",
    "/api/garage/list", "/api/garage/prefs", "/api/garage/audit", "/api/garage/audit/params",
    "/api/equipment/list", "/api/bike/config", "/api/instructions/list",
    "/api/calendar", "/api/calendar/wx",
    "/api/nutrition/status", "/api/nutrition/day-summary", "/api/nutrition/preset/values",
    "/api/nutrition/items", "/api/nutrition/data",
    "/api/trener/route_summary", "/api/trener/goals", "/api/trener/goals/status", "/api/trener/rules",
    "/api/trener/labs", "/api/trener/settings", "/api/trener/week", "/api/trener/health",
    "/api/trener/auto", "/api/trener/season", "/api/trener/exercises", "/api/trener/exercises/prompt",
    "/api/trener/sessions/{}/sheet", "/api/trener/balance", "/api/trener/time",
    "/api/komoot/session/status", "/api/strava/status", "/api/start/card",
)
_ALLOW_RX = tuple(re.compile(re.escape(t).replace(re.escape("{}"), "[^/]+")) for t in DEMO_ALLOWED_API_GET)

_deps = {}
_demo_cache = {}   # sha256(token) -> (info|None, checked_at)
_poll_last = {}    # request id -> czas ostatniego odpytania


def configure(db_conn, owner_user, sign_val):
    """db_conn() -> polaczenie psycopg (dict_row); owner_user(request) -> login z PELNEJ sesji albo None;
    sign_val() -> wartosc podpisu z konfiguracji (do tokenow CSRF)."""
    _deps.update(db=db_conn, owner=owner_user, sign=sign_val)


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _new_code():
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
    return raw[:3] + "-" + raw[3:]


def _csrf(request, purpose):
    sv = _deps["sign"]() or ""
    ck = request.cookies.get(OWNER_COOKIE, "")
    if not sv or not ck:
        return ""
    return hmac.new(sv.encode(), (purpose + "|" + ck).encode(), hashlib.sha256).hexdigest()


def _csrf_ok(request, purpose, given):
    exp = _csrf(request, purpose)
    return bool(exp) and isinstance(given, str) and hmac.compare_digest(exp, given)


def _nostore(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def clear_demo_cache():
    _demo_cache.clear()


# ---------------- sesja demo: walidacja i polityka ----------------

def demo_from_request(request):
    """Zwraca {'session_id','owner','scope','exp'} dla waznej sesji demo albo None (fail-closed)."""
    tok = request.cookies.get(DEMO_COOKIE, "")
    if not tok or len(tok) > 200:
        return None
    h = _sha(tok)
    now = time.time()
    c = _demo_cache.get(h)
    if c and now - c[1] < DEMO_CACHE_S:
        info = c[0]
    else:
        try:
            with _deps["db"]() as conn:
                row = conn.execute(
                    "SELECT id, owner, scope, extract(epoch FROM expires_at)::float8 AS exp "
                    "FROM qbot_v2.web_sessions WHERE token_hash=%s AND kind='demo' "
                    "AND revoked_at IS NULL AND expires_at > now()", (h,)).fetchone()
        except Exception:
            return None
        info = ({"session_id": row["id"], "owner": row["owner"], "scope": row["scope"], "exp": row["exp"]}
                if row else None)
        if len(_demo_cache) > 500:
            _demo_cache.clear()
        _demo_cache[h] = (info, now)
    if not info or info["exp"] <= now:
        return None
    return info


def demo_allows(method, path, query_keys=()):
    method = (method or "").upper()
    if (method, path) in DEMO_EXTRA_ALLOWED:
        return True
    if method not in ("GET", "HEAD"):
        return False
    if any(str(k).lower() in FORBIDDEN_PARAMS for k in query_keys):
        return False
    if path.startswith("/auth/"):
        return False
    if path.startswith("/api/"):
        return any(rx.fullmatch(path) for rx in _ALLOW_RX)
    # statyki: bez kopii zapasowych (*.bak*) i plikow roboczych (segment zaczynajacy sie od "_")
    if ".bak" in path or any(seg.startswith("_") for seg in path.split("/") if seg):
        return False
    return path not in DEMO_BLOCKED_PAGES


def demo_denied_response(request):
    if request.url.path.startswith(("/api/", "/auth/")) or request.method != "GET":
        return Response(status_code=403, content="demo: tylko podglad")
    return _nostore(HTMLResponse(status_code=403, content=(
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Tryb demo</title></head>'
        '<body style="font-family:system-ui,sans-serif;padding:2rem">'
        '<h1>Niedostepne w trybie demo</h1><p>Ta czesc nie jest pokazywana w dostepie tymczasowym.</p>'
        '<p><a href="/">Wroc na strone glowna</a></p></body></html>')))


# ---------------- strony HTML ----------------

_PAGE_CSS = ("body{font-family:-apple-system,system-ui,sans-serif;background:#0f1115;color:#e8e8e8;"
             "display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}"
             ".box{background:#1a1d24;padding:1.6rem 1.8rem;border-radius:12px;max-width:360px;width:90%}"
             "h1{font-size:1.1rem;color:#9fd3ff;margin:0 0 1rem}.code{font-size:2rem;letter-spacing:.15em;"
             "font-weight:700;text-align:center;margin:.6rem 0 1rem;color:#fff}.muted{color:#aaa;font-size:.85rem}"
             "button{width:100%;padding:.7rem;border:0;border-radius:8px;font-size:1rem;margin-top:.6rem;cursor:pointer}"
             ".ok{background:#22c55e;color:#04140a}.no{background:#374151;color:#eee}")


def _page(title, body, status=200):
    return _nostore(HTMLResponse(status_code=status, content=(
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>' + html.escape(title) + '</title><style>' + _PAGE_CSS + '</style></head>'
        '<body><div class="box">' + body + '</div></body></html>')))


def _read_req_cookie(request):
    v = request.cookies.get(REQ_COOKIE, "")
    if "." not in v or len(v) > 200:
        return None, None
    rid, sec = v.split(".", 1)
    return (rid, sec) if rid and sec else (None, None)


def build_router():
    r = APIRouter()

    @r.post("/auth/device/start")
    async def device_start(request: Request):
        rid = secrets.token_urlsafe(18)
        sec = secrets.token_urlsafe(32)
        code = _new_code()
        ua = (request.headers.get("user-agent") or "")[:200]
        with _deps["db"]() as conn:
            n = conn.execute(
                "SELECT count(*) AS n FROM qbot_v2.web_device_auth_requests "
                "WHERE status='PENDING' AND expires_at > now()").fetchone()["n"]
            if n >= MAX_PENDING:
                return _nostore(JSONResponse({"error": "too_many_pending"}, status_code=429))
            conn.execute(
                "INSERT INTO qbot_v2.web_device_auth_requests "
                "(id, browser_secret_hash, user_code, status, expires_at, device_info) "
                "VALUES (%s, %s, %s, 'PENDING', now() + make_interval(secs => %s), %s)",
                (rid, _sha(sec), code, REQ_TTL_S, ua))
        approve_path = "/auth/device/approve?id=" + rid
        try:
            import qbot_web_auth_ui as _ui
            qr = _ui.qr_svg(PUBLIC_BASE.rstrip("/") + approve_path)
        except Exception as e:
            print("qr_svg blad:", type(e).__name__)
            qr = None
        resp = JSONResponse({"id": rid, "code": code, "approve_path": approve_path,
                             "expires_in": REQ_TTL_S, "qr_svg": qr})
        resp.set_cookie(REQ_COOKIE, rid + "." + sec, max_age=REQ_TTL_S + CLAIM_GRACE_S,
                        httponly=True, secure=True, samesite="lax", path="/auth/device")
        return _nostore(resp)

    @r.get("/auth/device/status")
    async def device_status(request: Request):
        rid, sec = _read_req_cookie(request)
        if not rid:
            return _nostore(JSONResponse({"error": "no_request"}, status_code=401))
        now = time.time()
        last = _poll_last.get(rid)
        if last and now - last < POLL_MIN_INTERVAL_S:
            return _nostore(JSONResponse({"error": "slow_down"}, status_code=429))
        if len(_poll_last) > 2000:
            _poll_last.clear()
        _poll_last[rid] = now
        with _deps["db"]() as conn:
            row = conn.execute(
                "SELECT status, user_code, extract(epoch FROM expires_at)::float8 AS exp "
                "FROM qbot_v2.web_device_auth_requests WHERE id=%s AND browser_secret_hash=%s",
                (rid, _sha(sec))).fetchone()
            if not row:
                return _nostore(JSONResponse({"error": "unknown"}, status_code=404))
            st = row["status"]
            if st == "PENDING" and row["exp"] <= now:
                conn.execute("UPDATE qbot_v2.web_device_auth_requests SET status='EXPIRED' "
                             "WHERE id=%s AND status='PENDING'", (rid,))
                st = "EXPIRED"
            elif st == "APPROVED" and row["exp"] + CLAIM_GRACE_S <= now:
                st = "EXPIRED"
        return _nostore(JSONResponse({"status": st, "code": row["user_code"],
                                      "expires_in": max(0, int(row["exp"] - now))}))

    @r.post("/auth/device/claim")
    async def device_claim(request: Request):
        rid, sec = _read_req_cookie(request)
        if not rid:
            return _nostore(JSONResponse({"error": "no_request"}, status_code=401))
        tok = secrets.token_urlsafe(32)
        with _deps["db"]() as conn:
            with conn.transaction():
                row = conn.execute(
                    "UPDATE qbot_v2.web_device_auth_requests SET status='CONSUMED', consumed_at=now() "
                    "WHERE id=%s AND browser_secret_hash=%s AND status='APPROVED' "
                    "AND expires_at + make_interval(secs => %s) > now() "
                    "RETURNING approved_by, scope, session_ttl_s, device_info",
                    (rid, _sha(sec), CLAIM_GRACE_S)).fetchone()
                if not row:
                    return _nostore(JSONResponse({"error": "not_claimable"}, status_code=409))
                ttl = int(row["session_ttl_s"] or SESSION_TTL_S)
                s = conn.execute(
                    "INSERT INTO qbot_v2.web_sessions "
                    "(token_hash, owner, kind, scope, expires_at, request_id, device_info) "
                    "VALUES (%s, %s, 'demo', %s, now() + make_interval(secs => %s), %s, %s) RETURNING id",
                    (_sha(tok), row["approved_by"], row["scope"] or SCOPE_DEMO, ttl, rid,
                     row["device_info"])).fetchone()
                conn.execute("UPDATE qbot_v2.web_device_auth_requests SET session_id=%s WHERE id=%s",
                             (s["id"], rid))
        resp = JSONResponse({"ok": True, "redirect": "/", "expires_in": ttl})
        resp.set_cookie(DEMO_COOKIE, tok, max_age=ttl, httponly=True, secure=True, samesite="lax", path="/")
        resp.delete_cookie(REQ_COOKIE, path="/auth/device")
        return _nostore(resp)

    @r.get("/auth/device/approve", response_class=HTMLResponse)
    async def device_approve_page(request: Request, id: str = ""):
        owner = _deps["owner"](request)
        if not owner:
            return Response(status_code=303, headers={
                "Location": "/login?next=" + quote("/auth/device/approve?id=" + id, safe="")})
        with _deps["db"]() as conn:
            row = conn.execute(
                "SELECT status, user_code, device_info, expires_at > now() AS live "
                "FROM qbot_v2.web_device_auth_requests WHERE id=%s", (id,)).fetchone()
        if not row or row["status"] != "PENDING" or not row["live"]:
            return _page("Dostep tymczasowy", "<h1>Kod nieaktualny</h1>"
                         "<p class='muted'>Prosba wygasla albo zostala juz obsluzona. "
                         "Wygeneruj nowy kod QR na komputerze.</p>", status=410)
        csrf = _csrf(request, "decide|" + id)
        hid = ('<input type="hidden" name="id" value="' + html.escape(id, quote=True) + '">'
               '<input type="hidden" name="csrf" value="' + csrf + '">')
        body = ("<h1>Dostep tymczasowy dla komputera</h1>"
                "<p class='muted'>Sprawdz, czy ten sam kod widac na ekranie komputera:</p>"
                "<div class='code'>" + html.escape(row["user_code"]) + "</div>"
                "<p class='muted'>Konto: <b>" + html.escape(owner) + "</b><br>"
                "Zakres: podglad wszystkich modulow, bez zmian i zapisow<br>"
                "Czas: 1 godzina, potem automatyczne wylogowanie<br>"
                "Urzadzenie: " + html.escape(row["device_info"] or "nieznane") + "</p>"
                "<form method='post' action='/auth/device/decide'>" + hid +
                "<input type='hidden' name='decision' value='approve'>"
                "<button class='ok' type='submit'>Zatwierdz</button></form>"
                "<form method='post' action='/auth/device/decide'>" + hid +
                "<input type='hidden' name='decision' value='deny'>"
                "<button class='no' type='submit'>Odrzuc</button></form>")
        return _page("Dostep tymczasowy", body)

    @r.post("/auth/device/decide", response_class=HTMLResponse)
    async def device_decide(request: Request):
        owner = _deps["owner"](request)
        if not owner:
            return Response(status_code=403, content="owner session required")
        f = parse_qs((await request.body()).decode("utf-8", errors="replace"))
        rid = f.get("id", [""])[0]
        decision = f.get("decision", [""])[0]
        if decision not in ("approve", "deny") or not _csrf_ok(request, "decide|" + rid, f.get("csrf", [""])[0]):
            return Response(status_code=403, content="csrf")
        with _deps["db"]() as conn:
            if decision == "approve":
                row = conn.execute(
                    "UPDATE qbot_v2.web_device_auth_requests SET status='APPROVED', approved_by=%s, "
                    "approved_at=now(), scope=%s, session_ttl_s=%s "
                    "WHERE id=%s AND status='PENDING' AND expires_at > now() RETURNING id",
                    (owner, SCOPE_DEMO, SESSION_TTL_S, rid)).fetchone()
            else:
                row = conn.execute(
                    "UPDATE qbot_v2.web_device_auth_requests SET status='DENIED' "
                    "WHERE id=%s AND status='PENDING' RETURNING id", (rid,)).fetchone()
        if not row:
            return _page("Dostep tymczasowy", "<h1>Kod nieaktualny</h1><p class='muted'>Prosba wygasla "
                         "albo zostala juz obsluzona.</p>", status=410)
        if decision == "approve":
            return _page("Dostep tymczasowy", "<h1>Zatwierdzono</h1><p class='muted'>Komputer zaloguje sie "
                         "za chwile na 1 godzine. Dostep mozesz zakonczyc wczesniej w ustawieniach dostepu.</p>")
        return _page("Dostep tymczasowy", "<h1>Odrzucono</h1><p class='muted'>Komputer nie dostanie dostepu.</p>")

    @r.get("/auth/sessions", response_class=HTMLResponse)
    async def sessions_page(request: Request):
        if not _deps["owner"](request):
            return Response(status_code=303, headers={"Location": "/login?next=%2Fauth%2Fsessions"})
        import qbot_web_auth_ui as _ui
        return _page("Dostepy tymczasowe", _ui.SESSIONS_BODY)

    @r.post("/auth/demo/logout")
    async def demo_logout(request: Request):
        tok = request.cookies.get(DEMO_COOKIE, "")
        if tok and len(tok) <= 200:
            with _deps["db"]() as conn:
                conn.execute("UPDATE qbot_v2.web_sessions SET revoked_at=now() "
                             "WHERE token_hash=%s AND revoked_at IS NULL", (_sha(tok),))
            clear_demo_cache()
        resp = JSONResponse({"ok": True, "redirect": "/login"})
        resp.delete_cookie(DEMO_COOKIE, path="/")
        return _nostore(resp)

    @r.get("/auth/demo/whoami")
    async def demo_whoami(request: Request):
        a = request.scope.get("qbot_auth") or {}
        if a.get("kind") == "demo":
            return _nostore(JSONResponse({"kind": "demo", "expires_in": max(0, int(a["exp"] - time.time()))}))
        if _deps["owner"](request):
            return _nostore(JSONResponse({"kind": "owner"}))
        return _nostore(JSONResponse({"kind": "none"}, status_code=401))

    @r.get("/api/auth/sessions")
    async def sessions_list(request: Request):
        owner = _deps["owner"](request)
        if not owner:
            return Response(status_code=403, content="owner session required")
        with _deps["db"]() as conn:
            rows = conn.execute(
                "SELECT id, created_at, expires_at, device_info FROM qbot_v2.web_sessions "
                "WHERE owner=%s AND revoked_at IS NULL AND expires_at > now() ORDER BY created_at DESC",
                (owner,)).fetchall()
        return _nostore(JSONResponse({
            "sessions": [{"id": x["id"], "created_at": x["created_at"].isoformat(),
                          "expires_at": x["expires_at"].isoformat(), "device": x["device_info"]} for x in rows],
            "csrf": _csrf(request, "sessions")}))

    @r.post("/api/auth/sessions/revoke")
    async def sessions_revoke(request: Request):
        owner = _deps["owner"](request)
        if not owner:
            return Response(status_code=403, content="owner session required")
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not _csrf_ok(request, "sessions", body.get("csrf")):
            return Response(status_code=403, content="csrf")
        sid = body.get("id")
        with _deps["db"]() as conn:
            if sid == "all":
                n = conn.execute("UPDATE qbot_v2.web_sessions SET revoked_at=now() "
                                 "WHERE owner=%s AND revoked_at IS NULL", (owner,)).rowcount
            else:
                try:
                    sid = int(sid)
                except (TypeError, ValueError):
                    return Response(status_code=400, content="bad id")
                n = conn.execute("UPDATE qbot_v2.web_sessions SET revoked_at=now() "
                                 "WHERE id=%s AND owner=%s AND revoked_at IS NULL", (sid, owner)).rowcount
        clear_demo_cache()
        return _nostore(JSONResponse({"ok": True, "revoked": n}))

    return r
