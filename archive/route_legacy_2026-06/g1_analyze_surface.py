#!/usr/bin/env python3
"""G1 — Surface analysis hardening for Gravel Intelligence.

Standalone CLI with retry logic, normalized categories, cache, confidence.

Usage:
  .venv/bin/python scripts/g1_analyze_surface.py --route-id 55395119
  .venv/bin/python scripts/g1_analyze_surface.py --route-id 55401067 --force
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
USER_AGENT = "QBot/1.0 (gravel intelligence g1; michal@qbot)"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
BATCH_SIZE = 15
MAX_SAMPLES = 120
MAX_MATCH_DIST_M = 150

SURFACE_RAW_MAP: dict[str, str] = {
    "asphalt": "asphalt",
    "paved": "asphalt",
    "concrete": "asphalt",
    "cobblestone": "asphalt",
    "sett": "asphalt",
    "paving_stones": "asphalt",
    "chipseal": "asphalt",
    "gravel": "gravel",
    "fine_gravel": "gravel",
    "pebblestone": "gravel",
    "compacted": "compacted",
    "dirt": "dirt",
    "ground": "dirt",
    "earth": "dirt",
    "mud": "dirt",
    "sand": "sand",
    "grass": "grass",
    "grass_paver": "grass",
    "unpaved": "unpaved_track",
    "woodchips": "unpaved_track",
}

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


def _hms(seconds: float) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _dist_fast(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = (lat2 - lat1) * 111320.0
    dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
    return math.sqrt(dlat * dlat + dlon * dlon)


# ── Step 1: Ensure GPX ──────────────────────────────────────────────────────

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


# ── Step 2: Parse GPX ──────────────────────────────────────────────────────

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


# ── Step 3: Sample + segment into batches ──────────────────────────────────

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


# ── Step 4: Overpass with retry ─────────────────────────────────────────────

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
                r = c.post(
                    OVERPASS_URL,
                    content=urlencode({"data": query}).encode("utf-8"),
                    headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
                )
                if r.status_code == 429 and attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    print(f"      429, retry {attempt}/{MAX_RETRIES} after {delay:.0f}s")
                    time.sleep(delay)
                    continue
                if r.status_code == 504 and attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    print(f"      504, retry {attempt}/{MAX_RETRIES} after {delay:.0f}s")
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
    # Use tracktype as heuristic for unpaved
    tt = tags.get("tracktype", "").lower()
    if tt in ("grade1",):
        return "asphalt"
    if tt in ("grade2", "grade3"):
        return "gravel"
    if tt in ("grade4", "grade5"):
        return "dirt"
    return "unknown"


# ── Step 5: Process batches ────────────────────────────────────────────────

def analyze_surface(points: list[list[float]], sample_distance_m: int = 500) -> dict:
    samples, batches, dists, total_dist_m = sample_and_batch(points, sample_distance_m)
    total_dist_km = total_dist_m / 1000.0

    surface_counts: dict[str, int] = {}
    highway_counts: dict[str, int] = {}
    tracktype_counts: dict[str, int] = {}
    matched = 0
    unmatched = 0
    osm_errors: list[str] = []
    retry_count = 0

    print(f"    {len(points)} pts → {len(samples)} samples → {len(batches)} batches (retry={MAX_RETRIES}x)")

    for bidx, batch in enumerate(batches):
        print(f"      batch {bidx + 1}/{len(batches)} ...", end=" ")
        elements, error = query_batch(batch)
        if error:
            print(f"ERROR: {error}")
            osm_errors.append(f"batch {bidx + 1}: {error}")
            unmatched += len(batch)
            continue
        if not elements:
            print("no data")
            unmatched += len(batch)
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
                unmatched += 1
                continue
            matched += 1
            cat = classify_surface(best_tags)
            surface_counts[cat] = surface_counts.get(cat, 0) + 1
            hw = best_tags.get("highway")
            if hw:
                highway_counts[hw] = highway_counts.get(hw, 0) + 1
            tt = best_tags.get("tracktype")
            if tt:
                tracktype_counts[tt] = tracktype_counts.get(tt, 0) + 1

        print(f"{len(elements)} ways, {matched}/{unmatched + matched} matched")

    total = sum(surface_counts.values()) or 1
    unknown_pct = round(surface_counts.get("unknown", 0) / total * 100, 1)
    coverage_pct = round(matched / max(1, len(samples)) * 100, 1)

    # Compute km breakdown
    km_per_sample = total_dist_km / len(samples) if samples else 0
    surface_km: dict[str, float] = {}
    for cat in CATEGORY_ORDER:
        cnt = surface_counts.get(cat, 0)
        surface_km[cat] = round(cnt * km_per_sample, 2)

    # Confidence
    if unknown_pct < 20 and coverage_pct >= 80:
        confidence = "high"
    elif unknown_pct < 40 and coverage_pct >= 50:
        confidence = "medium"
    else:
        confidence = "low"

    warnings_list: list[str] = []
    if unknown_pct > 40:
        warnings_list.append(f"Unknown surface: {unknown_pct}% — OSM brak tagów surface dla znacznej części trasy")
    if coverage_pct < 70:
        warnings_list.append(f"Niski coverage OSM: {coverage_pct}% — część batchy nieudana")
    if osm_errors:
        warnings_list.append(f"Błędy Overpass: {len(osm_errors)}/{len(batches)} batchy ({'; '.join(osm_errors[:2])})")

    surface_pct = {}
    for cat in CATEGORY_ORDER:
        cnt = surface_counts.get(cat, 0)
        pct = round(cnt / total * 100, 1) if total else 0
        if pct > 0:
            surface_pct[cat] = pct

    return {
        "ok": True,
        "status": "OK",
        "source": "g1_analyze_surface",
        "point_count": len(points),
        "distance_km": round(total_dist_km, 3),
        "sampled_points": len(samples),
        "matched_points": matched,
        "unmatched_points": unmatched,
        "coverage_pct": coverage_pct,
        "surface_breakdown": surface_pct,
        "surface_km": surface_km,
        "dominant_surface": max(surface_pct, key=surface_pct.get) if surface_pct else "unknown",
        "unknown_pct": unknown_pct,
        "confidence": confidence,
        "highway_breakdown": {k: round(v / total * 100, 1) for k, v in sorted(highway_counts.items(), key=lambda x: -x[1])} if highway_counts else {},
        "tracktype_breakdown": {k.replace("grade", ""): round(v / total * 100, 1) for k, v in sorted(tracktype_counts.items())} if tracktype_counts else {},
        "warnings": warnings_list if warnings_list else None,
    }


# ── Step 6: Output writers ────────────────────────────────────────────────

def output_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def output_md(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Analiza nawierzchni — route_id={result.get('route_id', '?')}")
    lines.append("")
    lines.append(f"- **Route ID:** {result.get('route_id', '?')}")
    if result.get("route_name"):
        lines.append(f"- **Route:** {result['route_name']}")
    lines.append(f"- **GPX:** {result.get('gpx_path', '?')}")
    lines.append(f"- **Punkty GPX:** {result['point_count']}")
    lines.append(f"- **Dystans:** {result['distance_km']} km")
    lines.append(f"- **Próbkowanie:** co 500m ({result['sampled_points']} pts)")
    lines.append(f"- **Coverage OSM:** {result['coverage_pct']}% ({result['matched_points']}/{result['matched_points'] + result['unmatched_points']})")
    lines.append(f"- **Ufność:** {result['confidence']}")
    lines.append(f"- **Czas analizy:** {result.get('duration_s', '?')}s")
    lines.append("")

    lines.append("## Nawierzchnia")
    lines.append("")
    lines.append("| Kategoria | % | km | Opis |")
    lines.append("|-----------|---|----|------|")
    for cat in CATEGORY_ORDER:
        pct = result.get("surface_breakdown", {}).get(cat, 0)
        km = result.get("surface_km", {}).get(cat, 0)
        if pct > 0 or km > 0:
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"| {label} | {pct}% | {km:.2f} km | — |")
    lines.append("")

    lines.append(f"**Nieznana:** {result['unknown_pct']}%")
    lines.append(f"**Dominująca:** {CATEGORY_LABELS.get(result.get('dominant_surface', '?'), result.get('dominant_surface', '?'))}")
    lines.append("")

    hw = result.get("highway_breakdown", {})
    if hw:
        lines.append("## Typ drogi (highway)")
        lines.append("")
        lines.append("| Typ | % |")
        lines.append("|-----|---|")
        for k, v in sorted(hw.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v}% |")
        lines.append("")

    tt = result.get("tracktype_breakdown", {})
    if tt:
        lines.append("## Tracktype (grade)")
        lines.append("")
        lines.append("| Grade | % |")
        lines.append("|-------|---|")
        for k, v in sorted(tt.items(), key=lambda x: x[0]):
            lines.append(f"| grade{k} | {v}% |")
        lines.append("")

    warns = result.get("warnings")
    if warns:
        lines.append("## Ostrzeżenia")
        lines.append("")
        for w in warns:
            lines.append(f"- ⚠ {w}")
        lines.append("")

    lines.append("## Ograniczenia")
    lines.append("")
    lines.append("1. Dane OSM mogą być niekompletne dla dróg gruntowych/leśnych")
    lines.append("2. Próbkowanie co 500m może pominąć krótkie odcinki")
    lines.append("3. Promień matchowania 150m — najbliższa droga OSM nie zawsze faktyczną drogą")
    lines.append("4. Brak rozróżnienia sucha/mokra nawierzchnia")
    lines.append("")
    lines.append("---")
    lines.append(f"*Wygenerowano: {result.get('generated_at', '?')} | G1 surface analyzer*")

    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="G1 surface analysis (hardened)")
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--force", action="store_true", default=False, help="Ignore cache, re-fetch Overpass")
    args = parser.parse_args()

    route_id = args.route_id
    force = args.force
    ts_start = datetime.now(timezone.utc)

    print(f"[{ts_start.isoformat()}] G1 surface analysis: route_id={route_id}")

    # 1. Ensure GPX
    print("  [1/5] GPX artifact...")
    gpx_path = ensure_gpx(route_id)
    if not gpx_path.exists():
        print(f"    ERROR: GPX not found at {gpx_path}")
        sys.exit(1)
    file_sha = hashlib.sha256(gpx_path.read_bytes()).hexdigest()
    print(f"    {gpx_path} ({gpx_path.stat().st_size} bytes)")

    # 2. Cache check (by route_id)
    surface_dir = ARTIFACTS_DIR / "surface"
    surface_dir.mkdir(parents=True, exist_ok=True)
    cache_path = surface_dir / f"surface_{route_id}.json"
    if cache_path.exists() and not force:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("ok") and cached.get("source") == "g1_analyze_surface":
                cached["cache_hit"] = True
                cached["duration_s"] = 0
                cached["generated_at"] = ts_start.isoformat()
                print(f"    cache HIT: {cache_path}")
                # Still write MD for completeness
                md_path = surface_dir / f"surface_{route_id}.md"
                output_md(md_path, cached)
                print(f"    MD: {md_path}")
                print(f"\n{'='*60}")
                print(f"G1 CACHED RESULT — route_id={route_id}")
                print(f"  confidence: {cached.get('confidence', '?')}")
                print(f"  unknown_pct: {cached.get('unknown_pct', '?')}%")
                print(f"  dominant: {cached.get('dominant_surface', '?')}")
                print(f"{'='*60}")
                return
        except Exception:
            pass
    print(f"    cache MISS")

    # 3. Parse GPX
    print("  [2/5] Parsing GPX...")
    points = parse_gpx_points(gpx_path)
    print(f"    {len(points)} track points")

    # 4. Analyze surface
    print("  [3/5] Surface analysis via Overpass (with retry)...")
    result = analyze_surface(points)

    # 5. Build output
    print("  [4/5] Building output...")
    ts_end = datetime.now(timezone.utc)
    duration_s = (ts_end - ts_start).total_seconds()

    # Get route name
    route_name = f"Route {route_id}"
    try:
        from tools.rwgps.client import get_rwgps_raw_route
        raw = get_rwgps_raw_route(route_id)
        if raw.get("ok"):
            rn = raw["route"].get("name")
            if rn:
                route_name = rn
    except Exception:
        pass

    result.update({
        "route_id": route_id,
        "route_name": route_name,
        "gpx_path": str(gpx_path),
        "gpx_sha256": file_sha,
        "generated_at": ts_end.isoformat(),
        "duration_s": round(duration_s, 1),
        "cache_hit": False,
        "generator": "g1_analyze_surface.py",
    })

    # 6. Write outputs
    print("  [5/5] Writing artifacts...")
    json_path = surface_dir / f"surface_{route_id}.json"
    md_path = surface_dir / f"surface_{route_id}.md"
    output_json(json_path, result)
    output_md(md_path, result)
    # Also cache at analysis dir for mcp_server compatibility
    analysis_cache = ARTIFACTS_DIR / "analysis" / f"surface_rwgps_{route_id}_500m.json"
    try:
        analysis_cache.parent.mkdir(parents=True, exist_ok=True)
        analysis_cache.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    print(f"    JSON: {json_path}")
    print(f"    MD:   {md_path}")
    print(f"    Duration: {_hms(duration_s)}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"G1 SURFACE ANALYSIS — route_id={route_id}")
    print(f"  confidence: {result['confidence']}")
    print(f"  unknown_pct: {result['unknown_pct']}%")
    print(f"  coverage: {result['coverage_pct']}%")
    print(f"  dominant: {CATEGORY_LABELS.get(result['dominant_surface'], result['dominant_surface'])}")
    for cat in CATEGORY_ORDER:
        pct = result.get("surface_breakdown", {}).get(cat, 0)
        km = result.get("surface_km", {}).get(cat, 0)
        if pct > 0:
            print(f"    {CATEGORY_LABELS.get(cat, cat):30s} {pct:5.1f}%  {km:6.2f} km")
    warns = result.get("warnings")
    if warns:
        for w in warns:
            print(f"  ⚠ {w}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
