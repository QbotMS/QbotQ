#!/usr/bin/env python3
"""Smoke test: PUT course_points with on-route validation + restore.

Adds 1 test course point, verifies it, restores original state.

Usage:
  .venv/bin/python scripts/test_rwgps_course_points_on_route_put_smoke.py \
    --route-id 55395119 --confirm --allow-production-route --restore-after-test
"""

import argparse
import json
import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

PRODUCTION_ROUTES = {"55395119", "55401067"}


def main():
    parser = argparse.ArgumentParser(description="Smoke test RWGPS course_points PUT")
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--confirm", action="store_true", default=False)
    parser.add_argument("--restore-after-test", action="store_true", default=True)
    parser.add_argument("--allow-production-route", action="store_true", default=False)
    parser.add_argument("--max-distance-to-track-m", type=int, default=100)
    args = parser.parse_args()

    route_id = str(args.route_id).strip()
    confirm = args.confirm
    restore = args.restore_after_test
    allow_prod = args.allow_production_route
    max_dist = args.max_distance_to_track_m

    print("=" * 60)
    print("RWGPS COURSE_POINTS PUT — SMOKE TEST")
    print("=" * 60)
    print(f"  route_id={route_id}")
    print(f"  confirm={confirm}")
    print(f"  restore_after_test={restore}")
    print(f"  max_distance_to_track_m={max_dist}")

    if route_id in PRODUCTION_ROUTES and not allow_prod:
        print("\n  ⛔ BLOCKED: Production route detected. Use --allow-production-route.")
        sys.exit(1)

    if not confirm:
        print("\n  ⛔ BLOCKED: --confirm is required.")
        sys.exit(1)

    from tools.rwgps.client import (
        apply_rwgps_course_points_update,
        get_rwgps_raw_route,
    )

    # GET before
    raw = get_rwgps_raw_route(route_id)
    route = raw.get("route", {})
    before_cp = len(route.get("course_points") or [])
    before_tp = len(route.get("track_points") or [])
    before_name = route.get("name", "?")
    print(f"\n  Before: {before_cp} course_points, {before_tp} track_points")
    print(f"  Route: {before_name}")

    # Test point — on-route at start
    tp = route.get("track_points", [])
    if tp:
        test_pt = {
            "name": "QBot TEST CP R3.4 - remove",
            "category": "water",
            "lat": float(tp[0]["y"]),
            "lng": float(tp[0]["x"]),
            "distance_to_track_m": 0,
        }
    else:
        test_pt = {
            "name": "QBot TEST CP R3.4 - remove",
            "category": "water",
            "lat": 43.591107,
            "lng": 10.683066,
            "distance_to_track_m": 0,
        }

    # Execute PUT
    print(f"\n  Executing PUT smoke test (1 on-route CP)...")
    result = apply_rwgps_course_points_update(
        route_id=route_id,
        new_points=[test_pt],
        confirm=True,
        restore_after_test=restore,
        max_distance_to_track_m=max_dist,
    )

    print(f"\n  RESULTS:")
    print(f"    ok={result.get('ok')}")
    print(f"    status={result.get('status', '?')}")
    print(f"    put_executed={result.get('put_executed')}")
    print(f"    accepted_count={result.get('accepted_count')}")
    print(f"    rejected_count={result.get('rejected_count')}")
    print(f"    before_course_points_count={result.get('before_course_points_count')}")
    print(f"    after_put_course_points_count={result.get('after_put_course_points_count')}")
    print(f"    verify_has_test_points={result.get('verify_has_test_points')}")
    print(f"    track_points_count_before={result.get('track_points_count_before')}")
    print(f"    track_points_count_after={result.get('track_points_count_after')}")
    print(f"    track_points_unchanged={result.get('track_points_unchanged')}")
    print(f"    route_id_unchanged={result.get('route_id_unchanged')}")
    print(f"    restore_attempted={result.get('restore_attempted')}")
    print(f"    restored={result.get('restored')}")
    if result.get('after_restore_course_points_count') is not None:
        print(f"    after_restore_course_points_count={result.get('after_restore_course_points_count')}")
        print(f"    restore_matched_original={result.get('restore_matched_original')}")
    if result.get('error'):
        print(f"    error={result['error']}")
    print(f"    backup_path={result.get('backup_path')}")

    # Validation
    errors = []
    if not result.get("ok"):
        errors.append(f"PUT failed: {result.get('error', 'unknown')}")
    if result.get("accepted_count", 0) != 1:
        errors.append(f"Expected 1 accepted, got {result.get('accepted_count')}")
    if not result.get("verify_has_test_points"):
        errors.append("Test CP not found after PUT")
    if not result.get("track_points_unchanged", True):
        errors.append("Track points changed!")
    if not result.get("route_id_unchanged", True):
        errors.append("Route ID changed!")
    if restore and not result.get("restored"):
        errors.append("Restore failed!")

    if errors:
        print("\n  ❌ VALIDATION FAILED:")
        for e in errors:
            print(f"    - {e}")
        sys.exit(1)

    print("\n  ✅ ALL VALIDATIONS PASSED")
    print()
    print("=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)
    print(f"  Route: {result.get('route_name', '?')}")
    print(f"  PUT executed: {result.get('put_executed')}")
    print(f"  Points accepted: {result.get('accepted_count')}")
    print(f"  Test CP visible: {result.get('verify_has_test_points')}")
    print(f"  Track points unchanged: {result.get('track_points_unchanged')}")
    print(f"  Restored: {result.get('restored')}")
    print(f"  Backup: {result.get('backup_path')}")


if __name__ == "__main__":
    main()
