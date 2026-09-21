import os, sys, time, json
sys.path.insert(0, "/opt/qbot/app")
import httpx

Q = "[out:json][timeout:25];node(37.05,15.28,37.06,15.29)[amenity=cafe];out count;"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]
print("QBOT_OVERPASS_ENDPOINTS env:", os.getenv("QBOT_OVERPASS_ENDPOINTS", "(brak)"))
print("QBOT_OVERPASS_TIMEOUT_SEC env:", os.getenv("QBOT_OVERPASS_TIMEOUT_SEC", "(brak)"))
for url in ENDPOINTS:
    t0 = time.time()
    try:
        r = httpx.post(url, data={"data": Q}, timeout=30,
                       headers={"User-Agent": "QBot/1.0 diag; contact=qbot-local"})
        print(f"{url} -> HTTP {r.status_code} w {time.time()-t0:.1f}s  ({len(r.content)} B)")
    except Exception as e:
        print(f"{url} -> BLAD po {time.time()-t0:.1f}s: {type(e).__name__}: {str(e)[:120]}")
