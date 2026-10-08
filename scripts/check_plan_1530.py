#!/usr/bin/env python3
"""Sprawdzenie 2026-10-06: silnik pogody trasy dla roznych godzin startu (bez web)."""
import json, os, sys, time
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from qbot3.routes.route_meteo_engine import run_meteo_engine
RID = sys.argv[1] if len(sys.argv) > 1 else "komoot-3332912673"
for st in ("09:30", "15:30", "20:00"):
    t = time.time()
    m = run_meteo_engine(route_id=RID, date_str="2026-10-06", start_time=st)
    seg = m.get("per_segment") or []
    print("== start", st, "| s:", round(time.time() - t, 1), "| status:", m.get("status"), "| odcinkow:", len(seg),
          "| alertow:", len(m.get("alerts") or []))
    if m.get("error"):
        print("   blad:", m.get("error"))
    print("   summary:", json.dumps(m.get("summary"), ensure_ascii=False, default=str)[:400])
    if seg:
        a, b = seg[0], seg[-1]
        keys = [k for k in a.keys() if any(x in k for x in ("eta", "time", "temp", "utci", "wind", "precip", "km"))][:10]
        print("   pierwszy:", {k: a.get(k) for k in keys})
        print("   ostatni :", {k: b.get(k) for k in keys})
