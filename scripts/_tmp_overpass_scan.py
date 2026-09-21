import json, sys, time
sys.path.insert(0, "/opt/qbot/app")
import httpx
from tools.rwgps import route_surface_engine as eng

OUT = "/opt/qbot/app/logs/_tmp_overpass_scan.json"
ART = "/opt/qbot/app/outgoing/komoot/komoot-3180619966.gpx"

CANDIDATES = [
    "https://overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.osm.rambler.ru/cgi/interpreter",
]

pts = eng.extract_artifact_points(ART)
dists = eng._cumulative_distances(pts)
samples = eng._sample_track(pts, dists, 50)
chunk = samples[:220]
s_, w_, n_, e_ = eng._bbox_for_samples(chunk, pad_m=float(eng.PRIMARY_CORRIDOR_RADIUS_M))
q = (f'[out:json][timeout:60];way["highway"]({s_:.7f},{w_:.7f},{n_:.7f},{e_:.7f});out tags geom;')

res = {"bbox": [s_, w_, n_, e_], "endpoints": []}
headers = {"User-Agent": eng.USER_AGENT, "Referer": eng.REFERER}

for url in CANDIDATES:
    t0 = time.time()
    entry = {"endpoint": url}
    try:
        r = httpx.post(url, data={"data": q}, headers=headers, timeout=60)
        entry["http"] = r.status_code
        entry["sec"] = round(time.time() - t0, 1)
        entry["bytes"] = len(r.content)
        if r.status_code == 200:
            try:
                entry["ways"] = sum(1 for el in r.json().get("elements", [])
                                    if el.get("type") == "way")
            except Exception as ex:
                entry["parse_error"] = str(ex)[:150]
        else:
            entry["body_head"] = r.text[:200]
    except Exception as ex:
        entry["error"] = f"{type(ex).__name__}: {str(ex)[:130]}"
        entry["sec"] = round(time.time() - t0, 1)
    res["endpoints"].append(entry)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

res["done"] = True
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("DONE")
