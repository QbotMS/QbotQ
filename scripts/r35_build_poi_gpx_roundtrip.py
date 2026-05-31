#!/usr/bin/env python3
"""R3.5B — Production GPX round-trip generator for POI.

Reads route track_points from RWGPS + poi_buffer JSON, produces:
  - GPX with <trk> (full geometry) + <wpt> (off-route POI)
  - MD manual import instructions
  - JSON summary

Usage:
  .venv/bin/python scripts/r35_build_poi_gpx_roundtrip.py \\
    --route-id 55395119 \\
    --poi-buffer /opt/qbot/artifacts/poi/poi_buffer_55395119.json \\
    --dry-run
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

POI_DIR = Path("/opt/qbot/artifacts/poi")
ON_ROUTE_MAX_M = 100
GPX_NS = "http://www.topografix.com/GPX/1/1"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _min_dist_to_track(track_points: list[dict], lat: float, lon: float) -> float:
    return min(_haversine_m(tp["y"], tp["x"], lat, lon) for tp in track_points)


# ── Loaders ─────────────────────────────────────────────────────────────────

def load_route_track_points(route_id: str) -> list[dict]:
    """Fetch track_points from RWGPS API (read-only GET)."""
    from tools.rwgps.client import _remote_headers, RWGPS_API_BASE
    import httpx

    headers = _remote_headers()
    url = f"{RWGPS_API_BASE}/api/v1/routes/{route_id}.json?track_points=1"
    r = httpx.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    route = r.json().get("route", {})
    tps = route.get("track_points", [])
    if not tps:
        raise ValueError(f"No track_points for route_id={route_id}")
    return tps


def load_poi_buffer(path: str | Path) -> dict:
    """Load and validate poi_buffer JSON."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"poi_buffer not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("poi_buffer must be a JSON object")
    return data


# ── Classification ──────────────────────────────────────────────────────────

def normalize_poi_symbols(
    poi_buffer: dict,
    on_route_max_m: int = ON_ROUTE_MAX_M,
) -> tuple[list[dict], list[dict]]:
    """Split poi_buffer into on-route (<wpt> Waypoint) and off-route (<wpt> Custom POI).

    Supports both the legacy format (off_route_candidates / on_route_candidates)
    and the R3.5 schema format (pois / warnings).

    Returns (off_route_pois, on_route_warnings).
    """
    off_route: list[dict] = []
    on_route: list[dict] = []

    # Try R3.5 schema format first (pois array)
    raw_pois = poi_buffer.get("pois", [])
    raw_warnings = poi_buffer.get("warnings", [])

    # Also collect from legacy format
    for item in poi_buffer.get("off_route_candidates", []):
        raw_pois.append(item)
    for item in poi_buffer.get("on_route_candidates", []):
        raw_pois.append(item)

    for item in raw_pois:
        dist = item.get("distance_m") or item.get("distance_to_track_m")
        if dist is None:
            continue
        try:
            dist_f = float(dist)
        except (TypeError, ValueError):
            continue
        if dist_f <= on_route_max_m:
            on_route.append(item)
        else:
            off_route.append(item)

    for item in raw_warnings:
        severity = item.get("severity", "medium")
        dist_w = item.get("distance_m") or item.get("distance_to_track_m")
        if severity == "high" or (severity == "medium" and dist_w is not None and float(dist_w) <= on_route_max_m):
            on_route.append(item)

    return off_route, on_route


# ── GPX Builder ─────────────────────────────────────────────────────────────

