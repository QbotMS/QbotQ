#!/usr/bin/env python3
"""G10 — OSM Cascade Surface Scoring dla Gravel Intelligence.

Rozszerza G1 o kaskadową klasyfikację nawierzchni (surface → tracktype →
smoothness → highway heuristic → regional fallback) i zapisuje wyniki
jako g10_surface_{route_id}.json (nie nadpisuje G1).

Usage:
  .venv/bin/python scripts/g10_osm_cascade_scoring.py --route-id 55401067
  .venv/bin/python scripts/g10_osm_cascade_scoring.py --route-id 55395119 --force
  .venv/bin/python scripts/g10_osm_cascade_scoring.py --routes 55401067,55395119
"""
from __future__ import annotations

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

from lib.surface_classifier import classify_osm_cascade, aggregate_cascade

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "QBot/1.0 (gravel intelligence g10; michal@qbot)"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0
BATCH_SIZE = 15
MAX_SAMPLES = 120
MAX_MATCH_DIST_M = 150

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

CATEGORY_ORDER = ["asphalt", "gravel", "compacted", "dirt", "sand", "grass", "unpaved_track", "unknown"]
CATEGORY_LABELS: dict[str, str] = {
    "asphalt": "Asfalt / utwardzona", "gravel": "Gravel / szuter",
    "compacted": "Ubita / stabilizowana", "dirt": "Ziemia / grunt",
    "sand": "Piasek", "grass": "Trawa",
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


# ── Step 2: Parse GPX ───────────────────────────────────────────────────────

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


# ── Step 3: Sample + segment into batches ───────────────────────────────────

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


# ── Step 4: Overpass with retry ──────────────────────────────────────────────

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


# ── Step 5: Cascade analysis ────────────────────────────────────────────────

def _is_poland_region(route_id: str) -> str:
    """Heuristic: determine region based on route_id range or fixed default."""
    # All current test routes are in Poland/Tuscany
    # For Puznówka (Poland) return mazowsze, for Tuscany return default
    # Since we can't determine from route_id alone, we use a geo heuristic later
    return "default"


def analyze_cascade(points: list[list[float]], route_id: str,
                    sample_distance_m: int = 500) -> dict:
    samples, batches, dists, total_dist_m = sample_and_batch(points, sample_distance_m)
    total_dist_km = total_dist_m / 1000.0

    surface_counts: dict[str, int] = {}
    highway_counts: dict[str, int] = {}
    tracktype_counts: dict[str, int] = {}
    matched = 0
    unmatched = 0
    osm_errors: list[str] = []

    # Per-sample cascade results
    sample_results: list[dict] = []

    print(f"    {len(points)} pts → {len(samples)} samples → {len(batches)} batches (retry={MAX_RETRIES}x)")

    for bidx, batch in enumerate(batches):
        print(f"      batch {bidx + 1}/{len(batches)} ...", end=" ")
        elements, error = query_batch(batch)
        if error:
            print(f"ERROR: {error}")
            osm_errors.append(f"batch {bidx + 1}: {error}")
            unmatched += len(batch)
            for pt in batch:
                cascade = classify_osm_cascade({}, region="default")
                if cascade.get("cascade_chain") is None:
                    cascade["cascade_chain"] = []
                cascade["sample_lat"] = pt[0]
                cascade["sample_lon"] = pt[1]
                cascade["matched"] = False
                cascade["best_tags"] = {}
                sample_results.append(cascade)
            continue
        if not elements:
            print("no data")
            unmatched += len(batch)
            for pt in batch:
                cascade = classify_osm_cascade({}, region="default")
                if cascade.get("cascade_chain") is None:
                    cascade["cascade_chain"] = []
                cascade["sample_lat"] = pt[0]
                cascade["sample_lon"] = pt[1]
                cascade["matched"] = False
                cascade["best_tags"] = {}
                sample_results.append(cascade)
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
                cascade = classify_osm_cascade({}, region="default")
                if cascade.get("cascade_chain") is None:
                    cascade["cascade_chain"] = []
                cascade["sample_lat"] = pt[0]
                cascade["sample_lon"] = pt[1]
                cascade["matched"] = False
                cascade["best_tags"] = {}
                sample_results.append(cascade)
                continue

            matched += 1

            # Determine region based on lat
            lat = pt[0]
            region = "mazowsze" if (52.0 <= lat <= 53.0) else "default"

            cascade = classify_osm_cascade(best_tags, region=region)
            if cascade.get("cascade_chain") is None:
                cascade["cascade_chain"] = ["surface_miss", "tracktype_miss",
                                             "smoothness_miss", "highway_miss"]

            cascade["sample_lat"] = pt[0]
            cascade["sample_lon"] = pt[1]
            cascade["matched"] = True
            cascade["best_tags"] = {
                "surface": best_tags.get("surface"),
                "tracktype": best_tags.get("tracktype"),
                "smoothness": best_tags.get("smoothness"),
                "highway": best_tags.get("highway"),
            }
            sample_results.append(cascade)

            # Legacy G1-style counts
            raw_surface = best_tags.get("surface", "").lower()
            if raw_surface in SURFACE_RAW_MAP:
                cat = SURFACE_RAW_MAP[raw_surface]
            elif raw_surface:
                cat = "unpaved_track"
            else:
                tt = best_tags.get("tracktype", "").lower()
                if tt in ("grade1",):
                    cat = "asphalt"
                elif tt in ("grade2", "grade3"):
                    cat = "gravel"
                elif tt in ("grade4", "grade5"):
                    cat = "dirt"
                else:
                    cat = "unknown"
            surface_counts[cat] = surface_counts.get(cat, 0) + 1
            hw = best_tags.get("highway")
            if hw:
                highway_counts[hw] = highway_counts.get(hw, 0) + 1
            tt = best_tags.get("tracktype")
            if tt:
                tracktype_counts[tt] = tracktype_counts.get(tt, 0) + 1

        print(f"{len(elements)} ways, {matched}/{unmatched + matched} matched")

    # Aggregate
    total = sum(surface_counts.values()) or 1
    unknown_pct = round(surface_counts.get("unknown", 0) / total * 100, 1)
    coverage_pct = round(matched / max(1, len(samples)) * 100, 1)

    km_per_sample = total_dist_km / len(samples) if samples else 0
    surface_km: dict[str, float] = {}
    for cat in CATEGORY_ORDER:
        cnt = surface_counts.get(cat, 0)
        surface_km[cat] = round(cnt * km_per_sample, 2)

    # Confidence (same as G1)
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

    # Cascade aggregate stats
    cascade_stats = aggregate_cascade(sample_results)

    result = {
        "ok": True,
        "status": "OK",
        "source": "g10_osm_cascade_scoring",
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
        "cascade_stats": cascade_stats,
        "samples": sample_results,
    }
    return result


# ── Output writers ──────────────────────────────────────────────────────────

def output_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def output_md(path: Path, result: dict, old_result: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cs = result.get("cascade_stats", {})
    lines = [
        f"# G10 — OSM Cascade Surface Scoring — route_id={result.get('route_id', '?')}",
        "",
        f"- **Route ID:** {result.get('route_id', '?')}",
    ]
    if result.get("route_name"):
        lines.append(f"- **Route:** {result['route_name']}")
    lines.extend([
        f"- **GPX:** {result.get('gpx_path', '?')}",
        f"- **Dystans:** {result.get('distance_km', '?')} km",
        f"- **Próbkowanie:** 500m ({result.get('sampled_points', '?')} pts)",
        f"- **Coverage OSM:** {result.get('coverage_pct', '?')}%",
        f"- **Confidence:** {result.get('confidence', '?')}",
        "",
        "## Porównanie G1 (old) vs G10 (cascade)",
        "",
    ])

    old_unk = old_result.get("unknown_pct", "?") if old_result else "N/A"
    new_unk = result.get("unknown_pct", "?")
    reduction = ""
    if old_result and isinstance(old_unk, (int, float)) and isinstance(new_unk, (int, float)):
        diff = old_unk - new_unk
        reduction = f" (redukcja: {diff:+.1f}pp)"
    lines.append(f"- **G1 unknown:** {old_unk}%")
    lines.append(f"- **G10 unknown:** {new_unk}%{reduction}")

    if cs:
        for level, info in cs.get("cascade_level_breakdown", {}).items():
            lines.append(f"- **Cascade level {level}:** {info['count']} próbek ({info['pct']}%)")
        lines.append(f"- **Średni score G10:** {cs.get('avg_cascade_score', '?')}")
        lines.append(f"- **Próbki good (<0.35):** {cs.get('samples_good', '?')}")
        lines.append(f"- **Próbki caution (0.35–0.65):** {cs.get('samples_caution', '?')}")
        lines.append(f"- **Próbki high-risk (>=0.65):** {cs.get('samples_high_risk', '?')}")

    lines.extend([
        "",
        "## Nawierzchnia (G10)",
        "",
        "| Kategoria | % | km |",
        "|-----------|---|----|",
    ])
    for cat in CATEGORY_ORDER:
        pct = result.get("surface_breakdown", {}).get(cat, 0)
        km = result.get("surface_km", {}).get(cat, 0)
        if pct > 0 or km > 0:
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"| {label} | {pct}% | {km:.2f} km |")
    lines.append(f"\n**Nieznana:** {result['unknown_pct']}%")

    # Highway + tracktype
    hw = result.get("highway_breakdown", {})
    if hw:
        lines.extend(["", "## Typ drogi (highway)", "", "| Typ | % |", "|-----|---|"])
        for k, v in sorted(hw.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v}% |")
    tt = result.get("tracktype_breakdown", {})
    if tt:
        lines.extend(["", "## Tracktype (grade)", "", "| Grade | % |", "|-------|---|"])
        for k, v in sorted(tt.items(), key=lambda x: x[0]):
            lines.append(f"| grade{k} | {v}% |")

    # First 20 km segment details
    lines.extend(["", "## Szczegóły pierwszych 20 km (kaskada)", ""])
    first20 = [s for s in result.get("samples", []) if s.get("sample_lat") and s.get("sample_lon")]
    # We need to approximate km for each sample — use index-based estimate
    km_per = (result.get("distance_km", 0) or 0) / max(1, len(first20))
    lines.append("| # | approx km | score | level | label | reason | tags |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, s in enumerate(first20[:40]):  # ~20km / 500m = 40 samples
        approx_km = round(i * km_per, 1)
        score = s.get("score", "?")
        lv = s.get("source_level", "?")
        lbl = s.get("class_label", "?")
        reason = s.get("reason", "")[:60]
        tags = s.get("best_tags", {})
        tag_str = "; ".join(f"{k}={v}" for k, v in tags.items() if v)
        if isinstance(score, float):
            score_str = f"{score:.2f}"
        else:
            score_str = str(score)
        icon = {"good": "🟢", "acceptable": "🟡", "caution": "🟠", "risk": "🔴", "avoid": "⛔"}.get(lbl, "⬜")
        lines.append(f"| {i} | {approx_km} | {score_str} | {lv} | {icon} {lbl} | {reason} | {tag_str} |")

    # Known problem segments check
    lines.extend(["", "## Weryfikacja odcinków problemowych", ""])
    route_id = result.get("route_id", "")
    if route_id == "55401067":
        lines.append("**Puznówka — odcinki piaszczyste:**")
        for s in first20:
            score = s.get("score", 0) or 0
            km_approx = first20.index(s) * km_per
            if 8 <= km_approx <= 12 or 14 <= km_approx <= 17:
                lbl = s.get("class_label", "?")
                lv = s.get("source_level", "?")
                icon = {"good": "🟢", "acceptable": "🟡", "caution": "🟠", "risk": "🔴", "avoid": "⛔"}.get(lbl, "⬜")
                lines.append(f"  km {km_approx:.1f}: score={score:.2f} {icon} level={lv} label={lbl}")

        lines.append("")
        lines.append("**Puznówka — asfaltowy początek (km 0-3):**")
        for s in first20[:6]:
            score = s.get("score", 0) or 0
            km_approx = first20.index(s) * km_per
            lbl = s.get("class_label", "?")
            icon = {"good": "🟢", "acceptable": "🟡", "caution": "🟠", "risk": "🔴", "avoid": "⛔"}.get(lbl, "⬜")
            if score < 0.30:
                lines.append(f"  km {km_approx:.1f}: score={score:.2f} {icon} ✅ OK")

    lines.extend([
        "",
        "---",
        f"*Wygenerowano: {result.get('generated_at', '?')} | G10 OSM Cascade*",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────

def run_single(route_id: str, force: bool = False, region_hint: str = "default") -> dict | None:
    ts_start = datetime.now(timezone.utc)
    print(f"\n[{ts_start.isoformat()}] G10 cascade: route_id={route_id}")

    # 1. Ensure GPX
    print("  [1/5] GPX artifact...")
    gpx_path = ensure_gpx(route_id)
    if not gpx_path.exists():
        print(f"    ERROR: GPX not found at {gpx_path}")
        return None
    file_sha = hashlib.sha256(gpx_path.read_bytes()).hexdigest()
    print(f"    {gpx_path} ({gpx_path.stat().st_size} bytes)")

    # 2. Cache check
    surface_dir = ARTIFACTS_DIR / "surface"
    surface_dir.mkdir(parents=True, exist_ok=True)
    g10_cache = surface_dir / f"g10_surface_{route_id}.json"
    if g10_cache.exists() and not force:
        try:
            cached = json.loads(g10_cache.read_text(encoding="utf-8"))
            if cached.get("ok") and cached.get("source") == "g10_osm_cascade_scoring":
                print(f"    cache HIT: {g10_cache}")
                cached["cache_hit"] = True
                cached["duration_s"] = 0
                cached["generated_at"] = ts_start.isoformat()
                return cached
        except Exception:
            pass

    print(f"    cache MISS")

    # 3. Parse GPX
    print("  [2/5] Parsing GPX...")
    points = parse_gpx_points(gpx_path)
    print(f"    {len(points)} track points")

    # 4. Cascade analysis
    print("  [3/5] Cascade surface analysis via Overpass...")
    result = analyze_cascade(points, route_id)

    # 5. Build output
    print("  [4/5] Building output...")
    ts_end = datetime.now(timezone.utc)
    duration_s = (ts_end - ts_start).total_seconds()

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
        "generator": "g10_osm_cascade_scoring.py",
    })

    return result


def main():
    parser = argparse.ArgumentParser(description="G10 OSM Cascade Surface Scoring")
    parser.add_argument("--route-id", help="Single route_id")
    parser.add_argument("--routes", help="Comma-separated route_ids")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Ignore cache, re-fetch Overpass")
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
    print("G10 — OSM Cascade Surface Scoring")
    print("=" * 70)

    surface_dir = ARTIFACTS_DIR / "surface"

    for rid in route_ids:
        result = run_single(rid, force=args.force)
        if not result:
            print(f"  ✗ {rid} — failed")
            continue

        # Write g10_surface_{route_id}.json (separate from G1)
        g10_json = surface_dir / f"g10_surface_{rid}.json"
        output_json(g10_json, result)

        # Read old G1 result for comparison
        old_path = surface_dir / f"surface_{rid}.json"
        old_result = None
        if old_path.exists():
            try:
                old_result = json.loads(old_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        g10_md = surface_dir / f"g10_surface_{rid}.md"
        output_md(g10_md, result, old_result)

        old_unk = old_result.get("unknown_pct", "N/A") if old_result else "N/A"
        new_unk = result.get("unknown_pct", "?")
        cs = result.get("cascade_stats", {})
        avg_score = cs.get("avg_cascade_score", "?")

        hi = cs.get("samples_high_risk", 0)
        reduction = ""
        if old_result and isinstance(old_unk, (int, float)) and isinstance(new_unk, (int, float)):
            diff = old_unk - new_unk
            reduction = f" (Δ{diff:+.1f}pp)"
            if diff < 0:
                reduction += " ⚠️ unknown WZGLĘDEM G1 wzrósł!"

        print(f"\n  ✓ {rid} — {result.get('route_name', '?')[:55]}")
        print(f"    G1 unknown: {old_unk}% → G10 unknown: {new_unk}%{reduction}")
        print(f"    avg cascade score: {avg_score} | high-risk samples: {hi}")
        print(f"    g10 JSON: {g10_json}")

    print(f"\n{'='*70}")
    print("G10 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
