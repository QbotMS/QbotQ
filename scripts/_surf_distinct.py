#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/qbot/app")
from scripts.route_map_render import db_connect, load_segments
rid = "55798129"
segs = load_segments(rid)
from collections import Counter
c = Counter()
for _, dist, surf in segs:
    c[surf] += (dist or 0)
total = sum(c.values()) or 1
print("n_segments", len(segs))
for surf, m in c.most_common():
    print(f"{m/total*100:6.2f}%  {m/1000:7.2f}km  surface={surf!r}")
