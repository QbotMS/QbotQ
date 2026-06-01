#!/usr/bin/env python3
"""Test the RWGPS custom POI writer dry-run.

Verifies that the prepare_rwgps_poi_update function works correctly
without executing a real PUT.

Usage:
  cd /opt/qbot/app
  .venv/bin/python scripts/test_rwgps_poi_writer_dry_run.py
"""

import json
import sys
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

ROUTE_ID = 55395119

TEST_POIS = [
    {
        "name": "Sklep spożywczy testowy",
        "category": "groceries",
        "lat": 43.550,
        "lng": 10.600,
        "description": "Testowy sklep spożywczy",
        "distance_to_track_m": 150,
        "nearest_track_km": 12.0,
    },
    {
        "name": "Bar testowy pod trasą",
        "category": "food",
        "lat": 43.400,
        "lng": 10.480,
        "description": "Testowy bar z jedzeniem",
        "distance_to_track_m": 300,
        "nearest_track_km": 40.0,
    },
    {
        "name": "Punkt wody testowy",
        "category": "water",
        "lat": 43.300,
        "lng": 10.490,
        "description": "Testowy punkt z wodą pitną",
        "distance_to_track_m": 80,
        "nearest_track_km": 58.0,
    },
]


def main():
    from tools.rwgps.client import (
        prepare_rwgps_poi_update,
        get_rwgps_raw_route,
        _rwgps_poi_category,
    )

    print("=" * 60)
    print("TEST: RWGPS Custom POI Writer Dry-Run")
    print("=" * 60)

    # ── Test 0: category mapping ──────────────────────────────
    print("\n[Test 0] Category mapping")
    for label in ("groceries", "food", "water", "bike_service", "camping", "restroom", "unknown"):
        m = _rwgps_poi_category(label)
        print(f"  {label:15s} → type={m['type']:20s} type_id={m['type_id']}")
        assert isinstance(m["type"], str), f"type must be str for {label}"
        assert isinstance(m["type_id"], int), f"type_id must be int for {label}"
    print("  ✅ Category mapping OK")

    # ── Test 1: GET raw route ──────────────────────────────────
    print("\n[Test 1] GET raw route (read-only)")
    raw = get_rwgps_raw_route(ROUTE_ID)
    assert raw.get("ok"), f"Failed to fetch route: {raw.get('error')}"
    route = raw["route"]
    route_name = route.get("name", "(unnamed)")
    existing_pois = route.get("points_of_interest") or []
    print(f"  route_id={ROUTE_ID}")
    print(f"  route_name={route_name}")
    print(f"  existing POIs={len(existing_pois)}")
    print(f"  route keys sample: {sorted(route.keys())[:10]}")
    assert isinstance(existing_pois, list), "existing POIs must be a list"
    print("  ✅ GET route OK")

    # ── Test 2: dry-run with 3 new POIs ────────────────────────
    print("\n[Test 2] prepare_rwgps_poi_update dry-run")
    result = prepare_rwgps_poi_update(ROUTE_ID, TEST_POIS, dry_run=True)
    assert result.get("ok"), f"prepare failed: {result.get('error')}"
    print(f"  existing_pois_count={result['existing_pois_count']}")
    print(f"  new_pois_count={result['new_pois_count']}")
    print(f"  duplicates_skipped={result['duplicates_skipped']}")
    print(f"  final_pois_count={result['final_pois_count']}")
    print(f"  no_put_executed={result['no_put_executed']}")
    print(f"  warnings={result['warnings']}")
    print(f"  duplicate_keys={result['duplicate_keys']}")

    assert result["new_pois_count"] == 3, f"expected 3 new POIs, got {result['new_pois_count']}"
    assert result["no_put_executed"] is True, "no_put_executed must be True"
    assert result["existing_pois_count"] >= 0, "existing_pois_count must be a number"
    assert result["final_pois_count"] >= result["existing_pois_count"], \
        f"final ({result['final_pois_count']}) must be >= existing ({result['existing_pois_count']})"
    assert "payload_preview" in result, "payload_preview missing"
    print("  ✅ Dry-run basic assertions OK")

    # ── Test 3: payload_preview structure ──────────────────────
    print("\n[Test 3] payload_preview structure")
    preview = result["payload_preview"]
    assert "route" in preview, "preview missing route key"
    assert "points_of_interest" in preview["route"], "preview missing points_of_interest"
    poi_list = preview["route"]["points_of_interest"]
    assert len(poi_list) == result["final_pois_count"], \
        f"preview POI count ({len(poi_list)}) != final_pois_count ({result['final_pois_count']})"

    for poi in poi_list:
        assert "type" in poi, f"POI missing type: {poi}"
        assert "type_id" in poi, f"POI missing type_id: {poi}"
        assert "name" in poi, f"POI missing name: {poi}"
        assert "lat" in poi, f"POI missing lat: {poi}"
        assert "lng" in poi, f"POI missing lng: {poi}"
        assert isinstance(poi["lat"], (int, float)), f"lat must be number"
        assert isinstance(poi["lng"], (int, float)), f"lng must be number"
        # description should include src:QBot/OSM
        assert "src:QBot/OSM" in poi.get("description", ""), \
            f"POI description missing source marker: {poi.get('description')}"

    print(f"  payload_preview has {len(poi_list)} POIs, all valid")
    print("  ✅ payload_preview structure OK")

    # ── Test 4: dedupe test ────────────────────────────────────
    print("\n[Test 4] Deduplication test")
    # Add a duplicate of the first test POI
    dup_test_pois = TEST_POIS + [dict(TEST_POIS[0])]
    result2 = prepare_rwgps_poi_update(ROUTE_ID, dup_test_pois, dry_run=True)
    print(f"  With duplicate: new_pois_count={result2['new_pois_count']}, "
          f"duplicates_skipped={result2['duplicates_skipped']}")
    # new_pois_count should be 3 (the original 3, with 1 duplicate skipped)
    # But existing POIs from previous run are not persisted, so all 3+1 = 4 items,
    # with 1 duplicate
    assert result2["new_pois_count"] == 3, \
        f"Expected 3 after dedupe, got {result2['new_pois_count']}"
    assert result2["duplicates_skipped"] == 1, \
        f"Expected 1 duplicate skipped, got {result2['duplicates_skipped']}"
    print("  ✅ Deduplication OK")

    # ── Test 5: ensure no secrets in output ────────────────────
    print("\n[Test 5] No secrets in output")
    serialized = json.dumps(result)
    # Check no tokens leaked
    for secret_hint in ("api_key", "auth_token", "x-rwgps", "password", "secret"):
        assert secret_hint not in serialized.lower(), f"Possible secret leak: {secret_hint}"
    print("  ✅ No secrets leaked in response")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"\nFinal result summary:")
    print(f"  Route: {result['route_name']} ({ROUTE_ID})")
    print(f"  Existing POIs: {result['existing_pois_count']}")
    print(f"  New POIs: 3 (test)")
    print(f"  Final POIs: {result['final_pois_count']}")
    print(f"  Duplicates skipped: {result['duplicates_skipped']}")
    print(f"  no_put_executed: {result['no_put_executed']}")
    print(f"\nExample payload_preview (first POI):")
    if result["payload_preview"]["route"]["points_of_interest"]:
        print(f"  {json.dumps(result['payload_preview']['route']['points_of_interest'][0], indent=4)}")


if __name__ == "__main__":
    main()
