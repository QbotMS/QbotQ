"""QBot dashboard — auth na podpisanym ciasteczku (stdlib) + realne metryki z qbot_v2.
Dodane 2026-06-19. Zero dodatkowych zaleznosci poza psycopg (juz w venv).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html as _html
import json
import os
import time

from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, RedirectResponse

router = APIRouter()

_USER = os.getenv("DASH_USER", "michal")
_SECRET = os.getenv("DASH_SECRET", "")
_SALT = os.getenv("DASH_SALT", "")
_PASS_HASH = os.getenv("DASH_PASS_HASH", "")
_COOKIE = "qdash"
_MAX_AGE = 7 * 24 * 3600


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _ub64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: bytes) -> str:
    p = _b64(payload)
    sig = hmac.new(_SECRET.encode(), p.encode(), hashlib.sha256).hexdigest()
    return p + "." + sig


def _verify(token: str):
    try:
        p, sig = token.split(".", 1)
        exp_sig = hmac.new(_SECRET.encode(), p.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, exp_sig):
            return None
        data = json.loads(_ub64(p))
        if float(data.get("exp", 0)) < time.time():
            return None
        return data
    except Exception:
        return None


def _check_pw(pw: str) -> bool:
    if not (_SALT and _PASS_HASH):
        return False
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(_SALT), 200000).hex()
    return hmac.compare_digest(h, _PASS_HASH)


def _make_cookie() -> str:
    payload = json.dumps({"u": _USER, "exp": int(time.time()) + _MAX_AGE}).encode()
    return _sign(payload)


def _authed(request: Request):
    tok = request.cookies.get(_COOKIE)
    return _verify(tok) if tok else None


def _set_cookie(resp, value: str):
    resp.set_cookie(
        key=_COOKIE, value=value, max_age=_MAX_AGE, path="/",
        httponly=True, secure=True, samesite="lax",
    )


def _login_page(err: str = "") -> str:
    err_html = (
        '<p style="color:#b00020;font-size:14px;margin:0 0 12px">' + _html.escape(err) + "</p>"
        if err else ""
    )
    return (
        "<!doctype html><html lang=pl><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>QBot - logowanie</title>"
        "<style>body{font-family:system-ui,Arial,sans-serif;background:#f5f5f4;margin:0;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center}"
        ".card{background:#fff;border:1px solid #e3e3e0;border-radius:12px;padding:28px;"
        "width:320px;box-shadow:0 1px 3px rgba(0,0,0,.06)}"
        "h1{font-size:18px;font-weight:500;margin:0 0 18px}"
        "label{display:block;font-size:13px;color:#666;margin:10px 0 4px}"
        "input{width:100%;box-sizing:border-box;padding:9px;border:1px solid #d0d0cc;"
        "border-radius:8px;font-size:15px}"
        "button{width:100%;margin-top:18px;padding:10px;border:0;border-radius:8px;"
        "background:#1d9e75;color:#fff;font-size:15px;cursor:pointer}</style></head><body>"
        "<form class=card method=post action='/login'>"
        "<h1>QBot - logowanie</h1>" + err_html +
        "<label>Uzytkownik</label><input name=user autofocus>"
        "<label>Haslo</label><input name=password type=password>"
        "<button type=submit>Zaloguj</button></form></body></html>"
    )


def _fmt(v, suffix="", nd=0):
    if v is None:
        return "&mdash;"
    try:
        if nd == 0:
            return f"{round(float(v))}{suffix}"
        return f"{round(float(v), nd)}{suffix}"
    except Exception:
        return _html.escape(str(v)) + suffix


def _fetch_metrics() -> dict:
    d = {"cards": [], "ride": None, "error": None}
    try:
        import psycopg
        with psycopg.connect("", connect_timeout=5) as conn:
            with conn.cursor() as cur:
                def one(sql):
                    try:
                        cur.execute(sql)
                        return cur.fetchone()
                    except Exception:
                        conn.rollback()
                        return None

                xert = one(
                    "select date, form_status, form_ratio, training_load, fatigue, ftp_power_w "
                    "from qbot_v2.xert_profile_snapshots order by snapshot_at desc limit 1"
                )
                wtss = one(
                    "select coalesce(round(sum(tss)),0) from qbot_v2.training_sessions "
                    "where started_at >= now() - interval '7 days'"
                )
                ride = one(
                    "select date, sport_type, normalized_power_w, avg_power_w, avg_hr_bpm, "
                    "tss, intensity_factor from qbot_v2.training_sessions "
                    "order by started_at desc limit 1"
                )
                weight = one(
                    "select date, weight_kg from qbot_v2.body_latest_weight order by date desc limit 1"
                )

                if xert:
                    xd = xert[0]
                    d["cards"].append(("Forma (Xert)", _html.escape(str(xert[1] or "—")),
                                       f"ratio {_fmt(xert[2], nd=2)} &middot; {xd}"))
                    d["cards"].append(("Training load", _fmt(xert[3]),
                                       f"fatigue {_fmt(xert[4])} &middot; {xd}"))
                    d["cards"].append(("FTP (Xert)", _fmt(xert[5], " W"), str(xd)))
                if wtss:
                    d["cards"].append(("TSS / 7 dni", _fmt(wtss[0]), "ostatnie 7 dni"))
                if ride:
                    d["cards"].append(("Ostatni przejazd", _fmt(ride[2], " W"),
                                       f"NP &middot; {ride[0]}"))
                    d["ride"] = ride
                if weight:
                    d["cards"].append(("Waga", _fmt(weight[1], " kg", nd=1), str(weight[0])))
    except Exception as e:
        d["error"] = str(e)
    return d


def _dash_page() -> str:
    m = _fetch_metrics()
    cards_html = ""
    for label, val, sub in m["cards"]:
        cards_html += (
            "<div class=card><div class=lbl>" + label + "</div>"
            "<div class=val>" + val + "</div>"
            "<div class=sub>" + sub + "</div></div>"
        )
    if not cards_html:
        cards_html = "<div class=card><div class=lbl>Brak danych</div></div>"

    ride_html = ""
    r = m["ride"]
    if r:
        ride_html = (
            "<div class=detail><strong>Ostatni przejazd</strong> &middot; " + str(r[0]) +
            " (" + _html.escape(str(r[1] or "")) + ")<br>"
            "NP " + _fmt(r[2], " W") + " &middot; avg " + _fmt(r[3], " W") +
            " &middot; HR " + _fmt(r[4], " bpm") + " &middot; TSS " + _fmt(r[5]) +
            " &middot; IF " + _fmt(r[6], nd=2) + "</div>"
        )

    banner = ""
    if m["error"]:
        banner = ("<div class=warn>Problem z baza danych: " +
                  _html.escape(m["error"]) + "</div>")

    return (
        "<!doctype html><html lang=pl><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>QBot - dashboard</title>"
        "<style>body{font-family:system-ui,Arial,sans-serif;background:#f5f5f4;margin:0;color:#222}"
        ".top{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;"
        "background:#fff;border-bottom:1px solid #e3e3e0}"
        ".top a{color:#1d9e75;text-decoration:none;font-size:14px}"
        ".wrap{max-width:760px;margin:24px auto;padding:0 16px}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}"
        ".card{background:#fff;border:1px solid #e3e3e0;border-radius:10px;padding:16px}"
        ".lbl{font-size:13px;color:#777}.val{font-size:26px;font-weight:500;margin:4px 0}"
        ".sub{font-size:12px;color:#999}"
        ".detail{margin-top:16px;background:#fff;border:1px solid #e3e3e0;border-radius:10px;"
        "padding:16px;font-size:14px;line-height:1.6}"
        ".warn{margin-top:16px;background:#fff3cd;border:1px solid #ffe08a;border-radius:10px;"
        "padding:12px;font-size:13px;color:#7a5b00}"
        ".foot{margin-top:18px;font-size:12px;color:#aaa}</style></head><body>"
        "<div class=top><strong>QBot</strong><span>zalogowany: " + _html.escape(_USER) +
        " &nbsp; <a href='/logout'>wyloguj</a></span></div>"
        "<div class=wrap><div class=grid>" + cards_html + "</div>" +
        ride_html + banner +
        "<div class=foot>Dane na zywo z qbot_v2.</div>"
        "</div></body></html>"
    )


@router.get("/login")
async def login_get(request: Request):
    if _authed(request):
        return RedirectResponse(url="/dash", status_code=303)
    return HTMLResponse(_login_page())


@router.post("/login")
async def login_post(request: Request):
    form = await request.form()
    user = (form.get("user") or "").strip()
    pw = form.get("password") or ""
    if user == _USER and _check_pw(pw):
        resp = RedirectResponse(url="/dash", status_code=303)
        _set_cookie(resp, _make_cookie())
        return resp
    return HTMLResponse(_login_page("Bledny uzytkownik lub haslo."), status_code=401)


@router.get("/logout")
async def logout(request: Request):
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(_COOKIE, path="/")
    return resp


@router.get("/dash")
async def dash(request: Request):
    if not _authed(request):
        return RedirectResponse(url="/login", status_code=303)
    return HTMLResponse(_dash_page())
