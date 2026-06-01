#!/usr/bin/env python3
"""Test off-route POI writer (points_of_interest) + GPX wpt fallback.

RWGPS API does NOT accept points_of_interest via PUT (confirmed HTTP 500).
This test validates:
  1. On-route POIs (<100m) are rejected from points_of_interest
  2. Off-route POIs (100-1000m) are accepted for points_of_interest
  3. Fallback GPX <wpt> generator works
  4. GPX artifact export works

Usage:
  cd /opt/qbot/app
  .venv/bin/python scripts/test_rwgps_points_of_interest_off_route.py
"""

import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

ROUTE_ID = 55395119

TEST_POIS = [
    # 1: On-route — should be rejected (use course_points instead)
    {
        "name": "Fontana near track",
        "category": "water",
        "lat": 43.591107,
        "lng": 10.683066,
        "distance_to_track_m": 5,
    },
    # 2: Off-route ~200m — should be accepted
    {
        "name": "Bar Centrale off-route",
        "category": "food",
        "lat": 43.5935,
        "lng": 10.6850,
        "distance_to_track_m": 200,
    },
    # 3: Off-route ~500m — should be accepted
    {
        "name": "Bike shop in town",
        "category": "bike_service",
        "lat": 43.5960,
        "lng": 10.6880,
        "distance_to_track_m": 500,
    },
    # 4: Far off-route ~1500m — should be accepted with warning
    {
        "name": "Castello far away",
        "category": "attractions",
        "lat": 43.6000,
        "lng": 10.6950,
        "distance_to_track_m": 1500,
    },
]


def main():
    from tools.rwgps.client import (
        prepare_rwgps_points_of_interest_update,
        generate_poi_gpx_wpt,
        export_poi_to_gpx_artifact,
    )

    print("=" * 60)
    print("TEST: Off-route POI writer + GPX wpt fallback")
    print("=" * 60)

    # Test 1: prepare_rwgps_points_of_interest_update
    print("\n[Test 1] prepare_rwgps_points_of_interest_update (dry-run)")
    print(f"  Test POIs: {len(TEST_POIS)}")

    result = prepare_rwgps_points_of_interest_update(
        ROUTE_ID, TEST_POIS, dry_run=True,
        min_distance_m=100, max_distance_m=1000,
    )
    print(f"  ok={result.get('ok')}")
    print(f"  existing_pois_count={result.get('existing_pois_count')}")
    print(f"  accepted_count={result.get('accepted_count')}")
    print(f"  rejected_count={result.get('rejected_count')}")
    print(f"  duplicates_skipped={result.get('duplicates_skipped')}")
    print(f"  final_pois_count={result.get('final_pois_count')}")
    print(f"  no_put_executed={result.get('no_put_executed')}")

    # Validate
    assert result.get("ok"), f"prepare failed: {result.get('error')}"
    # On-route (5m) rejected, 200m + 500m + 1500m (with warning) accepted
    assert result["accepted_count"] == 3, f"Expected 3 accepted (200+500+1500m), got {result['accepted_count']}"
    assert result["rejected_count"] == 1, f"Expected 1 rejected (5m on-route), got {result['rejected_count']}"
    assert result["no_put_executed"] is True

    # Check rejected reasons
    rejected = result.get("rejected", [])
    reasons = [r.get("_reason", "") for r in rejected]
    print(f"  Rejected reasons: {reasons}")
    assert any("too close" in r for r in reasons), "Missing 'too close' rejection"
    print("  ✅ Off-route acceptance / on-route rejection OK")

    # Test 2: RWGPS API note
    print(f"\n[Test 2] RWGPS API note")
    note = result.get("_rwgps_api_note", "")
    assert "HTTP 500" in note, "Missing HTTP 500 note"
    print(f"  {note[:100]}...")
    print("  ✅ Note present")

    # Test 3: GPX wpt generation
    print(f"\n[Test 3] generate_poi_gpx_wpt()")
    accepted_pois = [p for i, p in enumerate(TEST_POIS) if i in (1, 2, 3)]  # 200m + 500m + 1500m
    wpt_xml = generate_poi_gpx_wpt(accepted_pois)
    print(f"  Generated GPX wpt ({len(wpt_xml)} chars):")
    for line in wpt_xml.split("\n"):
        print(f"    {line}")
    assert "<wpt " in wpt_xml, "Missing <wpt> element"
    assert "<name>" in wpt_xml, "Missing <name>"
    assert "<desc>" in wpt_xml, "Missing <desc>"
    assert "Bar Centrale" in wpt_xml, "Missing test POI name"
    print("  ✅ GPX wpt generation OK")

    # Test 4: Export to GPX artifact
    print(f"\n[Test 4] export_poi_to_gpx_artifact()")
    export = export_poi_to_gpx_artifact(ROUTE_ID, accepted_pois)
    print(f"  ok={export.get('ok')}")
    print(f"  artifact_path={export.get('artifact_path')}")
    print(f"  poi_count={export.get('poi_count')}")
    assert export.get("ok")
    assert export.get("artifact_path") and Path(export["artifact_path"]).exists()
    print(f"  File size: {Path(export['artifact_path']).stat().st_size} bytes")
    print("  ✅ GPX artifact export OK")

    # Test 5: PUT smoke test — confirm HTTP 500
    print(f"\n[Test 5] Confirm PUT points_of_interest still fails")
    from tools.rwgps.client import _remote_headers, RWGPS_API_BASE
    import httpx

    headers = _remote_headers()
    url = f'{RWGPS_API_BASE}/routes/{ROUTE_ID}.json'
    test_poi_off = [{
        "type": "generic", "type_id": 0,
        "name": "QBot TEST POI off-route - remove",
        "description": "R3.4B smoke test",
        "url": "", "lat": 43.5935, "lng": 10.685,
    }]

    # Try 1: full context (like R3.2B confirmed)
    from tools.rwgps.client import get_rwgps_raw_route
    raw = get_rwgps_raw_route(ROUTE_ID)
    route = raw.get("route", {})
    tps = route.get("track_points", [])
    cps = route.get("course_points", [])

    r = httpx.put(url, headers=headers, json={
        "route": {
            "track_points": tps,
            "course_points": cps,
            "points_of_interest": test_poi_off,
        }
    }, timeout=30)
    print(f"  PUT with full context: HTTP {r.status_code}")
    assert r.status_code == 500, f"Expected 500, got {r.status_code}. points_of_interest write may have started working!"
    print("  ✅ PUT still returns HTTP 500 (confirmed read-only)")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"\nAccepted for points_of_interest: {result['accepted_count']} (off-route)")
    print(f"Rejected from points_of_interest: {result['rejected_count']} (on-route/far)")
    print(f"GPX fallback: {export.get('artifact_path')}")
    print(f"RWGPS points_of_interest write: NOT AVAILABLE (HTTP 500)")


if __name__ == "__main__":
    main()
