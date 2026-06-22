#!/usr/bin/env python3
"""Gravel Intelligence — Warning/POI GPX Builder for Hammerhead/Karoo.

Combines risk segments + optional POI into a single GPX import file.
Default mode is G6 (human-readable descriptions, Karoo-optimized names).

Usage:
  .venv/bin/python scripts/g3_build_gravel_import_gpx.py --route-id 55401067 --mode build
  .venv/bin/python scripts/g3_build_gravel_import_gpx.py --route-id 55395119 --mode dry-run
  .venv/bin/python scripts/g3_build_gravel_import_gpx.py --route-id 55401067 --mode build --output-prefix g6_test
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
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
sys.path.insert(0, str(APP_DIR))

GPX_NS = "http://www.topografix.com/GPX/1/1"
GPX_DIR = ARTIFACTS_DIR / "gravel"

MAX_WARNINGS_DEFAULT = 8
MAX_WARNINGS_G5 = 6
MAX_WARNINGS_G5_RISKY = 8

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "⚪"}

WARNING_FORMAT: dict[str, dict] = {
    "sand":           {"label": "Piasek",       "min_severity": "medium"},
    "grass":          {"label": "Trawa/łąka",   "min_severity": "medium"},
    "gravel_rough":   {"label": "Szorstki gravel", "min_severity": "medium"},
    "dirt":           {"label": "Grunt",        "min_severity": "high",   "min_km": 1.0},
    "unpaved_track":  {"label": "Nieutwardzona","min_severity": "high",   "min_km": 1.0},
    "unknown_long":   {"label": "Brak danych",   "min_severity": "high",   "min_km": 3.0},
    "mixed_bad":      {"label": "Mieszana zła",  "min_severity": "medium"},
}

CATEGORY_LABELS: dict[str, str] = {
    "asphalt": "Asfalt", "gravel": "Gravel", "compacted": "Ubita",
    "dirt": "Grunt", "sand": "Piasek", "grass": "Trawa",
    "unpaved_track": "Nieutwardzona", "unknown": "Nieznana",
}

G5_SHORT_NAMES: dict[str, str] = {
    "sand":           "PIACH",
    "grass":          "TRAWA",
    "gravel_rough":   "SZUTER?",
    "dirt":           "GRUNT",
    "unpaved_track":  "TRACK",
    "unknown_long":   "UNKNOWN",
    "mixed_bad":      "MIESZ.",
}

SURFACE_RISK_PRIORITY: dict[str, int] = {
    "sand": 0,
    "grass": 1,
    "unpaved_track": 2,
    "dirt": 3,
    "gravel_rough": 4,
    "mixed_bad": 5,
}

DATA_RISK_TYPES = {"unknown_long"}

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _hms(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


# ── Loaders ─────────────────────────────────────────────────────────────────

def load_risk_segments(path: str | Path) -> tuple[list[dict], dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"risk_segments not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    meta = {k: data[k] for k in ("route_id", "route_name", "distance_km", "num_segments",
                                  "total_risk_km", "high_risk_km", "medium_risk_km") if k in data}
    return data.get("segments", []), meta


def load_poi_buffer(path: str | None) -> list[dict]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"poi_buffer not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    pois = data.get("pois", [])
    # Filter to accepted confidence
    return [poi for poi in pois if poi.get("confidence") in ("high", "medium")]


def load_track_points(route_id: str) -> list[dict]:
    """Load track_points from GPX artifact."""
    gpx_path = ARTIFACTS_DIR / "exports" / "rwgps" / f"rwgps_{route_id}.gpx"
    if not gpx_path.exists():
        from tools.rwgps.client import export_route_to_artifact
        result = export_route_to_artifact(route_id, fmt="gpx")
        if not result.get("ok"):
            raise RuntimeError(f"export failed: {result.get('error', 'unknown')}")
    tree = ET.parse(str(gpx_path))
    root = tree.getroot()
    ns = {"gpx": GPX_NS}
    points: list[dict] = []
    for trkpt in root.findall(".//gpx:trkpt", ns):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat and lon:
            p = {"lat": float(lat), "lon": float(lon)}
            ele_el = trkpt.find("gpx:ele", ns)
            if ele_el is not None and ele_el.text:
                p["ele"] = float(ele_el.text)
            points.append(p)
    if not points:
        raise ValueError(f"No track points in GPX for {route_id}")
    return points


# ── Warning selection ───────────────────────────────────────────────────────

def select_warnings(segments: list[dict], max_warnings: int = MAX_WARNINGS_DEFAULT) -> list[dict]:
    selected: list[dict] = []
    skipped: list[dict] = []

    for seg in segments:
        risk_type = seg.get("risk_type", "")
        severity = seg.get("severity", "low")
        length_km = seg.get("length_km", 0)
        fmt = WARNING_FORMAT.get(risk_type, {"min_severity": "high", "min_km": 0})

        # Check min severity
        sev_order = {"low": 0, "medium": 1, "high": 2}
        if sev_order.get(severity, 0) < sev_order.get(fmt.get("min_severity", "high"), 2):
            skipped.append(seg)
            continue

        # Check min length for some types
        min_km = fmt.get("min_km", 0)
        if length_km < min_km:
            skipped.append(seg)
            continue

        selected.append(seg)

    # Sort: high first, then by length desc
    selected.sort(key=lambda s: (0 if s["severity"] == "high" else 1, -s["length_km"]))

    # Limit unknown_long to top 3
    unknown_high = [s for s in selected if s["risk_type"] == "unknown_long" and s["severity"] == "high"]
    other_high = [s for s in selected if not (s["risk_type"] == "unknown_long" and s["severity"] == "high")]
    if len(unknown_high) > 3:
        skipped.extend(unknown_high[3:])
        unknown_high = unknown_high[:3]
    selected = unknown_high + other_high

    # Cap at max_warnings
    if len(selected) > max_warnings:
        skipped.extend(selected[max_warnings:])
        selected = selected[:max_warnings]

    return selected


def build_warning_name(seg: dict) -> str:
    risk_type = seg.get("risk_type", "unknown")
    length_km = seg.get("length_km", 0)
    fmt = WARNING_FORMAT.get(risk_type, {"label": "Uwaga"})
    label = fmt["label"]
    return f"UWAGA: {label} {length_km:.1f}km"


def build_warning_desc(seg: dict) -> str:
    parts = []
    parts.append(f"km {seg.get('start_km', '?'):.1f}–{seg.get('end_km', '?'):.1f}")
    parts.append(f"naw: {CATEGORY_LABELS.get(seg.get('dominant_surface', ''), seg.get('dominant_surface', ''))}")
    parts.append(f"typ: {seg.get('risk_type', '?')}")
    parts.append(f"poziom: {seg.get('severity', '?')}")
    parts.append(f"ufność: {seg.get('confidence', '?')}")
    parts.append(f"powód: {seg.get('reason', '?')[:100]}")
    return " | ".join(parts)


# ── G5 Warning quality / Karoo readability helpers ────────────────────────────

SURFACE_RISK_PRIORITY_LIST = ["sand", "grass", "unpaved_track", "dirt", "gravel_rough", "mixed_bad"]


def format_warning_name_g5(seg: dict) -> str:
    risk_type = seg.get("risk_type", "unknown_long")
    short = G5_SHORT_NAMES.get(risk_type, "UWAGA")
    length_km = seg.get("length_km", 0)
    return f"{short} {length_km:.1f} km"


def format_warning_desc_g5(seg: dict) -> str:
    parts = []
    parts.append(f"km {seg.get('start_km', '?'):.1f}–{seg.get('end_km', '?'):.1f}")
    parts.append(f"risk_type={seg.get('risk_type', '?')}")
    parts.append(f"surface={CATEGORY_LABELS.get(seg.get('dominant_surface', ''), seg.get('dominant_surface', '?'))}")
    parts.append(f"severity={seg.get('severity', '?')}")
    parts.append(f"confidence={seg.get('confidence', '?')}")
    reason = seg.get("reason", "?")[:120]
    parts.append(f"reason={reason}")
    return " | ".join(parts)


def _is_very_risky_route(segments: list[dict]) -> bool:
    high_surface = [
        s for s in segments
        if s.get("risk_type") in SURFACE_RISK_PRIORITY
        and s.get("severity") == "high"
    ]
    total_risk_km = sum(s.get("length_km", 0) for s in segments if s.get("severity") == "high")
    return len(high_surface) >= 3 or total_risk_km >= 40


def select_warnings_for_karoo(segments: list[dict], max_warnings: int = MAX_WARNINGS_G5) -> list[dict]:
    high_only = [s for s in segments if s.get("severity") == "high"]

    surface_risk = [
        s for s in high_only
        if s.get("risk_type") in SURFACE_RISK_PRIORITY
        and s.get("length_km", 0) >= 1.0
    ]
    data_risk = [
        s for s in high_only
        if s.get("risk_type") in DATA_RISK_TYPES
        and s.get("length_km", 0) >= 3.0
    ]

    surface_risk.sort(key=lambda s: (
        SURFACE_RISK_PRIORITY.get(s.get("risk_type", ""), 99),
        -s.get("length_km", 0)
    ))

    data_risk.sort(key=lambda s: -s.get("length_km", 0))
    data_risk = data_risk[:3]

    selected = surface_risk + data_risk

    selected = merge_nearby_warnings_if_needed(selected, min_gap_km=1.0)

    if len(selected) > max_warnings:
        selected = selected[:max_warnings]

    return selected


def merge_nearby_warnings_if_needed(warnings: list[dict], min_gap_km: float = 1.0) -> list[dict]:
    if not warnings:
        return []

    by_start = sorted(warnings, key=lambda s: s.get("start_km", 0))
    merged: list[dict] = [by_start[0]]

    for w in by_start[1:]:
        prev = merged[-1]
        gap = w.get("start_km", 0) - prev.get("end_km", 0)

        if gap < min_gap_km and gap >= 0:
            prev_type = prev.get("risk_type", "")
            curr_type = w.get("risk_type", "")
            prev_is_surface = prev_type in SURFACE_RISK_PRIORITY
            curr_is_surface = curr_type in SURFACE_RISK_PRIORITY

            if prev_is_surface and not curr_is_surface:
                continue
            elif not prev_is_surface and curr_is_surface:
                merged[-1] = w
            else:
                if w.get("length_km", 0) > prev.get("length_km", 0):
                    merged[-1] = w
        else:
            merged.append(w)

    merged.sort(key=lambda s: (
        0 if s.get("risk_type") in SURFACE_RISK_PRIORITY else 1,
        SURFACE_RISK_PRIORITY.get(s.get("risk_type", ""), 99),
        -s.get("length_km", 0)
    ))

    return merged


# ── G6 Human-readable descriptions ────────────────────────────────────────────


def _surface_human(seg: dict) -> str:
    ds = seg.get("dominant_surface", "")
    mapping = {
        "dirt": "grunt/ziemia",
        "gravel": "szuter/gravel",
        "sand": "piasek",
        "grass": "trawa",
        "unpaved_track": "nieutwardzona",
        "asphalt": "asfalt",
        "compacted": "ubita",
        "unknown": "brak danych",
    }
    return mapping.get(ds, str(ds))


def _severity_human(sev: str) -> str:
    return {"high": "wysokie", "medium": "średnie", "low": "niskie"}.get(sev, sev)


def format_warning_desc_human(seg: dict) -> str:
    start = seg.get("start_km", 0)
    end = seg.get("end_km", 0)
    length = seg.get("length_km", 0)
    risk_type = seg.get("risk_type", "unknown_long")
    surface = _surface_human(seg)
    severity = _severity_human(seg.get("severity", "high"))

    prefix = f"km {start:.1f}–{end:.1f}."

    templates = {
        "dirt": (
            f"{prefix} {surface}, odcinek {length:.1f} km. "
            f"Ryzyko {severity} — możliwa wolniejsza jazda."
        ),
        "unpaved_track": (
            f"{prefix} Droga nieutwardzona/track, {length:.1f} km. "
            f"Ryzyko {severity}."
        ),
        "sand": (
            f"{prefix} Możliwy piach, odcinek {length:.1f} km. "
            f"Ryzyko {severity} — przygotuj niższą prędkość."
        ),
        "grass": (
            f"{prefix} Trawiasty odcinek {length:.1f} km. "
            f"Może być wolno po deszczu."
        ),
        "gravel_rough": (
            f"{prefix} Szorstki gravel, {length:.1f} km. "
            f"Ryzyko {severity}."
        ),
        "mixed_bad": (
            f"{prefix} Mieszana nawierzchnia, {length:.1f} km. "
            f"Ryzyko {severity}."
        ),
        "unknown_long": (
            f"{prefix} Brak danych OSM dla {length:.1f} km. "
            f"To ryzyko danych, nie potwierdzona zła nawierzchnia."
        ),
    }

    return templates.get(risk_type, f"{prefix} Odcinek {length:.1f} km. Ryzyko {severity}.")


# ── GPX Builder ─────────────────────────────────────────────────────────────

def build_gpx(track_points: list[dict], warnings: list[dict], pois: list[dict],
              route_name: str, g5_mode: bool = False, g6_mode: bool = False) -> str:
    lines: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(f'<gpx version="1.1" creator="QBot Gravel Intelligence" xmlns="{GPX_NS}">')
    lines.append("  <metadata>")
    lines.append(f"    <name>{escape(route_name)}</name>")
    lines.append(f"    <desc>Gravel Intelligence — {len(warnings)} warning(s), {len(pois)} POI(s)</desc>")
    lines.append(f"    <time>{ts}</time>")
    lines.append("  </metadata>")

    # Warning <wpt>
    for w in warnings:
        lat = w.get("representative_lat") or w.get("lat")
        lon = w.get("representative_lon") or w.get("lng") or w.get("lon")
        if g6_mode:
            name = format_warning_name_g5(w)
            desc = format_warning_desc_human(w)
            sym = {
                "high": "Alert",
                "medium": "Warning",
                "low": "Info",
            }.get(w.get("severity", ""), "Warning")
        elif g5_mode:
            name = format_warning_name_g5(w)
            desc = format_warning_desc_g5(w)
            sym = {
                "high": "Alert",
                "medium": "Warning",
                "low": "Info",
            }.get(w.get("severity", ""), "Warning")
        else:
            name = build_warning_name(w)
            desc = build_warning_desc(w)
            sym = "Warning"
        lines.append(f'  <wpt lat="{lat}" lon="{lon}">')
        lines.append(f"    <name>{escape(name)}</name>")
        lines.append(f"    <desc>{escape(desc)}</desc>")
        lines.append(f"    <type>{sym}</type>")
        lines.append(f"  </wpt>")

    # POI <wpt>
    for poi in pois:
        lat = poi.get("lat")
        lon = poi.get("lng") or poi.get("lon")
        name = str(poi.get("name", "POI"))[:60]
        cat = poi.get("category", "")
        dist = poi.get("distance_m") or poi.get("distance_to_track_m")
        rwgps_sym = poi.get("rwgps_sym", "Waypoint")
        desc_parts = []
        if cat:
            desc_parts.append(f"cat: {cat}")
        if dist is not None:
            desc_parts.append(f"dist: {float(dist):.0f}m")
        desc = " | ".join(desc_parts) if desc_parts else "QBot POI"
        lines.append(f'  <wpt lat="{lat}" lon="{lon}">')
        lines.append(f"    <name>{escape(name)}</name>")
        lines.append(f"    <desc>{escape(desc)}</desc>")
        lines.append(f"    <type>{escape(rwgps_sym)}</type>")
        lines.append(f"  </wpt>")

    # <trk>
    lines.append("  <trk>")
    lines.append(f"    <name>{escape(route_name)}</name>")
    lines.append("    <trkseg>")
    for tp in track_points:
        line = f'      <trkpt lat="{tp["lat"]}" lon="{tp["lon"]}">'
        if tp.get("ele") is not None:
            line += f"<ele>{tp['ele']}</ele>"
        line += "</trkpt>"
        lines.append(line)
    lines.append("    </trkseg>")
    lines.append("  </trk>")
    lines.append("</gpx>")

    return "\n".join(lines)


# ── Validation ──────────────────────────────────────────────────────────────

def validate_gpx(gpx_content: str) -> dict:
    try:
        root = ET.fromstring(gpx_content)
    except ET.ParseError as e:
        return {"valid": False, "error": str(e)}
    ns = {"gpx": GPX_NS}
    trkpts = root.findall(".//gpx:trkpt", ns)
    wpts = root.findall(".//gpx:wpt", ns)
    return {"valid": True, "trkpt_count": len(trkpts), "wpt_count": len(wpts)}


# ── Output ──────────────────────────────────────────────────────────────────

def output_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def output_md(path: Path, result: dict, all_segments: list[dict], selected: list[dict], skipped: list[dict],
              g5_mode: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Gravel Import — route_id={result.get('route_id', '?')}")
    lines.append("")
    if result.get("route_name"):
        lines.append(f"**Route:** {result['route_name']}")
    lines.append(f"**Dystans:** {result.get('distance_km', '?')} km")
    lines.append(f"**Warnings dostępne:** {len(all_segments)}")
    lines.append(f"**Warnings w GPX:** {result.get('warnings_in_gpx', 0)}")
    lines.append(f"**Warnings pominięte:** {result.get('warnings_skipped', 0)}")
    lines.append(f"**POI w GPX:** {result.get('poi_in_gpx', 0)}")
    lines.append(f"**GPX:** `{result.get('output_gpx_path', '?')}`")
    lines.append("")

    if selected:
        lines.append("## Warningi w GPX")
        lines.append("")
        lines.append("| # | km | Długość | Ryzyko | Poziom | Opis |")
        lines.append("|---|----|---------|--------|--------|------|")
        for i, w in enumerate(selected, 1):
            emoji = SEVERITY_EMOJI.get(w.get("severity", ""), "⚪")
            lines.append(
                f"| {i} | {w['start_km']:.1f}–{w['end_km']:.1f} | {w['length_km']:.1f} km | "
                f"{WARNING_FORMAT.get(w.get('risk_type', ''), {}).get('label', w.get('risk_type', '?'))} | "
                f"{emoji} {w['severity'].upper()} | "
                f"{w.get('reason', '')[:80]}"
            )
        lines.append("")

    if skipped:
        lines.append("## Warningi pominięte (zbyt niski poziom lub limit)")
        lines.append("")
        lines.append("| km | Długość | Ryzyko | Poziom | Przyczyna pominięcia |")
        lines.append("|----|---------|--------|--------|---------------------|")
        for s in skipped:
            emoji = SEVERITY_EMOJI.get(s.get("severity", ""), "⚪")
            risk_type = s.get("risk_type", "?")
            severity = s.get("severity", "?")
            # Determine skip reason
            fmt = WARNING_FORMAT.get(risk_type, {"min_severity": "high", "min_km": 0})
            sev_order = {"low": 0, "medium": 1, "high": 2}
            if sev_order.get(severity, 0) < sev_order.get(fmt.get("min_severity", "high"), 2):
                reason = f"próg severity ({fmt['min_severity']})"
            elif s.get("length_km", 0) < fmt.get("min_km", 0):
                reason = f"próg długości ({fmt['min_km']} km)"
            else:
                reason = "limit warningów"
            lines.append(
                f"| {s['start_km']:.1f}–{s['end_km']:.1f} | {s['length_km']:.1f} km | "
                f"{WARNING_FORMAT.get(risk_type, {}).get('label', risk_type)} | "
                f"{emoji} {severity.upper()} | {reason}"
            )
        lines.append("")

    if result.get("poi_in_gpx", 0) > 0:
        lines.append("## POI w GPX")
        lines.append("")
        for i, poi in enumerate(result.get("pois_in_gpx", []), 1):
            lines.append(f"{i}. **{poi.get('name', '?')}** — {poi.get('rwgps_sym', 'Waypoint')} — {poi.get('distance_m', '?')}m od trasy")
        lines.append("")

    lines.append("## Instrukcja importu")
    lines.append("")
    lines.append("1. **Pobierz GPX:**")
    lines.append("   ```bash")
    lines.append(f"   scp root@olga181:{result.get('output_gpx_path', '')} /tmp/")
    lines.append("   ```")
    lines.append("2. Otwórz **RideWithGPS.com → Route Planner**")
    lines.append("3. **Import → Upload File** → wybierz GPX")
    lines.append("4. **Add to Planner**")
    lines.append("5. **Save** (tworzy nową wersję trasy)")
    lines.append("6. **Pin** → **Hammerhead Sync** → **Karoo**")
    lines.append("")
    lines.append("## Weryfikacja po imporcie")
    lines.append("")
    lines.append(f"| Element | Oczekiwana liczba |")
    lines.append(f"|---------|-------------------|")
    lines.append(f"| Track points | {result.get('trkpt_count', '?')} |")
    lines.append(f"| Warningi na mapie | {result.get('warnings_in_gpx', 0)} |")
    lines.append(f"| POI na mapie | {result.get('poi_in_gpx', 0)} |")
    lines.append(f"| Dystans trasy | Bez zmian |")
    lines.append("")
    lines.append("---")
    lines.append(f"*Wygenerowano: {result.get('generated_at', '?')} | {result.get('mode', 'G6')}*")

    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gravel Intelligence GPX builder for Hammerhead/Karoo")
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--risk-segments", default=None,
                        help="Path to risk_segments JSON (default: auto from surface dir)")
    parser.add_argument("--poi-buffer", default=None, help="Optional poi_buffer JSON")
    parser.add_argument("--mode", choices=["dry-run", "build"], default="dry-run")
    parser.add_argument("--max-warnings", type=int, default=MAX_WARNINGS_DEFAULT)
    parser.add_argument("--g3", action="store_true", help="Legacy G3 mode: old names + technical desc")
    parser.add_argument("--g5", action="store_true", help="G5 debug mode: short names + technical desc")
    parser.add_argument("--g6", action="store_true", help="G6 mode: short names + human-readable desc (default)")
    parser.add_argument("--output-prefix", default=None,
                        help="Custom output prefix (e.g. g6_test → g6_test_gravel_import_55401067.gpx)")
    args = parser.parse_args()

    route_id = args.route_id
    mode = args.mode
    max_w = args.max_warnings

    # Determine mode: default = G6
    g3_mode = args.g3
    g5_mode = args.g5
    g6_mode = args.g6 or not (g3_mode or g5_mode)  # default to G6
    use_karoo_select = not g3_mode  # G3 uses old select, everything else uses Karoo select
    use_human_desc = g6_mode
    use_short_names = not g3_mode  # G3 uses old names, everything else uses short names

    ts_start = datetime.now(timezone.utc)

    risk_path = args.risk_segments or str(ARTIFACTS_DIR / "surface" / f"risk_segments_{route_id}.json")

    label = "G6" if g6_mode else ("G5" if g5_mode else "G3")
    print(f"[{ts_start.isoformat()}] {label} gravel import builder: route_id={route_id} mode={mode}")

    # 1. Load risk segments
    print("  [1/5] Loading risk segments...")
    all_segments, risk_meta = load_risk_segments(risk_path)
    route_name = risk_meta.get("route_name", f"Route {route_id}")
    total_risk_km = sum(s.get("length_km", 0) for s in all_segments if s.get("severity") == "high")
    print(f"    {len(all_segments)} segments available, route: {route_name}")

    # 2. Select warnings
    if use_karoo_select:
        very_risky = _is_very_risky_route(all_segments)
        max_w = MAX_WARNINGS_G5_RISKY if very_risky else MAX_WARNINGS_G5
        print(f"  [2/5] Selecting warnings (Karoo mode, max {max_w})...")
        selected = select_warnings_for_karoo(all_segments, max_w)
        skipped = [s for s in all_segments if s not in selected]
    else:
        print(f"  [2/5] Selecting warnings (G3 legacy, max {max_w})...")
        selected = select_warnings(all_segments, max_w)
        skipped = [s for s in all_segments if s not in selected]
    print(f"    {len(selected)} in GPX, {len(skipped)} skipped")

    # 3. Load POI buffer (optional)
    print("  [3/5] Loading POI buffer...")
    pois = load_poi_buffer(args.poi_buffer) if args.poi_buffer else []
    print(f"    {len(pois)} POIs accepted")

    # 4. Load track points
    print("  [4/5] Loading track points...")
    track_points = load_track_points(route_id)
    print(f"    {len(track_points)} track points")

    # 5. Build GPX
    print("  [5/5] Building GPX...")
    gpx_content = build_gpx(track_points, selected, pois, route_name, g5_mode=use_short_names, g6_mode=use_human_desc)

    validation = validate_gpx(gpx_content)
    if not validation.get("valid"):
        print(f"    GPX INVALID: {validation.get('error')}")
        sys.exit(1)
    print(f"    GPX valid: {validation['trkpt_count']} trkpt, {validation['wpt_count']} wpt")

    name_fn = format_warning_name_g5 if use_short_names else build_warning_name
    desc_fn = format_warning_desc_human if use_human_desc else (format_warning_desc_g5 if use_short_names else build_warning_desc)

    if mode == "dry-run":
        print(f"\n{'='*60}")
        print(f"{label} DRY-RUN — route_id={route_id}")
        print(f"  Warnings in GPX: {len(selected)}")
        print(f"  POI in GPX: {len(pois)}")
        print(f"  Track points: {validation['trkpt_count']}")
        print(f"  Total <wpt>: {validation['wpt_count']}")
        print(f"  Skipped: {len(skipped)}")
        for w in selected:
            print(f"    {SEVERITY_EMOJI.get(w.get('severity',''),'')} {name_fn(w):32s}  {w['start_km']:.1f}–{w['end_km']:.1f} km")
            if mode == "dry-run":
                print(f"      desc: {desc_fn(w)}")
        print(f"{'='*60}")
        return

    # Build mode — write files
    GPX_DIR.mkdir(parents=True, exist_ok=True)
    if args.output_prefix:
        prefix = args.output_prefix + "_"
    else:
        prefix = ""  # default: production filenames

    gpx_path = GPX_DIR / f"{prefix}gravel_import_{route_id}.gpx"
    md_path = GPX_DIR / f"{prefix}gravel_import_{route_id}.md"
    summary_path = GPX_DIR / f"{prefix}gravel_import_{route_id}_summary.json"

    ts_end = datetime.now(timezone.utc)

    summary = {
        "ok": True,
        "route_id": route_id,
        "route_name": route_name,
        "distance_km": risk_meta.get("distance_km"),
        "total_warnings_available": len(all_segments),
        "warnings_in_gpx": len(selected),
        "warnings_skipped": len(skipped),
        "poi_in_gpx": len(pois),
        "trkpt_count": validation["trkpt_count"],
        "wpt_count": validation["wpt_count"],
        "output_gpx_path": str(gpx_path),
        "output_md_path": str(md_path),
        "warnings_in_gpx_list": [
            {"name": name_fn(w), "start_km": w["start_km"], "end_km": w["end_km"],
             "length_km": w["length_km"], "risk_type": w.get("risk_type", "?"), "severity": w.get("severity", "?"),
             "desc_technical": build_warning_desc(w),
             "desc_human": format_warning_desc_human(w) if use_human_desc else None}
            for w in selected
        ],
        "pois_in_gpx": [{"name": p.get("name"), "rwgps_sym": p.get("rwgps_sym", "Waypoint"),
                         "distance_m": p.get("distance_m") or p.get("distance_to_track_m")} for p in pois],
        "generator": "g3_build_gravel_import_gpx.py",
        "mode": f"{label}_{mode}",
        "duration_s": round((ts_end - ts_start).total_seconds(), 1),
        "generated_at": ts_end.isoformat(),
    }

    gpx_path.write_text(gpx_content, encoding="utf-8")
    print(f"    GPX: {gpx_path} ({gpx_path.stat().st_size} bytes)")

    output_json(summary_path, summary)
    print(f"    Summary: {summary_path}")

    output_md(md_path, summary, all_segments, selected, skipped, g5_mode=use_short_names)
    print(f"    MD: {md_path}")

    print(f"\n{'='*60}")
    print(f"{label} BUILD COMPLETE — route_id={route_id}")
    print(f"  Warnings in GPX: {len(selected)}")
    print(f"  POI in GPX: {len(pois)}")
    print(f"  Track points: {validation['trkpt_count']}")
    print(f"  Total <wpt>: {validation['wpt_count']}")
    print(f"  Route: {route_name}")
    for w in selected:
        print(f"    {SEVERITY_EMOJI.get(w.get('severity',''),'')} {name_fn(w):32s}  {w['start_km']:.1f}–{w['end_km']:.1f} km")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
