#!/usr/bin/env python3
from tools.trip_attractions import handle_trip_attractions
from qbot_query_handler import _handle_wellness_day, _handle_route_climbs

# P1: woda etap 1 — tylko water section
print("=== P1: woda pitna na etapie 1 ===")
r = handle_trip_attractions("woda pitna na etapie 1 toskania")
print("  section_filter:", r["data"].get("section_filter"))
print("  records:", r["data"]["count"])
# Czy odpowiedź zawiera tylko Woda pitna?
sections = [l for l in r["answer"].split("\n") if l.startswith("[") or "Woda" in l or "Atrakcje" in l or "Jedzenie" in l]
print("  sections in answer:", sections[:8])

# P2: podjazdy toskania etap 3 — resolved_route_id
print()
print("=== P2: podjazdy toskania etap 3 ===")
r2 = _handle_route_climbs("podjazdy toskania etap 3")
print("  resolved_route_id:", r2["data"].get("resolved_route_id"))
print("  answer[:120]:", r2["answer"][:120])

# P3: HRV null message
print()
print("=== P3: wellness hrv null ===")
r3 = _handle_wellness_day(None, "HRV i body battery dzi\u015b")
print("  answer:", r3["answer"])
