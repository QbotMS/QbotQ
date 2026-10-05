#!/usr/bin/env python3
"""Sledzi wybrane obiekty przez potok atrakcji (bez Google - 0 zapytan): zrodla -> dedupe
-> classify/score -> collapse_stops. Wikipedia/Wikidata z cache, OSM z bazy lokalnej.
  .venv/bin/python3 scripts/diag_attraction_trace.py <gpx> <fraza> [<fraza> ...]"""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.routes import route_attraction_engine as eng  # noqa: E402
from qbot3.routes import route_attraction_sources as src  # noqa: E402

gpx = Path(sys.argv[1])
needles = [n.lower() for n in sys.argv[2:]]


def hit(row):
    return any(n in str(row.get("name", "")).lower() for n in needles)


s = requests.Session()
s.headers.update({"User-Agent": src.USER_AGENT, "Accept": "application/json"})
pts = src._route_points(gpx)
wiki = src.discover_wikipedia(s, pts)
osm, _miss = src.discover_osm_landmarks(s, pts)
rows = wiki + osm
wd = src.discover_wikidata(s, (r.get("qid") for r in rows))
print("ZRODLA:")
for r in rows:
    if hit(r):
        print(f"  {sorted(r['sources'])} {r['name']} km={r['km']:.1f} dist={r['dist']:.0f} qid={r.get('qid')} tags={ {k: r['tags'][k] for k in list(r['tags'])[:6]} }")
merged = eng.dedupe(rows)
print("PO DEDUPE:")
for r in merged:
    if hit(r):
        print(f"  {sorted(r['sources'])} {r['name']} km={r['km']:.1f} dist={r['dist']:.0f} qid={r.get('qid')}")
        cat, why = eng.classify(r, wd.get(r.get("qid"), {}))
        sc = eng.score(r, wd.get(r.get("qid"), {}), [])
        print(f"     classify={cat} ({why})  score={None if sc is None else sc['score']} comp={None if sc is None else sc['components']}")
scored = [v for r in merged if (v := eng.score(r, wd.get(r.get("qid"), {}), []))]
stops = eng.collapse_stops(scored)
print("PRZYSTANKI:")
for st in stops:
    if hit(st) or any(any(n in x.lower() for n in needles) for x in st.get("nearby", [])):
        print(f"  {st['name']} score={st['score']} km={st['km']:.1f} nearby={st.get('nearby')}")
