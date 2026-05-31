#!/usr/bin/env python3
"""G11 — Weather Modifier / Open-Meteo dla Gravel Intelligence.

Wczytuje output G10 (g10_surface_{route_id}.json), pobiera dane opadowe
z Open-Meteo, modyfikuje scoring i zapisuje g11_weather_surface_{route_id}.

Usage:
    .venv/bin/python scripts/g11_weather_modifier.py --route-id 55401067
    .venv/bin/python scripts/g11_weather_modifier.py --route-id 55401067 --date 2026-05-31
    .venv/bin/python scripts/g11_weather_modifier.py --routes 55401067,55395119
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
SURFACE_DIR = ARTIFACTS_DIR / "surface"
sys.path.insert(0, str(APP_DIR))

from lib.weather_modifier import (
    fetch_open_meteo_precipitation,
    apply_weather_to_samples,
    aggregate_weather_stats,
    route_centroid,
)


CATEGORY_ORDER = ["asphalt", "gravel", "compacted", "dirt", "sand", "grass", "unpaved_track", "unknown"]
CATEGORY_LABELS = {
    "asphalt": "Asfalt / utwardzona", "gravel": "Gravel / szuter",
    "compacted": "Ubita / stabilizowana", "dirt": "Ziemia / grunt",
    "sand": "Piasek", "grass": "Trawa",
    "unpaved_track": "Nieutwardzona / inna",
    "unknown": "Nieznana",
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _parse_gpx_points(gpx_path: Path) -> list[list[float]]:
    import xml.etree.ElementTree as ET
    ns = "http://www.topografix.com/GPX/1/1"
    tree = ET.parse(str(gpx_path))
    root = tree.getroot()
    points = []
    for trkpt in root.iter(f"{{{ns}}}trkpt"):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat and lon:
            points.append([float(lat), float(lon)])
    return points


def run_single(route_id: str, target_date: str | None = None, force: bool = False) -> dict | None:
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] G11 weather modifier: route_id={route_id}")

    # 1. Read G10 output
    g10_path = SURFACE_DIR / f"g10_surface_{route_id}.json"
    if not g10_path.exists():
        print(f"  ✗ G10 output not found: {g10_path}")
        return None

    g10 = _read_json(g10_path)
    if not g10 or not g10.get("ok"):
        print(f"  ✗ G10 output invalid")
        return None

    samples = g10.get("samples", [])
    if not samples:
        print(f"  ✗ No samples in G10 output")
        return None

    print(f"  Read G10: {len(samples)} samples, route={g10.get('route_name','?')}")

    # 2. Get GPX points for centroid
    gpx_path = ARTIFACTS_DIR / "exports" / "rwgps" / f"rwgps_{route_id}.gpx"
    points = []
    if gpx_path.exists():
        points = _parse_gpx_points(gpx_path)
    centroid = route_centroid(points)
    print(f"  Centroid: {centroid[0]:.4f}, {centroid[1]:.4f} ({len(points)} GPX pts)")

    # 3. Fetch weather
    td = target_date or date.today().isoformat()
    print(f"  Fetching Open-Meteo precipitation for {td}...")
    weather = fetch_open_meteo_precipitation(
        latitude=centroid[0],
        longitude=centroid[1],
        target_date=td,
        past_days=7,
        forecast_days=3,
    )

    sc = weather.get("soil_condition", "unknown")
    p7 = weather.get("precipitation_7d_total_mm", "?")
    f3 = weather.get("forecast_3d_total_mm", "?")
    note = weather.get("note", "")
    print(f"  Weather: {sc}, precip_7d={p7}mm, forecast_3d={f3}mm")
    print(f"  Note: {note}")

    # 4. Apply weather modifier
    modified = apply_weather_to_samples(samples, weather)
    stats = aggregate_weather_stats(modified)
    print(f"  Stats: avg_base={stats['avg_base_score']}, avg_weather={stats['avg_weather_score']}")
    print(f"  Changed: {stats['samples_changed']} ({stats['samples_increased']}↑, {stats['samples_decreased']}↓)")

    # 5. Build output
    route_name = g10.get("route_name", f"Route {route_id}")
    result = {
        "ok": True,
        "status": "OK",
        "route_id": route_id,
        "route_name": route_name,
        "source": "g11_weather_modifier",
        "g10_source": g10.get("generator", "g10_osm_cascade_scoring"),
        "target_date": td,
        "weather": weather,
        "weather_stats": stats,
        "modified_samples": modified,
        "generated_at": _iso_now(),
        "generator": "g11_weather_modifier.py",
    }

    # Write output
    out_json = SURFACE_DIR / f"g11_weather_surface_{route_id}.json"
    out_md = SURFACE_DIR / f"g11_weather_surface_{route_id}.md"
    _write_json(out_json, result)
    _write_md(out_md, result)

    print(f"  Output: {out_json}")
    return result


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Redact samples list for size (keep summary, drop per-sample in MD)
    write_data = {k: v for k, v in data.items() if k != "modified_samples"}
    write_data["sample_count"] = len(data.get("modified_samples", []))
    path.write_text(json.dumps(write_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_md(path: Path, result: dict) -> None:
    weather = result.get("weather", {})
    stats = result.get("weather_stats", {})
    samples = result.get("modified_samples", [])
    route_id = result["route_id"]
    route_name = result.get("route_name", "?")

    lines = [
        f"# G11 — Weather Modifier — {route_name}",
        f"",
        f"- **Route ID:** {route_id}",
        f"- **Target date:** {result.get('target_date', '?')}",
        f"- **Weather condition:** {weather.get('soil_condition', '?')}",
        f"- **Opady 7d:** {weather.get('precipitation_7d_total_mm', '?')} mm",
        f"- **Prognoza 3d:** {weather.get('forecast_3d_total_mm', '?')} mm",
        f"- **Nota:** {weather.get('note', '')}",
        f"",
        f"## Porównanie base_score vs weather_score",
        f"",
        f"| Metryka | Wartość |",
        f"|---|---|",
        f"| Avg base score | {stats.get('avg_base_score', '?')} |",
        f"| Avg weather score | {stats.get('avg_weather_score', '?')} |",
        f"| Avg multiplier | {stats.get('avg_multiplier', '?')} |",
        f"| Samples changed | {stats.get('samples_changed', '?')} |",
        f"| Increased (↑) | {stats.get('samples_increased', '?')} |",
        f"| Decreased (↓) | {stats.get('samples_decreased', '?')} |",
        f"| Soil condition | {stats.get('soil_condition', '?')} |",
        f"",
        f"## Próbki najbardziej zmienione przez pogodę (top 10)",
        f"",
        f"| # | km | base | weather | mult | surface | highway | powód |",
        f"|---|---|---|---|---|---|---|---|",
    ]

    # Sort by absolute multiplier difference
    sorted_samples = sorted(
        samples,
        key=lambda s: abs((s.get("weather_multiplier") or 1.0) - 1.0),
        reverse=True,
    )[:10]

    # Approximate km for each sample
    total_km = g10_distance(result.get("g10_source", ""), route_id) or 80
    km_per = total_km / max(1, len(samples))

    for i, s in enumerate(sorted_samples):
        approx_km = round(i * km_per, 1)
        base = s.get("base_score", "?")
        ws = s.get("weather_score", "?")
        mult = s.get("weather_multiplier", 1.0)
        surf = (s.get("best_tags") or {}).get("surface", "-")
        hw = (s.get("best_tags") or {}).get("highway", "-")
        reason = s.get("weather_note", "")[:60]
        base_str = f"{base:.2f}" if isinstance(base, float) else str(base)
        ws_str = f"{ws:.2f}" if isinstance(ws, float) else str(ws)
        lines.append(f"| {i + 1} | {approx_km} | {base_str} | {ws_str} | {mult:.2f} | {surf} | {hw} | {reason} |")

    lines.extend([
        "",
        "---",
        f"*Raport wygenerowany przez g11_weather_modifier.py — {_iso_now()}*",
    ])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def g10_distance(source: str, route_id: str) -> float | None:
    g10 = _read_json(SURFACE_DIR / f"g10_surface_{route_id}.json")
    if g10:
        return g10.get("distance_km")
    return None


def main():
    parser = argparse.ArgumentParser(description="G11 Weather Modifier for Gravel Intelligence")
    parser.add_argument("--route-id", help="Single route_id")
    parser.add_argument("--routes", help="Comma-separated route_ids")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--force", action="store_true", default=False)
    args = parser.parse_args()

    route_ids = []
    if args.route_id:
        route_ids = [args.route_id.strip()]
    elif args.routes:
        route_ids = [r.strip() for r in args.routes.split(",") if r.strip()]
    else:
        parser.print_help()
        sys.exit(1)

    print("=" * 70)
    print("G11 — Weather Modifier / Open-Meteo")
    print("=" * 70)

    for rid in route_ids:
        run_single(rid, target_date=args.date, force=args.force)

    print(f"\n{'='*70}")
    print("G11 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