def build_combined_gpx(
    track_points: list[dict],
    off_route_pois: list[dict],
    on_route_warnings: list[dict],
    route_name: str = "QBot Route",
) -> str:
    """Build a GPX 1.1 string with <trk> + <wpt> elements."""
    lines: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(f'<gpx version="1.1" creator="QBot R3.5B" xmlns="{GPX_NS}">')
    lines.append("  <metadata>")
    lines.append(f"    <name>{escape(route_name)}</name>")
    lines.append(f"    <desc>QBot POI round-trip GPX — {len(off_route_pois)} off-route, {len(on_route_warnings)} on-route warnings</desc>")
    lines.append(f"    <time>{ts}</time>")
    lines.append("  </metadata>")

    # Off-route <wpt> — Custom POI
    lines.append(f"  <!-- {len(off_route_pois)} off-route POI(s) — import as Custom POI in RWGPS Route Planner -->")
    for poi in off_route_pois:
        lat = poi.get("lat")
        lng = poi.get("lng") or poi.get("lon")
        name = str(poi.get("name", "unnamed")).strip()[:60]
        cat = poi.get("category", "")
        dist = poi.get("distance_m") or poi.get("distance_to_track_m")
        km = poi.get("nearest_track_km")
        wpt_type = str(poi.get("rwgps_sym", "Custom POI"))[:40]
        desc_parts = [f"Category: {cat}"]
        if dist is not None:
            desc_parts.append(f"Distance: {float(dist):.0f}m")
        if km is not None:
            desc_parts.append(f"Track km: {float(km):.1f}")
        desc = " | ".join(desc_parts)
        lines.append(f'  <wpt lat="{lat}" lon="{lng}">')
        lines.append(f"    <name>{escape(name)}</name>")
        lines.append(f"    <desc>{escape(desc)}</desc>")
        lines.append(f"    <type>{escape(wpt_type)}</type>")
        lines.append(f"  </wpt>")

    # On-route <wpt> — Waypoint
    lines.append(f"  <!-- {len(on_route_warnings)} on-route POI(s) — import as Waypoint in RWGPS Route Planner -->")
    for poi in on_route_warnings:
        lat = poi.get("lat")
        lng = poi.get("lng") or poi.get("lon")
        name = str(poi.get("name", "unnamed")).strip()[:60]
        cat = poi.get("category", "")
        dist = poi.get("distance_m") or poi.get("distance_to_track_m")
        km = poi.get("nearest_track_km")
        wpt_type = str(poi.get("rwgps_sym", "Waypoint"))[:40]
        desc_parts = [f"Category: {cat}"]
        if dist is not None:
            desc_parts.append(f"Distance: {float(dist):.0f}m")
        if km is not None:
            desc_parts.append(f"Track km: {float(km):.1f}")
        desc = " | ".join(desc_parts)
        lines.append(f'  <wpt lat="{lat}" lon="{lng}">')
        lines.append(f"    <name>{escape(name)}</name>")
        lines.append(f"    <desc>{escape(desc)}</desc>")
        lines.append(f"    <type>Waypoint</type>")
        lines.append(f"  </wpt>")

    # <trk> with full geometry
    lines.append(f"  <trk>")
    lines.append(f"    <name>{escape(route_name)}</name>")
    lines.append("    <trkseg>")
    for tp in track_points:
        lat = tp["y"]
        lon = tp["x"]
        ele = tp.get("e")
        line = f'      <trkpt lat="{lat}" lon="{lon}">'
        if ele is not None:
            line += f"<ele>{ele}</ele>"
        line += "</trkpt>"
        lines.append(line)
    lines.append("    </trkseg>")
    lines.append("  </trk>")
    lines.append("</gpx>")

    return "\n".join(lines)


# ── Validation ──────────────────────────────────────────────────────────────

def validate_gpx_xml(gpx_content: str) -> dict:
    """Validate GPX XML and return stats.

    Returns dict with: valid, trkpt_count, wpt_count, errors.
    """
    try:
        root = ET.fromstring(gpx_content)
    except ET.ParseError as e:
        return {"valid": False, "error": str(e), "trkpt_count": 0, "wpt_count": 0}

    ns = {"gpx": GPX_NS}
    trkpts = root.findall(".//gpx:trkpt", ns)
    wpts = root.findall(".//gpx:wpt", ns)

    return {
        "valid": True,
        "trkpt_count": len(trkpts),
        "wpt_count": len(wpts),
    }


# ── Output Writers ──────────────────────────────────────────────────────────

