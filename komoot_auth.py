#!/usr/bin/env python3
"""Komoot web-session auth/refresh dla QBot.

Mechanizm (potwierdzony na zywo):
- .komoot_session trzyma pelny naglowek Cookie (kmt_sess, kmt_sess.sig, koa_at,
  koa_ae, koa_re, koa_rt).
- koa_at = poswiadczenie dostepu (JWT, ~30 min), koa_rt = poswiadczenie odswiezajace (~rok).
- Backend www.komoot.com sam rotuje: GET / z waznym koa_rt zwraca swiezy komplet
  przez Set-Cookie. API v007 tego NIE robi (401 na wygaslym).
Zadne wartosci sekretne nie sa logowane.
"""
from __future__ import annotations
import base64, json, os, re, time, urllib.request, urllib.error
from pathlib import Path

SESSION_FILE = Path(os.getenv("KOMOOT_SESSION_FILE", "/opt/qbot/app/.komoot_session"))
HOME_URL = "https://www.komoot.com/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
REFRESH_SKEW = 300


class KomootAuthError(RuntimeError):
    pass


def _parse_jar(raw):
    return dict(t.split("=", 1) for t in re.split(r"[;\s]+", raw.strip()) if "=" in t)


def _jar_to_header(jar):
    return "; ".join(k + "=" + v for k, v in jar.items() if v)


def _jwt_exp(atk):
    try:
        seg = atk.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        return int(json.loads(base64.urlsafe_b64decode(seg)).get("exp"))
    except Exception:
        return None


class KomootSession:
    def __init__(self, path=None):
        self.path = path or SESSION_FILE
        self.jar = _parse_jar(self.path.read_text(encoding="utf-8"))

    def _save(self):
        self.path.write_text(_jar_to_header(self.jar), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def is_fresh(self):
        exp = _jwt_exp(self.jar.get("koa_at", ""))
        return bool(exp and exp > int(time.time()) + REFRESH_SKEW)

    def refresh(self):
        req = urllib.request.Request(HOME_URL, headers={"User-Agent": UA, "Cookie": self.cookie_header()})
        try:
            resp = urllib.request.urlopen(req, timeout=25)
        except urllib.error.HTTPError as e:
            raise KomootAuthError("Komoot refresh HTTP %s" % e.code)
        fresh = {}
        for h in (resp.headers.get_all("Set-Cookie") or []):
            part = h.split(";", 1)[0]
            name, _, val = part.partition("=")
            if val and val not in ("deleted", ""):
                fresh[name.strip()] = val
        if "koa_at" not in fresh:
            raise KomootAuthError("Komoot refresh: brak nowego koa_at (sesja wygasla? przeloguj)")
        self.jar.update(fresh)
        self._save()
        return True

    def cookie_header(self):
        return _jar_to_header(self.jar)

    def access_token(self):
        if not self.is_fresh():
            self.refresh()
        return self.jar.get("koa_at", "")

    def authed_headers(self, accept="application/hal+json"):
        atk = self.access_token()
        return {"User-Agent": UA, "Authorization": "Bearer " + atk,
                "Cookie": self.cookie_header(), "Accept": accept}


if __name__ == "__main__":
    s = KomootSession()
    print("fresh_przed:", s.is_fresh())
    s.access_token()
    print("fresh_po:", s.is_fresh(), "| exp_za_min:",
          round((_jwt_exp(s.jar.get("koa_at","")) - time.time())/60, 1))
