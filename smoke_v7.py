#!/usr/bin/env python3
from qbot_query_handler import handle_query, _normalize_question, _resolve_tuscany_route_id

print("=== C1: normalizacja ===")
tests = [
    ("etap4 toskania", "etap 4 toskania"),
    ("stage3 climbs tuscany", "stage 3 climbs tuscany"),
    ("waga trend 30d", "waga trend 30 dni"),
    ("waga 7d", "waga 7 dni"),
]
for inp, expected in tests:
    out = _normalize_question(inp)
    ok = "OK" if out == expected else "FAIL"
    print(f"  {ok}: {inp!r} -> {out!r}")

print()
print("=== C4: stage 3 english ===")
rid = _resolve_tuscany_route_id("stage 3 climbs tuscany")
print(f"  stage 3 -> route_id: {rid} (expected 55395120)")

print()
print("=== C1+C4: end-to-end etap4 ===")
r = handle_query("pokaz etap4 toskanie")
print(f"  intent: {r.get('intent')}")
print(f"  answer[:100]: {r.get('answer','')[:100]}")

print()
print("=== E1: dodaj posilek ===")
r2 = handle_query("dodaj posilek: owsianka 400kcal")
print(f"  intent: {r2.get('intent')}, status: {r2.get('status')}")
print(f"  answer[:120]: {r2.get('answer','')[:120]}")

print()
print("=== E3: skasuj wpis ===")
r3 = handle_query("skasuj ostatni wpis zywieniowy")
print(f"  intent: {r3.get('intent')}, status: {r3.get('status')}")
print(f"  answer[:100]: {r3.get('answer','')[:100]}")

print()
print("=== E4: dodaj etap ===")
r4 = handle_query("dodaj etap 8 toskania: Scandicci-Rzym 200km")
print(f"  intent: {r4.get('intent')}, status: {r4.get('status')}")
print(f"  answer[:100]: {r4.get('answer','')[:100]}")

print()
print("=== D: krotkie pytanie bez kontekstu ===")
r5 = handle_query("a jakie sa tam atrakcje?")
print(f"  intent: {r5.get('intent')}, status: {r5.get('status')}")
print(f"  answer[:150]: {r5.get('answer','')[:150]}")

print()
print("=== C5: waga trend 30d ===")
r6 = handle_query("waga trend 30d")
print(f"  intent: {r6.get('intent')}")
print(f"  answer[:100]: {r6.get('answer','')[:100]}")
