#!/usr/bin/env python3
"""Szybki test lokalnej bazy drog na trasie komoot-3331694546: pokrycie i liczba drog
dla kazdego kawalka (17 x 220 probek), czas zapytania. Sekundy - mozna z dev_shell_exec."""
import collections
import sys
import time

sys.path.insert(0, "/opt/qbot/app")
import tools.rwgps.route_surface_engine as eng  # noqa: E402
from tools.rwgps import osm_local  # noqa: E402
from tools.rwgps.client import extract_artifact_points  # noqa: E402

print("meta:", osm_local.meta())
pts = extract_artifact_points("/opt/qbot/app/outgoing/komoot/komoot-3331694546.gpx")
samples = eng._sample_track(pts, eng._cumulative_distances(pts), 50)
tot_t = 0.0
for i, start in enumerate(range(0, len(samples), 220), start=1):
    ch = samples[start:start + 220]
    s, w, n, e = eng._bbox_for_samples(ch, pad_m=80.0)
    cov = osm_local.covers_bbox(s, w, n, e)
    t = time.time()
    p = osm_local.query_ways(s, w, n, e) if cov else {"elements": []}
    dt = time.time() - t
    tot_t += dt
    surf = sum(1 for el in p["elements"] if el["tags"].get("surface"))
    hw = collections.Counter(el["tags"].get("highway") for el in p["elements"]).most_common(3)
    print(f"kawalek {i:2d} km {ch[0].dist_m/1000:5.1f}-{ch[-1].dist_m/1000:5.1f} | lokalnie={cov} | drog={len(p['elements']):5d} | z surface={surf:5d} | {dt*1000:5.0f} ms | {hw}")
print(f"razem zapytania: {tot_t:.1f}s")