def write_outputs(
    route_id: str,
    gpx_content: str,
    summary: dict,
    track_points: list[dict],
    off_route: list[dict],
    on_route: list[dict],
    route_name: str,
    dry_run: bool = False,
) -> dict:
    """Write GPX, MD, and summary JSON to POI_DIR.

    In dry-run mode, only print to stdout; skip file writes.
    """
    POI_DIR.mkdir(parents=True, exist_ok=True)

    gpx_path = POI_DIR / f"poi_{route_id}_import.gpx"
    md_path = POI_DIR / f"poi_{route_id}_import.md"
    summary_path = POI_DIR / f"poi_{route_id}_import_summary.json"

    if dry_run:
        print("\n=== DRY-RUN — no files written ===\n")
        print(f"  Would write: {gpx_path}")
        print(f"  Would write: {md_path}")
        print(f"  Would write: {summary_path}")
        print()
        print("GPX preview (first 500 chars):")
        print(gpx_content[:500])
        return summary

    # GPX
    gpx_path.write_text(gpx_content, encoding="utf-8")
    print(f"  GPX: {gpx_path} ({gpx_path.stat().st_size} bytes)")

    # Summary JSON
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Summary: {summary_path}")

    # MD instructions
    lines: list[str] = []
    lines.append(f"# POI Import — {route_name}")
    lines.append("")
    lines.append(f"**Route ID:** {route_id}")
    lines.append(f"**Generator:** QBot R3.5B")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**GPX:** `{gpx_path}`")
    lines.append("")
    lines.append("## GPX Contents")
    lines.append("")
    lines.append(f"| Element | Count |")
    lines.append(f"|---------|-------|")
    lines.append(f"| `<trkpt>` (track) | {len(track_points)} |")
    lines.append(f"| `<wpt>` (off-route → Custom POI) | {len(off_route)} |")
    lines.append(f"| `<wpt>` (on-route → Waypoint) | {len(on_route)} |")
    lines.append("")
    lines.append("## Off-route POI (Custom POI)")
    lines.append("")
    for i, p in enumerate(off_route, 1):
        name = p.get("name", "?")
        cat = p.get("category", "?")
        dist = p.get("distance_to_track_m", "?")
        km = p.get("nearest_track_km", "?")
        lines.append(f"{i}. **{name}** — {cat}, {dist}m from track, km {km}")
    lines.append("")
    lines.append("## On-route Warnings (Waypoint)")
    lines.append("")
    for i, p in enumerate(on_route, 1):
        name = p.get("name", "?")
        cat = p.get("category", "?")
        dist = p.get("distance_to_track_m", "?")
        km = p.get("nearest_track_km", "?")
        lines.append(f"{i}. **{name}** — {cat}, {dist}m from track, km {km}")
    lines.append("")
    lines.append("## Manual Import Instructions")
    lines.append("")
    lines.append("1. **Download GPX to Mac:**")
    lines.append("   ```bash")
    lines.append(f"   scp root@olga181:{gpx_path} /tmp/")
    lines.append("   ```")
    lines.append("2. Open **RideWithGPS.com → Route Planner**")
    lines.append("3. Click **Import → Upload File**")
    lines.append("4. Select the downloaded GPX")
    lines.append("5. Click **Add to Planner**")
    lines.append("6. **Verify:**")
    lines.append("   - Off-route POIs appear as icons (Custom POI)")
    lines.append("   - On-route POIs snap to track (Waypoint)")
    lines.append("   - Track distance unchanged")
    lines.append("7. **Save** the route (creates a new version)")
    lines.append("8. **Pin** the route")
    lines.append("9. **Sync** to Hammerhead → Karoo")
    lines.append("")
    lines.append("## Post-import Verification")
    lines.append("")
    lines.append("| Check | Expected |")
    lines.append("|-------|----------|")
    lines.append(f"| Track points | {len(track_points)} (unchanged) |")
    lines.append(f"| Off-route POIs visible? | ✅ {len(off_route)} Custom POI icons on map |")
    lines.append(f"| On-route POIs visible? | ✅ {len(on_route)} Waypoints on/ near track |")
    lines.append("| Route distance | Unchanged |")
    lines.append("| Cue sheet has on-route waypoints | Likely |")
    lines.append("| Cue sheet does NOT have off-route POIs | Likely (Custom POI) |")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by QBot R3.5B — GPX round-trip POI exporter*")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  MD:   {md_path}")

    return summary


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="R3.5B GPX round-trip POI exporter")
    parser.add_argument("--route-id", required=True, help="RWGPS route ID")
    parser.add_argument("--poi-buffer", required=True, help="Path to poi_buffer JSON")
    parser.add_argument("--route-name-suffix", default="[+POI QBot]", help="Suffix for route name in GPX")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Skip file writes")
    args = parser.parse_args()

    route_id = args.route_id
    poi_buffer_path = args.poi_buffer
    suffix = args.route_name_suffix
    dry_run = args.dry_run

    print(f"{'='*60}")
    print(f"R3.5B GPX Round-Trip POI Exporter")
    print(f"{'='*60}")
    print(f"  route_id={route_id}")
    print(f"  poi_buffer={poi_buffer_path}")
    print(f"  dry_run={dry_run}")
    print()

    # 1. Load track points
    print("[1/5] Loading route track_points from RWGPS...")
    try:
        track_points = load_route_track_points(route_id)
        print(f"  {len(track_points)} track points loaded")
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # 2. Load poi_buffer
    print("[2/5] Loading POI buffer...")
    try:
        poi_buffer = load_poi_buffer(poi_buffer_path)
        print(f"  pois:       {len(poi_buffer.get('pois', []))}")
        print(f"  warnings:   {len(poi_buffer.get('warnings', []))}")
        if "on_route_candidates" in poi_buffer or "off_route_candidates" in poi_buffer:
            print(f"  on_route_candidates:  {len(poi_buffer.get('on_route_candidates', []))}")
            print(f"  off_route_candidates: {len(poi_buffer.get('off_route_candidates', []))}")
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # 3. Normalize POI symbols
    print(f"[3/5] Normalizing POI symbols (on-route ≤{ON_ROUTE_MAX_M}m)...")
    off_route, on_route = normalize_poi_symbols(poi_buffer)
    print(f"  off_route (Custom POI): {len(off_route)}")
    print(f"  on_route (Waypoint):    {len(on_route)}")

    # Get route name
    route_name = f"Route {route_id}"
    for item in [*off_route, *on_route]:
        pass  # no route_name in poi_buffer, just use default

    # 4. Build GPX
    print("[4/5] Building combined GPX...")
    try:
        gpx_content = build_combined_gpx(track_points, off_route, on_route, route_name)
    except Exception as e:
        print(f"  ERROR building GPX: {e}")
        sys.exit(1)

    # Validate
    validation = validate_gpx_xml(gpx_content)
    if not validation.get("valid"):
        print(f"  GPX XML INVALID: {validation.get('error')}")
        sys.exit(1)
    print(f"  GPX valid: ✅")
    print(f"  <trkpt>: {validation['trkpt_count']}")
    print(f"  <wpt>:   {validation['wpt_count']}")
    assert validation["trkpt_count"] == len(track_points), "Track point count mismatch"
    assert validation["wpt_count"] == len(off_route) + len(on_route), "Waypoint count mismatch"

    # 5. Write outputs
    print("[5/5] Writing outputs...")
    summary = {
        "ok": True,
        "route_id": route_id,
        "route_name": route_name,
        "dry_run": dry_run,
        "track_point_count": len(track_points),
        "off_route_poi_count": len(off_route),
        "on_route_poi_count": len(on_route),
        "total_wpt_count": validation["wpt_count"],
        "gpx_valid": True,
        "on_route_max_distance_m": ON_ROUTE_MAX_M,
        "off_route_pois": [
            {"name": p.get("name"), "category": p.get("category"),
             "distance_m": p.get("distance_m") or p.get("distance_to_track_m"),
             "nearest_track_km": p.get("nearest_track_km")}
            for p in off_route
        ],
        "on_route_warnings": [
            {"name": p.get("name"), "category": p.get("category"),
             "distance_m": p.get("distance_m") or p.get("distance_to_track_m"),
             "nearest_track_km": p.get("nearest_track_km")}
            for p in on_route
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    write_outputs(route_id, gpx_content, summary, track_points, off_route, on_route, route_name, dry_run)

    print()
    print(f"{'='*60}")
    print(f"R3.5B {'DRY-RUN ' if dry_run else ''}COMPLETE")
    print(f"{'='*60}")
    print(f"  Track points: {len(track_points)}")
    print(f"  Off-route POIs (Custom POI): {len(off_route)}")
    print(f"  On-route (Waypoint):         {len(on_route)}")
    print(f"  Total <wpt>:                 {validation['wpt_count']}")
    if not dry_run:
        sn = summary.get("route_id", route_id)
        print(f"  GPX:  poi/poi_{sn}_import.gpx")
        print(f"  MD:   poi/poi_{sn}_import.md")
        print(f"  JSON: poi/poi_{sn}_import_summary.json")


if __name__ == "__main__":
    main()
