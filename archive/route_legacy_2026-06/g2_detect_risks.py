#!/usr/bin/env python3
"""G2 — Risk segment detection for Gravel Intelligence.

Groups contiguous risky surface samples into segments, classifies by
risk type and severity.

Usage:
  .venv/bin/python scripts/g2_detect_risks.py --route-id 55395119
  .venv/bin/python scripts/g2_detect_risks.py --route-id 55401067
"""

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
sys.path.insert(0, str(APP_DIR))

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "QBot/1.0 (gravel intelligence g2; michal@qbot)"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
BATCH_SIZE = 15
MAX_SAMPLES = 120
MAX_MATCH_DIST_M = 150
SEGMENT_MIN_M = 100

SURFACE_RAW_MAP: dict[str, str] = {
    "asphalt": "asphalt", "paved": "asphalt", "concrete": "asphalt",
    "cobblestone": "asphalt", "sett": "asphalt", "paving_stones": "asphalt",
    "chipseal": "asphalt",
    "gravel": "gravel", "fine_gravel": "gravel", "pebblestone": "gravel",
    "compacted": "compacted",
    "dirt": "dirt", "ground": "dirt", "earth": "dirt", "mud": "dirt",
    "sand": "sand",
    "grass": "grass", "grass_paver": "grass",
    "unpaved": "unpaved_track", "woodchips": "unpaved_track",
}

RISK_SURFACES = {"dirt", "sand", "grass", "unpaved_track", "gravel", "unknown"}
LOW_RISK = {"asphalt", "compacted"}

CATEGORY_ORDER = ["asphalt", "gravel", "compacted", "dirt", "sand", "grass", "unpaved_track", "unknown"]

CATEGORY_LABELS: dict[str, str] = {
    "asphalt": "Asfalt / utwardzona",
    "gravel": "Gravel / szuter",
    "compacted": "Ubita / stabilizowana",
    "dirt": "Ziemia / grunt",
    "sand": "Piasek",
    "grass": "Trawa",
    "unpaved_track": "Nieutwardzona / inna",
    "unknown": "Nieznana (brak tagu surface)",
}

RISK_TYPE_LABELS: dict[str, str] = {
    "sand": "Piasek / możliwy piasek",
    "dirt": "Grunt / ziemia",
    "unpaved_track": "Nieutwardzona droga",
    "grass": "Trawa / łąka",
    "gravel_rough": "Gravel / szorstki",
    "unknown_long": "Długi odcinek bez danych OSM",
    "mixed_bad": "Mieszana zła nawierzchnia",
}


def _hms(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _dist_fast(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = (lat2 - lat1) * 111320.0
    dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dlat * dlat + dlon * dlon)


# ── Ensure GPX ──────────────────────────────────────────────────────────────

def ensure_gpx(route_id: str) -> Path:
    gpx_path = ARTIFACTS_DIR / "exports" / "rwgps" / f"rwgps_{route_id}.gpx"
    if gpx_path.exists():
        return gpx_path
    from tools.rwgps.client import export_route_to_artifact
    print(f"    exporting GPX for {route_id}...")
    result = export_route_to_artifact(route_id, fmt="gpx")
    if not result.get("ok"):
        raise RuntimeError(f"export failed: {result.get('error', 'unknown')}")
    if not gpx_path.exists():
        raise RuntimeError(f"GPX not created after export: {gpx_path}")
    return gpx_path


# ── Parse GPX ──────────────────────────────────────────────────────────────

def parse_gpx_points(gpx_path: Path) -> list[list[float]]:
    import xml.etree.ElementTree as ET
    ns = "http://www.topografix.com/GPX/1/1"
    tree = ET.parse(str(gpx_path))
    root = tree.getroot()
    points: list[list[float]] = []
    for trkpt in root.iter(f"{{{ns}}}trkpt"):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat and lon:
            points.append([float(lat), float(lon)])
    if not points:
        raise ValueError(f"No track points in {gpx_path}")
    return points


# ── Sample + batch ─────────────────────────────────────────────────────────

def sample_and_batch(points: list[list[float]], sample_distance_m: int = 500) -> tuple[list[list[float]], list[list[list[float]]], list[float], float]:
    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + _dist_fast(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1]))
    total_dist_m = dists[-1]

    samples = [points[0]]
    next_target = sample_distance_m
    for i in range(1, len(points)):
        if dists[i] >= next_target:
            samples.append(points[i])
            next_target += sample_distance_m
    if samples[-1] != points[-1]:
        samples.append(points[-1])

    if len(samples) > MAX_SAMPLES:
        step = len(samples) / MAX_SAMPLES
        samples = [samples[int(i * step)] for i in range(MAX_SAMPLES)]

    batches = [samples[i:i + BATCH_SIZE] for i in range(0, len(samples), BATCH_SIZE)]
    return samples, batches, dists, total_dist_m


