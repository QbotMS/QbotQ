#!/usr/bin/env python3
"""Diagnostyka: gdzie pada zapis profilu nawierzchni (wyjatek polykany w client.py)."""
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
os.chdir("/opt/qbot/app")
for p in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"):
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'"))
    except OSError as exc:
        print("env", p, exc)
os.environ.setdefault("QBOT3_ENABLED", "1")

import api_db  # noqa: E402
import tools.rwgps.client as client  # noqa: E402
from tools.rwgps.route_surface_engine import analyze_route_surface  # noqa: E402


def _wrap(mod, name):
    orig = getattr(mod, name)

    def inner(*a, **kw):
        try:
            r = orig(*a, **kw)
            print(f"{name} -> {type(r).__name__} {str(r)[:200] if not isinstance(r, dict) else {k: r.get(k) for k in ('id', 'route_id', 'sha256')}}")
            return r
        except Exception:
            print(f"{name} WYJATEK:")
            traceback.print_exc()
            raise
    setattr(mod, name, inner)


for n in ("_persist_route_artifact_record", "_surface_profile_quality_score", "_has_better_existing_surface_profile", "_artifact_route_id_from_path"):
    _wrap(client, n)
for n in ("upsert_route_surface_profile", "replace_route_surface_segments"):
    _wrap(api_db, n)

path = Path("/opt/qbot/app/outgoing/komoot/komoot-3331694546.gpx")
sr = analyze_route_surface(artifact_path=str(path), sample_distance_m=50)
print("analiza:", sr.get("quality_status"), sr.get("coverage_pct"), "segmentow:", len(sr.get("segments") or []))
payload = {"surface_profile": {"quality_status": sr.get("quality_status")}, "surface_source": "auto", "sample_every_m": 50}
print("persist:", str(client._persist_route_surface_profile(path, payload, sr))[:300])
