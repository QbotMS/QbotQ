#!/usr/bin/env python3
from qbot_query_handler import _resolve_intent, handle_query

print("=== Routing ===")
tests = [
    ("gara\u017c", "garage_status"),
    ("poka\u017c gara\u017c", "garage_status"),
    ("szukaj kask\u00f3w w gara\u017cu", "garage_search"),
    ("mam jakie\u015b r\u0119kawiczki?", "garage_search"),
]
for q, exp in tests:
    got = _resolve_intent(q)
    ok = "OK" if got == exp else "FAIL"
    print(f"  {ok}: {q!r} -> {got}")

print()
print("=== Feasibility ===")
r = handle_query("ocena trasy 55395119")
print("  status:", r.get("status"))
print("  answer:", r.get("answer", "")[:200])

print()
print("=== Multi xert+bilans+waga ===")
r2 = handle_query("forma Xert, bilans kaloryczny i waga z dzi\u015b")
print("  answer:", r2.get("answer", "")[:400])
