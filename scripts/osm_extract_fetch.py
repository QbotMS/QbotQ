#!/usr/bin/env python3
"""Pobieranie wycinka OSM Polski z Geofabrik na serwer (zrodlo lokalne nawierzchni).

  .venv/bin/python3 scripts/osm_extract_fetch.py --check   # tylko HEAD (rozmiar, data) - sekundy
  .venv/bin/python3 scripts/osm_extract_fetch.py --start   # odpala pobieranie W TLE i od razu wraca
  .venv/bin/python3 scripts/osm_extract_fetch.py --status  # postep z pliku logu

Pobieranie idzie do *.part, po sprawdzeniu MD5 z Geofabrik zmiana nazwy na docelowa.
Dok.: docs/OSM_LOCAL_SURFACE.md (do napisania przy wdrozeniu silnika).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

URL = os.getenv("QBOT_OSM_EXTRACT_URL", "https://download.geofabrik.de/europe/poland-latest.osm.pbf")
DIR = Path(os.getenv("QBOT_OSM_DIR", "/opt/qbot/data/osm"))
DEST = DIR / "poland-latest.osm.pbf"
PART = DIR / "poland-latest.osm.pbf.part"
LOG = Path("/opt/qbot/artifacts/osm_extract_fetch.log")


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def check() -> int:
    import httpx

    r = httpx.head(URL, timeout=10, follow_redirects=True)
    size = int(r.headers.get("content-length") or 0)
    print(f"HTTP {r.status_code} | rozmiar {size/1e9:.2f} GB | Last-Modified {r.headers.get('last-modified')}")
    return 0 if r.status_code == 200 else 1


def download() -> int:
    import httpx

    DIR.mkdir(parents=True, exist_ok=True)
    _log(f"START {URL}")
    try:
        md5_txt = httpx.get(URL + ".md5", timeout=20, follow_redirects=True).text.split()[0].strip()
    except Exception as exc:  # noqa: BLE001
        md5_txt = ""
        _log(f"brak md5: {exc}")
    h = hashlib.md5()
    done = 0
    last = time.time()
    with httpx.stream("GET", URL, timeout=60, follow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        with PART.open("wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if time.time() - last > 15:
                    _log(f"POSTEP {done/1e9:.2f}/{total/1e9:.2f} GB")
                    last = time.time()
    got = h.hexdigest()
    if md5_txt and got != md5_txt:
        _log(f"BLAD md5 {got} != {md5_txt} (plik zostaje jako .part)")
        return 1
    PART.replace(DEST)
    _log(f"KONIEC OK {done/1e9:.2f} GB md5={got} -> {DEST}")
    return 0


def start() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(os.devnull, "rb") as dn, LOG.open("a") as lf:
        p = subprocess.Popen(
            [sys.executable, __file__, "--run"], stdin=dn, stdout=lf, stderr=lf,
            start_new_session=True, close_fds=True,
        )
    print(f"pobieranie w tle, pid={p.pid}, log={LOG}")
    return 0


def status() -> int:
    if LOG.exists():
        lines = LOG.read_text(encoding="utf-8").splitlines()
        print("\n".join(lines[-5:]))
    else:
        print("brak logu")
    for p in (PART, DEST):
        if p.exists():
            print(f"{p.name}: {p.stat().st_size/1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--check"
    sys.exit({"--check": check, "--start": start, "--status": status, "--run": download}.get(arg, check)())
