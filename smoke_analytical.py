#!/usr/bin/env python3
import time
from qbot_query_handler import handle_query

tests = [
    ("1.1 najlepszy bilans", "który dzień w ostatnim tygodniu miałem najlepszy bilans kaloryczny?"),
    ("1.2 delta wagi",       "ile schudłem od 2026-05-01 do dziś i jaki był średni dzienny deficyt?"),
    ("1.3 trening vs ATL",   "czy mój ostatni trening był przed czy po szczycie zmęczenia Xert?"),
    ("B2 sen vs średnia",    "czy mój sen z wczoraj był lepszy niż średnia z ostatniego tygodnia?"),
]

for label, q in tests:
    print(f"\n=== {label} ===")
    t0 = time.time()
    r = handle_query(q)
    elapsed = time.time() - t0
    print(f"  intent: {r.get('intent')}  fallback: {r.get('fallback_reason','none')}")
    print(f"  status: {r.get('status')}  time: {elapsed:.1f}s")
    print(f"  answer: {r.get('answer','')[:250]}")
