#!/usr/bin/env python3
"""g14_reroute_hints.py — Reroute Hints dla Gravel Intelligence.

Dla segmentów z decyzją OMIT/REVIEW/critical/manual high
przygotowuje dane anchorowe do przyszłego reroutingu (Brouter/Valhalla).

Usage:
    python3 scripts/g14_reroute_hints.py --route-id 55401067 --mode dry-run
    python3 scripts/g14_reroute_hints.py --route-id 55401067 --mode build
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

ARTIFACTS_REVIEW = Path("/opt/qbot/artifacts/review")
ARTIFACTS_EXPORTS = Path("/opt/qbot/artifacts/exports/rwgps")
ARTIFACTS_REROUTE = Path("/opt/qbot/artifacts/reroute")


# ── Helpers ───────────────────────────────────────────────────────────────

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
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── GPX Loading ───────────────────────────────────────────────────────────

def load_gpx(route_id: str) -> dict | None:
    """Load GPX file and return dict with points and cumulative distances."""
    gpx_path = ARTIFACTS_EXPORTS / f"rwgps_{route_id}.gpx"
    if not gpx_path.exists():
        return None

    try:
        tree = ET.parse(str(gpx_path))
        root = tree.getroot()
    except Exception:
        return None

    # Namespace-aware parsing
    ns = "{http://www.topografix.com/GPX/1/1}"
    ns0 = "{http://www.topografix.com/GPX/1/0}"
    trkpts = root.findall(f".//{ns}trkpt") or root.findall(f".//{ns0}trkpt")
    if not trkpts:
        return None

    points = []
    for pt in trkpts:
        lat = pt.get("lat")
        lon = pt.get("lon")
        if lat and lon:
            points.append((float(lat), float(lon)))

    if not points:
        return None

    # Compute cumulative distances
    cum_dist = [0.0]
    for i in range(1, len(points)):
        d = _haversine_km(
            points[i - 1][0], points[i - 1][1],
            points[i][0], points[i][1],
        )
        cum_dist.append(cum_dist[-1] + d)

    total_km = cum_dist[-1]

    return {
        "points": points,
        "cum_dist": cum_dist,
        "total_km": round(total_km, 3),
        "n": len(points),
    }


def find_anchor_at_km(gpx: dict, target_km: float) -> dict:
    """Find the nearest GPX point to target_km.

    Returns {km, lat, lng, index}.
    """
    cum_dist = gpx["cum_dist"]
    points = gpx["points"]
    n = len(cum_dist)

    if target_km <= 0:
        return {"km": 0.0, "lat": points[0][0], "lng": points[0][1], "index": 0}
    if target_km >= cum_dist[-1]:
        return {
            "km": cum_dist[-1],
            "lat": points[-1][0],
            "lng": points[-1][1],
            "index": n - 1,
        }

    # Binary search
    lo, hi = 0, n - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum_dist[mid] < target_km:
            lo = mid + 1
        else:
            hi = mid
    idx = lo

    # Interpolate for better accuracy
    if idx > 0 and idx < n:
        d0 = cum_dist[idx - 1]
        d1 = cum_dist[idx]
        frac = (target_km - d0) / (d1 - d0) if d1 > d0 else 0
        lat = points[idx - 1][0] + (points[idx][0] - points[idx - 1][0]) * frac
        lng = points[idx - 1][1] + (points[idx][1] - points[idx - 1][1]) * frac
    else:
        lat, lng = points[idx][0], points[idx][1]

    return {"km": round(target_km, 3), "lat": round(lat, 6), "lng": round(lng, 6), "index": idx}


# ── Hints Generation ──────────────────────────────────────────────────────

def load_inputs(route_id: str) -> dict:
    """Load all inputs for G14."""
    rid = str(route_id)
    result = {"route_id": rid}

    briefing = _read_json(ARTIFACTS_REVIEW / f"review_briefing_{rid}.json")
    decisions = _read_json(ARTIFACTS_REVIEW / f"review_decisions_{rid}.json")
    gpx = load_gpx(rid)

    result["briefing"] = briefing
    result["decisions"] = decisions
    result["gpx"] = gpx

    if briefing:
        result["route_name"] = briefing.get("route_name", "")
        result["distance_km"] = briefing.get("distance_km", 0)
    if gpx:
        result["distance_km"] = gpx["total_km"]

    return result


def needs_hint(problem: dict, decision_map: dict[str, str]) -> bool:
    """Check if a problem segment needs a reroute hint."""
    pid = problem["problem_id"]
    decision = decision_map.get(pid, "").upper()
    severity = problem.get("severity", "low")
    manual = problem.get("manual_override_applied", False)

    if decision in ("OMIT", "REVIEW"):
        return True
    if severity == "critical":
        return True
    if manual and severity in ("high", "critical"):
        return True
    return False


def get_anchor_buffer(problem: dict) -> float:
    """Determine anchor buffer distance based on problem length."""
    length = problem.get("length_km", 1)
    if length < 1.0:
        return 0.3
    elif length > 3.0:
        return 0.8
    return 0.5


def pick_strategy(problem: dict, decision: str) -> str:
    """Pick the reroute strategy based on problem + decision."""
    severity = problem.get("severity", "low")
    manual = problem.get("manual_override_applied", False)
    surface = problem.get("override_surface") or problem.get("risk_type", "")

    if decision == "OMIT":
        return "future_brouter_required"
    if decision == "REVIEW" and severity == "critical":
        return "manual_map_review"
    if manual and severity in ("high", "critical"):
        return "future_brouter_required"
    if decision == "REVIEW":
        return "manual_map_review"
    return "avoid_if_possible_later"


def generate_hints(inputs: dict) -> list[dict]:
    """Generate reroute hints for applicable problems."""
    briefing = inputs.get("briefing")
    decisions_data = inputs.get("decisions")
    gpx = inputs.get("gpx")

    if not briefing or not gpx:
        return []

    problems = briefing.get("problems", [])
    decisions_list = (decisions_data or {}).get("decisions", [])

    # Build decision map: problem_id → decision
    decision_map = {}
    for d in decisions_list:
        decision_map[d.get("problem_id", "")] = d.get("decision", "ACCEPT_WARNING")

    hints = []
    for prob in problems:
        if not needs_hint(prob, decision_map):
            continue

        pid = prob["problem_id"]
        decision = decision_map.get(pid, "REVIEW")
        start_km = prob.get("start_km", 0)
        end_km = prob.get("end_km", 0)
        length = prob.get("length_km", 0)
        severity = prob.get("severity", "low")
        score = prob.get("final_score", 0)

        # Compute anchor KMs
        buffer = get_anchor_buffer(prob)
        anchor_start_km = max(0, start_km - buffer)
        anchor_end_km = min(gpx["total_km"], end_km + buffer)

        # Find GPX anchors
        start_anchor = find_anchor_at_km(gpx, anchor_start_km)
        end_anchor = find_anchor_at_km(gpx, anchor_end_km)

        strategy = pick_strategy(prob, decision)

        # Build reason
        manual = prob.get("manual_override_applied", False)
        override_surface = prob.get("override_surface")
        risk_type = prob.get("risk_type", "unknown")

        if manual and override_surface:
            reason = (
                f"Ręcznie potwierdzony {override_surface} "
                f"(km {start_km:.1f}–{end_km:.1f}). "
                f"Decyzja: {decision}."
            )
        elif severity == "critical":
            reason = (
                f"Krytyczne ryzyko nawierzchni "
                f"(km {start_km:.1f}–{end_km:.1f}). "
                f"Decyzja: {decision}."
            )
        else:
            reason = (
                f"Segment problematyczny ({risk_type}) "
                f"km {start_km:.1f}–{end_km:.1f}. "
                f"Decyzja: {decision}."
            )

        hint = {
            "hint_id": f"g14_{inputs['route_id']}_hint_{len(hints):03d}",
            "problem_id": pid,
            "route_id": str(inputs["route_id"]),
            "start_km": round(start_km, 2),
            "end_km": round(end_km, 2),
            "length_km": round(length, 2),
            "severity": severity,
            "final_score": round(score, 4),
            "decision": decision,
            "manual_override": manual,
            "risk_type": risk_type,
            "reason": reason,
            "start_anchor_km": start_anchor["km"],
            "end_anchor_km": end_anchor["km"],
            "start_anchor_lat": start_anchor["lat"],
            "start_anchor_lng": start_anchor["lng"],
            "end_anchor_lat": end_anchor["lat"],
            "end_anchor_lng": end_anchor["lng"],
            "start_anchor_gpx_idx": start_anchor["index"],
            "end_anchor_gpx_idx": end_anchor["index"],
            "anchor_buffer_km": buffer,
            "strategy": strategy,
            "estimated_detour_status": "unknown",
            "requires_router": strategy in ("future_brouter_required", "manual_map_review"),
            "suggested_next_step": (
                "Uruchom Brouter/Valhalla dla alternatywy między anchor start a end."
                if strategy == "future_brouter_required"
                else "Sprawdź na mapie ręcznie."
            ),
        }
        hints.append(hint)

    return hints


# ── Output Builders ───────────────────────────────────────────────────────

def build_json_output(route_id: str, inputs: dict, hints: list[dict], mode: str) -> dict:
    return {
        "ok": True,
        "status": "OK",
        "mode": mode,
        "route_id": str(route_id),
        "route_name": inputs.get("route_name", ""),
        "distance_km": inputs.get("distance_km", 0),
        "source": "g14_reroute_hints",
        "g13_briefing_source": f"review_briefing_{route_id}.json" if inputs.get("briefing") else None,
        "g13_decisions_source": f"review_decisions_{route_id}.json" if inputs.get("decisions") else None,
        "gpx_source": f"rwgps_{route_id}.gpx" if inputs.get("gpx") else None,
        "gpx_points": inputs.get("gpx", {}).get("n", 0) if inputs.get("gpx") else 0,
        "hint_count": len(hints),
        "hints": hints,
        "generated_at": _iso_now(),
        "generator": "g14_reroute_hints.py",
    }


def build_md_output(route_id: str, inputs: dict, hints: list[dict], mode: str) -> str:
    lines = []
    route_name = inputs.get("route_name", "?")
    distance_km = inputs.get("distance_km", 0)

    lines.append(f"# Reroute Hints: {route_name}")
    lines.append("")
    lines.append(f"**Route ID:** {route_id}")
    lines.append(f"**Distance:** {distance_km:.2f} km")
    lines.append(f"**Mode:** {mode}")
    lines.append(f"**Generated:** {_iso_now()}")
    lines.append("")

    lines.append("## 📋 Podsumowanie")
    lines.append("")
    lines.append(f"| Kategoria | Liczba |")
    lines.append(f"|-----------|--------|")
    lines.append(f"| Total hints | {len(hints)} |")
    manual = sum(1 for h in hints if h.get("manual_override"))
    critical = sum(1 for h in hints if h.get("severity") == "critical")
    requires_router = sum(1 for h in hints if h.get("requires_router"))
    lines.append(f"| Manual confirmed | {manual} |")
    lines.append(f"| Critical | {critical} |")
    lines.append(f"| Requires router | {requires_router} |")
    lines.append("")

    if not hints:
        lines.append("✅ **Brak segmentów wymagających reroute hints.**")
        lines.append("")

    for h in hints:
        lines.append(f"## 🚧 {h['hint_id']}")
        lines.append("")
        lines.append(f"| Pole | Wartość |")
        lines.append(f"|------|---------|")
        lines.append(f"| Problem ID | {h['problem_id']} |")
        lines.append(f"| KM zakres | {h['start_km']:.1f} – {h['end_km']:.1f} |")
        lines.append(f"| Długość | {h['length_km']:.2f} km |")
        lines.append(f"| Severity | {h['severity']} |")
        lines.append(f"| Score | {h['final_score']:.2f} |")
        lines.append(f"| Decyzja | {h['decision']} |")
        lines.append(f"| Ręcznie potwierdzony | {'✅' if h['manual_override'] else '✗'} |")
        lines.append(f"| Ryzyko | {h['risk_type']} |")
        lines.append(f"| Powód | {h['reason']} |")
        lines.append(f"| **Start anchor** | km {h['start_anchor_km']:.2f} |")
        lines.append(f"| Start koordynaty | {h['start_anchor_lat']}, {h['start_anchor_lng']} |")
        lines.append(f"| Start GPX index | {h['start_anchor_gpx_idx']} |")
        lines.append(f"| **End anchor** | km {h['end_anchor_km']:.2f} |")
        lines.append(f"| End koordynaty | {h['end_anchor_lat']}, {h['end_anchor_lng']} |")
        lines.append(f"| End GPX index | {h['end_anchor_gpx_idx']} |")
        lines.append(f"| Anchor buffer | {h['anchor_buffer_km']} km |")
        lines.append(f"| Strategy | {h['strategy']} |")
        lines.append(f"| Wymaga routera | {'✅' if h['requires_router'] else '✗'} |")
        lines.append(f"| Estimated detour | {h['estimated_detour_status']} |")
        lines.append(f"| Sugerowany next step | {h['suggested_next_step']} |")
        lines.append("")

    lines.append("## ⚠️ Warning")
    lines.append("")
    lines.append("G14 MVP **nie wylicza jeszcze realnej alternatywy** — przygotowuje punkty anchorowe do Brouter/Valhalla. "
                  "Rzeczywisty rerouting będzie wymagał G14B (Brouter/Valhalla integration).")
    lines.append("")
    lines.append("---")
    lines.append(f"*Hints wygenerowane przez G14 — {_iso_now()}*")

    return "\n".join(lines)


# ── Main Pipeline ─────────────────────────────────────────────────────────

def run_reroute(route_id: str, mode: str = "dry-run") -> dict:
    rid = str(route_id)
    print(f"  Loading inputs for {rid}...")

    inputs = load_inputs(rid)
    if not inputs.get("gpx"):
        return {"ok": False, "status": "ERROR", "error": f"GPX not found for {rid}"}
    if not inputs.get("briefing"):
        return {"ok": False, "status": "ERROR", "error": f"G13 briefing not found for {rid}"}

    route_name = inputs.get("route_name", "")
    distance_km = inputs.get("distance_km", 0)
    print(f"  Route: {route_name} ({distance_km:.2f} km)")
    print(f"  GPX points: {inputs['gpx']['n']}")

    hints = generate_hints(inputs)
    print(f"  Hints generated: {len(hints)}")

    for h in hints:
        print(f"    {h['hint_id']}: km {h['start_km']:.1f}–{h['end_km']:.1f} "
              f"| {h['severity']} | decision={h['decision']} | strategy={h['strategy']}")

    json_out = build_json_output(rid, inputs, hints, mode)
    md_out = build_md_output(rid, inputs, hints, mode)

    if mode == "build":
        json_path = ARTIFACTS_REROUTE / f"reroute_hints_{rid}.json"
        md_path = ARTIFACTS_REROUTE / f"reroute_hints_{rid}.md"

        _write_json(json_path, json_out)
        _write_md(md_path, md_out)

        print(f"  Output written:")
        print(f"    JSON: {json_path}")
        print(f"    MD:   {md_path}")

    return json_out


def main():
    p = argparse.ArgumentParser(description="G14 Reroute Hints dla Gravel Intelligence")
    p.add_argument("--route-id", required=True, help="Garmin route ID")
    p.add_argument("--mode", choices=["dry-run", "build"], default="dry-run")
    args = p.parse_args()

    print("=" * 70)
    print("G14 Reroute Hints")
    print("=" * 70)
    print(f"  Route ID: {args.route_id}")
    print(f"  Mode:     {args.mode}")
    print()

    result = run_reroute(args.route_id, mode=args.mode)

    if not result.get("ok"):
        print(f"  ERROR: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    hints = result.get("hints", [])
    print()
    print(f"  Total hints: {len(hints)}")
    manual = sum(1 for h in hints if h.get("manual_override"))
    critical = sum(1 for h in hints if h.get("severity") == "critical")
    router = sum(1 for h in hints if h.get("requires_router"))
    print(f"    Manual confirmed: {manual}")
    print(f"    Critical: {critical}")
    print(f"    Requires router: {router}")

    if args.mode == "dry-run":
        print()
        print("  DRY RUN — no files written. Use --mode build to persist.")
    else:
        print()
        print("  Build complete.")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