# ── Overpass with retry ─────────────────────────────────────────────────────

def query_batch(batch: list[list[float]]) -> tuple[list[dict], str | None]:
    from urllib.parse import urlencode
    import httpx

    b_lats = [p[0] for p in batch]
    b_lons = [p[1] for p in batch]
    b_south = min(b_lats) - 0.003
    b_north = max(b_lats) + 0.003
    b_west = min(b_lons) - 0.003
    b_east = max(b_lons) + 0.003

    query = f"[out:json][timeout:30];way[highway]({b_south},{b_west},{b_north},{b_east});out tags geom;"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=35) as c:
                r = c.post(OVERPASS_URL, content=urlencode({"data": query}).encode("utf-8"),
                           headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT})
                if r.status_code in (429, 504) and attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    print(f"      {r.status_code}, retry {attempt}/{MAX_RETRIES} after {delay:.0f}s")
                    time.sleep(delay)
                    continue
                r.raise_for_status()
                return r.json().get("elements", []), None
        except httpx.HTTPStatusError as exc:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * attempt)
                continue
            return [], f"HTTP {exc.response.status_code}"
        except Exception as exc:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BASE_DELAY * attempt)
                continue
            return [], str(exc)[:100]
    return [], f"failed after {MAX_RETRIES} retries"


def classify_surface(tags: dict) -> str:
    raw = tags.get("surface", "").lower()
    if raw in SURFACE_RAW_MAP:
        return SURFACE_RAW_MAP[raw]
    if raw:
        return "unpaved_track"
    tt = tags.get("tracktype", "").lower()
    if tt in ("grade1",):
        return "asphalt"
    if tt in ("grade2", "grade3"):
        return "gravel"
    if tt in ("grade4", "grade5"):
        return "dirt"
    return "unknown"


# ── Build per-sample classifications ────────────────────────────────────────

def classify_samples(points: list[list[float]], sample_distance_m: int = 500) -> list[dict]:
    samples, batches, dists, total_dist_m = sample_and_batch(points, sample_distance_m)
    km_per_sample = total_dist_m / 1000.0 / len(samples) if samples else 0

    sample_data: list[dict] = []
    for bidx, batch in enumerate(batches):
        elements, error = query_batch(batch)
        if error or not elements:
            for pt in batch:
                sample_data.append({"lat": pt[0], "lon": pt[1], "surface": "unknown", "highway": None, "tracktype": None, "tags": {}})
            continue

        for pt in batch:
            best_tags: dict = {}
            best_dist = float("inf")
            for way in elements:
                for node in way.get("geometry", []):
                    d = _dist_fast(pt[0], pt[1], node["lat"], node["lon"])
                    if d < best_dist:
                        best_dist = d
                        best_tags = way.get("tags", {})
            if best_dist > MAX_MATCH_DIST_M:
                sample_data.append({"lat": pt[0], "lon": pt[1], "surface": "unknown", "highway": None, "tracktype": None, "tags": {}, "match_dist_m": round(best_dist, 1)})
            else:
                cat = classify_surface(best_tags)
                sample_data.append({
                    "lat": pt[0], "lon": pt[1],
                    "surface": cat,
                    "highway": best_tags.get("highway"),
                    "tracktype": best_tags.get("tracktype"),
                    "tags": {k: best_tags[k] for k in ("surface", "highway", "tracktype", "smoothness") if k in best_tags},
                    "match_dist_m": round(best_dist, 1),
                })

    # Assign km to each sample
    for i, sd in enumerate(sample_data):
        sd["km"] = round(i * km_per_sample, 3)
        sd["length_km"] = round(km_per_sample, 3)

    return sample_data


# ── Segment builder ─────────────────────────────────────────────────────────

def build_segments(sample_data: list[dict]) -> list[dict]:
    if not sample_data:
        return []

    segments: list[dict] = []
    current: list[dict] = []
    km_per_sample = sample_data[0].get("length_km", 0.5) if sample_data else 0.5

    for sd in sample_data:
        surf = sd["surface"]
        is_risk = surf in RISK_SURFACES

        if is_risk:
            current.append(sd)
        else:
            if len(current) >= 2:
                seg = _finalize_segment(current, km_per_sample)
                if seg:
                    segments.append(seg)
            current = []

    if len(current) >= 2:
        seg = _finalize_segment(current, km_per_sample)
        if seg:
            segments.append(seg)

    return segments


