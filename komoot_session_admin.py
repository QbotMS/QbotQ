#!/usr/bin/env python3
"""Zarzadzanie sesja Komoot (wspolne dla strony web i skryptu CLI).

Jedno miejsce prawdy o tym, co znaczy "zdrowa sesja Komoot":
- komplet ciasteczek (kmt_sess, koa_at, koa_rt),
- zadne z nich nie jest puste ('j:null' = Komoot wylogowal),
- API v007 faktycznie je akceptuje (test na liscie tras).

Zapis do .komoot_session nastepuje WYLACZNIE po udanym tescie na API,
a stara sesja ladnie laduje w .bak. Zadna wartosc ciasteczka nie jest
zwracana, wypisywana ani logowana - na zewnatrz ida tylko nazwy i statusy.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
import komoot_auth
from tools.komoot import client as kclient

NEEDED = ("kmt_sess", "koa_at", "koa_rt")


class SessionInputError(ValueError):
    """Wejscie od uzytkownika jest zle (brak ciasteczek, puste wartosci)."""


class SessionRejected(RuntimeError):
    """Ciasteczka wygladaja poprawnie, ale API Komoota ich nie przyjmuje."""


def parse_cookie_header(raw):
    """Tekst z przegladarki -> slownik ciasteczek. Rzuca SessionInputError."""
    raw = (raw or "").strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    jar = komoot_auth._parse_jar(raw)
    if not jar:
        raise SessionInputError("nie rozpoznano zadnego ciasteczka")
    brak = [k for k in NEEDED if k not in jar]
    if brak:
        raise SessionInputError("brakuje ciasteczek: %s" % ", ".join(brak))
    puste = sorted({k for k, v in jar.items() if komoot_auth._is_null_cookie(v)})
    if puste:
        raise SessionInputError("ciasteczka puste (j:null): %s - skopiuj po zalogowaniu"
                                % ", ".join(puste))
    return jar


def _probe(jar):
    """Test ciasteczek na tymczasowym pliku sesji. Zwraca (liczba_tras, jar)."""
    fd, tmp = tempfile.mkstemp(prefix=".komoot_test_", dir="/opt/qbot/app")
    os.close(fd)
    try:
        Path(tmp).write_text(komoot_auth._jar_to_header(jar), encoding="utf-8")
        os.chmod(tmp, 0o600)
        s = komoot_auth.KomootSession(path=Path(tmp))
        try:
            tours = kclient.list_planned_tours(s, limit=5, page=0)
        except komoot_auth.KomootAuthError as e:
            raise SessionRejected(str(e))
        except kclient.KomootClientError as e:
            raise SessionRejected(str(e))
        return len(tours), s.jar
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def store_session(raw):
    """Sprawdz i zapisz sesje. Zwraca {'ok': True, 'tours': N, 'backup': bool}."""
    jar = parse_cookie_header(raw)
    n, jar_after = _probe(jar)
    dst = Path(str(komoot_auth.SESSION_FILE))
    backup = False
    if dst.exists():
        bak = Path(str(dst) + ".bak")
        bak.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(bak, 0o600)
        backup = True
    dst.write_text(komoot_auth._jar_to_header(jar_after), encoding="utf-8")
    os.chmod(dst, 0o600)
    return {"ok": True, "tours": n, "backup": backup}


def status(live=True):
    """Stan sesji do pokazania na stronie. Nigdy nie rzuca."""
    out = {"alive": False, "detail": "", "file": str(komoot_auth.SESSION_FILE),
           "empty_cookies": [], "tours": None}
    try:
        s = komoot_auth.KomootSession()
    except FileNotFoundError:
        out["detail"] = "brak pliku sesji - wklej ciasteczka"
        return out
    except Exception as e:
        out["detail"] = "nie mozna odczytac sesji: %s" % e
        return out
    out["empty_cookies"] = sorted({k for k, v in s.jar.items()
                                   if komoot_auth._is_null_cookie(v)})
    brak = [k for k in NEEDED if k not in s.jar]
    if brak:
        out["detail"] = "niekompletna sesja (brak: %s)" % ", ".join(brak)
        return out
    if out["empty_cookies"]:
        out["detail"] = ("Komoot wylogowal sesje (puste: %s) - wklej swieze ciasteczka"
                         % ", ".join(out["empty_cookies"]))
        return out
    if not live:
        out["detail"] = "ciasteczka na miejscu (bez testu na API)"
        return out
    try:
        n = len(kclient.list_planned_tours(s, limit=5, page=0))
    except Exception as e:
        out["detail"] = "API Komoota odrzuca sesje: %s" % e
        return out
    out["alive"] = True
    out["tours"] = n
    out["detail"] = "sesja zywa - API odpowiada"
    return out


def last_seen_tour():
    """Ostatnia trasa wykryta przez watchera (do pokazania 'czy cos wpada')."""
    try:
        import api_db
        with api_db._conn() as c:
            row = c.execute(
                "SELECT name, created_date, last_status FROM qbot_v2.komoot_seen_tours "
                "WHERE last_status <> 'seeded' ORDER BY created_date DESC NULLS LAST LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {"name": row["name"], "date": row["created_date"], "status": row["last_status"]}
    except Exception:
        return None
