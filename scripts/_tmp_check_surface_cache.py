import json, os, sys
p = "/opt/qbot/app/data/route_surface_cache.json"
print("plik:", p, "| istnieje:", os.path.exists(p))
if os.path.exists(p):
    st = os.stat(p)
    import datetime
    print("zmodyfikowany:", datetime.datetime.fromtimestamp(st.st_mtime))
    d = json.load(open(p, encoding="utf-8"))
    print("wpisow:", len(d))
    items = []
    for k, v in d.items():
        ts = v.get("cached_at") or v.get("generated_at") or v.get("ts")
        err = v.get("error")
        dom = v.get("dominant_surface") or (v.get("result") or {}).get("dominant_surface")
        items.append((str(ts), k, dom, str(err)[:60]))
    for row in sorted(items)[-15:]:
        print(row)
