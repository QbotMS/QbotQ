"""QBot dashboard — minimalna auth na podpisanym ciasteczku (stdlib) + placeholder.
Dodane 2026-06-19. Zero dodatkowych zależności.
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


_DASH_TEMPLATE = """<!doctype html><html lang=pl><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>QBot - dashboard</title>
<style>body{font-family:system-ui,Arial,sans-serif;background:#f5f5f4;margin:0;color:#222}
.top{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;
background:#fff;border-bottom:1px solid #e3e3e0}
.top a{color:#1d9e75;text-decoration:none;font-size:14px}
.wrap{max-width:760px;margin:24px auto;padding:0 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.card{background:#fff;border:1px solid #e3e3e0;border-radius:10px;padding:16px}
.lbl{font-size:13px;color:#777}.val{font-size:26px;font-weight:500;margin-top:4px}
.note{margin-top:16px;background:#fff;border:1px dashed #cfcfca;border-radius:10px;
padding:18px;color:#999;font-size:14px}</style></head><body>
<div class=top><strong>QBot</strong><span>zalogowany: __USER__ &nbsp; <a href='/logout'>wyloguj</a></span></div>
<div class=wrap>
<div class=grid>
<div class=card><div class=lbl>CTL (forma)</div><div class=val>72</div></div>
<div class=card><div class=lbl>TSB (swiezosc)</div><div class=val>+4</div></div>
<div class=card><div class=lbl>TSS / tydzien</div><div class=val>540</div></div>
<div class=card><div class=lbl>Ostatni przejazd</div><div class=val>186 W</div></div>
</div>
<div class=note>To sa dane TESTOWE (placeholder). Nastepny krok: podpiac realne zapytania do qbot_v2.</div>
</div></body></html>"""


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
    return HTMLResponse(_DASH_TEMPLATE.replace("__USER__", _html.escape(_USER)))
