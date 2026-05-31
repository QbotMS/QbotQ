#!/usr/bin/env python3
"""g12_apply_manual_overrides.py — CLI for G12 Manual Surface Overrides Engine.

Usage:
    python3 scripts/g12_apply_manual_overrides.py \\
        --route-id 55401067 \\
        --overrides /opt/qbot/artifacts/surface_overrides/manual_surface_overrides.json \\
        --input-prefer g11 \\
        --mode dry-run

    python3 scripts/g12_apply_manual_overrides.py \\
        --route-id 55401067 \\
        --mode build
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.manual_surface_overrides import (
    apply_overrides_to_route,
    write_g12_output,
    build_md_report,
)


def main():
    p = argparse.ArgumentParser(description="G12 Manual Surface Overrides Engine")
    p.add_argument("--route-id", required=True, help="Garmin route ID")
    p.add_argument(
        "--overrides",
        default="/opt/qbot/artifacts/surface_overrides/manual_surface_overrides.json",
        help="Path to manual_surface_overrides.json",
    )
    p.add_argument(
        "--input-prefer",
        choices=["g10", "g11"],
        default="g11",
        help="Prefer G10 (base) or G11 (weather-modified) as input (default: g11)",
    )
    p.add_argument(
        "--mode",
        choices=["dry-run", "build"],
        default="dry-run",
        help="dry-run: print report only. build: write output files.",
    )
    args = p.parse_args()

    print("=" * 70)
    print("G12 Manual Surface Overrides Engine")
    print("=" * 70)
    print(f"  Route ID:     {args.route_id}")
    print(f"  Overrides:    {args.overrides}")
    print(f"  Input prefer: {args.input_prefer}")
    print(f"  Mode:         {args.mode}")
    print()

    # Apply overrides
    result = apply_overrides_to_route(
        route_id=args.route_id,
        overrides_path=args.overrides,
        input_prefer=args.input_prefer,
        mode=args.mode,
    )

    if not result.get("ok"):
        print(f"  ERROR: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    # Print summary
    print(f"  Route:          {result.get('route_name', '?')}")
    print(f"  Distance:       {result['total_distance_km']:.2f} km")
    print(f"  Samples:        {result['total_samples']}")
    print(f"  Overrides found: {result['route_overrides_count']}")
    print(f"  Applied:        {result['applied_overrides_count']}")
    print(f"  Unmatched:      {result.get('unmatched_overrides_count', 0)}")
    print(f"  Samples changed: {result['samples_changed']}")
    print(f"  Production:     {result.get('production_enabled', False)}")
    print()

    # Print applied overrides detail
    if result.get("overrides"):
        for ov in result["overrides"]:
            print(f"  ✅ {ov['override_id']}")
            print(f"     KM {ov['start_km']}–{ov['end_km']} → {ov['override_surface']} "
                  f"({ov['rideability']}), matched {ov['matched_samples']} samples, "
                  f"overlap {ov['overlap_km']}km ({ov['overlap_pct']}%)")

    if result.get("unmatched_overrides"):
        print()
        for uo in result["unmatched_overrides"]:
            print(f"  ⚠️  UNMATCHED: {uo['override_id']}: {uo['note']}")

    # Print sample-level changes
    if result.get("samples"):
        samples = result["samples"]
        changed = [s for s in samples if s.get("manual_override_applied")]
        if changed:
            print()
            print(f"  Changed samples ({len(changed)}):")
            print(f"  {'#':>3} {'Km':>7} {'Before':>8} {'After':>8} {'Surface':<12} {'Sev':<10} {'Source':<12}")
            print(f"  {'---':>3} {'---':>7} {'------':>8} {'-----':>8} {'-------':<12} {'---':<10} {'------':<12}")
            for i, s in enumerate(changed):
                km = s.get("_approx_km", 0)
                orig = s.get("original_score_before_override", 0)
                after = s.get("score_after_override", 0)
                surf = s.get("override_surface", "-")
                sev = s.get("override_severity", "-")
                src = s.get("override_source", "-")
                print(f"  {i:>3} {km:>7.2f} {orig:>8.4f} {after:>8.4f} {surf:<12} {sev:<10} {src:<12}")

    # Write output in build mode
    if args.mode == "build":
        write_result = write_g12_output(result, mode="build")
        print()
        print(f"  JSON: {write_result['json_path']}")
        print(f"  MD:   {write_result['md_path']}")
    else:
        # In dry-run, still write to a temp path for review
        md_content = build_md_report(result, print_samples=True)
        print()
        print("─" * 70)
        print(md_content)
        print("─" * 70)
        print()
        print("DRY RUN — no files written. Use --mode build to persist.")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
