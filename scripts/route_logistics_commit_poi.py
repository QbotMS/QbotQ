#!/usr/bin/env python3
"""QBot Route Logistics — TEMPO 2: Commit POI.

Selects candidates from candidates.json and writes final POI artifacts.
Generates route_with_selected_poi.gpx — original GPX track + selected POI <wpt>.
This enriched GPX is the file to import to RWGPS.
selected_poi.gpx is a debug artifact only (waypoints without track).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.route_logistics import (
    LOGISTICS_DIR, CATEGORY_ORDER,
    write_selected_poi_json, write_selected_poi_geojson,
    write_selected_poi_gpx, write_route_with_selected_poi_gpx,
    write_commit_summary_md,
    POICandidate,
)


def load_candidates(route_id: str) -> tuple[list[POICandidate], dict]:
    """Load candidates.json and return (candidates_list, full_payload)."""
    path = LOGISTICS_DIR / str(route_id) / "candidates.json"
    if not path.exists():
        print(f"\u274c candidates.json not found: {path}")
        print(f"  Run candidates first: python3 scripts/route_logistics_candidates.py --route-id {route_id}")
        sys.exit(1)

    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates_raw = payload.get("candidates", [])
    candidates = []

    for r in candidates_raw:
        c = POICandidate(
            candidate_id=r.get("candidate_id", ""),
            category=r.get("category", ""),
            subtype=r.get("subtype", ""),
            name=r.get("name", ""),
            lat=r.get("lat", 0.0),
            lon=r.get("lon", 0.0),
            distance_from_track_m=r.get("distance_from_track_m"),
            km_on_route=r.get("km_on_route"),
            detour_m=r.get("detour_m"),
            source=r.get("source", "OSM"),
            source_url=r.get("source_url"),
            confidence=r.get("confidence", "SOURCE_ONLY"),
            status=r.get("status", "CANDIDATE"),
            notes=r.get("notes", ""),
            opening_hours=r.get("opening_hours"),
            phone=r.get("phone"),
            website=r.get("website"),
            estimated_stop_time_min=r.get("estimated_stop_time_min"),
            price_eur=r.get("price_eur"),
            availability=r.get("availability"),
            rating=r.get("rating"),
        )
        candidates.append(c)

    return candidates, payload


def validate_selection(selected_ids: list[str], candidates: list[POICandidate]) -> tuple[list[POICandidate], list[str]]:
    """Validate selected IDs exist in candidates. Returns (valid, invalid)."""
    valid: list[POICandidate] = []
    invalid: list[str] = []
    candidate_map = {c.candidate_id: c for c in candidates}

    for sid in selected_ids:
        if sid in candidate_map:
            valid.append(candidate_map[sid])
        else:
            invalid.append(sid)

    return valid, invalid


def main():
    parser = argparse.ArgumentParser(description="QBot Route Logistics — TEMPO 2: Commit POI")
    parser.add_argument("--route-id", required=True, help="RWGPS route ID")
    parser.add_argument("--select", nargs="+", required=True, help="Candidate IDs to select (space or comma separated)")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")

    args = parser.parse_args()
    route_id = args.route_id
    dry_run = args.dry_run

    # Flatten select: support both "a,b" and "a b"
    selected_ids: list[str] = []
    for s in args.select:
        selected_ids.extend([x.strip() for x in s.replace(",", " ").split() if x.strip()])

    print(f"\U0001f4cb QBot Route Logistics — TEMPO 2: Commit POI")
    print(f"  Route ID: {route_id}")
    print(f"  Selected: {selected_ids}")
    print(f"  Dry run: {dry_run}")
    print()

    # ── Load candidates ──
    candidates, payload = load_candidates(route_id)
    print(f"  Loaded {len(candidates)} candidates from candidates.json")
    print()

    # ── Validate selection ──
    valid_pois, invalid_ids = validate_selection(selected_ids, candidates)

    if invalid_ids:
        print(f"\u274c Invalid candidate IDs (not in candidates.json): {invalid_ids}")
        print(f"  Use candidate_ids from candidates.json:")
        for c in candidates:
            print(f"    {c.candidate_id}: {c.name} ({c.category})")
        sys.exit(1)

    if not valid_pois:
        print(f"\u274c No valid POIs selected.")
        sys.exit(1)

    print(f"  Valid POIs: {len(valid_pois)}")

    # Find rejected IDs
    all_ids = {c.candidate_id for c in candidates}
    selected_set = {c.candidate_id for c in valid_pois}
    rejected_ids = list(all_ids - selected_set)

    print(f"  Rejected: {len(rejected_ids)}")

    # ── Summarize selection ──
    counts = {}
    for c in valid_pois:
        counts[c.category] = counts.get(c.category, 0) + 1
    print(f"\n  Zatwierdzone POI:")
    for cat, cnt in counts.items():
        print(f"    {cat}: {cnt}")
    for c in valid_pois:
        print(f"    \u2022 {c.candidate_id}: {c.name} ({c.lat:.5f}, {c.lon:.5f})")

    if dry_run:
        print(f"\n  Dry run: PASSED. Set --dry-run=False to commit.")
        sys.exit(0)

    # ── Write artifacts ──
    print(f"\n  Writing artifacts...")
    write_selected_poi_json(valid_pois, route_id)
    write_selected_poi_geojson(valid_pois, route_id)
    write_selected_poi_gpx(valid_pois, route_id)          # debug/review: waypoints only
    write_route_with_selected_poi_gpx(valid_pois, route_id)  # import-ready: track + wpt
    write_commit_summary_md(valid_pois, rejected_ids, route_id)

    out_dir = LOGISTICS_DIR / str(route_id)
    print(f"  Output: {out_dir}")
    print(f"    selected_poi.json         — POI metadane")
    print(f"    selected_poi.geojson      — POI GeoJSON (review)")
    print(f"    selected_poi.gpx          — POI waypoints only (debug)")
    print(f"    route_with_selected_poi.gpx — track + POI waypoints (IMPORT TO RWGPS)")
    print(f"    poi_commit_summary.md     — podsumowanie")

    print(f"\n  Status: GPX_READY_FOR_RIDEWITHGPS_IMPORT")
    print(f"  Plik do importu: route_with_selected_poi.gpx")
    print(f"  Zawiera oryginalny przebieg trasy + {len(valid_pois)} zatwierdzone POI.")
    print(f"  \u017baden niezatwierdzony kandydat nie trafi\u0142 do GPX.")
    print(f"  Next action: rwgps_import")


if __name__ == "__main__":
    main()
