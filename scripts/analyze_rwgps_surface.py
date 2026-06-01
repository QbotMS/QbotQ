#!/usr/bin/env python3
"""CLI surface analyzer for any RWGPS route.

Orchestrates: export GPX artifact → parse geometry → surface analysis via
Overpass (OSM tags).  Generates JSON + MD artifacts per route.

Usage:
  .venv/bin/python scripts/analyze_rwgps_surface.py --route-id 55401067 --project-id tuscany_2026
  .venv/bin/python scripts/analyze_rwgps_surface.py --route-id 55395119 --project-id tuscany_2026 --force-export
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
sys.path.insert(0, str(APP_DIR))


def _hms(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def analyze_rwgps_surface_route(
    route_id: str,
    project_id: str = "tuscany_2026",
    force_export: bool = False,
    refresh_overpass: bool = False,
    segment_km: float = 10.0,
    sample_distance_m: int = 500,
    output_prefix: str | None = None,
) -> dict[str, Any]:
    """Run surface analysis for an RWGPS route and return result dict.

    Pipeline: ensure GPX artifact → parse geometry → surface via Overpass →
    generate JSON/MD artifacts.

    Returns the output dict with keys: ok, status, route_id, route_name,
    geometry, surface, highway, overpass, json_path, md_path, warnings, etc.
    """
    prefix = output_prefix or f"rwgps_{route_id}"
    ts_start = datetime.now(timezone.utc)

    project_dir = ARTIFACTS_DIR / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    json_path = project_dir / f"{prefix}_surface_analysis.json"
    md_path = project_dir / f"{prefix}_surface_analysis.md"

    # ── Step 1: Ensure GPX artifact exists ────────────────────
    gpx_path = ARTIFACTS_DIR / "exports" / "rwgps" / f"rwgps_{route_id}.gpx"
    export_needed = False

    if not gpx_path.exists() or force_export:
        from tools.rwgps.client import export_route_to_artifact
        export_result = export_route_to_artifact(route_id, fmt="gpx")
        if not export_result.get("ok"):
            error_output = {
                "ok": False, "status": "EXPORT_FAILED",
                "route_id": route_id, "error": export_result.get("error"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "json_path": str(json_path), "md_path": str(md_path),
            }
            json_path.write_text(json.dumps(error_output, indent=2, ensure_ascii=False), encoding="utf-8")
            md_path.write_text(f"# Surface analysis FAILED\n\nExport route {route_id}: {export_result.get('error')}\n", encoding="utf-8")
            return error_output
        export_needed = True

    # ── Step 2: Parse geometry ────────────────────────────────
    from tools.rwgps.client import parse_gpx_artifact_geometry
    geometry = parse_gpx_artifact_geometry(route_id=route_id)
    if not geometry.get("ok"):
        error_output = {
            "ok": False, "status": "GEOMETRY_FAILED",
            "route_id": route_id,
            "error": f"{geometry.get('status')} – {geometry.get('error')}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "json_path": str(json_path), "md_path": str(md_path),
        }
        json_path.write_text(json.dumps(error_output, indent=2, ensure_ascii=False), encoding="utf-8")
        return error_output

    point_count = geometry.get("point_count", 0)
    distance_km = geometry.get("distance_km", 0)
    elev_gain = geometry.get("elevation_gain_m")
    elev_loss = geometry.get("elevation_loss_m")
    bbox = geometry.get("bbox", {})
    route_name = geometry.get("route_id", str(route_id))

    # ── Step 3: Surface analysis via Overpass ─────────────────
    if refresh_overpass:
        import hashlib
        sha = hashlib.sha256(gpx_path.read_bytes()).hexdigest()
        cache_name = f"surface_{gpx_path.stem}_{sample_distance_m}m.json"
        cache_path = ARTIFACTS_DIR / "analysis" / cache_name
        if cache_path.exists():
            cache_path.unlink()

    from mcp_server import analyze_rwgps_artifact_surface
    raw_surface = analyze_rwgps_artifact_surface(str(gpx_path), sample_distance_m=sample_distance_m)
    surface = json.loads(raw_surface)

    if not surface.get("ok"):
        error_output = {
            "ok": False, "status": "SURFACE_FAILED",
            "route_id": route_id,
            "error": surface.get("error"), "reason": surface.get("reason", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "json_path": str(json_path), "md_path": str(md_path),
        }
        json_path.write_text(json.dumps(error_output, indent=2, ensure_ascii=False), encoding="utf-8")
        return error_output

    surf_pct = surface.get("surface_percentages", {})
    hw_pct = surface.get("road_type_percentages", {})
    tt_pct = surface.get("tracktype_percentages", {})
    sm_pct = surface.get("smoothness_summary", {})
    dominant = surface.get("dominant_surface", "?")
    matched = surface.get("matched_points", 0)
    unmatched = surface.get("unmatched_points", 0)
    total_samples = surface.get("sampled_points", 0)
    coverage = surface.get("coverage_pct", 0)
    confidence = surface.get("confidence", "low")
    warnings_list = surface.get("warnings") or []

    paved = sum(v for k, v in surf_pct.items() if k in ("asfalt", "beton", "kostka brukowa", "kocie łby"))
    gravel_sum = sum(v for k, v in surf_pct.items() if k in ("gravel/żwir", "gravel drobny", "ubita nawierzchnia"))
    dirt = sum(v for k, v in surf_pct.items() if k in ("ziemia/grunt", "nieutwardzona", "grunt", "piasek", "trawa"))
    unknown = surf_pct.get("nieznana", 0)

    # ── Step 4: Build output ──────────────────────────────────
    ts_end = datetime.now(timezone.utc)
    duration_s = (ts_end - ts_start).total_seconds()

    output: dict[str, Any] = {
        "ok": True,
        "status": "OK",
        "route_id": route_id,
        "route_name": route_name,
        "project_id": project_id,
        "gpx_path": str(gpx_path),
        "gpx_bytes": gpx_path.stat().st_size,
        "config": {
            "sample_distance_m": sample_distance_m,
            "segment_km": segment_km,
            "force_export": force_export,
            "refresh_overpass": refresh_overpass,
        },
        "geometry": {
            "point_count": point_count,
            "distance_km": distance_km,
            "elevation_gain_m": elev_gain,
            "elevation_loss_m": elev_loss,
            "bbox": bbox,
        },
        "surface_breakdown": surf_pct,
        "dominant_surface": dominant,
        "practical_groups": {
            "paved_pct": round(paved, 1),
            "gravel_pct": round(gravel_sum, 1),
            "dirt_pct": round(dirt, 1),
            "unknown_pct": round(unknown, 1),
        },
        "unknown_percent": round(unknown, 1),
        "highway_breakdown": hw_pct,
        "tracktype": tt_pct,
        "smoothness": sm_pct,
        "overpass": {
            "sampled_points": total_samples,
            "matched_points": matched,
            "unmatched_points": unmatched,
            "coverage_pct": coverage,
            "confidence": confidence,
            "cache_hit": surface.get("cache_hit", False),
        },
        "warnings": warnings_list,
        "limitations": [
            "Dane OSM mogą być niekompletne dla dróg gruntowych/leśnych",
            f"Próbkowanie co {sample_distance_m}m może pominąć krótkie odcinki",
            "Najbliższa droga OSM w promieniu 150m — nie zawsze faktyczna droga na trasie",
        ],
        "recommendation": _build_recommendation(paved, gravel_sum, dirt, unknown),
        "export_needed": export_needed,
        "duration_s": round(duration_s, 1),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "generated_at": ts_end.isoformat(),
    }

    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── MD output ─────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"# Analiza nawierzchni — route_id={route_id}")
    lines.append("")
    lines.append(f"- **Route:** {route_name}")
    lines.append(f"- **Route ID:** {route_id}")
    lines.append(f"- **GPX:** {gpx_path}")
    lines.append(f"- **Punkty:** {point_count}")
    lines.append(f"- **Dystans:** {distance_km} km")
    lines.append(f"- **Przewyższenie:** +{elev_gain}/-{elev_loss} m")
    if bbox:
        lines.append(f"- **Bbox:** sw({bbox.get('sw_lat', '?')}, {bbox.get('sw_lng', '?')}) → ne({bbox.get('ne_lat', '?')}, {bbox.get('ne_lng', '?')})")
    lines.append(f"- **Próbkowanie:** co {sample_distance_m}m ({total_samples} pts)")
    lines.append(f"- **Overpass:** {matched} matched / {unmatched} unmatched ({coverage}% coverage)")
    lines.append(f"- **Ufność:** {confidence}")
    lines.append(f"- **Czas analizy:** {_hms(duration_s)}")
    lines.append("")

    lines.append("## Podsumowanie praktyczne")
    lines.append("")
    lines.append(f"**Asfalt≈{paved:.0f}% / Gravel≈{gravel_sum:.0f}% / Grunt≈{dirt:.0f}% / Nieznana≈{unknown:.0f}%**")
    lines.append("")
    lines.append("| Grupa | % | Opis |")
    lines.append("|-------|---|------|")
    lines.append(f"| Asfalt/beton | {paved:.0f}% | Drogi utwardzone — optymalne dla szosy/gravela |")
    lines.append(f"| Gravel/żwir/ubita | {gravel_sum:.0f}% | Dobre dla gravela, możliwe dla szosy z ostrożnością |")
    lines.append(f"| Grunt/nieutwardzona | {dirt:.0f}% | Wymaga gravela/MTB, może być ciężko po deszczu |")
    lines.append(f"| Nieznana | {unknown:.0f}% | Brak danych OSM — sprawdzić lokalnie |")
    lines.append("")

    lines.append("## Rekomendacja")
    lines.append("")
    lines.append(output["recommendation"])
    lines.append("")

    lines.append("## Nawierzchnia (surface tag)")
    lines.append("")
    lines.append("| Typ | % |")
    lines.append("|-----|---|")
    for k, v in sorted(surf_pct.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v}% |")
    lines.append("")

    lines.append("## Typ drogi (highway)")
    lines.append("")
    lines.append("| Typ | % |")
    lines.append("|-----|---|")
    for k, v in sorted(hw_pct.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v}% |")
    lines.append("")

    if tt_pct:
        lines.append("## Tracktype (grade)")
        lines.append("")
        lines.append("| Grade | % |")
        lines.append("|-------|---|")
        for k, v in sorted(tt_pct.items(), key=lambda x: -x[1]):
            lines.append(f"| grade{k} | {v}% |")
        lines.append("")

    if sm_pct:
        lines.append("## Gładkość (smoothness)")
        lines.append("")
        lines.append("| Poziom | % |")
        lines.append("|--------|---|")
        for k, v in sorted(sm_pct.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v}% |")
        lines.append("")

    if warnings_list:
        lines.append("## Ostrzeżenia")
        lines.append("")
        for w in warnings_list:
            lines.append(f"- ⚠ {w}")
        lines.append("")

    lines.append("## Ograniczenia")
    lines.append("")
    for i, lim in enumerate(output["limitations"], 1):
        lines.append(f"{i}. {lim}")
    lines.append(f"4. Niektóre batch Overpass mogą zwrócić 429 — dane są wtedy niekompletne")
    lines.append("")

    lines.append("---")
    lines.append(f"*Wygenerowano: {ts_end.isoformat()} | analyze_rwgps_surface.py*")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return output


def main():
    parser = argparse.ArgumentParser(description="Surface analysis for RWGPS route")
    parser.add_argument("--route-id", required=True, help="RWGPS route ID")
    parser.add_argument("--project-id", default="tuscany_2026")
    parser.add_argument("--force-export", action="store_true", default=False,
                        help="Re-export GPX even if already cached")
    parser.add_argument("--refresh-overpass", action="store_true", default=False,
                        help="Ignore Overpass cache and re-fetch")
    parser.add_argument("--segment-km", type=float, default=10.0,
                        help="Segment size in km (used for track breakdown)")
    parser.add_argument("--sample-distance-m", type=int, default=500,
                        help="Sample spacing in meters for surface analysis")
    parser.add_argument("--output-prefix", default=None,
                        help="Custom prefix for output files")
    args = parser.parse_args()

    result = analyze_rwgps_surface_route(
        route_id=args.route_id,
        project_id=args.project_id,
        force_export=args.force_export,
        refresh_overpass=args.refresh_overpass,
        segment_km=args.segment_km,
        sample_distance_m=args.sample_distance_m,
        output_prefix=args.output_prefix,
    )

    if result.get("ok"):
        print(f"\n{'='*60}")
        print(f"SURFACE ANALYSIS COMPLETE — route_id={args.route_id}")
        print(f"  JSON: {result.get('json_path')}")
        print(f"  MD:   {result.get('md_path')}")
        print(f"  Duration: {result.get('duration_s', '?')}s")
        print(f"  {result.get('surface', {}).get('summary_short', '')}")
        print(f"{'='*60}")
    else:
        print(f"\nSURFACE ANALYSIS FAILED: {result.get('error', 'unknown')}")
        sys.exit(1)


def _build_recommendation(paved: float, gravel: float, dirt: float, unknown: float) -> str:
    if paved >= 70:
        return "Trasa szosowa — dominuje asfalt. Rowerek szosowy w pełni wystarczy."
    if paved >= 40:
        return "Trasa mieszana — sporo asfaltu, ale też odcinki nieutwardzone. Gravel zalecany, szosa możliwa z ostrożnością."
    if gravel >= 30:
        return "Trasa gravelowa — dominują drogi szutrowe/gruntowe. Gravel idealny, MTB też OK."
    if dirt >= 40:
        return "Trasa terenowa — dużo dróg gruntowych/leśnych. MTB zalecany, gravel może być wymagający."
    if unknown >= 50:
        return "Dużo dróg bez danych nawierzchni w OSM — zalecany gravel/MTB, sprawdzić lokalnie przed wyjazdem."
    return "Trasa zróżnicowana. Gravel lub MTB zalecany."


if __name__ == "__main__":
    main()
