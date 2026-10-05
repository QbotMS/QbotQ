#!/usr/bin/env python3
"""Diagnostyka 2026-10-05: lista serwerow Overpass widziana przez silnik nawierzchni
(z env uslugi) + test kazdego: male zapytanie i realny kawalek 12 trasy komoot-3331694546.
Uruchamiac przez SSH/kolejke (do ~3 min), NIE przez dev_shell_exec."""
import os
import sys
import time

sys.path.insert(0, "/opt/qbot/app")
os.chdir("/opt/qbot/app")
for p in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"):
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass

import httpx  # noqa: E402
import tools.rwgps.route_surface_engine as eng  # noqa: E402
from tools.rwgps.client import extract_artifact_points  # noqa: E402

print("QBOT_OVERPASS_ENDPOINTS env:", repr(os.getenv("QBOT_OVERPASS_ENDPOINTS")))
print("timeout/retries/backoff:", eng.OVERPASS_TIMEOUT_SEC, eng.OVERPASS_RETRIES, eng.OVERPASS_BACKOFF_SEC)
eps = eng._configured_overpass_endpoints()
print("endpointy:", eps, flush=True)

pts = extract_artifact_points("/opt/qbot/app/outgoing/komoot/komoot-3331694546.gpx")
d = eng._cumulative_distances(pts)
samples = eng._sample_track(pts, d, 50)
chunk = samples[11 * 220: 12 * 220]
s, w, n, e = eng._bbox_for_samples(chunk, pad_m=80.0)
print(f"kawalek 12: km {chunk[0].dist_m/1000:.1f}-{chunk[-1].dist_m/1000:.1f} bbox {s:.4f},{w:.4f},{n:.4f},{e:.4f}", flush=True)

small = '[out:json][timeout:10];way["highway"](50.40,19.70,50.41,19.71);out ids;'
real = f'[out:json][timeout:25];way["highway"]({s:.7f},{w:.7f},{n:.7f},{e:.7f});out tags geom;'
hdr = {"User-Agent": eng.USER_AGENT, "Referer": eng.REFERER, "Accept": "application/json"}
for ep in eps:
    for name, q, to in (("male", small, 15), ("kawalek12", real, 30)):
        t = time.time()
        try:
            r = httpx.post(ep, data={"data": q}, headers=hdr, timeout=to)
            body = r.text[:120].replace("\n", " ")
            n_el = len(r.json().get("elements", [])) if r.status_code == 200 else None
            print(f"{ep} | {name} | HTTP {r.status_code} | {time.time()-t:.1f}s | elementy={n_el} | {body if r.status_code != 200 else ''}", flush=True)
        except Exception as exc:
            print(f"{ep} | {name} | BLAD {type(exc).__name__}: {exc} | {time.time()-t:.1f}s", flush=True)
print("KONIEC")
