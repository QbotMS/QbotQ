#!/usr/bin/env python3
from tools.trip_attractions import handle_trip_attractions
from qbot_query_handler import _handle_nutrition_range, handle_query

# R5: woda etapie 1
print("=== R5: woda pitna na etapie 1 ===")
r = handle_trip_attractions("woda pitna na etapie 1 toskania")
print("  records:", r["data"]["count"])
print("  ids:", r["data"]["records"])
titles = [line for line in r["answer"].split("\n") if "[" in line and "]" in line]
print("  sections:", titles)

# N1: per_day bez intake_kcal
print()
print("=== N1: per_day 2026-05-30 ===")
r2 = _handle_nutrition_range("makro za ostatni tydzien")
pd = r2["data"]["per_day"]
e30 = [e for e in pd if e["date"] == "2026-05-30"][0]
print("  keys:", sorted(e30.keys()))
print("  kcal_total:", e30.get("kcal_total"))
print("  intake_kcal:", e30.get("intake_kcal"))
print("  balance_kcal:", e30.get("balance_kcal"))

# R6: shelf canonical
print()
print("=== R6: canonical shelf ===")
r3 = handle_query("artefakty canonical tuscany")
print("  shelf_filter:", r3["data"].get("shelf_filter"))
print("  count:", r3["data"].get("count", 0))
lines = [l for l in r3["answer"].split("\n") if "polka:" in l]
print("  polka values:", list(set(lines))[:5])
