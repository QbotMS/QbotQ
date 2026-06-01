#!/usr/bin/env python3
"""QBot Route Logistics — TEMPO 1: Candidates.

Searches for POI candidates along a route track using OSM Overpass.
Generates candidates.json, candidates.geojson, candidates.md, candidates.xlsx, debug.json.

Usage:
    python3 scripts/route_logistics_candidates.py --route-id 55395119 --mode full
    python3 scripts/route_logistics_candidates.py --route-id 55401067 --mode attractions
    python3 scripts/route_logistics_candidates.py --route-id 55395119 --mode lodging --require '{"people":2,"budget":150}'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.route_logistics import (
    ARTIFACTS_ROOT, LOGISTICS_DIR, CATEGORY_ORDER, DEFAULT_BUFFERS,
    load_gpx_track, resolve_route_gpx,
    _overpass_segmented, osm_elements_to_candidates,
    write_candidates_json, write_candidates_geojson, write_candidates_md,
    write_candidates_xlsx, write_debug_json,
    parse_lodging_requirements,
    POICandidate,
)


def main():
    parser = argparse.ArgumentParser(description="QBot Route Logistics — TEMPO 1: Candidates")
    parser.add_argument("--route-id", required=True, help="RWGPS route ID")
    parser.add_argument("--stage", type=int, default=None, help="Stage number (optional)")
    parser.add_argument("--mode", choices=["full", "poi", "food", "lodging", "attractions", "shops", "water", "bike_service", "pharmacy", "transport"],
                        default="full", help="Search mode")
    parser.add_argument("--require", type=str, default=None, help="JSON requirements for lodging")
    parser.add_argument("--buffer", type=int, default=None, help="Override buffer in meters for all categories")
    parser.add_argument("--output", type=str, default=None, help="Output directory (default: /opt/qbot/artifacts/route_logistics/{route_id})")

    args = parser.parse_args()
    route_id = args.route_id
    mode = args.mode
    stage = args.stage
    require_raw = args.require

    print(f"\U0001f50d QBot Route Logistics — TEMPO 1: Candidates")
    print(f"  Route ID: {route_id}")
    print(f"  Mode: {mode}")
    print(f"  Stage: {stage or 'none'}")
    print()

    # ── Resolve GPX ──
    gpx_path = resolve_route_gpx(route_id)
    if not gpx_path:
        print(f"\u274c GPX not found for route {route_id}")
        sys.exit(1)
    print(f"  GPX: {gpx_path}")

    try:
        track = load_gpx_track(gpx_path)
    except Exception as e:
        print(f"\u274c Failed to load GPX: {e}")
        sys.exit(1)
    print(f"  Track points: {len(track)}")
    print()

    # ── Determine categories ──
    if mode == "full":
        categories = CATEGORY_ORDER
    else:
        categories = [mode]

    # ── Lodging requirements ──
    lodging_requirements = None
    if "lodging" in categories:
        if require_raw:
            try:
                req_data = json.loads(require_raw)
            except json.JSONDecodeError:
                print(f"\u274c Invalid --require JSON: {require_raw}")
                sys.exit(1)
            lodging_requirements = parse_lodging_requirements(req_data)
            if lodging_requirements.get("status") == "NEEDS_REQUIREMENTS":
                missing = lodging_requirements.get("missing", [])
                print(f"\u274c Lodging: NEEDS_REQUIREMENTS — brakuje: {', '.join(missing)}")
                print(f"  Wymagane pola: {', '.join(lodging_requirements['missing'])}")
                result = {
                    "ok": False,
                    "status": "NEEDS_REQUIREMENTS",
                    "route_id": route_id,
                    "missing_fields": lodging_requirements["missing"],
                    "required_fields": ["people", "budget", "radius_from_stage_end_m"],
                    "notes": "Lodging wymaga indywidualnych wymaga\u0144 u\u017cytkownika.",
                }
                out_dir = LOGISTICS_DIR / str(route_id)
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"\n  Wynik: {json.dumps(result, ensure_ascii=False, indent=2)}")
                sys.exit(0)
        else:
            print(f"\u26a0\ufe0f  Lodging: brak --require. Uruchom z --require '{{\"people\":2,\"budget\":150}}'")
            result = {
                "ok": False,
                "status": "NEEDS_REQUIREMENTS",
                "route_id": route_id,
                "missing_fields": ["people", "budget", "radius_from_stage_end_m"],
                "required_fields": ["people", "budget", "radius_from_stage_end_m", "room_type", "beds", "bike_storage"],
                "notes": "Lodging wymaga indywidualnych wymaga\u0144 u\u017cytkownika.",
            }
            out_dir = LOGISTICS_DIR / str(route_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n  Wynik: {json.dumps(result, ensure_ascii=False, indent=2)}")
            sys.exit(0)

    # ── Overpass queries ──
    all_candidates: list[POICandidate] = []
    warnings: list[str] = []
    errors: list[str] = []
    debug_info: dict[str, Any] = {
        "route_id": route_id,
        "gpx": str(gpx_path),
        "track_points": len(track),
        "mode": mode,
        "stage": stage,
        "categories": {},
        "timing": {},
    }

    for cat in categories:
        buffer_m = args.buffer or DEFAULT_BUFFERS.get(cat, 1000)
        if cat == "lodging" and lodging_requirements:
            buffer_m = lodging_requirements.get("radius_from_stage_end_m", 5000)

        print(f"  \U0001f50d Querying {cat} (buffer={buffer_m}m)...")

        t0 = time.time()
        elements = _overpass_segmented(cat, track, buffer_m)
        elapsed = time.time() - t0

        candidates = osm_elements_to_candidates(elements, cat, track)

        # For lodging, mark price/availability as unknown
        if cat == "lodging":
            for c in candidates:
                c.price_eur = None
                c.availability = "UNKNOWN"
                c.notes += "; price unknown, availability unknown — NEEDS_REVIEW"

        all_candidates.extend(candidates)

        debug_info["categories"][cat] = {
            "buffer_m": buffer_m,
            "raw_elements": len(elements),
            "candidates": len(candidates),
            "elapsed_s": round(elapsed, 2),
        }
        print(f"    -> {len(candidates)} candidates ({elapsed:.1f}s)")

    print(f"\n  Total candidates: {len(all_candidates)}")

    # ── Write artifacts ──
    print(f"\n  Writing artifacts...")
    write_candidates_json(all_candidates, route_id, mode, stage, warnings, errors)
    write_candidates_geojson(all_candidates, route_id)
    write_candidates_md(all_candidates, route_id, mode)
    write_candidates_xlsx(all_candidates, route_id)
    write_debug_json(debug_info, route_id)

    out_dir = LOGISTICS_DIR / str(route_id)
    print(f"  Output: {out_dir}")
    print(f"    candidates.json")
    print(f"    candidates.geojson")
    print(f"    candidates.md")
    print(f"    candidates.xlsx")
    print(f"    debug.json")

    # ── Summary counts ──
    counts = {}
    for c in all_candidates:
        counts[c.category] = counts.get(c.category, 0) + 1
    print(f"\n  Podsumowanie:")
    for cat in CATEGORY_ORDER:
        if cat in counts:
            print(f"    {cat}: {counts[cat]}")
    print(f"\n  Status: CANDIDATES_READY")
    print(f"  Next action: manual_review")
    print(f"\n  Aby zatwierdzi\u0107 POI, u\u017Cyj:")
    print(f"    python3 scripts/route_logistics_commit_poi.py --route-id {route_id} --select <candidate_ids>")


if __name__ == "__main__":
    main()
