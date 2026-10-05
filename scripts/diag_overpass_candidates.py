#!/usr/bin/env python3
"""Diagnostyka 2 (2026-10-05): DNS (IPv4/IPv6) dla serwerow Overpass + test
kandydatow na niezalezne zapasy. Kolejka/SSH, nie dev_shell_exec."""
import socket
import time

import httpx

UA = {"User-Agent": "QBot/1.0 route_surface_engine_v1; contact=qbot-local", "Accept": "application/json"}
SMALL = '[out:json][timeout:10];way["highway"](50.40,19.70,50.41,19.71);out ids;'
REAL = '[out:json][timeout:25];way["highway"](50.2856,19.4953,50.3259,19.5968);out tags geom;'
EPS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
for ep in EPS:
    host = ep.split("/")[2]
    try:
        addrs = sorted({f"{'v6' if a[0] == socket.AF_INET6 else 'v4'}:{a[4][0]}" for a in socket.getaddrinfo(host, 443)})
    except Exception as exc:
        addrs = [f"DNS BLAD {exc}"]
    print(host, addrs, flush=True)
    for name, q, to in (("male", SMALL, 15), ("kawalek12", REAL, 35)):
        t = time.time()
        try:
            r = httpx.post(ep, data={"data": q}, headers=UA, timeout=to)
            n = len(r.json().get("elements", [])) if r.status_code == 200 else None
            print(f"  {name}: HTTP {r.status_code} {time.time()-t:.1f}s elementy={n} {'' if r.status_code == 200 else r.text[:150]!r}", flush=True)
        except Exception as exc:
            print(f"  {name}: BLAD {type(exc).__name__}: {exc} {time.time()-t:.1f}s", flush=True)
# status limitu na overpass-api.de (czy nas zbanowano)
for url in ("https://overpass-api.de/api/status", "http://overpass-api.de/api/status"):
    try:
        r = httpx.get(url, timeout=10)
        print(url, r.status_code, r.text[:300].replace("\n", " | "))
    except Exception as exc:
        print(url, "BLAD", type(exc).__name__, exc)
print("KONIEC")
