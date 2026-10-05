#!/usr/bin/env python3
"""Test lokalnych zabytkow OSM na trasie: ile obiektow w korytarzu 2 km, zamki/ruiny po km.
Bez Google i bez Overpass (tylko baza lokalna). Sekundy."""
import collections
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.routes import route_attraction_sources as src  # noqa: E402
from tools.rwgps import osm_local  # noqa: E402

gpx = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/qbot/app/outgoing/komoot/komoot-3331694546.gpx")
print("landmarks_enabled:", osm_local.landmarks_enabled())
pts = src._route_points(gpx)
t = time.time()
rows, missing = src.discover_osm_landmarks(None, pts, cache_root=Path("/tmp/qbot_lm_test_cache"))
print(f"obiekty OSM w korytarzu: {len(rows)}, brakujace odcinki: {missing}, {time.time()-t:.1f}s")
cnt = collections.Counter((r["tags"].get("historic") or r["tags"].get("tourism") or "?") for r in rows)
print("typy:", cnt.most_common(10))
for r in sorted(rows, key=lambda x: x["km"]):
    tg = r["tags"]
    if tg.get("historic") in ("castle", "ruins", "fort", "manor", "palace") or "zamek" in r["name"].lower():
        print(f"  km {r['km']:5.1f}  {r['dist']:5.0f} m  {r['name']}  [{tg.get('historic')}, heritage={tg.get('heritage')}]")
