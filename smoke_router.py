#!/usr/bin/env python3
from qbot_query_handler import handle_query, _resolve_intent

print("=== 2.1: suma etapów ===")
r = handle_query("ile łącznie kilometrów mają wszystkie etapy toskanii razem?")
print("  intent:", r.get("intent"))
print("  answer:", r.get("answer","")[:300])

print()
print("=== 2.2: najdłuższy etap ===")
r2 = handle_query("który etap toskanii jest najdłuższy?")
print("  intent:", r2.get("intent"))
print("  answer:", r2.get("answer","")[:200])

print()
print("=== 2.3: feasibility etap 2 ===")
r3 = handle_query("ocena trasy etap 2 toskania")
print("  intent:", r3.get("intent"))
print("  route_id in data:", r3.get("data",{}).get("form",{}).get("ftp","?"))
print("  answer[:150]:", r3.get("answer","")[:150])