def _finalize_segment(samples: list[dict], km_per_sample: float) -> dict | None:
    length_km = len(samples) * km_per_sample
    length_m = length_km * 1000

    if length_m < SEGMENT_MIN_M:
        return None

    start_km = samples[0]["km"]
    end_km = samples[-1]["km"] + km_per_sample

    # Count surface types
    surface_counts: dict[str, int] = {}
    for s in samples:
        surf = s["surface"]
        surface_counts[surf] = surface_counts.get(surf, 0) + 1

    dominant = max(surface_counts, key=surface_counts.get)
    dominated_pct = surface_counts[dominant] / len(samples) * 100

    # Determine risk type
    risk_type = _determine_risk_type(surface_counts, dominant, length_km, samples)
    severity = _determine_severity(risk_type, surface_counts, length_km, dominated_pct)

    # Representative point
    mid = samples[len(samples) // 2]
    rep_lat = mid["lat"]
    rep_lon = mid["lon"]

    # Confidence based on unknown ratio
    unknown_ratio = surface_counts.get("unknown", 0) / len(samples)
    if unknown_ratio > 0.5:
        seg_confidence = "low"
    elif unknown_ratio > 0.2:
        seg_confidence = "medium"
    else:
        seg_confidence = "high"

    # Reason
    reason = _build_reason(risk_type, dominant, length_km, dominated_pct, surface_counts, samples)

    # Source tags summary
    tags_seen: dict[str, set[str]] = {}
    for s in samples:
        for k, v in s.get("tags", {}).items():
            if v:
                tags_seen.setdefault(k, set()).add(str(v))

    source_tags = {k: sorted(v)[:3] for k, v in tags_seen.items()}

    return {
        "start_km": round(start_km, 2),
        "end_km": round(end_km, 2),
        "length_km": round(length_km, 2),
        "dominant_surface": dominant,
        "dominant_pct": round(dominated_pct, 1),
        "risk_type": risk_type,
        "severity": severity,
        "confidence": seg_confidence,
        "reason": reason,
        "representative_lat": rep_lat,
        "representative_lon": rep_lon,
        "source_tags": source_tags,
        "surface_counts": {k: v for k, v in sorted(surface_counts.items(), key=lambda x: -x[1])},
    }


def _determine_risk_type(surface_counts: dict, dominant: str, length_km: float, samples: list[dict]) -> str:
    if dominant == "sand":
        return "sand"
    if dominant == "grass":
        return "grass"
    if dominant == "dirt":
        return "dirt"
    if dominant == "unpaved_track":
        return "unpaved_track"
    if dominant == "gravel":
        # Check how rough — look for tracktype or smoothness
        rough_signals = 0
        for s in samples:
            tt = (s.get("tags") or {}).get("tracktype", "")
            sm = (s.get("tags") or {}).get("smoothness", "")
            if tt in ("grade4", "grade5"):
                rough_signals += 1
            if sm in ("bad", "very_bad", "horrible"):
                rough_signals += 1
        if rough_signals > len(samples) * 0.3:
            return "gravel_rough"
        return "dirt"  # treat standard gravel as medium risk, same as dirt
    if dominant == "unknown":
        if length_km > 3:
            return "unknown_long"
        return "dirt"
    return "mixed_bad"


def _determine_severity(risk_type: str, surface_counts: dict, length_km: float, dominated_pct: float) -> str:
    # Sand/grass: always at least medium
    if risk_type == "sand":
        return "high" if length_km > 0.5 else "medium"
    if risk_type == "grass":
        return "high" if length_km > 0.5 else "medium"

    # Unknown long sections
    if risk_type == "unknown_long":
        return "high" if length_km > 5 else "medium"

    # Dirt/unpaved: medium if >1km, high if >3km
    if risk_type in ("dirt", "unpaved_track"):
        if length_km > 3:
            return "high"
        if length_km > 1:
            return "medium"
        return "low"

    # Rough gravel
    if risk_type == "gravel_rough":
        if length_km > 2:
            return "high"
        if length_km > 0.5:
            return "medium"
        return "low"

    # Mixed bad
    if risk_type == "mixed_bad":
        return "high" if length_km > 2 else "medium"

    return "low"


def _build_reason(risk_type: str, dominant: str, length_km: float, dominated_pct: float, surface_counts: dict, samples: list[dict]) -> str:
    label = RISK_TYPE_LABELS.get(risk_type, risk_type)
    parts = [f"{label} ({length_km:.1f} km)"]

    if dominated_pct > 50:
        parts.append(f"dominuje {CATEGORY_LABELS.get(dominant, dominant)} ({dominated_pct:.0f}%)")

    # Add highway info if consistent
    highways = set()
    for s in samples:
        hw = (s.get("tags") or {}).get("highway")
        if hw:
            highways.add(hw)
    if highways:
        hw_str = ", ".join(sorted(highways)[:2])
        parts.append(f"droga: {hw_str}")

    # Add tracktype
    tracktypes = set()
    for s in samples:
        tt = (s.get("tags") or {}).get("tracktype")
        if tt:
            tracktypes.add(tt)
    if tracktypes:
        parts.append(f"tracktype: {', '.join(sorted(tracktypes)[:2])}")

    return ". ".join(parts)


# ── Output ──────────────────────────────────────────────────────────────────

def output_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def output_md(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Segmenty ryzyka — route_id={result.get('route_id', '?')}")
    lines.append("")
    if result.get("route_name"):
        lines.append(f"**Route:** {result['route_name']}")
    lines.append(f"**Route ID:** {result.get('route_id', '?')}")
    lines.append(f"**Dystans:** {result.get('distance_km', '?')} km")
    lines.append(f"**Segmentów ryzyka:** {result.get('num_segments', 0)}")
    lines.append(f"**Całkowity dystans ryzyka:** {result.get('total_risk_km', 0):.1f} km")
    lines.append(f"**High risk:** {result.get('high_risk_km', 0):.1f} km")
    lines.append(f"**Medium risk:** {result.get('medium_risk_km', 0):.1f} km")
    lines.append(f"**Unknown risk (brak danych OSM):** {result.get('unknown_risk_km', 0):.1f} km")
    lines.append("")

    segments = result.get("segments", [])
    if not segments:
        lines.append("## Brak segmentów ryzyka")
        lines.append("")
        lines.append("Nie znaleziono znaczących segmentów ryzyka dla tej trasy.")
        path.write_text("\n".join(lines), encoding="utf-8")
        return

    # Summary table
    lines.append("## Segmenty")
    lines.append("")
    lines.append("| # | km | Długość | Główna nawierzchnia | Ryzyko | Poziom | Opis |")
    lines.append("|---|----|---------|--------------------|--------|--------|------|")
    for i, seg in enumerate(segments, 1):
        lines.append(
            f"| {i} | {seg['start_km']:.1f}–{seg['end_km']:.1f} | {seg['length_km']:.1f} km | "
            f"{CATEGORY_LABELS.get(seg['dominant_surface'], seg['dominant_surface'])} | "
            f"{RISK_TYPE_LABELS.get(seg['risk_type'], seg['risk_type'])} | "
            f"{seg['severity'].upper()} | "
            f"{seg['reason'][:80]}"
        )
    lines.append("")

    # Detail per segment
    lines.append("## Szczegóły segmentów")
    lines.append("")
    for i, seg in enumerate(segments, 1):
        lines.append(f"### {i}. {seg['start_km']:.1f}–{seg['end_km']:.1f} km ({seg['length_km']:.1f} km)")
        lines.append("")
        lines.append(f"- **Główna nawierzchnia:** {CATEGORY_LABELS.get(seg['dominant_surface'], seg['dominant_surface'])} ({seg['dominant_pct']}%)")
        lines.append(f"- **Ryzyko:** {RISK_TYPE_LABELS.get(seg['risk_type'], seg['risk_type'])}")
        lines.append(f"- **Poziom:** {seg['severity'].upper()}")
        lines.append(f"- **Ufność:** {seg['confidence']}")
        lines.append(f"- **Przyczyna:** {seg['reason']}")
        lines.append(f"- **Punkt reprezentatywny:** ({seg['representative_lat']:.5f}, {seg['representative_lon']:.5f})")
        if seg.get("source_tags"):
            tags_str = "; ".join(f"{k}={v}" for k, v in seg["source_tags"].items())
            lines.append(f"- **Tagi OSM:** {tags_str}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Wygenerowano: {result.get('generated_at', '?')} | G2 risk detector*")
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="G2 risk segment detection")
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--force", action="store_true", default=False, help="Ignore cache")
    args = parser.parse_args()

    route_id = args.route_id
    force = args.force
    ts_start = datetime.now(timezone.utc)

    print(f"[{ts_start.isoformat()}] G2 risk detection: route_id={route_id}")

    # 1. GPX
    print("  [1/5] GPX artifact...")
    gpx_path = ensure_gpx(route_id)
    print(f"    {gpx_path}")

    # 2. Cache check (by route_id)
    surface_dir = ARTIFACTS_DIR / "surface"
    surface_dir.mkdir(parents=True, exist_ok=True)
    cache_path = surface_dir / f"risk_segments_{route_id}.json"
    if cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("ok"):
                cached["cache_hit"] = True
                cached["generated_at"] = ts_start.isoformat()
                print(f"    cache HIT")
                md_path = surface_dir / f"risk_segments_{route_id}.md"
                output_md(md_path, cached)
                print(f"    MD: {md_path}")
                _print_summary(cached)
                return
        except Exception:
            pass
    print(f"    cache MISS")

    # 3. Parse GPX
    print("  [2/5] Parsing GPX...")
    points = parse_gpx_points(gpx_path)
    print(f"    {len(points)} track points")

    # 4. Classify samples
    print("  [3/5] Classifying surfaces (Overpass with retry)...")
    sample_data = classify_samples(points)
    risk_count = sum(1 for s in sample_data if s["surface"] in RISK_SURFACES)
    total_count = len(sample_data)
    print(f"    {total_count} samples, {risk_count} risky ({risk_count / max(1, total_count) * 100:.0f}%)")

    # 5. Build segments
    print("  [4/5] Building risk segments...")
    segments = build_segments(sample_data)

    # Compute aggregate
    total_risk_km = sum(s["length_km"] for s in segments)
    high_risk_km = sum(s["length_km"] for s in segments if s["severity"] == "high")
    medium_risk_km = sum(s["length_km"] for s in segments if s["severity"] == "medium")
    unknown_risk_km = sum(s["length_km"] for s in segments if s["dominant_surface"] == "unknown")

    # Top 5 by length
    top5 = sorted(segments, key=lambda s: -s["length_km"])[:5]

    # 6. Build output
    print("  [5/5] Writing outputs...")
    ts_end = datetime.now(timezone.utc)
    duration_s = (ts_end - ts_start).total_seconds()

    # Get route name
    route_name = f"Route {route_id}"
    try:
        from tools.rwgps.client import get_rwgps_raw_route
        raw = get_rwgps_raw_route(route_id)
        if raw.get("ok") and raw["route"].get("name"):
            route_name = raw["route"]["name"]
    except Exception:
        pass

    result = {
        "ok": True,
        "status": "OK",
        "route_id": route_id,
        "route_name": route_name,
        "gpx_path": str(gpx_path),
        "point_count": len(points),
        "distance_km": round(sample_data[-1]["km"] + sample_data[-1]["length_km"] if sample_data else 0, 3),
        "num_segments": len(segments),
        "total_risk_km": round(total_risk_km, 2),
        "high_risk_km": round(high_risk_km, 2),
        "medium_risk_km": round(medium_risk_km, 2),
        "unknown_risk_km": round(unknown_risk_km, 2),
        "top_5_segments": [
            {"start_km": s["start_km"], "end_km": s["end_km"], "length_km": s["length_km"],
             "dominant_surface": s["dominant_surface"], "risk_type": s["risk_type"],
             "severity": s["severity"]}
            for s in top5
        ],
        "segments": segments,
        "generator": "g2_detect_risks.py",
        "duration_s": round(duration_s, 1),
        "generated_at": ts_end.isoformat(),
    }

    json_path = surface_dir / f"risk_segments_{route_id}.json"
    md_path = surface_dir / f"risk_segments_{route_id}.md"
    output_json(json_path, result)
    output_md(md_path, result)

    print(f"    JSON: {json_path}")
    print(f"    MD:   {md_path}")
    print(f"    Duration: {_hms(duration_s)}")

    _print_summary(result)


def _print_summary(result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"G2 RISK SEGMENTS — route_id={result.get('route_id', '?')}")
    print(f"  Segments: {result.get('num_segments', 0)}")
    print(f"  Total risk: {result.get('total_risk_km', 0):.1f} km")
    print(f"  High risk:  {result.get('high_risk_km', 0):.1f} km")
    print(f"  Medium risk: {result.get('medium_risk_km', 0):.1f} km")
    print(f"  Unknown (data gap): {result.get('unknown_risk_km', 0):.1f} km")
    print(f"  Top segments:")
    for s in result.get("top_5_segments", []):
        print(f"    {s['start_km']:.1f}–{s['end_km']:.1f} km ({s['length_km']:.1f} km) "
              f"{s['risk_type']} [{s['severity']}]")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
