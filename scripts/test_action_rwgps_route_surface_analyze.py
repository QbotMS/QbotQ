#!/usr/bin/env python3
"""Test rwgps_route_surface_analyze action type.

Tests the handler directly (not via MCP tool dispatch).

Usage:
  cd /opt/qbot/app
  .venv/bin/python scripts/test_action_rwgps_route_surface_analyze.py
"""

import json
import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

CONTROL_ROUTE_ID = 55395119
TARGET_ROUTE_ID = 55401067


def main():
    from qbot3.adapters.mcp_adapter import _execute_rwgps_route_surface_analyze

    print("=" * 60)
    print("TEST: rwgps_route_surface_analyze action handler")
    print("=" * 60)

    # ── Test 1: route_id required ──────────────────────────────
    print("\n[Test 1] route_id required")
    r = _execute_rwgps_route_surface_analyze("rwgps_route_surface_analyze", {}, "test-1")
    print(f"  status={r.get('status')} error={r.get('error')}")
    assert r["status"] == "ERROR", "Expected ERROR when route_id missing"
    print("  ✅ OK")

    # ── Test 2: empty route_id ─────────────────────────────────
    print("\n[Test 2] empty route_id")
    r = _execute_rwgps_route_surface_analyze("rwgps_route_surface_analyze", {"route_id": ""}, "test-2")
    print(f"  status={r.get('status')} error={r.get('error')}")
    assert r["status"] == "ERROR", "Expected ERROR when route_id empty"
    print("  ✅ OK")

    # ── Test 3: control route 55395119 (Toscany Etap II) ───────
    print(f"\n[Test 3] surface analyze route {CONTROL_ROUTE_ID}")
    r = _execute_rwgps_route_surface_analyze(
        "rwgps_route_surface_analyze",
        {"route_id": CONTROL_ROUTE_ID, "project_id": "tuscany_2026"},
        "test-3-control",
    )
    status = r.get("status")
    print(f"  status={status}")
    print(f"  point_count={r.get('point_count')}")
    print(f"  distance_km={r.get('distance_km')}")
    print(f"  elevation_gain_m={r.get('elevation_gain_m')}")
    print(f"  surface_breakdown keys={list(r.get('surface_breakdown', {}).keys())[:5]}")
    print(f"  highway_breakdown keys={list(r.get('highway_breakdown', {}).keys())[:5]}")
    print(f"  unknown_percent={r.get('unknown_percent')}")
    print(f"  json_path={r.get('json_path')}")
    print(f"  md_path={r.get('md_path')}")
    print(f"  write_committed={r.get('write_committed')}")

    assert status == "OK", f"Expected OK, got {status}"
    assert r.get("point_count", 0) > 0, "point_count must be > 0"
    assert r.get("distance_km", 0) > 0, "distance_km must be > 0"
    assert r.get("surface_breakdown"), "surface_breakdown must not be empty"
    assert r.get("highway_breakdown"), "highway_breakdown must not be empty"
    assert isinstance(r.get("unknown_percent"), (int, float)), "unknown_percent must be a number"
    assert r.get("json_path") and Path(r["json_path"]).exists(), "json_path must exist"
    assert r.get("md_path") and Path(r["md_path"]).exists(), "md_path must exist"
    assert r.get("write_committed") is False, "write_committed must be False"
    print("  ✅ OK")

    # ── Test 4: target route 55401067 (Puznówka 31.05) ─────────
    print(f"\n[Test 4] surface analyze route {TARGET_ROUTE_ID}")
    r = _execute_rwgps_route_surface_analyze(
        "rwgps_route_surface_analyze",
        {"route_id": TARGET_ROUTE_ID, "project_id": "tuscany_2026"},
        "test-4-target",
    )
    status = r.get("status")
    print(f"  status={status}")
    print(f"  route_name={r.get('route_name')}")
    print(f"  point_count={r.get('point_count')}")
    print(f"  distance_km={r.get('distance_km')}")
    print(f"  elevation_gain_m={r.get('elevation_gain_m')}")
    print(f"  unknown_percent={r.get('unknown_percent')}")
    print(f"  json_path={r.get('json_path')}")
    print(f"  md_path={r.get('md_path')}")
    print(f"  write_committed={r.get('write_committed')}")
    print(f"  recommendation={r.get('recommendation', '')[:80]}")

    assert status == "OK", f"Expected OK, got {status}"
    assert r.get("point_count", 0) > 0, "point_count must be > 0"
    assert r.get("surface_breakdown"), "surface_breakdown must not be empty"
    assert r.get("highway_breakdown"), "highway_breakdown must not be empty"
    assert isinstance(r.get("unknown_percent"), (int, float)), "unknown_percent must be a number"
    assert r.get("json_path") and Path(r["json_path"]).exists(), "json_path must exist"
    assert r.get("md_path") and Path(r["md_path"]).exists(), "md_path must exist"
    assert r.get("write_committed") is False, "write_committed must be False"
    print("  ✅ OK")

    # ── Test 5: no PUT to RWGPS ────────────────────────────────
    print("\n[Test 5] no PUT to RWGPS / no route mutation")
    assert not r.get("write_committed", True), "write_committed must be False"
    assert "import" not in str(r.get("error", "")).lower()
    print("  write_committed=False ✅")
    print("  no RWGPS mutation ✅")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"\nResults summary:")
    for rid, label in [(CONTROL_ROUTE_ID, "Toscany Etap II"), (TARGET_ROUTE_ID, "Puznówka")]:
        print(f"  {label} ({rid}):")
        sb = r.get("surface_breakdown", {}) if rid == TARGET_ROUTE_ID else {}
        print(f"    surface: {dict(sorted(sb.items(), key=lambda x: -x[1])[:4])}")
        print(f"    unknown: {r.get('unknown_percent', '?')}%")


if __name__ == "__main__":
    main()
