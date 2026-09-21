import json, sys, time
sys.path.insert(0, "/opt/qbot/app")
import httpx
from tools.rwgps import route_surface_engine as eng

OUT = "/opt/qbot/app/logs/_tmp_overpass_diag.json"
ART = "/opt/qbot/app/outgoing/komoot/komoot-3180619966.gpx"
ENDPOINTS = [
    "https://overpass.osm.ch/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

pts = eng.extract_artifact_points(ART)
dists = eng._cumulative_distances(pts)
samples = eng._sample_track(pts, dists, 50)
chunk_size = 220
chunks = [samples[i:i + chunk_size] for i in range(0, len(samples), chunk_size)]

res = {"points": len(pts), "samples": len(samples), "chunks": len(chunks),
       "timeout": eng.OVERPASS_TIMEOUT_SEC, "results": []}

headers = {"User-Agent": eng.USER_AGENT, "Referer": eng.REFERER}

for idx, chunk in enumerate(chunks, start=1):
    s_, w_, n_, e_ = eng._bbox_for_samples(chunk, pad_m=float(eng.PRIMARY_CORRIDOR_RADIUS_M))
    q = (f'[out:json][timeout:{int(eng.OVERPASS_TIMEOUT_SEC)}];'
         f'way["highway"]({s_:.7f},{w_:.7f},{n_:.7f},{e_:.7f});out tags geom;')
    for url in ENDPOINTS:
        t0 = time.time()
        entry = {"chunk": idx, "endpoint": url}
        try:
            r = httpx.post(url, data={"data": q}, headers=headers,
                           timeout=eng.OVERPASS_TIMEOUT_SEC)
            entry["http"] = r.status_code
            entry["sec"] = round(time.time() - t0, 1)
            entry["bytes"] = len(r.content)
            if r.status_code == 200:
                try:
                    entry["ways"] = sum(1 for el in r.json().get("elements", [])
                                        if el.get("type") == "way")
                except Exception as ex:
                    entry["parse_error"] = str(ex)[:200]
                    entry["body_head"] = r.text[:300]
            else:
                entry["body_head"] = r.text[:300]
        except Exception as ex:
            entry["error"] = f"{type(ex).__name__}: {str(ex)[:160]}"
            entry["sec"] = round(time.time() - t0, 1)
        res["results"].append(entry)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)

res["done"] = True
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("DONE")
