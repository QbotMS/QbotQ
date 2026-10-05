#!/usr/bin/env python3
"""Budowa lokalnej bazy drog OSM (zrodlo nawierzchni niezalezne od Overpass).

poland-latest.osm.pbf --(osmium tags-filter w/highway)--> roads.osm.pbf
  --(osmium export geojsonseq, tylko linie)--> SQLite z indeksem R-tree:
  /opt/qbot/data/osm/roads.sqlite  (ways: id, tags_json, geom_json; ways_rtree: bbox; meta)

  .venv/bin/python3 scripts/osm_local_build.py --start   # w tle, od razu wraca
  .venv/bin/python3 scripts/osm_local_build.py --status
Budowa do roads.sqlite.tmp, na koncu podmiana atomowa (silnik nigdy nie widzi polowy bazy).
Obszar pokrycia: plik .poly z Geofabrik (poland.poly) zapisany obok.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DIR = Path(os.getenv("QBOT_OSM_DIR", "/opt/qbot/data/osm"))
SRC = DIR / "poland-latest.osm.pbf"
ROADS = DIR / "roads.osm.pbf"
SEQ = DIR / "roads.geojsonseq"
DB = DIR / "roads.sqlite"
TMP = DIR / "roads.sqlite.tmp"
POLY = DIR / "poland.poly"
POLY_URL = "https://download.geofabrik.de/europe/poland.poly"
LOG = Path("/opt/qbot/artifacts/osm_local_build.log")
KEEP_TAGS = ("highway", "surface", "tracktype", "smoothness", "name", "ref", "bicycle",
             "access", "cycleway", "service", "mtb:scale", "sac_scale")


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


def build() -> int:
    t0 = time.time()
    _log("START budowa")
    try:
        import httpx

        POLY.write_text(httpx.get(POLY_URL, timeout=30, follow_redirects=True).text, encoding="utf-8")
        _log(f"poly OK {POLY.stat().st_size} B")

        _run(["osmium", "tags-filter", str(SRC), "w/highway", "-o", str(ROADS), "--overwrite"])
        _log(f"roads.osm.pbf {ROADS.stat().st_size/1e6:.0f} MB")
        _run(["osmium", "export", str(ROADS), "-f", "geojsonseq", "--geometry-types=linestring",
              "-a", "id", "--index-type=sparse_file_array," + str(DIR / "nodes.idx"),
              "-o", str(SEQ), "--overwrite"])
        _log(f"geojsonseq {SEQ.stat().st_size/1e9:.2f} GB")

        if TMP.exists():
            TMP.unlink()
        con = sqlite3.connect(TMP)
        con.executescript("""
            PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
            CREATE TABLE ways(id INTEGER PRIMARY KEY, tags_json TEXT NOT NULL, geom_json TEXT NOT NULL);
            CREATE VIRTUAL TABLE ways_rtree USING rtree(id, min_lat, max_lat, min_lon, max_lon);
            CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        n = 0
        batch_w, batch_r = [], []
        with SEQ.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip().lstrip("\x1e")
                if not line:
                    continue
                f = json.loads(line)
                props = f.get("properties") or {}
                wid = props.get("@id")
                coords = (f.get("geometry") or {}).get("coordinates") or []
                if wid is None or len(coords) < 2:
                    continue
                tags = {k: props[k] for k in KEEP_TAGS if k in props}
                lats = [c[1] for c in coords]
                lons = [c[0] for c in coords]
                geom = [[round(c[1], 7), round(c[0], 7)] for c in coords]
                batch_w.append((int(wid), json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                                json.dumps(geom, separators=(",", ":"))))
                batch_r.append((int(wid), min(lats), max(lats), min(lons), max(lons)))
                n += 1
                if len(batch_w) >= 50000:
                    con.executemany("INSERT OR REPLACE INTO ways VALUES (?,?,?)", batch_w)
                    con.executemany("INSERT OR REPLACE INTO ways_rtree VALUES (?,?,?,?,?)", batch_r)
                    con.commit()
                    batch_w, batch_r = [], []
                    if n % 500000 == 0:
                        _log(f"zaladowano {n} drog")
        if batch_w:
            con.executemany("INSERT OR REPLACE INTO ways VALUES (?,?,?)", batch_w)
            con.executemany("INSERT OR REPLACE INTO ways_rtree VALUES (?,?,?,?,?)", batch_r)
        src_info = subprocess.run(["osmium", "fileinfo", "-g", "header.option.osmosis_replication_timestamp", str(SRC)],
                                  capture_output=True, text=True).stdout.strip()
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [
            ("source", str(SRC.name)), ("source_timestamp", src_info),
            ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S")), ("ways", str(n)),
            ("keep_tags", ",".join(KEEP_TAGS)),
        ])
        con.commit()
        con.close()
        TMP.replace(DB)
        for p in (SEQ, DIR / "nodes.idx"):
            try:
                p.unlink()
            except OSError:
                pass
        _log(f"KONIEC OK {n} drog, {DB.stat().st_size/1e9:.2f} GB, {time.time()-t0:.0f}s, zrodlo {src_info}")
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
    print("\n".join(LOG.read_text(encoding="utf-8").splitlines()[-8:]) if LOG.exists() else "brak logu")
    for p in (ROADS, SEQ, TMP, DB):
        if p.exists():
            print(f"{p.name}: {p.stat().st_size/1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--status"
    sys.exit({"--start": start, "--status": status, "--run": build}.get(arg, status)())
