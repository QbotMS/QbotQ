#!/usr/bin/env python3
"""Diagnostyka wejsc opisu Planera (planer_opis) dla trasy: atrakcje, spine, krajobraz."""
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.routes import planer_opis as po  # noqa: E402
from qbot3.routes.route_attraction_store import get_route_attractions  # noqa: E402

rid = sys.argv[1] if len(sys.argv) > 1 else "komoot-3331694546"
conn = po._db()
base = po._resolve_base(conn, rid)
print("base:", base)
for tier in ("recommended", "candidates", None):
    try:
        r = get_route_attractions(conn, base["base_id"], tier=tier) if tier else get_route_attractions(conn, base["base_id"])
        print(f"atrakcje tier={tier}:", None if r is None else len(r), (r or [])[:3])
    except Exception as exc:
        print(f"atrakcje tier={tier} BLAD:", type(exc).__name__, exc)
print("pois():", po._pois(conn, base["base_id"])[:6])
p = po._SPINE_DIR / ("spine_%s.json" % rid)
print("spine:", p, p.exists(), (p.stat().st_mtime if p.exists() else None))
print("spine_surface:", po._spine_surface(rid))
print("krajobraz:", po._landscape(conn, base["base_id"])[:4])
