#!/usr/bin/env python3
from qbot_query_handler import (
    _handle_garage_search, _handle_memories_search, _handle_ride_report_diagnostic,
    handle_query
)
from tools.trip_attractions import handle_trip_attractions

print("=== 1: rękawiczki? (punctuation) ===")
r = _handle_garage_search("mam jakie\u015b r\u0119kawiczki?")
print("  status:", r.get("status"))
print("  count:", r["data"].get("result_count", 0))
print("  first result:", r["answer"][:100])

print()
print("=== 2: ride_report ostatnia jazda ===")
r2 = _handle_ride_report_diagnostic("raport z ostatniej jazdy")
print("  answer:", r2["answer"][:200])

print()
print("=== 3: POI etap 1 toskania ===")
r3 = handle_trip_attractions("atrakcje toskania etap 1")
lines = r3["answer"].split("\n")
print("  records:", r3["data"].get("count", 0))
# Sprawdź czy jest tylko stage 01
titles = [l for l in lines if "[" in l and "stage" in l.lower() or "etap" in l.lower()]
print("  sections:", titles[:5])

print()
print("=== 4: artifact canonical tuscany ===")
r4 = handle_query("artefakty canonical tuscany")
print("  answer:", r4["answer"][:200])

print()
print("=== 5: memories toskania ===")
r5 = _handle_memories_search("co pami\u0119tasz o Toskanii?")
print("  answer:", r5["answer"][:200])

print()
print("=== 6: kaski helmet-first ===")
r6 = _handle_garage_search("szukaj kask\u00f3w")
items = r6["data"].get("results", [])
cats = list(set(i.get("category","") for i in items))
print("  categories:", cats)
print("  count:", len(items))
