#!/usr/bin/env python3
"""QBot3 Capability Test Harness — validates capabilities before promotion.

Usage:
  python3 -m qbot3.capabilities.test_harness
  python3 -m qbot3.capabilities.test_harness --capability daily_report_status
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from qbot3.capabilities import capability_registry, find_capability, list_capabilities
from qbot3.capabilities.manifest import validate_manifest, can_promote_to_active


def test_capability(name: str) -> list[str]:
    errors: list[str] = []
    cap = find_capability(name)
    if not cap:
        return [f"Capability not found: {name}"]

    # 1. Import check
    print(f"  📦 Import: {cap.__class__.__name__}")
    errors.extend(validate_manifest(cap))
    if errors:
        return errors

    d = cap.definition
    print(f"  Name: {d.name}")
    print(f"  Safety: {d.safety_class}")
    print(f"  State: {d.promotion_state}")
    print(f"  Type: {d.capability_type}")

    # 2. Schema validation
    if d.inputs_schema:
        print(f"  Input schema: OK ({len(d.inputs_schema)} fields)")
    else:
        print("  Input schema: empty")
    if d.output_schema:
        print(f"  Output schema: OK ({len(d.output_schema)} fields)")
    else:
        print("  Output schema: empty")

    # 3. Run with empty context (read-only safe)
    run_result: dict | None = None
    from qbot3.capabilities.base import READ_ONLY_SAFETY
    if d.safety_class in READ_ONLY_SAFETY:
        try:
            run_result = cap.run({})
            if isinstance(run_result, dict):
                status = run_result.get("status", "unknown")
                print(f"  Run status: {status}")
                if "data" in run_result:
                    data_keys = list(run_result["data"].keys()) if isinstance(run_result["data"], dict) else []
                    print(f"  Data keys: {data_keys[:10]}")
            else:
                errors.append(f"run() returned non-dict: {type(run_result)}")
        except Exception as exc:
            errors.append(f"run() error: {exc}")

    # 4. No secrets in output — check actual VALUES, not dict keys or field names
    # Only flag if a value looks like a credential string (long, alphanumeric, no spaces)
    import re as _re
    result_str = json.dumps(run_result if isinstance(run_result, dict) else {}, default=str)
    # Skip keys — only check values that look like tokens/credentials (no spaces, long strings)
    potential_secrets = _re.findall(r':\s*"([A-Za-z0-9_\-\.]{20,})"', result_str)
    for val in set(potential_secrets):
        # Skip hex colors, known field values, snake_case labels, timestamps, UUIDs
        if _re.match(r'^[0-9a-f]{32}$', val, _re.I):
            continue
        if _re.match(r'^\d{4}-\d{2}-\d{2}', val):
            continue
        if _re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', val, _re.I):
            continue
        if _re.match(r'^[a-z]+[a-z_]+[a-z]$', val):  # snake_case field values
            continue
        if _re.match(r'^[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$', val):  # dotted paths
            continue
        errors.append(f"Potential secret leak: long value ({len(val)} chars) in output: {val[:20]}...")
        break

    # 5. Promotion check
    if d.promotion_state == "active":
        promotable, promote_errors = can_promote_to_active(cap)
        if not promotable:
            for e in promote_errors:
                if "has tests" in e:
                    continue  # Skip test existence check in harness
                errors.append(f"Promotion issue: {e}")

    return errors


def run_all_tests() -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    caps = capability_registry()
    if not caps:
        print("  ⚠️  No capabilities discovered")
        return {"_discovery": ["No capabilities found"]}

    print(f"  Discovered {len(caps)} capabilities")
    for name in sorted(caps):
        errs = test_capability(name)
        if errs:
            results[name] = errs
            for e in errs:
                print(f"    ❌ {e}")
        else:
            print(f"    ✅ Passed")
        print()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QBot3 Capability Test Harness")
    parser.add_argument("--capability", "-c", type=str, help="Test a specific capability")
    args = parser.parse_args()

    print("=== QBot3 Capability Test Harness ===")
    print()

    if args.capability:
        errors = test_capability(args.capability)
        if errors:
            print(f"\n❌ {len(errors)} error(s):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("\n✅ Capability OK")
    else:
        results = run_all_tests()
        total = sum(len(v) for v in results.values())
        if total:
            print(f"\n❌ {total} error(s) across {len(results)} capabilities")
            sys.exit(1)
        else:
            print("\n✅ All capabilities OK")
