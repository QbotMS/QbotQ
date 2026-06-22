#!/usr/bin/env python3
"""g14e_build_candidate_route_gpx.py — Candidate Route GPX Dry-run dla Gravel Intelligence.

Tworzy kandydacki GPX z podmienionymi segmentami USE_CANDIDATE z G14C.

Usage:
    python3 scripts/g14e_build_candidate_route_gpx.py --route-id 55401067
    python3 scripts/g14e_build_candidate_route_gpx.py --route-id 55401067 --force
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACTS_REROUTE = Path("/opt/qbot/artifacts/reroute")
ARTIFACTS_EXPORTS = Path("/opt/qbot/artifacts/exports/rwgps")


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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
    # Find namespace
    gpx_ns = ns if root.findall(f".//{ns}trkpt") else ns0
    trkpts = root.findall(f".//{gpx_ns}trkpt")
    if not trkpts:
        return None

    points = []
    for pt in trkpts:
        lat = pt.get("lat")
        lon = pt.get("lon")
        if lat and lon:
            points.append({"lat": float(lat), "lon": float(lon), "ele": None})
            ele = pt.find(f"{gpx_ns}ele")
            if ele is not None and ele.text:
                points[-1]["ele"] = float(ele.text)

    # Cumulative distance
    cum_dist = [0.0]
    for i in range(1, len(points)):
        d = _haversine_km(points[i-1]["lat"], points[i-1]["lon"],
                          points[i]["lat"], points[i]["lon"])
        cum_dist.append(cum_dist[-1] + d)

    return {
        "points": points,
        "cum_dist": cum_dist,
        "total_km": round(cum_dist[-1], 3),
        "n": len(points),
        "gpx_ns": gpx_ns,
        "gpx_path": gpx_path,
    }


# ── Candidate Builder ────────────────────────────────────────────────────

def build_candidate_gpx(route_id: str, original: dict, alternatives: list[dict]) -> dict:
    """Build candidate GPX by replacing USE_CANDIDATE segments."""
    points = list(original["points"])  # copy
    cum_dist = list(original["cum_dist"])
    applied = []
    skipped = []
    safety_warnings = []
    waypoints = []

    # Sort alternatives by start_anchor_gpx_idx descending so we replace from end to start
    # (avoid index shifting)
    sorted_alts = sorted(
        [a for a in alternatives if a.get("coordinates")],
        key=lambda a: a.get("hint_id", ""),
    )
    # Get anchor indices from the hint metadata by re-loading the hints file
    hints_data = _read_json(ARTIFACTS_REROUTE / f"reroute_hints_{route_id}.json")
    hints = {h["hint_id"]: h for h in (hints_data.get("hints", []) if hints_data else [])}

    # Build list with indices for replacement (process in reverse index order)
    replacements = []
    for alt in sorted_alts:
        hid = alt["hint_id"]
        hint = hints.get(hid, {})
        s_idx = hint.get("start_anchor_gpx_idx", 0)
        e_idx = hint.get("end_anchor_gpx_idx", 0)
        coords = alt.get("coordinates", [])
        status = alt.get("status", "ERROR")
        rec = alt.get("recommendation", "MANUAL_REVIEW")

        replacements.append({
            "alt": alt,
            "hint": hint,
            "start_idx": s_idx,
            "end_idx": e_idx,
            "coords": coords,
            "status": status,
            "recommendation": rec,
        })

    # Process in reverse index order to avoid shifting
    replacements.sort(key=lambda r: r["end_idx"], reverse=True)

    for r in replacements:
        hid = r["alt"]["hint_id"]
        rec = r["recommendation"]
        status = r["status"]
        s_idx = r["start_idx"]
        e_idx = r["end_idx"]
        coords = r["coords"]
        start_km = r["hint"].get("start_km", 0)
        end_km = r["hint"].get("end_km", 0)

        if status == "FOUND" and rec == "USE_CANDIDATE":
            if not coords or s_idx >= e_idx:
                skipped.append({"hint_id": hid, "reason": "Invalid indices or no coordinates"})
                continue
            if s_idx < 0 or e_idx >= len(points):
                skipped.append({"hint_id": hid, "reason": f"Indices out of range ({s_idx}-{e_idx})"})
                continue

            # Replace points between start_idx+1 and end_idx with alternative
            # Keep the anchor points themselves (start_idx and end_idx)
            new_pts = [{"lat": c[0], "lon": c[1], "ele": None} for c in coords]

            # Remove the original segment (keep anchors)
            del points[s_idx + 1:e_idx]

            # Insert alternative after start anchor
            points[s_idx + 1:s_idx + 1] = new_pts

            applied.append({
                "hint_id": hid,
                "start_km": start_km,
                "end_km": end_km,
                "alternative_km": r["alt"].get("alternative_distance_km", 0),
                "original_segment_km": r["alt"].get("original_distance_km", 0),
                "delta_pct": r["alt"].get("delta_pct", 0),
                "new_points": len(coords),
            })

            waypoints.append({
                "lat": coords[0][0], "lon": coords[0][1],
                "name": f"OBJAZD START {hid}",
                "desc": f"Początek objazdu. Alternatywa Brouter: {r['alt'].get('delta_pct',0):+.1f}% ({r['alt'].get('alternative_distance_km',0):.2f} km zamiast {r['alt'].get('original_distance_km',0):.2f} km).",
            })
            waypoints.append({
                "lat": coords[-1][0], "lon": coords[-1][1],
                "name": f"OBJAZD KONIEC {hid}",
                "desc": f"Koniec objazdu. Powrót do oryginalnej trasy.",
            })
        else:
            # Not applied
            reason = f"status={status}, recommendation={rec}"
            skipped.append({"hint_id": hid, "start_km": start_km, "end_km": end_km, "reason": reason})
            waypoints.append({
                "lat": points[s_idx]["lat"], "lon": points[s_idx]["lon"],
                "name": f"REVIEW {hid}",
                "desc": f"Segment km {start_km:.1f}–{end_km:.1f} wymaga ręcznego sprawdzenia. Alternatywa +{r['alt'].get('delta_pct',0):+.1f}%, nie zastosowano.",
            })

    # Recalculate cumulative distance
    new_cum = [0.0]
    for i in range(1, len(points)):
        d = _haversine_km(points[i-1]["lat"], points[i-1]["lon"],
                          points[i]["lat"], points[i]["lon"])
        new_cum.append(new_cum[-1] + d)
    candidate_km = round(new_cum[-1], 3)

    # Validation
    original_km = original["total_km"]
    delta_km = round(candidate_km - original_km, 4)
    delta_pct = round((delta_km / original_km * 100) if original_km > 0 else 0, 1)

    candidate_suspicious = False
    if abs(delta_pct) > 25:
        safety_warnings.append(f"Delta ({delta_pct:+.1f}%) przekracza 25%")
        candidate_suspicious = True
    if len(points) < original["n"] * 0.5:
        safety_warnings.append(f"Candidate ma {len(points)} punktów, oryginał {original['n']} (<50%)")
        candidate_suspicious = True

    # Check for jumps > 500m
    for i in range(1, len(points)):
        d = _haversine_km(points[i-1]["lat"], points[i-1]["lon"],
                          points[i]["lat"], points[i]["lon"])
        if d > 0.5:
            safety_warnings.append(f"Skok >500m między punktami {i-1}–{i} ({d*1000:.0f}m)")
            candidate_suspicious = True
            break

    # Build GPX XML
    gpx_ns = original["gpx_ns"]
    gpx_root = ET.Element("gpx", {
        "version": "1.1",
        "creator": "QBot-GravelIntelligence-G14E",
        "xmlns": gpx_ns.strip("{}"),
    })

    # Metadata
    meta = ET.SubElement(gpx_root, "meta" if gpx_ns == "{http://www.topografix.com/GPX/1/1}" else "metadata")
    meta_ele = ET.SubElement(meta, "name")
    meta_ele.text = f"Candidate Route {route_id} — G14E"
    meta_ele = ET.SubElement(meta, "desc")
    meta_ele.text = f"Candidate GPX with Brouter reroute segments. Generated {_iso_now()}. {len(applied)} replacements applied, {len(skipped)} skipped."

    # Waypoints
    for wp in waypoints:
        wpt = ET.SubElement(gpx_root, "wpt" if gpx_ns == "{http://www.topografix.com/GPX/1/1}" else "wpt")
        wpt.set("lat", str(wp["lat"]))
        wpt.set("lon", str(wp["lon"]))
        name = ET.SubElement(wpt, "name" if gpx_ns == "{http://www.topografix.com/GPX/1/1}" else "name")
        name.text = wp["name"]
        desc = ET.SubElement(wpt, "desc" if gpx_ns == "{http://www.topografix.com/GPX/1/1}" else "desc")
        desc.text = wp["desc"]

    # Track
    trk = ET.SubElement(gpx_root, "trk")
    trk_name = ET.SubElement(trk, "name")
    trk_name.text = f"Candidate Route {route_id} (G14E)"
    trk_desc = ET.SubElement(trk, "desc")
    trk_desc.text = f"Kandydat z objazdami. Oryginał: {original_km:.2f}km → Kandydat: {candidate_km:.2f}km ({delta_pct:+.1f}%). {len(applied)} podmian."

    trkseg = ET.SubElement(trk, "trkseg")
    for pt in points:
        trkpt = ET.SubElement(trkseg, "trkpt")
        trkpt.set("lat", str(pt["lat"]))
        trkpt.set("lon", str(pt["lon"]))
        if pt.get("ele") is not None:
            ele = ET.SubElement(trkpt, "ele")
            ele.text = str(pt["ele"])

    gpx_xml = ET.tostring(gpx_root, encoding="unicode", xml_declaration=True)

    return {
        "gpx_xml": gpx_xml,
        "candidate_points": len(points),
        "candidate_km": candidate_km,
        "original_km": original_km,
        "delta_km": delta_km,
        "delta_pct": delta_pct,
        "applied": applied,
        "skipped": skipped,
        "safety_warnings": safety_warnings,
        "candidate_suspicious": candidate_suspicious,
        "waypoints": waypoints,
    }


# ── Main Pipeline ─────────────────────────────────────────────────────────

def run(route_id: str, force: bool = False) -> dict:
    rid = str(route_id)
    print(f"  Loading original GPX for {rid}...")

    original = load_original_gpx(rid)
    if not original:
        return {"ok": False, "error": f"Original GPX not found for {rid}"}
    print(f"    {original['n']} points, {original['total_km']:.2f} km")

    # Load G14C alternatives
    alt_path = ARTIFACTS_REROUTE / f"g14c_reroute_alternatives_{rid}.json"
    alt_data = _read_json(alt_path)
    if not alt_data:
        return {"ok": False, "error": f"G14C alternatives not found: {alt_path}"}

    alternatives = alt_data.get("alternatives", [])
    print(f"    {len(alternatives)} alternatives loaded")

    # Build candidate
    print(f"  Building candidate GPX...")
    result = build_candidate_gpx(rid, original, alternatives)

    print(f"    Applied: {len(result['applied'])} replacements")
    print(f"    Skipped: {len(result['skipped'])} replacements")
    print(f"    Original: {result['original_km']:.2f} km → Candidate: {result['candidate_km']:.2f} km ({result['delta_pct']:+.1f}%)")
    print(f"    Suspicious: {result['candidate_suspicious']}")

    # Write outputs
    gpx_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}.gpx"
    md_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}.md"
    sum_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}_summary.json"

    _write_gpx(gpx_path, result["gpx_xml"])
    print(f"    GPX: {gpx_path}")

    # Build summary JSON
    summary = {
        "route_id": rid,
        "mode": "dry_run_candidate",
        "generated_at": _iso_now(),
        "generator": "g14e_build_candidate_route_gpx.py",
        "original_gpx_path": str(original["gpx_path"]),
        "candidate_gpx_path": str(gpx_path),
        "applied_replacements": len(result["applied"]),
        "skipped_replacements": len(result["skipped"]),
        "original_distance_km": result["original_km"],
        "candidate_distance_km": result["candidate_km"],
        "delta_km": result["delta_km"],
        "delta_pct": result["delta_pct"],
        "original_trkpt_count": original["n"],
        "candidate_trkpt_count": result["candidate_points"],
        "candidate_suspicious": result["candidate_suspicious"],
        "safety_warnings": result["safety_warnings"],
        "no_rwgps_upload": True,
    }
    _write_json(sum_path, summary)
    print(f"    Summary: {sum_path}")

    # Build MD report
    md = _build_md(rid, alt_data.get("route_name", ""), original, result, summary)
    _write_md(md_path, md)
    print(f"    MD: {md_path}")

    return {"ok": True, **summary}


def _build_md(rid: str, route_name: str, original: dict, result: dict, summary: dict) -> str:
    lines = []
    lines.append(f"# Candidate Route GPX: {route_name}")
    lines.append("")
    lines.append(f"**Route ID:** {rid}")
    lines.append(f"**Generated:** {_iso_now()}")
    lines.append("")
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Replacements applied | {len(result['applied'])} |")
    lines.append(f"| Replacements skipped | {len(result['skipped'])} |")
    lines.append(f"| Original distance | {result['original_km']:.2f} km |")
    lines.append(f"| Candidate distance | {result['candidate_km']:.2f} km |")
    lines.append(f"| Delta | {result['delta_km']:+.4f} km ({result['delta_pct']:+.1f}%) |")
    lines.append(f"| Original points | {original['n']} |")
    lines.append(f"| Candidate points | {result['candidate_points']} |")
    lines.append(f"| Candidate suspicious | {'⚠️ YES' if result['candidate_suspicious'] else '✅ No'} |")
    lines.append(f"| RWGPS upload | ❌ Not performed |")
    lines.append("")

    if result["safety_warnings"]:
        lines.append("### ⚠️ Safety Warnings")
        lines.append("")
        for w in result["safety_warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    if result["applied"]:
        lines.append("## ✅ Applied Replacements (USE_CANDIDATE)")
        lines.append("")
        lines.append("| Hint | KM | Original | Alternative | Δ% | New Points |")
        lines.append("|------|-----|----------|-------------|-----|------------|")
        for a in result["applied"]:
            lines.append(f"| {a['hint_id']} | {a['start_km']:.1f}–{a['end_km']:.1f} | {a['original_segment_km']:.2f} km | {a['alternative_km']:.2f} km | {a['delta_pct']:+.1f}% | {a['new_points']} |")
        lines.append("")

    if result["skipped"]:
        lines.append("## ❌ Skipped Replacements")
        lines.append("")
        lines.append("| Hint | KM | Reason |")
        lines.append("|------|-----|--------|")
        for s in result["skipped"]:
            km = f"{s.get('start_km',0):.1f}–{s.get('end_km',0):.1f}"
            lines.append(f"| {s['hint_id']} | {km} | {s['reason']} |")
        lines.append("")

    if result["waypoints"]:
        lines.append("## 📍 Waypoints")
        lines.append("")
        for wp in result["waypoints"]:
            lines.append(f"- **{wp['name']}** ({wp['lat']}, {wp['lon']}): {wp['desc']}")
        lines.append("")

    lines.append("## 💡 Instructions")
    lines.append("")
    lines.append(f"1. Download candidate GPX: `{summary['candidate_gpx_path']}`")
    lines.append(f"2. Import to RWGPS as a **NEW** route (do NOT overwrite original)")
    lines.append(f"3. Manually review the replaced segments on the map")
    lines.append(f"4. For REVIEW waypoints: check satellite/map to determine if the detour is needed")
    lines.append(f"5. If candidate looks good — ride it and report back for G13/G14 feedback")
    lines.append("")
    lines.append("## ⚠️ Important")
    lines.append("")
    lines.append("- This is a **dry-run candidate**. No GPX was modified in place.")
    lines.append("- No route was uploaded to RWGPS.")
    lines.append("- The candidate was generated automatically by Brouter (trekking profile).")
    lines.append("- Manual review of REVIEW waypoints is required.")
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by G14E — {_iso_now()}*")

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="G14E Candidate Route GPX Dry-run")
    p.add_argument("--route-id", required=True, help="Garmin route ID")
    p.add_argument("--force", action="store_true", help="Force rebuild even if candidate exists")
    args = p.parse_args()

    print("=" * 70)
    print("G14E Candidate Route GPX Dry-run")
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
