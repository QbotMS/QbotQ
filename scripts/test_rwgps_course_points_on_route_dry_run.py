#!/usr/bin/env python3
"""Dry-run test: course_points on-route validator.

Tests distance validation, off-route rejection, and payload preview.
No PUT is executed.

Usage:
  cd /opt/qbot/app
  .venv/bin/python scripts/test_rwgps_course_points_on_route_dry_run.py
"""

import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

ROUTE_ID = 55395119
MAX_DIST_M = 100

TEST_POINTS = [
    # 1: On-route point at start
    {
        "name": "QBot TEST CP ON-ROUTE 1 - remove",
        "category": "water",
        "lat": 43.591107,
        "lng": 10.683066,
        "distance_to_track_m": 0,
    },
    # 2: On-route point ~50m from track
    {
        "name": "QBot TEST CP ON-ROUTE 2 - remove",
        "category": "food",
        "lat": 43.5905,
        "lng": 10.6815,
        "distance_to_track_m": 45,
    },
    # 3: Off-route point ~500m from track
    {
        "name": "QBot TEST CP OFF-ROUTE - remove",
        "category": "attractions",
        "lat": 43.5956,
        "lng": 10.6893,
        "distance_to_track_m": 500,
    },
]


def main():
    from tools.rwgps.client import (
        prepare_rwgps_course_points_update,
        _format_qbot_poi_as_course_point,
    )

    print("=" * 60)
    print("DRY-RUN: course_points on-route validator")
    print("=" * 60)

    # Test 1: format conversion
    print("\n[Test 1] Format conversion")
    for pt in TEST_POINTS:
        cp = _format_qbot_poi_as_course_point(pt)
        print(f"  {pt['name'][:40]:40s} → x={cp['x']:.4f} y={cp['y']:.4f} n='{cp['n']}' t='{cp['t']}'")
        assert isinstance(cp["x"], float)
        assert isinstance(cp["y"], float)
        assert isinstance(cp["n"], str) and len(cp["n"]) > 0
        assert isinstance(cp["t"], str)
    print("  ✅ Format OK")

    # Test 2: dry-run with max_distance_to_track_m=100
    print(f"\n[Test 2] Dry-run with max_distance_to_track_m={MAX_DIST_M}")
    result = prepare_rwgps_course_points_update(
        ROUTE_ID, TEST_POINTS,
        dry_run=True,
        max_distance_to_track_m=MAX_DIST_M,
    )
    print(f"  ok={result.get('ok')}")
    print(f"  existing_course_points_count={result.get('existing_course_points_count')}")
    print(f"  accepted_count={result.get('accepted_count')}")
    print(f"  rejected_count={result.get('rejected_count')}")
    print(f"  duplicates_skipped={result.get('duplicates_skipped')}")
    print(f"  final_course_points_count={result.get('final_course_points_count')}")
    print(f"  no_put_executed={result.get('no_put_executed')}")
    print(f"  max_distance_to_track_m={result.get('max_distance_to_track_m')}")

    assert result.get("ok"), f"prepare failed: {result.get('error')}"
    assert result["accepted_count"] == 2, f"Expected 2 accepted, got {result['accepted_count']}"
    assert result["rejected_count"] == 1, f"Expected 1 rejected, got {result['rejected_count']}"
    assert result["no_put_executed"] is True, "no_put_executed must be True"
    assert result["final_course_points_count"] >= result["accepted_count"]

    # Check rejected reasons
    rejected = result.get("rejected", [])
    assert len(rejected) == 1, f"Expected 1 rejected item"
    reason = rejected[0].get("_reason", "")
    assert "off-route" in reason, f"Expected off-route reason, got: {reason}"
    print("  ✅ Acceptance/rejection OK")

    # Test 3: payload_preview structure
    print("\n[Test 3] Payload preview")
    preview = result.get("payload_preview", {})
    assert "route" in preview
    assert "course_points" in preview["route"]
    cps = preview["route"]["course_points"]
    assert len(cps) == result["final_course_points_count"]
    for cp in cps:
        assert "x" in cp and "y" in cp and "n" in cp and "t" in cp
    print(f"  {len(cps)} course_points, all have x/y/n/t")
    print("  ✅ Payload OK")

    # Test 4: missing distance_to_track_m
    print("\n[Test 4] Missing distance_to_track_m")
    bad_pt = {"name": "Bad POI", "category": "water", "lat": 43.59, "lng": 10.68}
    r2 = prepare_rwgps_course_points_update(ROUTE_ID, [bad_pt], dry_run=True)
    assert r2["rejected_count"] == 1, f"Expected 1 rejected, got {r2['rejected_count']}"
    print(f"  rejected_count={r2['rejected_count']} (missing dist) ✅")

    # Test 5: duplicates
    print(f"\n[Test 5] Duplicate detection")
    dup_pts = [
        {"name": "Dupe", "category": "water", "lat": 43.5911, "lng": 10.6831, "distance_to_track_m": 0},
        {"name": "Dupe", "category": "water", "lat": 43.5911, "lng": 10.6831, "distance_to_track_m": 0},
    ]
    r3 = prepare_rwgps_course_points_update(ROUTE_ID, dup_pts, dry_run=True)
    assert r3["accepted_count"] == 1, f"Expected 1 accepted, got {r3['accepted_count']}"
    assert r3["duplicates_skipped"] == 1, f"Expected 1 dup skipped, got {r3['duplicates_skipped']}"
    print(f"  accepted={r3['accepted_count']} dups_skipped={r3['duplicates_skipped']} ✅")

    print("\n" + "=" * 60)
    print("ALL DRY-RUN TESTS PASSED")
    print("=" * 60)
    print(f"\nAccepted: {result['accepted_count']} (on-route)")
    print(f"Rejected: {result['rejected_count']} (off-route)")
    print(f"No PUT executed: {result['no_put_executed']}")


if __name__ == "__main__":
    main()
