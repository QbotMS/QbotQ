#!/usr/bin/env python3
"""Lokalna baza zabytkow/atrakcji OSM (Polska) dla silnika atrakcji - zamiast Overpass.

Ten sam zakres co zapytanie Overpass w route_attraction_sources.discover_osm_landmarks:
historic=*, heritage=*, military~bunker|fort|trench, tourism~attraction|museum,
man_made z wikipedia/wikidata. Obiekty node/way/relation -> srodek (center) z geometrii.

  .venv/bin/python3 scripts/osm_landmarks_build.py --start   # w tle, od razu wraca
  .venv/bin/python3 scripts/osm_landmarks_build.py --status
  .venv/bin/python3 scripts/osm_landmarks_build.py --run     # na pierwszym planie (cron)
Wynik: /opt/qbot/data/osm/landmarks.sqlite (landmarks: id 'n123'/'w'/'r', lat, lon, tags_json;
landmarks_rtree; meta). Budowa do .tmp i podmiana atomowa. Zrodlo: poland-latest.osm.pbf.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DIR = Path(os.getenv("QBOT_OSM_DIR", "/opt/qbot/data/osm"))
SRC = DIR / "poland-latest.osm.pbf"
FILT = DIR / "landmarks.osm.pbf"
SEQ = DIR / "landmarks.geojsonseq"
DB = DIR / "landmarks.sqlite"
TMP = DIR / "landmarks.sqlite.tmp"
LOG = Path("/opt/qbot/artifacts/osm_landmarks_build.log")
_MIL = re.compile(r"bunker|fort|trench", re.I)
_TOUR = re.compile(r"attraction|museum", re.I)


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def _run(cmd: list[str]) -> None:
    t = time.time()
    _log("CMD " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} rc={r.returncode}: {r.stderr[-800:]}")
    _log(f"OK {time.time()-t:.0f}s")


def is_landmark(tags: dict) -> bool:
    """Ten sam filtr co zapytanie Overpass w discover_osm_landmarks."""
    if tags.get("historic") or tags.get("heritage"):
        return True
    if _MIL.search(str(tags.get("military") or "")):
        return True
    if _TOUR.search(str(tags.get("tourism") or "")):
        return True
    if tags.get("man_made") and (tags.get("wikipedia") or tags.get("wikidata")):
        return True
    return False


def _coords(geom: dict) -> list:
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Point":
        return [c]
    if t == "LineString":
        return c
    if t in ("Polygon", "MultiLineString"):
        return [p for ring in c for p in ring]
    if t == "MultiPolygon":
        return [p for poly in c for ring in poly for p in ring]
    return []


def build() -> int:
    t0 = time.time()
    _log("START budowa zabytkow")
    try:
        _run(["osmium", "tags-filter", str(SRC), "nwr/historic", "nwr/heritage", "nwr/military",
              "nwr/tourism", "nwr/man_made", "-o", str(FILT), "--overwrite"])
        _log(f"landmarks.osm.pbf {FILT.stat().st_size/1e6:.0f} MB")
        _run(["osmium", "export", str(FILT), "-f", "geojsonseq", "-a", "type,id",
              "--index-type=sparse_file_array," + str(DIR / "nodes_lm.idx"),
              "-o", str(SEQ), "--overwrite"])
        if TMP.exists():
            TMP.unlink()
        con = sqlite3.connect(TMP)
        con.executescript("""
            PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
            CREATE TABLE landmarks(id TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, tags_json TEXT NOT NULL);
            CREATE VIRTUAL TABLE landmarks_rtree USING rtree(rid, min_lat, max_lat, min_lon, max_lon);
            CREATE TABLE landmarks_rid(rid INTEGER PRIMARY KEY, id TEXT NOT NULL);
            CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        n = 0
        rid = 0
        with SEQ.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip().lstrip("\x1e")
                if not line:
                    continue
                f = json.loads(line)
                props = f.get("properties") or {}
                otype, oid = props.get("@type"), props.get("@id")
                tags = {k: v for k, v in props.items() if not k.startswith("@")}
                if oid is None or not is_landmark(tags):
                    continue
                pts = _coords(f.get("geometry") or {})
                if not pts:
                    continue
                lats = [p[1] for p in pts]
                lons = [p[0] for p in pts]
                lat = (min(lats) + max(lats)) / 2.0
                lon = (min(lons) + max(lons)) / 2.0
                key = f"{str(otype or '?')[0]}{oid}"
                cur = con.execute("INSERT OR IGNORE INTO landmarks VALUES (?,?,?,?)",
                                  (key, lat, lon, json.dumps(tags, ensure_ascii=False, separators=(",", ":"))))
                if cur.rowcount:
                    rid += 1
                    con.execute("INSERT INTO landmarks_rid VALUES (?,?)", (rid, key))
                    con.execute("INSERT INTO landmarks_rtree VALUES (?,?,?,?,?)", (rid, lat, lat, lon, lon))
                    n += 1
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
            ("source", SRC.name), ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S")), ("objects", str(n)),
        ])
        con.commit()
        con.close()
        TMP.replace(DB)
        for p in (SEQ, DIR / "nodes_lm.idx", FILT):
            try:
                p.unlink()
            except OSError:
                pass
        _log(f"KONIEC OK {n} obiektow, {DB.stat().st_size/1e6:.0f} MB, {time.time()-t0:.0f}s")
        return 0
    except Exception as exc:  # noqa: BLE001
        _log(f"BLAD {type(exc).__name__}: {exc}")
        return 1


def start() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(os.devnull, "rb") as dn, LOG.open("a") as lf:
        p = subprocess.Popen([sys.executable, __file__, "--run"], stdin=dn, stdout=lf, stderr=lf,
                             start_new_session=True, close_fds=True)
    print(f"budowa w tle, pid={p.pid}, log={LOG}")
    return 0


def status() -> int:
    print("\n".join(LOG.read_text(encoding="utf-8").splitlines()[-6:]) if LOG.exists() else "brak logu")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--status"
    sys.exit({"--start": start, "--status": status, "--run": build}.get(arg, status)())
