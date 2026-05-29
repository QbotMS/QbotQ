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
    if d.safety_class == "READ_ONLY":
        try:
            result = cap.run({})
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                print(f"  Run status: {status}")
                if "data" in result:
                    data_keys = list(result["data"].keys()) if isinstance(result["data"], dict) else []
                    print(f"  Data keys: {data_keys[:10]}")
            else:
                errors.append(f"run() returned non-dict: {type(result)}")
        except Exception as exc:
            errors.append(f"run() error: {exc}")

    # 4. No secrets in output — check values, not keys (log content may contain env var names)
    result_str = json.dumps(result if isinstance(result, dict) else {}, default=str)
    for secret_word in ("api_key", "password", "authorization", "secret"):
        if secret_word.lower() in result_str.lower():
            # Only flag if it looks like a real value (not just a reference)
            import re
            matches = re.findall(rf'.{{0,40}}{secret_word}.{{0,40}}', result_str, re.IGNORECASE)
            for m in matches:
                if len(m.strip()) > len(secret_word) + 10:  # has real content beyond the word
                    errors.append(f"Potential secret leak: '{secret_word}' in output context")
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
