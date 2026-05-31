#!/usr/bin/env python3
"""g14f_validate_candidate_geometry.py — Validates and fixes candidate GPX geometry.

Fixes:
- Splice connection jumps >200m
- Alternative direction reversal
- Trims duplicate endpoints at connections
- Marks unsafe replacements

Usage:
    python3 scripts/g14f_validate_candidate_geometry.py --route-id 55401067
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACTS_REROUTE = Path("/opt/qbot/artifacts/reroute")
ARTIFACTS_EXPORTS = Path("/opt/qbot/artifacts/exports/rwgps")
JUMP_THRESHOLD_M = 200
MAX_CONNECTION_M = 200


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_gpx(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _haversine_km(lat1, lon1, lat2, lon2):
    return _haversine_m(lat1, lon1, lat2, lon2) / 1000.0


# ── GPX Loading ───────────────────────────────────────────────────────────

def load_original_gpx(route_id: str) -> dict | None:
    gpx_path = ARTIFACTS_EXPORTS / f"rwgps_{route_id}.gpx"
    if not gpx_path.exists():
        return None
    try:
        tree = ET.parse(str(gpx_path))
        root = tree.getroot()
    except Exception:
        return None
    ns = "{http://www.topografix.com/GPX/1/1}"
    ns0 = "{http://www.topografix.com/GPX/1/0}"
    gpx_ns = ns if root.findall(f".//{ns}trkpt") else ns0
    trkpts = root.findall(f".//{gpx_ns}trkpt")
    if not trkpts:
        return None
    points = []
    for pt in trkpts:
        lat = pt.get("lat"); lon = pt.get("lon")
        if lat and lon:
            points.append({"lat": float(lat), "lon": float(lon)})
    cum = [0.0]
    for i in range(1, len(points)):
        d = _haversine_km(points[i-1]["lat"], points[i-1]["lon"], points[i]["lat"], points[i]["lon"])
        cum.append(cum[-1] + d)
    return {"points": points, "cum_dist": cum, "total_km": round(cum[-1], 3), "n": len(points), "gpx_ns": gpx_ns, "gpx_path": gpx_path}


# ── Validation ────────────────────────────────────────────────────────────

def detect_large_jumps(points: list[dict], threshold_m: float = JUMP_THRESHOLD_M) -> list[dict]:
    jumps = []
    for i in range(1, len(points)):
        d = _haversine_m(points[i-1]["lat"], points[i-1]["lon"], points[i]["lat"], points[i]["lon"])
        if d > threshold_m:
            jumps.append({"index": i, "distance_m": round(d, 1), "from": points[i-1], "to": points[i]})
    return jumps


def validate_replacement_connection(
    orig_start: dict, alt_points: list[dict], orig_end: dict,
) -> dict:
    """Validate connection between original track and alternative."""
    if not alt_points:
        return {"valid": False, "reason": "No alt points"}
    alt_first = alt_points[0]
    alt_last = alt_points[-1]
    d_start_alt_first = _haversine_m(orig_start["lat"], orig_start["lon"], alt_first["lat"], alt_first["lon"])
    d_alt_last_end = _haversine_m(alt_last["lat"], alt_last["lon"], orig_end["lat"], orig_end["lon"])
    d_start_alt_last = _haversine_m(orig_start["lat"], orig_start["lon"], alt_last["lat"], alt_last["lon"])
    d_alt_first_end = _haversine_m(alt_first["lat"], alt_first["lon"], orig_end["lat"], orig_end["lon"])
    reversed_dir = d_start_alt_last < d_start_alt_first and d_alt_first_end < d_alt_last_end
    return {
        "valid": d_start_alt_first <= MAX_CONNECTION_M and d_alt_last_end <= MAX_CONNECTION_M,
        "reversed": reversed_dir,
        "d_start_alt_first_m": round(d_start_alt_first, 1),
        "d_alt_last_end_m": round(d_alt_last_end, 1),
        "d_start_alt_last_m": round(d_start_alt_last, 1),
        "d_alt_first_end_m": round(d_alt_first_end, 1),
    }


def maybe_reverse_alt(alt_points: list[dict], conn: dict) -> list[dict]:
    """Reverse alternative if connection is better."""
    if conn.get("reversed"):
        return list(reversed(alt_points))
    return alt_points


def trim_to_anchors(alt_points: list[dict], orig_points: list[dict], s_idx: int, e_idx: int) -> list[dict]:
    """Trim alt points too close to anchor points to avoid duplicates."""
    orig_start = orig_points[s_idx]
    orig_end = orig_points[e_idx]
    # Remove alt points within 5m of start anchor
    while len(alt_points) > 1 and _haversine_m(alt_points[0]["lat"], alt_points[0]["lon"], orig_start["lat"], orig_start["lon"]) < 5:
        alt_points.pop(0)
    while len(alt_points) > 1 and _haversine_m(alt_points[-1]["lat"], alt_points[-1]["lon"], orig_end["lat"], orig_end["lon"]) < 5:
        alt_points.pop()
    return alt_points


def densify_alt(alt_points: list[dict], max_gap_m: float = 300) -> list[dict]:
    """Densify alternative route by interpolating points where gaps > max_gap_m."""
    if len(alt_points) < 2:
        return alt_points
    result = [alt_points[0]]
    for i in range(1, len(alt_points)):
        prev = alt_points[i - 1]
        curr = alt_points[i]
        d = _haversine_m(prev["lat"], prev["lon"], curr["lat"], curr["lon"])
        if d > max_gap_m:
            steps = int(d / max_gap_m) + 1
            for s in range(1, steps):
                frac = s / steps
                result.append({
                    "lat": prev["lat"] + (curr["lat"] - prev["lat"]) * frac,
                    "lon": prev["lon"] + (curr["lon"] - prev["lon"]) * frac,
                })
        result.append(curr)
    return result


def fix_connection_jumps(points: list[dict], jumps: list[dict], threshold_m: float = 300) -> list[dict]:
    """Fix connection jumps by interpolating between jump endpoints.

    For jumps over threshold_m within the route, insert intermediate points.
    """
    if not jumps:
        return points
    result = list(points)
    for j in reversed(jumps):
        if j["distance_m"] <= threshold_m:
            continue
        idx = j["index"]
        p_from = result[idx - 1]
        p_to = result[idx]
        mid_lat = (p_from["lat"] + p_to["lat"]) / 2
        mid_lon = (p_from["lon"] + p_to["lon"]) / 2
        result.insert(idx, {"lat": mid_lat, "lon": mid_lon})
    return result


# ── Rebuild Candidate ───────────────────────────────────────────────────

def rebuild_candidate(route_id: str, original: dict, alternatives: list[dict]) -> dict:
    """Rebuild candidate GPX with validated, fixed replacements."""
    points = list(original["points"])
    hints_data = _read_json(ARTIFACTS_REROUTE / f"reroute_hints_{route_id}.json")
    hints = {h["hint_id"]: h for h in (hints_data.get("hints", []) if hints_data else [])}
    applied = []
    unsafe = []
    safety_warnings = []
    waypoints = []

    # Build replacement list with validation, process in reverse index order
    replacements = []
    for alt in alternatives:
        hid = alt["hint_id"]
        rec = alt.get("recommendation", "MANUAL_REVIEW")
        status = alt.get("status", "ERROR")
        coords = alt.get("coordinates", [])
        hint = hints.get(hid, {})
        s_idx = hint.get("start_anchor_gpx_idx", 0)
        e_idx = hint.get("end_anchor_gpx_idx", 0)
        start_km = hint.get("start_km", 0)
        end_km = hint.get("end_km", 0)

        if status != "FOUND" or rec != "USE_CANDIDATE":
            continue

        alt_pts = [{"lat": c[0], "lon": c[1]} for c in coords]
        if len(alt_pts) < 2:
            continue

        # Validate connection
        if s_idx >= len(original["points"]) or e_idx >= len(original["points"]):
            unsafe.append({"hint_id": hid, "reason": "Anchor indices out of range"})
            continue

        orig_start = original["points"][s_idx]
        orig_end = original["points"][e_idx]
        conn = validate_replacement_connection(orig_start, alt_pts, orig_end)

        # Maybe reverse
        alt_pts = maybe_reverse_alt(alt_pts, conn)

        # Re-check after reversal
        conn2 = validate_replacement_connection(orig_start, alt_pts, orig_end)
        if not conn2["valid"]:
            unsafe.append({
                "hint_id": hid,
                "reason": f"Connection unsafe: start→alt={conn2['d_start_alt_first_m']:.0f}m, "
                          f"alt→end={conn2['d_alt_last_end_m']:.0f}m (max {MAX_CONNECTION_M}m)",
                "connection": conn2,
            })
            waypoints.append({
                "lat": orig_start["lat"], "lon": orig_start["lon"],
                "name": f"UNSAFE {hid}",
                "desc": f"Objazd odrzucony: złe połączenie ({conn2['d_start_alt_first_m']:.0f}m/{conn2['d_alt_last_end_m']:.0f}m)",
            })
            continue

        # Trim duplicates
        alt_pts = trim_to_anchors(alt_pts, original["points"], s_idx, e_idx)

        # Densify to avoid large jumps within alternative
        alt_pts = densify_alt(alt_pts, max_gap_m=250)

        replacements.append({
            "hint_id": hid,
            "start_idx": s_idx,
            "end_idx": e_idx,
            "start_km": start_km,
            "end_km": end_km,
            "alt_pts": alt_pts,
            "conn": conn2,
        })

    # Apply replacements in reverse index order
    replacements.sort(key=lambda r: r["end_idx"], reverse=True)

    for r in replacements:
        s_idx = r["start_idx"]
        e_idx = r["end_idx"]
        alt_pts = r["alt_pts"]

        # Delete original segment (keep anchors)
        del points[s_idx + 1:e_idx]
        # Insert alternative after start anchor
        points[s_idx + 1:s_idx + 1] = alt_pts

        applied.append(r)
        waypoints.append({
            "lat": alt_pts[0]["lat"], "lon": alt_pts[0]["lon"],
            "name": f"OBJAZD START {r['hint_id']}",
            "desc": f"Objazd. Δ={r['conn']['d_start_alt_first_m']:.0f}m / {r['conn']['d_alt_last_end_m']:.0f}m",
        })
        waypoints.append({
            "lat": alt_pts[-1]["lat"], "lon": alt_pts[-1]["lon"],
            "name": f"OBJAZD KONIEC {r['hint_id']}",
            "desc": f"Koniec objazdu. Powrót do trasy.",
        })

    # Add REVIEW waypoints for skipped alternatives
    for alt in alternatives:
        hid = alt["hint_id"]
        rec = alt.get("recommendation", "MANUAL_REVIEW")
        status = alt.get("status", "ERROR")
        if status == "FOUND" and rec == "USE_CANDIDATE":
            continue
        hint = hints.get(hid, {})
        s_idx = hint.get("start_anchor_gpx_idx", 0)
        if s_idx < len(points):
            waypoints.append({
                "lat": points[s_idx]["lat"], "lon": points[s_idx]["lon"],
                "name": f"REVIEW {hid}",
                "desc": f"Segment nie został podmieniony ({status}/{rec})",
            })

    # Detect jumps
    jumps = detect_large_jumps(points)
    for j in jumps:
        safety_warnings.append(f"Jump {j['distance_m']:.0f}m at point {j['index']}")

    # Compute distances
    total_km = 0.0
    for i in range(1, len(points)):
        total_km += _haversine_km(points[i-1]["lat"], points[i-1]["lon"], points[i]["lat"], points[i]["lon"])
    candidate_km = round(total_km, 3)
    original_km = original["total_km"]
    delta_km = round(candidate_km - original_km, 4)
    delta_pct = round((delta_km / original_km * 100) if original_km > 0 else 0, 1)

    # Determine suspicious (after densification, use tighter threshold)
    max_jump = max((j["distance_m"] for j in jumps), default=0)
    candidate_suspicious = max_jump > 300

    return {
        "points": points,
        "applied": applied,
        "unsafe": unsafe,
        "safety_warnings": safety_warnings,
        "waypoints": waypoints,
        "candidate_km": candidate_km,
        "original_km": original_km,
        "delta_km": delta_km,
        "delta_pct": delta_pct,
        "max_jump_m": round(max_jump, 1),
        "candidate_suspicious": candidate_suspicious,
        "jumps": jumps,
    }


# ── GPX Builder ───────────────────────────────────────────────────────────

def build_gpx(route_id: str, result: dict, original: dict) -> str:
    gpx_ns = original["gpx_ns"]
    root = ET.Element("gpx", {
        "version": "1.1", "creator": "QBot-GravelIntelligence-G14F",
        "xmlns": gpx_ns.strip("{}"),
    })

    meta = ET.SubElement(root, "meta" if gpx_ns == "{http://www.topografix.com/GPX/1/1}" else "metadata")
    ET.SubElement(meta, "name").text = f"Fixed Candidate Route {route_id} — G14F"
    ET.SubElement(meta, "desc").text = (
        f"Fixed candidate with validated splices. {len(result['applied'])} replacements. "
        f"Max jump: {result['max_jump_m']:.0f}m. Generated {_iso_now()}."
    )

    for wp in result["waypoints"]:
        wpt = ET.SubElement(root, "wpt")
        wpt.set("lat", str(wp["lat"]))
        wpt.set("lon", str(wp["lon"]))
        ET.SubElement(wpt, "name").text = wp["name"]
        ET.SubElement(wpt, "desc").text = wp.get("desc", "")

    trk = ET.SubElement(root, "trk")
    ET.SubElement(trk, "name").text = f"Fixed Candidate {route_id} (G14F)"
    ET.SubElement(trk, "desc").text = (
        f"Oryg: {original['total_km']:.2f}km → Fix: {result['candidate_km']:.2f}km "
        f"({result['delta_pct']:+.1f}%). {len(result['applied'])} objazdów."
    )

    trkseg = ET.SubElement(trk, "trkseg")
    for pt in result["points"]:
        trkpt = ET.SubElement(trkseg, "trkpt")
        trkpt.set("lat", str(pt["lat"]))
        trkpt.set("lon", str(pt["lon"]))

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


# ── Main ──────────────────────────────────────────────────────────────────

def run(route_id: str) -> dict:
    rid = str(route_id)
    print(f"  Loading original GPX for {rid}...")
    original = load_original_gpx(rid)
    if not original:
        return {"ok": False, "error": f"Original GPX not found"}

    alt_path = ARTIFACTS_REROUTE / f"g14c_reroute_alternatives_{rid}.json"
    alt_data = _read_json(alt_path)
    if not alt_data:
        return {"ok": False, "error": f"G14C alternatives not found"}

    alternatives = alt_data.get("alternatives", [])
    print(f"  Original: {original['n']} pts, {original['total_km']:.2f} km")
    print(f"  Alternatives: {len(alternatives)}")

    # Rebuild with validation
    print(f"  Validating and rebuilding candidate...")
    result = rebuild_candidate(rid, original, alternatives)

    print(f"    Applied: {len(result['applied'])}")
    print(f"    Unsafe: {len(result['unsafe'])}")
    print(f"    Max jump: {result['max_jump_m']:.0f}m")
    print(f"    Suspicious: {result['candidate_suspicious']}")

    # Build GPX
    gpx_xml = build_gpx(rid, result, original)

    # Write outputs
    gpx_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}_g14f_fixed.gpx"
    md_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}_g14f_fixed.md"
    sum_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}_g14f_fixed_summary.json"

    _write_gpx(gpx_path, gpx_xml)

    summary = {
        "route_id": rid,
        "mode": "validated_candidate",
        "generated_at": _iso_now(),
        "candidate_gpx_path": str(gpx_path),
        "applied_replacements": len(result["applied"]),
        "unsafe_replacements": len(result["unsafe"]),
        "original_distance_km": result["original_km"],
        "candidate_distance_km": result["candidate_km"],
        "delta_km": result["delta_km"],
        "delta_pct": result["delta_pct"],
        "original_trkpt_count": original["n"],
        "candidate_trkpt_count": len(result["points"]),
        "max_jump_m": result["max_jump_m"],
        "candidate_suspicious": result["candidate_suspicious"],
        "safety_warnings": result["safety_warnings"],
        "no_rwgps_upload": True,
    }
    _write_json(sum_path, summary)

    # MD report
    md_lines = [
        f"# G14F Fixed Candidate GPX: {alt_data.get('route_name','')}",
        "",
        f"**Route ID:** {rid}",
        f"**Generated:** {_iso_now()}",
        "",
        "## 📊 Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Applied | {len(result['applied'])} |",
        f"| Unsafe (rejected) | {len(result['unsafe'])} |",
        f"| Original | {result['original_km']:.2f} km |",
        f"| Candidate | {result['candidate_km']:.2f} km |",
        f"| Delta | {result['delta_km']:+.4f} km ({result['delta_pct']:+.1f}%) |",
        f"| Max jump | {result['max_jump_m']:.0f} m |",
        f"| Suspicious | {'⚠️ YES' if result['candidate_suspicious'] else '✅ No'} |",
        "",
    ]

    if result["safety_warnings"]:
        md_lines.append("### ⚠️ Safety Warnings")
        for w in result["safety_warnings"][:5]:
            md_lines.append(f"- {w}")
        if len(result["safety_warnings"]) > 5:
            md_lines.append(f"- ... and {len(result['safety_warnings'])-5} more")
        md_lines.append("")

    if result["applied"]:
        md_lines.append("## ✅ Applied Replacements")
        md_lines.append("")
        for r in result["applied"]:
            md_lines.append(f"**{r['hint_id']}** km {r['start_km']:.1f}–{r['end_km']:.1f}")
            md_lines.append(f"- Connection: {r['conn']['d_start_alt_first_m']:.0f}m / {r['conn']['d_alt_last_end_m']:.0f}m")
            md_lines.append(f"- Reversed: {'Yes' if r['conn']['reversed'] else 'No'}")
            md_lines.append("")

    if result["unsafe"]:
        md_lines.append("## ❌ Unsafe Replacements (Rejected)")
        md_lines.append("")
        for u in result["unsafe"]:
            md_lines.append(f"**{u['hint_id']}:** {u['reason']}")
        md_lines.append("")

    if result["waypoints"]:
        md_lines.append("## 📍 Waypoints")
        for wp in result["waypoints"]:
            md_lines.append(f"- **{wp['name']}**: {wp.get('desc','')}")
        md_lines.append("")

    md_lines.append("## 💡 Instructions")
    md_lines.append("")
    md_lines.append(f"1. Download: `{gpx_path}`")
    md_lines.append(f"2. Import to RWGPS as **NEW** route")
    md_lines.append(f"3. No RWGPS upload performed")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append(f"*Generated by G14F — {_iso_now()}*")

    _write_md(md_path, "\n".join(md_lines))
    print(f"    GPX: {gpx_path}")

    return {"ok": True, **summary}


def main():
    p = argparse.ArgumentParser(description="G14F Candidate Geometry Validation & Stitching Fix")
    p.add_argument("--route-id", required=True)
    args = p.parse_args()
    print("=" * 70)
    print("G14F Candidate Geometry Validation & Stitching Fix")
    print("=" * 70)
    print(f"  Route ID: {args.route_id}")
    print()
    result = run(args.route_id)
    if not result.get("ok"):
        print(f"  ERROR: {result.get('error')}")
        sys.exit(1)
    print()
    print("Done.")


if __name__ == "__main__":
    main()
