#!/usr/bin/env python3
"""Smoke test: real PUT of custom POI to RWGPS route.

Performs backup → PUT test POI → verify → restore original POIs.

Usage:
  # Dry-run — shows blocked message
  .venv/bin/python scripts/test_rwgps_poi_writer_put_smoke.py --route-id 55395119

  # Real smoke test (after user confirmation)
  .venv/bin/python scripts/test_rwgps_poi_writer_put_smoke.py \\
    --route-id <ROUTE_ID> --confirm --restore-after-test true

Safety:
  - Blocks production routes (55395119, 55401067) unless --allow-production-route
  - Requires --confirm for PUT
  - Backs up existing POIs before modifying
  - Restores original POIs after test by default
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

PRODUCTION_ROUTES = {"55395119", "55401067"}

TEST_POI = {
    "name": "QBot TEST POI — do usunięcia",
    "category": "generic",
    "lat": 0.0,
    "lng": 0.0,
    "description": "R3.2 smoke test; można usunąć",
}


def get_start_point(route_id: str) -> tuple[float, float]:
    """Get a safe point (first track point) from the route."""
    from tools.rwgps.client import get_rwgps_raw_route
    raw = get_rwgps_raw_route(route_id)
    if not raw.get("ok"):
        return (0.0, 0.0)
    route = raw["route"]
    tp = route.get("track_points") or []
    if tp:
        first = tp[0]
        return (float(first.get("lat", 0)), float(first.get("lng", 0)))
    course = route.get("course_points") or []
    if course:
        first = course[0]
        return (float(first.get("lat", 0)), float(first.get("lng", 0)))
    return (0.0, 0.0)


def main():
    parser = argparse.ArgumentParser(description="Smoke test RWGPS custom POI PUT")
    parser.add_argument("--route-id", required=True, help="RWGPS route ID to test")
    parser.add_argument("--confirm", action="store_true", default=False,
                        help="Acknowledge real PUT execution")
    parser.add_argument("--restore-after-test", action="store_true", default=True,
                        help="Restore original POIs after test (default: true)")
    parser.add_argument("--allow-production-route", action="store_true", default=False,
                        help="Allow using production routes (55395119, 55401067)")
    args = parser.parse_args()

    route_id = str(args.route_id).strip()
    confirm = args.confirm
    restore = args.restore_after_test
    allow_prod = args.allow_production_route

    print("=" * 60)
    print("RWGPS CUSTOM POI PUT — SMOKE TEST")
    print("=" * 60)
    print(f"  route_id={route_id}")
    print(f"  confirm={confirm}")
    print(f"  restore_after_test={restore}")
    print(f"  allow_production_route={allow_prod}")

    # ── Safety: block production routes ─────────────────────────
    if route_id in PRODUCTION_ROUTES and not allow_prod:
        print()
        print("  ⛔ BLOCKED: Production route detected!")
        print(f"  route_id={route_id} is in PRODUCTION_ROUTES: {PRODUCTION_ROUTES}")
        print("  Use --allow-production-route only if you explicitly want to test on this route.")
        print()
        print("  SAFETY SUMMARY:")
        print("  - This script will execute a REAL PUT to RWGPS")
        print("  - It adds a test POI and then restores original POIs")
        print("  - But if restore fails, the test POI will remain on the route")
        print()
        sys.exit(1)

    if not confirm:
        print()
        print("  ⛔ BLOCKED: --confirm is required for real PUT.")
        print("  Use --confirm to acknowledge PUT execution.")
        print()
        sys.exit(1)

    from tools.rwgps.client import apply_rwgps_poi_update

    # Get a safe point from route
    lat, lng = get_start_point(route_id)
    if lat == 0.0 and lng == 0.0:
        print(f"  ⚠ Could not get track point — using fallback coordinates")
        lat, lng = 43.5, 10.5
    test_poi = dict(TEST_POI)
    test_poi["lat"] = lat
    test_poi["lng"] = lng
    print(f"  Test POI position: ({lat}, {lng})")

    # ── Execute PUT smoke test ──────────────────────────────────
    print()
    print(f"  Executing PUT smoke test...")
    result = apply_rwgps_poi_update(
        route_id=route_id,
        new_pois=[test_poi],
        confirm=True,
        restore_after_test=restore,
    )

    print()
    print("  RESULTS:")
    print(f"    ok={result.get('ok')}")
    print(f"    status={result.get('status', '?')}")
    print(f"    put_executed={result.get('put_executed')}")
    print(f"    backup_path={result.get('backup_path')}")
    print(f"    existing_pois_count={result.get('existing_pois_count')}")
    print(f"    new_pois_count={result.get('new_pois_count')}")
    print(f"    final_pois_count={result.get('final_pois_count')}")
    print(f"    verify_get_ok={result.get('verify_get_ok')}")
    print(f"    verify_pois_count={result.get('verify_pois_count')}")
    print(f"    verify_has_test_poi={result.get('verify_has_test_poi')}")
    print(f"    track_points_count_before={result.get('track_points_count_before')}")
    print(f"    track_points_count_after={result.get('track_points_count_after')}")
    print(f"    track_points_unchanged={result.get('track_points_unchanged')}")
    print(f"    route_id_unchanged={result.get('route_id_unchanged')}")
    print(f"    restore_attempted={result.get('restore_attempted')}")
    print(f"    restored={result.get('restored')}")
    if result.get('after_restore_pois_count') is not None:
        print(f"    after_restore_pois_count={result.get('after_restore_pois_count')}")
        print(f"    restore_matched_original={result.get('restore_matched_original')}")
    if result.get('error'):
        print(f"    error={result['error']}")

    # ── Validation ─────────────────────────────────────────────
    print()
    errors = []
    if not result.get("ok"):
        errors.append(f"PUT failed: {result.get('error', 'unknown')}")
    if not result.get("put_executed"):
        errors.append("PUT was not executed")
    if not result.get("verify_get_ok"):
        errors.append("Verify GET failed after PUT")
    if not result.get("verify_has_test_poi"):
        errors.append("Test POI not found after PUT")
    if not result.get("track_points_unchanged", True):
        errors.append("Track points were modified!")
    if not result.get("route_id_unchanged", True):
        errors.append("Route ID changed!")
    if restore and not result.get("restored"):
        errors.append(f"Restore failed: {result.get('restore_error', 'unknown')}")
    if restore and result.get("restored") and not result.get("restore_matched_original", True):
        errors.append(f"Restore count mismatch: expected {result.get('existing_pois_count')}, got {result.get('after_restore_pois_count')}")

    if errors:
        print("  ❌ VALIDATION FAILED:")
        for e in errors:
            print(f"    - {e}")
        sys.exit(1)

    print("  ✅ ALL VALIDATIONS PASSED")
    print()

    # ── Summary ────────────────────────────────────────────────
    print("=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)
    print(f"  Route: {result.get('route_name', route_id)} ({route_id})")
    print(f"  PUT executed: {result.get('put_executed')}")
    print(f"  Test POI added: {result.get('new_pois_count')}")
    print(f"  Verify GET: {'OK' if result.get('verify_get_ok') else 'FAILED'}")
    print(f"  Test POI visible: {result.get('verify_has_test_poi')}")
    print(f"  Track points unchanged: {result.get('track_points_unchanged')}")
    print(f"  Restored: {result.get('restored')}")
    print(f"  Backup: {result.get('backup_path')}")


if __name__ == "__main__":
    main()
