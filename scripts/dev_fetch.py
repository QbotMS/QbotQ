#!/usr/bin/env python3
"""dev_fetch.py - pobiera strone qbot-web JUZ ZALOGOWANY (omija brame /login).

PO CO: qbot-web trzyma KAZDA sciezke (poza /healthz, /login, favicon) za
ciasteczkiem sesji qbot_session. Goly urllib/urlopen bez ciasteczka dostaje
strone logowania, wiec weryfikacja tresci przez HTTP dawala falszywe wyniki.
Ten helper liczy poprawne ciasteczko i dolacza je do zadania.

ZASADY BEZPIECZENSTWA:
- Sekret (WEBAUTH_TOKEN) NIGDY nie jest drukowany - uzywany tylko do policzenia
  podpisu HMAC ciasteczka.
- Preferuje funkcje z samej aplikacji (qbot_web._webauth_*), wiec zmiana hasla
  / tokenu / algorytmu w produkcji jest podchwytywana automatycznie. Lokalny
  odpowiednik ponizej to tylko zapas na wypadek, gdyby import aplikacji sie nie udal.

UZYCIE:
    .venv/bin/python3 scripts/dev_fetch.py /raport-trasy.html
    .venv/bin/python3 scripts/dev_fetch.py /nav.js?v=3 --max 2000
    .venv/bin/python3 scripts/dev_fetch.py http://127.0.0.1:30181/forma.html
    .venv/bin/python3 scripts/dev_fetch.py /forma.html --grep "Analiza trasy"

Opcje:
    --max N       obetnij wypisywana tresc do N znakow (domyslnie: cala)
    --user NAME   uzyj konkretnego uzytkownika (domyslnie: pierwszy z listy)
    --grep TEKST  zamiast tresci wypisz tylko: czy TEKST wystepuje (mozna wiele razy)
    --head        wypisz tylko status + naglowki + dlugosc, bez tresci
"""
import sys
import os
import argparse
import urllib.request

APP_DIR = "/opt/qbot/app"
ENV_WEBAUTH = APP_DIR + "/.env.webauth"
PORT = int(os.environ.get("QBOT_WEB_PORT", "30181"))
sys.path.insert(0, APP_DIR)


def _load_local():
    """Zapasowy loader (kopia logiki qbot_web._webauth_load)."""
    users, sign_val = {}, ""
    try:
        for line in open(ENV_WEBAUTH):
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                if k == "WEBAUTH_USERS":
                    for pair in v.split(","):
                        pair = pair.strip()
                        if ":" in pair:
                            u, p = pair.split(":", 1)
                            users[u] = p
                elif k == "WEBAUTH_TOKEN":
                    sign_val = v
    except Exception:
        pass
    return users, sign_val


def _cookie_local(username, sign_val):
    """Zapasowy generator (kopia logiki qbot_web._webauth_cookie_make)."""
    import hmac, hashlib, time
    expiry = int(time.time()) + 365 * 24 * 3600
    msg = username + ":" + str(expiry)
    digest = hmac.new(sign_val.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return msg + ":" + digest, expiry


def get_auth():
    """Zwraca (users, sign_val, cookie_make) - preferujac funkcje aplikacji."""
    try:
        from qbot_web import _webauth_load, _webauth_cookie_make
        users, sign_val = _webauth_load()
        return users, sign_val, _webauth_cookie_make
    except Exception:
        users, sign_val = _load_local()
        return users, sign_val, _cookie_local


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--user", default=None)
    ap.add_argument("--grep", action="append", default=[])
    ap.add_argument("--head", action="store_true")
    args = ap.parse_args()

    url = args.url
    if not url.startswith("http"):
        if not url.startswith("/"):
            url = "/" + url
        url = "http://127.0.0.1:%d%s" % (PORT, url)

    users, sign_val, cookie_make = get_auth()
    if not sign_val or not users:
        print("BLAD: nie udalo sie wczytac danych logowania (WEBAUTH). Sprawdz %s" % ENV_WEBAUTH)
        return 2
    username = args.user or sorted(users.keys())[0]
    if username not in users:
        print("BLAD: uzytkownik %r nie istnieje. Dostepni: %s" % (username, ", ".join(sorted(users))))
        return 2

    cookie_value, _exp = cookie_make(username, sign_val)
    req = urllib.request.Request(url, headers={"Cookie": "qbot_session=" + cookie_value})
    with urllib.request.urlopen(req, timeout=15) as r:
        status = r.status
        ctype = r.getheader("Content-Type")
        body = r.read().decode("utf-8", "replace")

    is_login = "QBot Lab - logowanie" in body
    print("URL:    %s" % url)
    print("uzytk.: %s" % username)
    print("status: %s | ctype: %s | dlugosc: %d%s"
          % (status, ctype, len(body), "  [!! STRONA LOGOWANIA - ciasteczko odrzucone]" if is_login else ""))

    if args.grep:
        for g in args.grep:
            print(("OK  " if g in body else "!!  ") + repr(g))
        return 0
    if args.head:
        return 0
    out = body if args.max <= 0 else body[:args.max]
    print("-" * 60)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
