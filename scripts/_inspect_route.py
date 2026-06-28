import json
from collections import Counter
d=json.load(open('/opt/qbot/app/data/routes/rwgps_route_cache.json'))
tp=d['55798129']['route']['track_points']
print("N", len(tp))
print("S vals", Counter(p.get('S') for p in tp))
print("R vals", Counter(p.get('R') for p in tp))
# surface cache
try:
    sc=json.load(open('/opt/qbot/app/data/route_surface_cache.json'))
    print("SURF CACHE type", type(sc))
    if isinstance(sc,dict):
        print("SURF keys", list(sc.keys())[:10])
        if '55798129' in sc:
            v=sc['55798129']
            print("55798129 type", type(v))
            print(json.dumps(v)[:600])
except Exception as e:
    print("surfcache err", e)
