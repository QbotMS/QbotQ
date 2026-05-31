#!/usr/bin/env python3
"""manual_surface_overrides.py — G12 Manual Surface Overrides Engine.

Mechanizm ręcznych korekt nawierzchni/score'ów segmentów na podstawie
obserwacji użytkownika po jeździe (ride_after_action).

Zależności:
  - G10: /opt/qbot/artifacts/surface/g10_surface_{route_id}.json
  - G11: /opt/qbot/artifacts/surface/g11_weather_surface_{route_id}.json (opcjonalnie)

Usage:
    from lib.manual_surface_overrides import (
        load_manual_overrides,
        apply_overrides_to_route,
        override_output_paths,
    )
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────

ALLOWED_OVERRIDE_SURFACES = {
    "asphalt", "paved", "gravel", "compacted", "dirt", "ground",
    "sand", "mud", "grass", "mixed", "unknown",
}

ALLOWED_RIDEABILITY = {
    "easy", "normal", "hard", "very_hard", "hike_a_bike",
}

ALLOWED_SEVERITY = {"low", "medium", "high", "critical", None}

ALLOWED_CONFIDENCE = {
    "user_confirmed", "photo_confirmed", "ride_after_action", "low",
}

ALLOWED_SOURCE = {
    "user_manual", "ride_after_action", "mapillary", "satellite",
    "osm_edit", "qbot_review",
}

ARTIFACTS_DIR = Path("/opt/qbot/artifacts/surface")
OVERRIDES_DIR = Path("/opt/qbot/artifacts/surface_overrides")
DEFAULT_OVERRIDES_PATH = OVERRIDES_DIR / "manual_surface_overrides.json"

# Score boundaries for override enforcement
SAND_MUD_MIN_SCORE = 0.85
ASPHALT_PAVED_MAX_SCORE = 0.15

SEVERITY_RIDEABILITY_MAP = {
    "hike_a_bike": "critical",
    "very_hard": "high",
    "hard": "high",
}


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


# ── Load & Validate Overrides ─────────────────────────────────────────────

def load_manual_overrides(
    path: str | Path | None = None,
) -> list[dict]:
    """Load manual surface overrides from JSON file.

    Returns list of override records, or empty list if file not found/invalid.
    """
    if path is None:
        path = DEFAULT_OVERRIDES_PATH
    data = _read_json(Path(path))
    if not data or not isinstance(data, dict):
        return []
    overrides = data.get("overrides", [])
    if not isinstance(overrides, list):
        return []
    valid = []
    for o in overrides:
        err = validate_override(o)
        if err:
            continue
        valid.append(o)
    return valid


def validate_override(record: dict) -> str | None:
    """Validate a single override record. Returns error string or None if OK."""
    required = ["override_id", "route_id", "start_km", "end_km",
                "override_surface", "rideability"]
    for field in required:
        if field not in record or record[field] is None:
            return f"Missing required field: {field}"

    if record["override_surface"] not in ALLOWED_OVERRIDE_SURFACES:
        return f"Invalid override_surface: {record['override_surface']}"

    if record["rideability"] not in ALLOWED_RIDEABILITY:
        return f"Invalid rideability: {record['rideability']}"

    sev = record.get("severity_override")
    if sev not in ALLOWED_SEVERITY:
        return f"Invalid severity_override: {sev}"

    conf = record.get("confidence", "low")
    if conf not in ALLOWED_CONFIDENCE:
        return f"Invalid confidence: {conf}"

    src = record.get("source", "user_manual")
    if src not in ALLOWED_SOURCE:
        return f"Invalid source: {src}"

    if record["start_km"] >= record["end_km"]:
        return "start_km must be < end_km"

    return None


def find_overrides_for_route(
    route_id: str,
    overrides: list[dict],
) -> list[dict]:
    """Filter overrides matching the given route_id."""
    route_id_str = str(route_id)
    return [o for o in overrides if str(o.get("route_id", "")) == route_id_str]


# ── Segment/Sample Matching ───────────────────────────────────────────────

def compute_sample_kms(
    samples: list[dict],
    total_distance_km: float,
) -> list[dict]:
    """Add approximate km position to each G10 sample.

    G10 samples are evenly spaced along the route. Approx km = i * step.
    """
    n = len(samples)
    if n == 0:
        return samples
    step = total_distance_km / n
    result = []
    for i, s in enumerate(samples):
        s = dict(s)
        s["_approx_km"] = round(i * step, 3)
        s["_approx_km_end"] = round((i + 1) * step, 3)
        result.append(s)
    return result


def match_override_to_samples(
    override: dict,
    samples: list[dict],
) -> dict:
    """Match a single override to samples.

    Returns dict with:
      - matched_samples: list of sample indices that overlap with override range
      - overlap_km: total KM of overlap
      - overlap_pct: percentage of override range covered by samples
      - note: human-readable match description
    """
    start_km = override["start_km"]
    end_km = override["end_km"]
    override_len = end_km - start_km

    matched_indices = []
    for i, s in enumerate(samples):
        s_km = s.get("_approx_km", 0)
        s_km_end = s.get("_approx_km_end", s_km)
        # Check overlap: sample range intersects override range
        if s_km_end > start_km and s_km < end_km:
            matched_indices.append(i)

    if not matched_indices:
        return {
            "matched": False,
            "matched_indices": [],
            "overlap_km": 0.0,
            "overlap_pct": 0.0,
            "note": f"Override km {start_km}–{end_km} nie pasuje do żadnego segmentu",
        }

    # Calculate overlap
    overlap_start = max(start_km, samples[matched_indices[0]].get("_approx_km", 0))
    overlap_end = min(end_km, samples[matched_indices[-1]].get("_approx_km_end", end_km))
    overlap_km = max(0, overlap_end - overlap_start)
    overlap_pct = round(overlap_km / override_len * 100, 1) if override_len > 0 else 0

    return {
        "matched": True,
        "matched_indices": matched_indices,
        "overlap_km": round(overlap_km, 3),
        "overlap_pct": overlap_pct,
        "note": f"Dopasowano {len(matched_indices)} próbek, overlap={overlap_km}km ({overlap_pct}%)",
    }


# ── Apply Override Rules ──────────────────────────────────────────────────

def apply_override_to_sample(
    sample: dict,
    override: dict,
    match_info: dict,
) -> dict:
    """Apply a single override to one sample.

    Returns modified sample with added manual_override_* fields.
    Original score preserved as original_score_before_override.
    """
    result = dict(sample)
    original_score = sample.get("score") or sample.get("weather_score") or sample.get("base_score") or 0

    result["manual_override_applied"] = True
    result["manual_override_id"] = override["override_id"]
    result["original_score_before_override"] = round(original_score, 4)

    # Determine final score based on override rules
    override_surface = override["override_surface"]
    rideability = override["rideability"]
    confidence = override.get("confidence", "low")
    severity_override = override.get("severity_override")

    new_score = original_score

    # Rule: sand/mud + user_confirmed/ride_after_action → score >= SAND_MUD_MIN_SCORE
    if override_surface in ("sand", "mud") and confidence in ("user_confirmed", "ride_after_action"):
        new_score = max(new_score, SAND_MUD_MIN_SCORE)

    # Rule: asphalt/paved + user_confirmed → score <= ASPHALT_PAVED_MAX_SCORE
    if override_surface in ("asphalt", "paved") and confidence == "user_confirmed":
        new_score = min(new_score, ASPHALT_PAVED_MAX_SCORE)

    # Clamp
    new_score = max(0.0, min(1.0, new_score))
    new_score = round(new_score, 4)

    # Determine severity from rideability
    final_severity = severity_override
    if rideability in SEVERITY_RIDEABILITY_MAP:
        mapped_sev = SEVERITY_RIDEABILITY_MAP[rideability]
        if final_severity is None or _severity_rank(mapped_sev) > _severity_rank(final_severity):
            final_severity = mapped_sev

    # Determine class_label from new score
    new_label = _score_to_label(new_score)

    result["score"] = new_score
    result["score_after_override"] = new_score
    result["class_label"] = new_label
    result["override_severity"] = final_severity
    result["override_surface"] = override_surface
    result["override_rideability"] = rideability
    result["override_note"] = override.get("note", "")
    result["override_confidence"] = confidence
    result["override_source"] = override.get("source", "user_manual")
    result["override_overlap_km"] = match_info.get("overlap_km", 0)
    result["override_overlap_pct"] = match_info.get("overlap_pct", 0)
    result["override_match_note"] = match_info.get("note", "")

    return result


def _severity_rank(sev: str | None) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(sev, -1)


def _score_to_label(score: float) -> str:
    if score <= 0.10:
        return "good"
    if score <= 0.30:
        return "acceptable"
    if score <= 0.55:
        return "caution"
    if score <= 0.75:
        return "risk"
    return "avoid"


# ── Main Apply Function ───────────────────────────────────────────────────

def apply_overrides_to_route(
    route_id: str,
    overrides_path: str | Path | None = None,
    input_prefer: str = "g10",
    mode: str = "dry-run",
) -> dict:
    """Apply manual surface overrides to G10/G11 data for a route.

    Args:
        route_id: Garmin route ID
        overrides_path: Path to manual_surface_overrides.json
        input_prefer: "g10" or "g11" — which base data to use
        mode: "dry-run" | "build"

    Returns dict with result + report data.
    """
    route_id_str = str(route_id)
    ts = _iso_now()

    # 1. Load overrides
    all_overrides = load_manual_overrides(overrides_path)
    route_overrides = find_overrides_for_route(route_id_str, all_overrides)

    # 2. Load G10 data
    g10_path = ARTIFACTS_DIR / f"g10_surface_{route_id_str}.json"
    g10_data = _read_json(g10_path)
    if not g10_data:
        return {
            "ok": False,
            "status": "ERROR",
            "route_id": route_id_str,
            "error": f"G10 data not found: {g10_path}",
        }

    raw_samples = g10_data.get("samples", [])
    total_distance_km = g10_data.get("distance_km", 0)

    # 3. Compute approx km for samples
    samples = compute_sample_kms(raw_samples, total_distance_km)

    # 4. Load G11 data (optional)
    g11_path = ARTIFACTS_DIR / f"g11_weather_surface_{route_id_str}.json"
    g11_data = _read_json(g11_path)

    # If G11 preferred and available, use weather-modified scores as base
    use_g11 = input_prefer == "g11" and g11_data is not None
    if use_g11:
        # Get weather context
        weather = g11_data.get("weather", {})
        weather_stats = g11_data.get("weather_stats", {})
        # Re-apply weather to get modified samples (G11 redacts them from JSON)
        from lib.weather_modifier import apply_weather_to_samples
        samples = apply_weather_to_samples(samples, weather, region="default")
    else:
        weather = {}
        weather_stats = {}

    # 5. Match & apply overrides
    overridden_samples = list(samples)
    applied_overrides = []
    unmatched_overrides = []
    changed_count = 0

    for ov in route_overrides:
        match = match_override_to_samples(ov, overridden_samples)
        if not match["matched"]:
            unmatched_overrides.append({
                "override_id": ov["override_id"],
                "note": match["note"],
            })
            continue

        for idx in match["matched_indices"]:
            if idx < len(overridden_samples):
                orig_score = overridden_samples[idx].get("score")
                orig_severity = overridden_samples[idx].get("override_severity") or \
                                overridden_samples[idx].get("severity", "low")
                overridden_samples[idx] = apply_override_to_sample(
                    overridden_samples[idx], ov, match,
                )
                new_score = overridden_samples[idx]["score_after_override"]
                if orig_score != new_score:
                    changed_count += 1

        applied_overrides.append({
            "override_id": ov["override_id"],
            "start_km": ov["start_km"],
            "end_km": ov["end_km"],
            "override_surface": ov["override_surface"],
            "rideability": ov["rideability"],
            "matched_samples": len(match["matched_indices"]),
            "overlap_km": match["overlap_km"],
            "overlap_pct": match["overlap_pct"],
        })

    # 6. Build result
    g10_used = g10_path.name if g10_data else None
    g11_used = g11_path.name if g11_data and use_g11 else None

    result = {
        "ok": True,
        "status": "OK",
        "mode": mode,
        "route_id": route_id_str,
        "route_name": g10_data.get("route_name", ""),
        "source": "g12_manual_surface_overrides",
        "g10_source": g10_used,
        "g11_source": g11_used,
        "total_distance_km": total_distance_km,
        "total_samples": len(samples),
        "route_overrides_count": len(route_overrides),
        "applied_overrides_count": len(applied_overrides),
        "unmatched_overrides_count": len(unmatched_overrides),
        "samples_changed": changed_count,
        "overrides": applied_overrides,
        "unmatched_overrides": unmatched_overrides if unmatched_overrides else None,
        "samples": overridden_samples,
        "weather": weather if weather else None,
        "weather_stats": weather_stats if weather_stats else None,
        "generated_at": ts,
        "generator": "g12_manual_surface_overrides.py",
        "candidate_overrides_created": True,
        "production_enabled": False,
    }

    return result


# ── Input/Output Paths ────────────────────────────────────────────────────

def override_output_paths(route_id: str) -> tuple[Path, Path]:
    """Return (json_path, md_path) for G12 output files."""
    json_path = OVERRIDES_DIR / f"g12_surface_overridden_{route_id}.json"
    md_path = OVERRIDES_DIR / f"g12_surface_overridden_{route_id}.md"
    return json_path, md_path


def write_g12_output(result: dict, mode: str = "dry-run") -> dict:
    """Write G12 output JSON and MD report.

    In dry-run mode, only returns paths without writing.
    """
    route_id = result["route_id"]
    json_path, md_path = override_output_paths(route_id)

    if mode == "dry-run":
        return {
            "json_written": False,
            "md_written": False,
            "json_path": str(json_path),
            "md_path": str(md_path),
            "mode": "dry-run",
        }

    # Write JSON (without raw samples when production_enabled=False to save space)
    json_out = dict(result)
    if not result.get("production_enabled", False):
        json_out["sample_count"] = len(json_out.get("samples", []))
        json_out["samples"] = None  # redact samples in candidate mode
    else:
        json_out["samples"] = result.get("samples")

    _write_json(json_path, json_out)

    # Write MD report
    md_content = build_md_report(result, print_samples=True)
    _write_md(md_path, md_content)

    return {
        "json_written": True,
        "md_written": True,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "mode": mode,
    }


# ── Markdown Report Builder ───────────────────────────────────────────────

def build_md_report(result: dict, print_samples: bool = False) -> str:
    """Build a Markdown report from the G12 result dict."""
    lines = []
    lines.append("# G12 Manual Surface Overrides")
    lines.append("")
    lines.append(f"**Route:** {result.get('route_name', '?')} (ID: {result['route_id']})")
    lines.append(f"**Distance:** {result['total_distance_km']:.2f} km")
    lines.append(f"**Samples:** {result['total_samples']}")
    lines.append(f"**Mode:** {result.get('mode', '?')}")
    lines.append(f"**Generated:** {result.get('generated_at', '?')}")
    lines.append(f"**G10 source:** {result.get('g10_source', 'N/A')}")
    lines.append(f"**G11 source:** {result.get('g11_source', 'N/A')}")
    lines.append(f"**Production enabled:** {result.get('production_enabled', False)}")
    lines.append(f"**Candidate overrides:** {result.get('candidate_overrides_created', False)}")
    lines.append("")

    # Override summary
    lines.append("## Override Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Route overrides found | {result['route_overrides_count']} |")
    lines.append(f"| Applied | {result['applied_overrides_count']} |")
    lines.append(f"| Unmatched | {result.get('unmatched_overrides_count', 0)} |")
    lines.append(f"| Samples changed | {result['samples_changed']} |")
    lines.append("")

    # Applied overrides detail
    if result.get("overrides"):
        lines.append("## Applied Overrides")
        lines.append("")
        for ov in result["overrides"]:
            lines.append(f"### {ov['override_id']}")
            lines.append("")
            lines.append(f"| Field | Value |")
            lines.append(f"|-------|-------|")
            lines.append(f"| KM range | {ov['start_km']} – {ov['end_km']} km |")
            lines.append(f"| Override surface | {ov['override_surface']} |")
            lines.append(f"| Rideability | {ov.get('rideability', '?')} |")
            lines.append(f"| Matched samples | {ov['matched_samples']} |")
            lines.append(f"| Overlap | {ov['overlap_km']} km ({ov['overlap_pct']}%) |")
            lines.append("")

    # Unmatched overrides
    if result.get("unmatched_overrides"):
        lines.append("## Unmatched Overrides (Warning)")
        lines.append("")
        lines.append("The following overrides did not match any segment:")
        lines.append("")
        for uo in result["unmatched_overrides"]:
            lines.append(f"- {uo['override_id']}: {uo['note']}")
        lines.append("")

    # Sample-level detail (if samples available and requested)
    if print_samples and result.get("samples"):
        samples = result["samples"]
        overridden = [s for s in samples if s.get("manual_override_applied")]
        if overridden:
            lines.append(f"## Override-Flagged Samples Detail ({len(overridden)} samples)")
            lines.append("")
            lines.append("| # | Approx km | Score Before | Score After | Surface Override | Severity | Confidence | Note |")
            lines.append("|---|-----------|-------------|-------------|------------------|----------|------------|------|")
            for i, s in enumerate(overridden):
                km = s.get("_approx_km", 0)
                orig = s.get("original_score_before_override", 0)
                after = s.get("score_after_override", 0)
                surf = s.get("override_surface", "-")
                sev = s.get("override_severity", "-")
                conf = s.get("override_confidence", "-")
                note = (s.get("override_note", "") or "")[:60]
                lines.append(f"| {i} | {km:.2f} | {orig:.4f} | {after:.4f} | {surf} | {sev} | {conf} | {note} |")
            lines.append("")

        # Score comparison for changed samples
        changed_count = result.get("samples_changed", 0)
        lines.append("## Score Before/After Comparison")
        lines.append("")
        lines.append("```")
        before_scores = [s.get("original_score_before_override", 0) for s in overridden]
        after_scores = [s.get("score_after_override", 0) for s in overridden]
        if before_scores:
            lines.append(f"  Override-flagged samples: {len(overridden)}")
            lines.append(f"  Score actually changed:   {changed_count}")
            lines.append(f"  Avg score before:         {sum(before_scores)/len(before_scores):.4f}")
            lines.append(f"  Avg score after:          {sum(after_scores)/len(after_scores):.4f}")
            lines.append(f"  Delta:                    {sum(after_scores)/len(after_scores) - sum(before_scores)/len(before_scores):+.4f}")
        lines.append("```")
        lines.append("")

    # Weather context
    if result.get("weather"):
        lines.append("## Weather Context (G11)")
        lines.append("")
        w = result["weather"]
        lines.append(f"- Soil condition: {w.get('soil_condition', 'unknown')}")
        lines.append(f"- Precipitation 7d: {w.get('precipitation_7d_total_mm', '?')} mm")
        lines.append(f"- Note: {w.get('note', '')}")
        lines.append("")

    # Candidates disclaimer
    if not result.get("production_enabled", False):
        lines.append("## ⚠️ Candidate Mode")
        lines.append("")
        lines.append("These overrides are **candidates only** — not applied as production.")
        lines.append("Run with `--mode build` to persist the output files.")
        lines.append("No G10/G11 original data was modified.")
        lines.append("")

    return "\n".join(lines)
