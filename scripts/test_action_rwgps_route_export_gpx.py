#!/usr/bin/env python3
"""Test rwgps_route_export_gpx action type.

Tests the handler directly (not via MCP tool dispatch), verifies
export_route_to_artifact produces valid GPX artifact files.

Usage:
  cd /opt/qbot/app
  .venv/bin/python scripts/test_action_rwgps_route_export_gpx.py
"""

import json
import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

CONTROL_ROUTE_ID = 55395119
TARGET_ROUTE_ID = 55401067


def main():
    from qbot3.adapters.mcp_adapter import _execute_rwgps_route_export_gpx

    print("=" * 60)
    print("TEST: rwgps_route_export_gpx action handler")
    print("=" * 60)

    # ── Test 1: route_id required ──────────────────────────────
    print("\n[Test 1] route_id required")
    r = _execute_rwgps_route_export_gpx("rwgps_route_export_gpx", {}, "test-1")
    print(f"  status={r.get('status')} error={r.get('error')}")
    assert r["status"] == "ERROR", "Expected ERROR when route_id missing"
    print("  ✅ OK")

    # ── Test 2: empty route_id ─────────────────────────────────
    print("\n[Test 2] empty route_id")
    r = _execute_rwgps_route_export_gpx("rwgps_route_export_gpx", {"route_id": ""}, "test-2")
    print(f"  status={r.get('status')} error={r.get('error')}")
    assert r["status"] == "ERROR", "Expected ERROR when route_id empty"
    print("  ✅ OK")

    # ── Test 3: unsupported format ─────────────────────────────
    print("\n[Test 3] unsupported format")
    r = _execute_rwgps_route_export_gpx("rwgps_route_export_gpx", {"route_id": 55395119, "format": "json"}, "test-3")
    print(f"  status={r.get('status')} error={r.get('error')}")
    assert r["status"] == "ERROR", "Expected ERROR for non-gpx format"
    print("  ✅ OK")

    # ── Test 4: control route 55395119 ─────────────────────────
    print(f"\n[Test 4] export route {CONTROL_ROUTE_ID}")
    gpx_path = Path(f"/opt/qbot/artifacts/exports/rwgps/rwgps_{CONTROL_ROUTE_ID}.gpx")
    before_size = gpx_path.stat().st_size if gpx_path.exists() else 0
    print(f"  GPX exists before: {gpx_path.exists()} ({before_size} bytes)")

    r = _execute_rwgps_route_export_gpx(
        "rwgps_route_export_gpx",
        {"route_id": CONTROL_ROUTE_ID},
        "test-4-control",
    )
    status = r.get("status")
    print(f"  status={status}")
    print(f"  ok={r.get('ok')}")
    print(f"  artifact_path={r.get('artifact_path')}")
    print(f"  filename={r.get('filename')}")
    print(f"  point_count={r.get('point_count')}")
    print(f"  distance_km={r.get('distance_km')}")
    print(f"  elevation_gain_m={r.get('elevation_gain_m')}")
    print(f"  artifact_store_id={r.get('artifact_store_id')}")
    print(f"  artifact_store_status={r.get('artifact_store_status')}")

    assert status == "OK", f"Expected OK, got {status}"
    assert r.get("ok"), "ok must be True"
    assert r.get("artifact_path"), "artifact_path required"
    assert Path(r["artifact_path"]).exists(), f"GPX file not found: {r['artifact_path']}"
    assert "rwgps_55395119.gpx" in r.get("filename", ""), "filename must contain route_id"
    point_count = r.get("point_count")
    assert point_count is not None and point_count > 0, f"point_count must be > 0, got {point_count}"
    assert r.get("distance_km", 0) > 0, "distance_km must be > 0"
    assert r.get("elevation_gain_m", -1) >= 0, "elevation_gain_m must be >= 0"
    assert "content" not in r, "Must NOT return content field"
    assert "content_base64" not in r, "Must NOT return content_base64 field"
    print("  ✅ OK")

    # ── Test 5: target route 55401067 (Puznówka 31.05) ─────────
    print(f"\n[Test 5] export route {TARGET_ROUTE_ID} (Puznówka 31.05)")
    r = _execute_rwgps_route_export_gpx(
        "rwgps_route_export_gpx",
        {"route_id": TARGET_ROUTE_ID},
        "test-5-target",
    )
    status = r.get("status")
    print(f"  status={status}")
    print(f"  ok={r.get('ok')}")
    print(f"  route_name={r.get('route_name')}")
    print(f"  artifact_path={r.get('artifact_path')}")
    print(f"  filename={r.get('filename')}")
    print(f"  point_count={r.get('point_count')}")
    print(f"  distance_km={r.get('distance_km')}")
    print(f"  elevation_gain_m={r.get('elevation_gain_m')}")
    print(f"  artifact_store_id={r.get('artifact_store_id')}")
    print(f"  artifact_store_status={r.get('artifact_store_status')}")
    print(f"  source={r.get('source')}")

    assert status == "OK", f"Expected OK, got {status}"
    assert r.get("ok"), "ok must be True"
    assert r.get("artifact_path"), "artifact_path required"
    gp = Path(r["artifact_path"])
    assert gp.exists(), f"GPX file not found: {gp}"
    assert gp.stat().st_size > 0, "GPX file is empty"
    assert "rwgps_55401067.gpx" in r.get("filename", ""), "filename must contain 55401067"
    pc = r.get("point_count")
    dk = r.get("distance_km")
    eg = r.get("elevation_gain_m")
    print(f"  Expected: ~1499 pts, ~81.7 km, ~414m gain")
    print(f"  Got:      {pc} pts, {dk} km, {eg}m gain")
    assert pc is not None and pc > 0, f"point_count must be > 0, got {pc}"
    assert dk is not None and dk > 0, f"distance_km must be > 0, got {dk}"
    assert eg is not None and eg >= 0, f"elevation_gain_m must be >= 0, got {eg}"
    assert "content" not in r, "Must NOT return content"
    assert "content_base64" not in r, "Must NOT return content_base64"
    print("  ✅ OK")

    # ── Test 6: no PUT to RWGPS ────────────────────────────────
    print("\n[Test 6] no PUT to RWGPS")
    assert not r.get("write_committed", True), "write_committed must be False for exports"
    print("  write_committed=False ✅")

    # ── Test 7: verify GPX file content ────────────────────────
    print(f"\n[Test 7] verify GPX file content for {TARGET_ROUTE_ID}")
    gpx_text = gp.read_text(encoding="utf-8")
    assert '<?xml' in gpx_text[:100], "GPX must start with XML declaration"
    assert '<gpx' in gpx_text[:200], "GPX must have <gpx> root"
    assert '<trkpt' in gpx_text, "GPX must have track points"
    print(f"  GPX size: {gp.stat().st_size} bytes")
    print(f"  Starts with: {gpx_text[:80].strip()}")
    trkpt_count = gpx_text.count("<trkpt ")
    print(f"  XML trkpt count: {trkpt_count}")
    assert trkpt_count > 0, "GPX must have track points"
    print("  ✅ OK")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"\nControl route ({CONTROL_ROUTE_ID}):")
    print(f"  path: /opt/qbot/artifacts/exports/rwgps/rwgps_{CONTROL_ROUTE_ID}.gpx")
    print(f"\nTarget route ({TARGET_ROUTE_ID}):")
    print(f"  path: /opt/qbot/artifacts/exports/rwgps/rwgps_{TARGET_ROUTE_ID}.gpx")
    print(f"  point_count: {pc}")
    print(f"  distance_km: {dk}")
    print(f"  elevation_gain_m: {eg}")


if __name__ == "__main__":
    main()
