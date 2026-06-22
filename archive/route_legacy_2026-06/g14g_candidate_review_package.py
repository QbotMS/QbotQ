#!/usr/bin/env python3
"""g14g_candidate_review_package.py — Candidate Route Review Package dla Gravel Intelligence.

Łączy G13 briefing, G14C alternatives, G14F fixed candidate GPX
w jeden pakiet review: MD report, JSON summary, GeoJSON/KML.

Usage:
    python3 scripts/g14g_candidate_review_package.py --route-id 55401067
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
ARTIFACTS_REVIEW = Path("/opt/qbot/artifacts/review")
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


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── GPX Load ──────────────────────────────────────────────────────────────

def load_gpx_points(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except Exception:
        return []
    ns = "{http://www.topografix.com/GPX/1/1}"
    ns0 = "{http://www.topografix.com/GPX/1/0}"
    trkpts = root.findall(f".//{ns}trkpt") or root.findall(f".//{ns0}trkpt")
    pts = []
    for pt in trkpts:
        lat = pt.get("lat"); lon = pt.get("lon")
        if lat and lon:
            pts.append({"lat": float(lat), "lon": float(lon)})
    return pts


# ── Package Builder ───────────────────────────────────────────────────────

def build_package(route_id: str) -> dict:
    rid = str(route_id)

    # Load inputs
    candidate_summary = _read_json(ARTIFACTS_REROUTE / f"candidate_route_{rid}_g14f_fixed_summary.json")
    alternatives_data = _read_json(ARTIFACTS_REROUTE / f"g14c_reroute_alternatives_{rid}.json")
    briefing = _read_json(ARTIFACTS_REVIEW / f"review_briefing_{rid}.json")
    original_gpx = load_gpx_points(ARTIFACTS_EXPORTS / f"rwgps_{rid}.gpx")
    candidate_gpx = load_gpx_points(ARTIFACTS_REROUTE / f"candidate_route_{rid}_g14f_fixed.gpx")

    route_name = briefing.get("route_name", alternatives_data.get("route_name", f"Route {rid}")) if briefing else f"Route {rid}"

    # Build replacement details from alternatives
    hints_data = _read_json(ARTIFACTS_REROUTE / f"reroute_hints_{rid}.json")
    hints = {h["hint_id"]: h for h in (hints_data.get("hints", []) if hints_data else [])}
    problems_map = {}
    if briefing:
        for p in briefing.get("problems", []):
            problems_map[p["problem_id"]] = p

    alternatives = alternatives_data.get("alternatives", []) if alternatives_data else []
    replacements = []
    skipped = []

    for alt in alternatives:
        hid = alt["hint_id"]
        hint = hints.get(hid, {})
        # Map via problem_id from hint
        prob_id = hint.get("problem_id", "")
        prob = problems_map.get(prob_id, {})
        if not prob and hid in problems_map:
            prob = problems_map.get(hid, {})
        status = alt.get("status", "ERROR")
        rec = alt.get("recommendation", "MANUAL_REVIEW")
        start_km = hint.get("start_km", 0)
        end_km = hint.get("end_km", 0)
        manual = prob.get("manual_override_applied", False)
        risk_type = prob.get("risk_type", hint.get("risk_type", "unknown"))
        severity = prob.get("severity", hint.get("severity", "medium"))

        entry = {
            "hint_id": hid,
            "start_km": round(start_km, 1),
            "end_km": round(end_km, 1),
            "severity": severity,
            "risk_type": risk_type,
            "manual_override": manual,
            "original_distance_km": alt.get("original_distance_km"),
            "alternative_distance_km": alt.get("alternative_distance_km"),
            "delta_km": alt.get("delta_km"),
            "delta_pct": alt.get("delta_pct"),
            "router": alt.get("router", "none"),
        }

        if status == "FOUND" and rec == "USE_CANDIDATE":
            entry["applied"] = True
            entry["reason"] = "Brouter alternative applied"
            replacements.append(entry)
        else:
            entry["applied"] = False
            entry["reason"] = f"{status} / {rec}"
            skipped.append(entry)

    # Distances
    original_km = candidate_summary.get("original_distance_km", 0) if candidate_summary else 0
    candidate_km = candidate_summary.get("candidate_distance_km", 0) if candidate_summary else 0
    delta_km = candidate_summary.get("delta_km", candidate_km - original_km) if candidate_summary else 0
    delta_pct = candidate_summary.get("delta_pct", 0) if candidate_summary else 0
    max_jump = candidate_summary.get("max_jump_m", 0) if candidate_summary else 0
    suspicious = candidate_summary.get("candidate_suspicious", True) if candidate_summary else True
    safety_warnings = candidate_summary.get("safety_warnings", []) if candidate_summary else []

    # Build candidate GPX path
    candidate_gpx_path = ARTIFACTS_REROUTE / f"candidate_route_{rid}_g14f_fixed.gpx"
    original_gpx_path = ARTIFACTS_EXPORTS / f"rwgps_{rid}.gpx"

    # Checklist
    checklist = [
        {"id": "no_straight_lines", "label": "Brak dziwnych prostych linii / skoków na mapie", "checked": max_jump <= 300},
        {"id": "roads_not_fields", "label": "Objazdy prowadzą drogami, nie przez pola / lasy", "checked": False},
        {"id": "logistical_sense", "label": "Trasa zachowuje sens logistyczny (start/meta, długość)", "checked": False},
        {"id": "no_missing_sections", "label": "Nie pomija istotnych odcinków", "checked": False},
        {"id": "warnings_later", "label": "Warningi/POI zostaną dołożone przez G15", "checked": True},
    ]

    next_actions = [
        "Pobierz candidate GPX i otwórz w RWGPS jako NOWĄ trasę",
        "Porównaj z oryginałem — sprawdź 3 podmienione odcinki",
        "Zweryfikuj checklistę akceptacji",
        "Zdecyduj: RIDE tę trasę / OMIT / dalsze poprawki",
    ]

    review_package = {
        "status": "REVIEW_REQUIRED",
        "production_ready": False,
        "generated_at": _iso_now(),
        "generator": "g14g_candidate_review_package.py",
        "route_id": rid,
        "route_name": route_name,
        "candidate_gpx_path": str(candidate_gpx_path),
        "original_gpx_path": str(original_gpx_path),
        "original_distance_km": round(original_km, 2),
        "candidate_distance_km": round(candidate_km, 2),
        "delta_km": round(delta_km, 4),
        "delta_pct": round(delta_pct, 1),
        "original_trkpt_count": len(original_gpx),
        "candidate_trkpt_count": len(candidate_gpx),
        "applied_replacements": len(replacements),
        "skipped_replacements": len(skipped),
        "max_jump_m": round(max_jump, 1),
        "suspicious": suspicious,
        "safety_warnings": safety_warnings,
        "replacements": replacements,
        "skipped": skipped,
        "review_checklist": checklist,
        "next_actions": next_actions,
        "no_rwgps_upload": True,
    }
    return review_package


# ── Output Writers ────────────────────────────────────────────────────────

def write_json(pkg: dict) -> Path:
    path = ARTIFACTS_REROUTE / f"review_package_{pkg['route_id']}.json"
    _write(path, json.dumps(pkg, indent=2, ensure_ascii=False, default=str))
    return path


def write_md(pkg: dict) -> Path:
    rid = pkg["route_id"]
    lines = [
        f"# Review Package: {pkg['route_name']}",
        "",
        f"**Route ID:** {rid}",
        f"**Status:** {pkg['status']}",
        f"**Production ready:** {'❌ No' if not pkg['production_ready'] else '✅ Yes'}",
        f"**Generated:** {pkg['generated_at']}",
        "",
        "## 📊 Route Comparison",
        "",
        "| Metric | Original | Candidate | Delta |",
        "|--------|----------|-----------|-------|",
        f"| Distance | {pkg['original_distance_km']:.2f} km | {pkg['candidate_distance_km']:.2f} km | {pkg['delta_km']:+.4f} km ({pkg['delta_pct']:+.1f}%) |",
        f"| Track points | {pkg['original_trkpt_count']} | {pkg['candidate_trkpt_count']} | {pkg['candidate_trkpt_count'] - pkg['original_trkpt_count']:+d} |",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Replacements applied | {pkg['applied_replacements']} |",
        f"| Replacements skipped | {pkg['skipped_replacements']} |",
        f"| Max jump after fix | {pkg['max_jump_m']:.0f} m |",
        f"| Suspicious | {'⚠️ YES' if pkg['suspicious'] else '✅ No'} |",
        "",
    ]

    if pkg["safety_warnings"]:
        lines.append("### ⚠️ Safety Warnings")
        for w in pkg["safety_warnings"][:5]:
            lines.append(f"- {w}")
        if len(pkg["safety_warnings"]) > 5:
            lines.append(f"- ... and {len(pkg['safety_warnings'])-5} more")
        lines.append("")

    if pkg["replacements"]:
        lines.append("## ✅ Applied Replacements (Brouter)")
        lines.append("")
        lines.append("| # | KM | Risk | Manual | Original | Alternative | Δ% | Router |")
        lines.append("|---|-----|------|--------|----------|-------------|-----|--------|")
        for i, r in enumerate(pkg["replacements"]):
            m = "✅" if r["manual_override"] else " "
            orig_s = f"{r['original_distance_km']:.2f} km" if r['original_distance_km'] else "-"
            alt_s = f"{r['alternative_distance_km']:.2f} km" if r['alternative_distance_km'] else "-"
            delta = f"{r['delta_pct']:+.1f}%" if r['delta_pct'] is not None else "-"
            lines.append(f"| {i+1} | {r['start_km']}–{r['end_km']} | {r['risk_type']} | {m} | {orig_s} | {alt_s} | {delta} | {r['router']} |")
        lines.append("")
        for r in pkg["replacements"]:
            delta = f"{r['delta_pct']:+.1f}%" if r['delta_pct'] is not None else "N/A"
            lines.append(f"**{r['hint_id']}** km {r['start_km']}–{r['end_km']}")
            lines.append(f"- Powód: {r['reason']}")
            lines.append(f"- Oryginał: {r['original_distance_km']:.2f} km → Alternatywa: {r['alternative_distance_km']:.2f} km ({delta})")
            if r.get("manual_override"):
                lines.append(f"- Potwierdzone przez użytkownika: ✅")
            lines.append("")

    if pkg["skipped"]:
        lines.append("## ❌ Skipped Replacements")
        lines.append("")
        lines.append("| # | KM | Risk | Reason |")
        lines.append("|---|-----|------|--------|")
        for i, s in enumerate(pkg["skipped"]):
            lines.append(f"| {i+1} | {s['start_km']}–{s['end_km']} | {s['risk_type']} | {s['reason']} |")
        lines.append("")

    lines.append("## ✅ Review Checklist")
    lines.append("")
    for c in pkg["review_checklist"]:
        status = "✅" if c["checked"] else "⬜"
        lines.append(f"- [{status}] {c['label']}")
    lines.append("")

    lines.append("## 📋 Next Actions")
    lines.append("")
    for i, a in enumerate(pkg["next_actions"], 1):
        lines.append(f"{i}. {a}")
    lines.append("")

    lines.append("## 💡 Import Instructions")
    lines.append("")
    lines.append(f"1. Download candidate GPX:")
    lines.append(f"   `scp q:{pkg['candidate_gpx_path']} ~/Downloads/`")
    lines.append(f"2. Open RWGPS → Import → wybierz plik")
    lines.append(f"3. Zapisz jako **NOWĄ** trasę (nie nadpisuj oryginału)")
    lines.append(f"4. Porównaj z oryginałem wizualnie")
    lines.append(f"5. Zweryfikuj checklistę powyżej")
    lines.append("")
    lines.append("## ⚠️ Files")
    lines.append("")
    lines.append(f"- Candidate GPX: `{pkg['candidate_gpx_path']}`")
    lines.append(f"- Review JSON: `{ARTIFACTS_REROUTE / f'review_package_{rid}.json'}`")
    lines.append(f"- Review GeoJSON: `{ARTIFACTS_REROUTE / f'review_package_{rid}.geojson'}`")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by G14G — {pkg['generated_at']}*")

    path = ARTIFACTS_REROUTE / f"review_package_{rid}.md"
    _write(path, "\n".join(lines))
    return path


def write_geojson(pkg: dict) -> Path:
    rid = pkg["route_id"]
    original_pts = load_gpx_points(Path(pkg["original_gpx_path"]))
    candidate_pts = load_gpx_points(Path(pkg["candidate_gpx_path"]))

    features = []

    # Original route
    if original_pts:
        features.append({
            "type": "Feature",
            "properties": {"route_id": rid, "type": "original", "label": "Original route", "color": "#888888"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[p["lon"], p["lat"]] for p in original_pts],
            },
        })

    # Candidate route
    if candidate_pts:
        features.append({
            "type": "Feature",
            "properties": {"route_id": rid, "type": "candidate", "label": "Candidate route (Brouter)", "color": "#00cc00"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[p["lon"], p["lat"]] for p in candidate_pts],
            },
        })

    # Replacement points
    for r in pkg.get("replacements", []):
        hid = r["hint_id"]
        # Find coordinates from alternatives data
        alt_data = _read_json(ARTIFACTS_REROUTE / f"g14c_reroute_alternatives_{rid}.json")
        if alt_data:
            for a in alt_data.get("alternatives", []):
                if a["hint_id"] == hid and a.get("coordinates"):
                    coords = a["coordinates"]
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "route_id": rid, "type": "replacement_start",
                            "label": f"OBJAZD START km {r['start_km']}–{r['end_km']}",
                            "km_range": f"{r['start_km']}–{r['end_km']}",
                            "status": "applied",
                            "color": "#00cc00",
                        },
                        "geometry": {"type": "Point", "coordinates": [coords[0][1], coords[0][0]]},
                    })
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "route_id": rid, "type": "replacement_end",
                            "label": f"OBJAZD KONIEC km {r['start_km']}–{r['end_km']}",
                            "km_range": f"{r['start_km']}–{r['end_km']}",
                            "status": "applied",
                            "color": "#00cc00",
                        },
                        "geometry": {"type": "Point", "coordinates": [coords[-1][1], coords[-1][0]]},
                    })
                    break

    # Skipped points
    hints_data = _read_json(ARTIFACTS_REROUTE / f"reroute_hints_{rid}.json")
    hints = {h["hint_id"]: h for h in (hints_data.get("hints", []) if hints_data else [])}
    for s in pkg.get("skipped", []):
        hint = hints.get(s["hint_id"], {})
        # Get coordinates from original GPX at anchor point
        s_idx = hint.get("start_anchor_gpx_idx", 0)
        if s_idx < len(original_pts):
            pt = original_pts[s_idx]
            features.append({
                "type": "Feature",
                "properties": {
                    "route_id": rid, "type": "review_required",
                    "label": f"REVIEW km {s['start_km']}–{s['end_km']}: {s['reason']}",
                    "km_range": f"{s['start_km']}–{s['end_km']}",
                    "status": "review_required",
                    "color": "#ff6600",
                },
                "geometry": {"type": "Point", "coordinates": [pt["lon"], pt["lat"]]},
            })

    geojson = {"type": "FeatureCollection", "features": features}
    path = ARTIFACTS_REROUTE / f"review_package_{rid}.geojson"
    _write(path, json.dumps(geojson, indent=2, ensure_ascii=False, default=str))
    return path


def run(route_id: str) -> dict:
    rid = str(route_id)
    print(f"  Building review package for {rid}...")

    pkg = build_package(rid)

    json_path = write_json(pkg)
    md_path = write_md(pkg)
    geojson_path = write_geojson(pkg)

    print(f"    JSON: {json_path.name}")
    print(f"    MD:   {md_path.name}")
    print(f"    GeoJSON: {geojson_path.name}")
    print(f"    Status: {pkg['status']}")
    print(f"    Production: {pkg['production_ready']}")
    print(f"    Applied: {pkg['applied_replacements']}, Skipped: {pkg['skipped_replacements']}")
    print(f"    Suspicious: {pkg['suspicious']}")

    return {"ok": True, **pkg}


def main():
    p = argparse.ArgumentParser(description="G14G Candidate Route Review Package")
    p.add_argument("--route-id", required=True)
    args = p.parse_args()

    print("=" * 70)
    print("G14G Candidate Route Review Package")
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
