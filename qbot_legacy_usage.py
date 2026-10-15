#!/usr/bin/env python3
"""Licznik uzycia STAREJ warstwy QBota (sprzed Alberta) -- 15.10.2026, audyt etap 3.

Cel: po 7 dniach (22.10.2026) wyciac to, czego nikt nie uzyl (stary lacznik ChatGPT + martwe czesci starej warstwy).
Dziala tylko jako obserwator: zapisuje "uzyto funkcji X" do logs/legacy_usage.log i nic poza tym nie zmienia.

Uzycie (na KONCU modulu starej warstwy):
    from qbot_legacy_usage import instrument; instrument(globals())
Serwer qbot-api: middleware zapisuje adresy HTTP (mark_http).
Podsumowanie: python3 qbot_legacy_usage.py  (albo SETUP > Polaczenia > Status).
Wylaczenie awaryjne: QBOT_LEGACY_USAGE=0. Dok.: docs/LEGACY_USAGE.md
"""
from __future__ import annotations

import functools
import inspect
import os
import sys
import threading
import time
from datetime import datetime

LOG = "/opt/qbot/app/logs/legacy_usage.log"
_SEEN: dict[str, float] = {}
_LOCK = threading.Lock()
_ENABLED = os.getenv("QBOT_LEGACY_USAGE", "1") != "0"
# testy i narzedzia audytu nie licza sie jako uzycie
_ARGV0 = os.path.basename(sys.argv[0] if sys.argv else "")
if "pytest" in sys.modules or _ARGV0.startswith(("run_test_file", "audit_", "_tmp_", "pytest")):
    _ENABLED = False
_EVERY_S = 3600  # ta sama nazwa w tym procesie najwyzej raz na godzine (log nie puchnie)


def _write(kind: str, name: str) -> None:
    if not _ENABLED:
        return
    key = kind + ":" + name
    now = time.time()
    with _LOCK:
        if now - _SEEN.get(key, 0) < _EVERY_S:
            return
        _SEEN[key] = now
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{os.getpid()}\t{kind}\t{name}\n")
    except Exception:
        pass  # licznik nigdy nie psuje dzialania


def mark(name: str) -> None:
    _write("fn", name)


def mark_http(method: str, path: str) -> None:
    _write("http", f"{method} {path}")


def _wrap(fn, qual: str):
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def aw(*a, **k):
            mark(qual)
            return await fn(*a, **k)
        aw.__legacy_usage__ = True
        return aw

    @functools.wraps(fn)
    def w(*a, **k):
        mark(qual)
        return fn(*a, **k)
    w.__legacy_usage__ = True
    return w


def instrument(g: dict) -> int:
    """Owija wszystkie funkcje zdefiniowane w module + podmienia je w slownikach/listach modulu (rejestry narzedzi)."""
    if not _ENABLED:
        return 0
    mod = g.get("__name__", "?")
    repl = {}
    for k, v in list(g.items()):
        if inspect.isfunction(v) and v.__module__ == mod and not getattr(v, "__legacy_usage__", False):
            nw = _wrap(v, f"{mod}.{k}")
            g[k] = nw
            repl[id(v)] = nw

    def _fix(c, depth=0):
        if depth > 2:
            return
        if isinstance(c, dict):
            for kk, vv in list(c.items()):
                if id(vv) in repl:
                    c[kk] = repl[id(vv)]
                elif isinstance(vv, (dict, list)):
                    _fix(vv, depth + 1)
        elif isinstance(c, list):
            for i, vv in enumerate(c):
                if id(vv) in repl:
                    c[i] = repl[id(vv)]
                elif isinstance(vv, (dict, list, tuple)):
                    _fix(vv, depth + 1) if not isinstance(vv, tuple) else None

    for v in list(g.values()):
        if isinstance(v, (dict, list)) and v is not g:
            try:
                _fix(v)
            except Exception:
                pass
    return len(repl)


def summary(days: int = 7) -> dict:
    """Co uzyto w ostatnich N dniach: {nazwa: liczba_zapisow}, osobno funkcje i adresy HTTP."""
    cut = time.time() - days * 86400
    fn, http, first = {}, {}, None
    try:
        for line in open(LOG, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) != 4:
                continue
            try:
                ts = datetime.fromisoformat(p[0]).timestamp()
            except Exception:
                continue
            first = ts if first is None else min(first, ts)
            if ts < cut:
                continue
            d = fn if p[2] == "fn" else http
            d[p[3]] = d.get(p[3], 0) + 1
    except FileNotFoundError:
        pass
    return {"since": datetime.fromtimestamp(first).strftime("%d.%m %H:%M") if first else None,
            "functions": dict(sorted(fn.items())), "http": dict(sorted(http.items()))}


if __name__ == "__main__":
    s = summary()
    print("licznik od:", s["since"])
    print("funkcje uzyte (%d):" % len(s["functions"]))
    for k, v in s["functions"].items():
        print("  %4d  %s" % (v, k))
    print("adresy HTTP (%d):" % len(s["http"]))
    for k, v in s["http"].items():
        print("  %4d  %s" % (v, k))
