#!/usr/bin/env python3
"""test_intake_logs_0531.py — Test nutrition_intake_logs_list for 2026-05-31.

Usage:
    cd /opt/qbot/app
    .venv/bin/python scripts/test_intake_logs_0531.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/opt/qbot/app")
from qbot_query_handler import handle_query


def test_intake_logs_0531():
    queries = [
        ("pokaż całe jedzenie 2026-05-31", "całe jedzenie"),
        ("pokaż surową listę wpisów dla 2026-05-31", "surową listę"),
        ("co jadłem 2026-05-31", "co jadłem"),
        ("lista posiłków 2026-05-31", "lista posiłków"),
        ("pokaż intake_logs 2026-05-31", "intake_logs"),
    ]

    for q, label in queries:
        result = handle_query(q)
        intent = result.get("intent")
        status = result.get("status")
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print(f"Intent: {intent}  Status: {status}")

        if intent != "nutrition_intake_logs_list":
            print(f"FAIL: Expected nutrition_intake_logs_list, got {intent}")
            return False

        data = result.get("data", {})
        meals = data.get("meals", [])
        totals = data.get("totals", {})

        print(f"Meals count: {len(meals)}")
        print(f"Totals: {json.dumps(totals, ensure_ascii=False)}")

        if not meals:
            print("WARN: no meals returned (data may not exist for 2026-05-31)")
            continue

        print(f"\nMeals:")
        for m in meals:
            mt = m.get("meal_totals", {})
            note = m.get("note") or m.get("meal_type") or "?"
            items_str = ", ".join(ii.get("food_name", "?") for ii in m.get("items", []))
            print(f"  ID={m['id']} {m['eaten_at'][:16]} {note}")
            print(f"     kcal={mt.get('kcal',0):.0f} B={mt.get('protein_g',0):.1f} W={mt.get('carbs_g',0):.1f} T={mt.get('fat_g',0):.1f}")
            print(f"     items: {items_str}")

        # Check for expected meals
        food_names = set()
        for m in meals:
            for ii in m.get("items", []):
                fn = ii.get("food_name", "")
                if fn:
                    food_names.add(fn)

        expected_foods = [
            "Owsianka",
            "Pizza",
            "łosoś",
            "Red Bull",
            "Hot dog",
        ]
        found = [f for f in expected_foods if any(f.lower() in fn.lower() for fn in food_names)]
        missing = [f for f in expected_foods if f not in found]
        print(f"\nExpected food checks: found={found}, missing={missing}")

        # Check totals if data exists
        if totals:
            k = totals.get("kcal_total", 0)
            p = totals.get("protein_g", 0)
            c = totals.get("carbs_g", 0)
            f = totals.get("fat_g", 0)
            fb = totals.get("fiber_g", 0)
            print(f"\nTotals: kcal={k:.1f} protein={p:.1f} carbs={c:.1f} fat={f:.1f} fiber={fb:.1f}")

            # Allow some tolerance due to floating point
            expected = {"kcal_total": 2280, "protein_g": 108.8, "carbs_g": 271.0, "fat_g": 83.45, "fiber_g": 23.0}
            for key, exp_val in expected.items():
                actual = totals.get(key, 0)
                diff = abs(actual - exp_val)
                if diff > 1.0:
                    print(f"  {key}: expected {exp_val}, got {actual} (diff={diff:.2f}) — FAIL")
                    return False
                else:
                    print(f"  {key}: expected {exp_val}, got {actual} (diff={diff:.2f}) — OK")

    return True


def run():
    print("=" * 60)
    print("TEST: nutrition_intake_logs_list for 2026-05-31")
    print("=" * 60)

    success = test_intake_logs_0531()
    print(f"\n{'='*60}")
    if success:
        print("RESULT: PASSED")
        return 0
    else:
        print("RESULT: FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run())
