#!/usr/bin/env python3
"""g13_risk_briefing.py — Risk-aware Briefing / Review Workflow dla Gravel Intelligence.

Tworzy briefing segmentów problematycznych z G10+G11+G12(+G8),
generuje plik decisions z domyślnymi rekomendacjami.

Usage:
    python3 scripts/g13_risk_briefing.py --route-id 55401067 --mode dry-run
    python3 scripts/g13_risk_briefing.py --route-id 55401067 --mode build
    python3 scripts/g13_risk_briefing.py --route-id 55395119 --mode build
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.manual_surface_overrides import (
    load_manual_overrides,
    find_overrides_for_route,
    compute_sample_kms,
    match_override_to_samples,
    apply_override_to_sample,
)

# ── Paths ─────────────────────────────────────────────────────────────────

ARTIFACTS_SURFACE = Path("/opt/qbot/artifacts/surface")
ARTIFACTS_OVERRIDES = Path("/opt/qbot/artifacts/surface_overrides")
ARTIFACTS_GRAVEL_REPORTS = Path("/opt/qbot/artifacts/gravel/reports")
ARTIFACTS_REVIEW = Path("/opt/qbot/artifacts/review")
DEFAULT_OVERRIDES_PATH = ARTIFACTS_OVERRIDES / "manual_surface_overrides.json"

RISK_THRESHOLD_SCORE = 0.60
MIN_SEGMENT_KM = 0.3  # 300 m minimalna długość problem segmentu
MAX_SAMPLE_GAP_KM = 1.0  # max przerwa między próbkami do łączenia
UNKNOWN_RISK_MIN_KM = 3.0  # unknown/data-risk minimalny ciągły dystans


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


def _score_to_label(score: float) -> str:
    if score <= 0.10: return "good"
    if score <= 0.30: return "acceptable"
    if score <= 0.55: return "caution"
    if score <= 0.75: return "risk"
    return "avoid"


def _score_to_severity(score: float) -> str:
    if score <= 0.10: return "low"
    if score <= 0.30: return "medium"
    if score <= 0.55: return "medium"
    if score <= 0.75: return "high"
    return "critical"


def _severity_rank(sev: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(sev, 0)


def _problem_id(route_id: str, idx: int) -> str:
    return f"g13_{route_id}_seg_{idx:03d}"


def _km_range_key(seg: dict) -> tuple:
    return (seg.get("start_km", 0), seg.get("end_km", 0))


# ── Load Inputs ───────────────────────────────────────────────────────────

def load_inputs(route_id: str) -> dict:
    """Load all available input data for a route.

    Returns dict with g10, g11, g12_data, g12_overrides, g8, overrides_list.
    """
    rid = str(route_id)
    result = {
        "route_id": rid,
        "g10": None,
        "g11": None,
        "g12_data": None,
        "g12_overrides": None,
        "g8": None,
        "overrides_list": [],
    }

    g10_path = ARTIFACTS_SURFACE / f"g10_surface_{rid}.json"
    g10 = _read_json(g10_path)
    if g10 and g10.get("ok"):
        result["g10"] = g10
        result["route_name"] = g10.get("route_name", "")
        result["distance_km"] = g10.get("distance_km", 0)

    g11_path = ARTIFACTS_SURFACE / f"g11_weather_surface_{rid}.json"
    g11 = _read_json(g11_path)
    if g11 and g11.get("ok"):
        result["g11"] = g11

    g12_path = ARTIFACTS_OVERRIDES / f"g12_surface_overridden_{rid}.json"
    g12 = _read_json(g12_path)
    if g12 and g12.get("ok"):
        result["g12_data"] = g12
        result["g12_overrides"] = g12.get("overrides", [])
        # If samples are redacted (null), we'll re-apply from G10
        if g12.get("samples") is not None:
            result["g12_has_samples"] = True

    g8_path = ARTIFACTS_GRAVEL_REPORTS / f"stage_gravel_report_{rid}.json"
    g8 = _read_json(g8_path)
    if g8:
        result["g8"] = g8

    # Load raw manual overrides
    all_ov = load_manual_overrides(DEFAULT_OVERRIDES_PATH)
    result["overrides_list"] = find_overrides_for_route(rid, all_ov)

    return result


# ── Build final samples with scores ────────────────────────────────────────

def build_samples(inputs: dict) -> list[dict]:
    """Build unified sample array with final scores.

    Priority: G12 override score > G11 weather score > G10 score.
    Returns samples with _approx_km, final_score, score_source, severity, etc.
    """
    g10 = inputs.get("g10")
    if not g10:
        return []

    raw_samples = g10.get("samples", [])
    total_km = g10.get("distance_km", 0)
    if not raw_samples:
        return []

    # Compute approximate km for each sample
    samples = compute_sample_kms(raw_samples, total_km)

    # Apply G11 weather if available (re-apply since G11 redacts samples)
    g11 = inputs.get("g11")
    if g11 and g11.get("weather"):
        from lib.weather_modifier import apply_weather_to_samples
        weather = g11["weather"]
        samples = apply_weather_to_samples(samples, weather, region="default")

    # Apply G12 manual overrides if available
    overrides_list = inputs.get("overrides", [])
    route_overrides = inputs.get("g12_overrides", [])
    # Use raw manual overrides for detailed data if G12 overrides exist
    manual_ov = inputs.get("overrides_list", [])

    for ov in manual_ov:
        match = match_override_to_samples(ov, samples)
        if not match["matched"]:
            continue
        for idx in match["matched_indices"]:
            if idx < len(samples):
                samples[idx] = apply_override_to_sample(samples[idx], ov, match)

    # Build final_score per sample
    for s in samples:
        # Priority: manual override > weather > base
        if s.get("manual_override_applied"):
            s["final_score"] = s.get("score_after_override") or s.get("score", 0)
            s["score_source"] = "g12_manual"
            s["final_severity"] = s.get("override_severity") or _score_to_severity(s["final_score"])
        elif s.get("weather_score") is not None:
            s["final_score"] = s["weather_score"]
            s["score_source"] = "g11"
            s["final_severity"] = _score_to_severity(s["final_score"])
        else:
            s["final_score"] = s.get("score", 0)
            s["score_source"] = "g10"
            s["final_severity"] = _score_to_severity(s["final_score"])

        s["final_label"] = _score_to_label(s["final_score"])

    return samples


# ── Identify Problem Segments ─────────────────────────────────────────────

def _split_at_override_boundaries(
    samples: list[dict], start_idx: int, end_idx: int,
) -> list[tuple[int, int]]:
    """Split a problem run at manual override boundaries.

    Returns list of (sub_start, sub_end) index ranges.
    Each range has a consistent override_id (empty or a single override).
    """
    ranges = []
    i = start_idx
    while i <= end_idx:
        # Determine current override group
        current_ov = samples[i].get("manual_override_id", "") or ""
        sub_start = i
        while i <= end_idx:
            s_ov = samples[i].get("manual_override_id", "") or ""
            if s_ov != current_ov:
                break
            i += 1
        sub_end = i - 1
        ranges.append((sub_start, sub_end))
    return ranges


def identify_problems(samples: list[dict]) -> list[dict]:
    """Find contiguous problem segments from samples.

    Problem = final_score >= RISK_THRESHOLD or manual_override_applied.
    Splits at manual override boundaries so each override gets its own segment.
    """
    if not samples:
        return []

    n = len(samples)
    problem_flags = []
    for s in samples:
        is_problem = (
            s.get("manual_override_applied")
            or s.get("final_score", 0) >= RISK_THRESHOLD_SCORE
        )
        problem_flags.append(is_problem)

    segments = []
    i = 0
    while i < n:
        if not problem_flags[i]:
            i += 1
            continue

        start_idx = i
        while i < n and problem_flags[i]:
            i += 1
        end_idx = i - 1

        # Split at override boundaries within this run
        sub_ranges = _split_at_override_boundaries(samples, start_idx, end_idx)

        for sub_start, sub_end in sub_ranges:
            first = samples[sub_start]
            last = samples[sub_end]
            start_km = first.get("_approx_km", 0)
            end_km = last.get("_approx_km_end", last.get("_approx_km", 0))
            length_km = end_km - start_km

            slice_samples = samples[sub_start:sub_end + 1]
            has_override = any(s.get("manual_override_applied") for s in slice_samples)

            if length_km < MIN_SEGMENT_KM and not has_override:
                continue

            scores = [s.get("final_score", 0) for s in slice_samples]
            severities = [s.get("final_severity", "low") for s in slice_samples]
            sources = set(s.get("score_source", "g10") for s in slice_samples)
            override_ids = list(set(
                s.get("manual_override_id", "") for s in slice_samples
                if s.get("manual_override_id")
            ))
            override_surfaces = list(set(
                s.get("override_surface", "") for s in slice_samples
                if s.get("override_surface")
            ))

            max_severity = max(severities, key=_severity_rank)
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)

            if has_override and override_surfaces:
                risk_type = override_surfaces[0]
            elif max_score >= 0.75:
                risk_type = "high_risk_surface"
            elif max_score >= 0.55:
                risk_type = "moderate_risk_surface"
            else:
                risk_type = "unknown_risk"

            segments.append({
                "start_km": round(start_km, 2),
                "end_km": round(end_km, 2),
                "length_km": round(length_km, 2),
                "sample_count": sub_end - sub_start + 1,
                "avg_score": round(avg_score, 4),
                "max_score": round(max_score, 4),
                "max_severity": max_severity,
                "score_sources": sorted(sources),
                "has_manual_override": has_override,
                "manual_override_ids": override_ids,
                "override_surfaces": override_surfaces,
                "risk_type": risk_type,
                "samples_slice": {
                    "start_idx": sub_start,
                    "end_idx": sub_end,
                },
            })

    return segments


def add_override_only_segments(segments: list[dict], overrides: list[dict]) -> list[dict]:
    """Add segments for manual overrides not already covered by sample-based segments."""
    existing = []
    for seg in segments:
        existing.append((seg["start_km"], seg["end_km"]))

    new_segs = []
    for ov in overrides:
        start = ov["start_km"]
        end = ov["end_km"]
        # Check if overlap already exists
        overlaps = False
        for es, ee in existing:
            if not (end <= es or start >= ee):
                overlaps = True
                break
        if not overlaps:
            new_segs.append({
                "start_km": start,
                "end_km": end,
                "length_km": round(end - start, 2),
                "sample_count": ov.get("matched_samples", 0),
                "avg_score": 0.85,
                "max_score": 0.85,
                "max_severity": "high",
                "score_sources": ["g12_manual"],
                "has_manual_override": True,
                "manual_override_ids": [ov.get("override_id")],
                "override_surfaces": [ov.get("override_surface", "unknown")],
                "risk_type": ov.get("override_surface", "unknown"),
                "samples_slice": None,
            })

    return segments + new_segs


def add_g8_risk_segments(segments: list[dict], g8: dict) -> list[dict]:
    """Add G8 risk segments not already covered."""
    g8_segments = g8.get("risk_segments", []) or []
    g8_top5 = g8.get("top5_segments", []) or []

    # Both G8 risk and top5 may have start_km/end_km
    all_g8 = list(g8_segments) + list(g8_top5)

    existing = []
    for seg in segments:
        existing.append((seg["start_km"], seg["end_km"]))

    for gs in all_g8:
        start = gs.get("start_km", 0) or 0
        end = gs.get("end_km", 0) or 0
        if end <= start:
            continue
        length = end - start
        if length < MIN_SEGMENT_KM:
            continue
        # Check overlap
        overlaps = False
        for es, ee in existing:
            if not (end <= es or start >= ee):
                overlaps = True
                break
        if not overlaps:
            segments.append({
                "start_km": round(start, 2),
                "end_km": round(end, 2),
                "length_km": round(length, 2),
                "sample_count": 0,
                "avg_score": gs.get("risk_score", 0.7) or 0.7,
                "max_score": gs.get("risk_score", 0.7) or 0.7,
                "max_severity": gs.get("severity", "medium"),
                "score_sources": ["g8"],
                "has_manual_override": False,
                "manual_override_ids": [],
                "override_surfaces": [],
                "risk_type": gs.get("risk_type", gs.get("dominant_surface", "unknown")),
                "samples_slice": None,
            })

    return segments


def enrich_segments(segments: list[dict], inputs: dict, route_id: str) -> list[dict]:
    """Add human-readable fields, suggested decisions, and karoo warnings."""
    g11 = inputs.get("g11")
    weather_note = ""
    if g11 and g11.get("weather"):
        w = g11["weather"]
        soil = w.get("soil_condition", "unknown")
        precip = w.get("precipitation_7d_total_mm", 0)
        weather_note = f"Soil: {soil}, opady 7d: {precip}mm"

    enriched = []
    for i, seg in enumerate(segments):
        pid = _problem_id(route_id, i)
        has_override = seg.get("has_manual_override", False)
        override_surfaces = seg.get("override_surfaces", [])
        risk_type = seg.get("risk_type", "unknown")
        severity = seg.get("max_severity", "medium")
        max_score = seg.get("max_score", 0)

        # Human summary
        if has_override:
            surf = override_surfaces[0] if override_surfaces else "unknown"
            human = f"Potwierdzony {surf} w lesie (km {seg['start_km']}–{seg['end_km']}). Uwaga: może być trudny przy suchości."
        elif risk_type == "high_risk_surface":
            human = f"Ryzyko złej nawierzchni na km {seg['start_km']}–{seg['end_km']}. Wskazana ostrożność."
        elif risk_type == "moderate_risk_surface":
            human = f"Umiarkowane ryzyko nawierzchni km {seg['start_km']}–{seg['end_km']}. Możliwy luźny materiał."
        else:
            human = f"Niepotwierdzona nawierzchnia km {seg['start_km']}–{seg['end_km']}. Sprawdź na mapie."

        if weather_note:
            human += f" Warunki: {weather_note}"

        # Suggested default decision
        if has_override and severity in ("high", "critical"):
            suggested = "ACCEPT_WARNING"
        elif severity == "critical":
            suggested = "REVIEW"
        elif severity == "high":
            suggested = "ACCEPT_WARNING"
        elif severity == "medium":
            suggested = "REVIEW"
        else:
            suggested = "SUPPRESS"

        # Recommended action
        if suggested == "ACCEPT_WARNING":
            action = "Oznacz jako warning w GPX — jedź świadomie"
        elif suggested == "REVIEW":
            action = "Sprawdź na mapie przed jazdą"
        elif suggested == "OMIT":
            action = "Rozważ ominięcie tego odcinka"
        elif suggested == "SUPPRESS":
            action = "Brak akcji — pomiń w briefingu"
        else:
            action = "Weź pod uwagę przed jazdą"

        # Karoo warning candidates
        score_sources = seg.get("score_sources", ["g10"])
        if has_override:
            surf_label = override_surfaces[0] if override_surfaces else "unknown"
            kw_name = f"⚠️ {surf_label.title()} km {seg['start_km']:.0f}"
            kw_desc = f"{surf_label.title()} na km {seg['start_km']:.0f}–{seg['end_km']:.0f} ({seg['length_km']:.1f} km). "
            if weather_note:
                kw_desc += weather_note + ". "
            kw_desc += "Potwierdzone przez użytkownika." if has_override else "Ryzyko z danych."
        elif risk_type == "high_risk_surface":
            kw_name = f"⚠️ Trudna nawierzchnia km {seg['start_km']:.0f}"
            kw_desc = f"Trudna/ryzykowna nawierzchnia na km {seg['start_km']:.0f}–{seg['end_km']:.0f} ({seg['length_km']:.1f} km). Ostrożnie."
        elif risk_type == "unknown_risk":
            kw_name = f"❓ Niepotwierdzona naw. km {seg['start_km']:.0f}"
            kw_desc = f"Brak danych o nawierzchni na km {seg['start_km']:.0f}–{seg['end_km']:.0f} ({seg['length_km']:.1f} km). Sprawdź."
        else:
            kw_name = f"ℹ️ Umiarkowane ryzyko km {seg['start_km']:.0f}"
            kw_desc = f"Umiarkowane ryzyko nawierzchni km {seg['start_km']:.0f}–{seg['end_km']:.0f} ({seg['length_km']:.1f} km)."

        enriched.append({
            "problem_id": pid,
            "route_id": route_id,
            "start_km": seg["start_km"],
            "end_km": seg["end_km"],
            "length_km": seg["length_km"],
            "final_score": seg["max_score"],
            "avg_score": seg["avg_score"],
            "score_source": score_sources[0] if score_sources else "g10",
            "severity": severity,
            "risk_type": risk_type,
            "manual_override_applied": has_override,
            "override_surface": override_surfaces[0] if override_surfaces else None,
            "weather_note": weather_note if weather_note else None,
            "human_summary": human,
            "suggested_default_decision": suggested,
            "recommended_action": action,
            "karoo_warning_name_candidate": kw_name,
            "karoo_warning_desc_candidate": kw_desc,
        })

    # Sort by priority: override > severity > score
    enriched.sort(key=lambda s: (
        0 if s["manual_override_applied"] else 1,
        -_severity_rank(s["severity"]),
        -s["final_score"],
    ))

    # Reassign problem_ids after sorting
    for i, seg in enumerate(enriched):
        seg["problem_id"] = _problem_id(route_id, i)

    return enriched


# ── Default Decisions ─────────────────────────────────────────────────────

def generate_default_decisions(segments: list[dict], route_id: str) -> dict:
    """Generate initial decisions JSON from suggested defaults."""
    decisions = []
    for seg in segments:
        decisions.append({
            "problem_id": seg["problem_id"],
            "decision": seg["suggested_default_decision"],
            "note": seg.get("human_summary", "")[:200],
            "created_by": "qbot_g13",
        })

    return {
        "route_id": str(route_id),
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
        "decisions": decisions,
    }


# ── Output Builders ───────────────────────────────────────────────────────

def build_json_output(
    route_id: str,
    inputs: dict,
    segments: list[dict],
    decisions: dict,
    mode: str,
) -> dict:
    """Build the full JSON briefing output."""
    g10 = inputs.get("g10")
    g11 = inputs.get("g11")
    g12_data = inputs.get("g12_data")

    return {
        "ok": True,
        "status": "OK",
        "mode": mode,
        "route_id": str(route_id),
        "route_name": inputs.get("route_name", ""),
        "distance_km": inputs.get("distance_km", 0),
        "source": "g13_risk_briefing",
        "g10_source": f"g10_surface_{route_id}.json" if g10 else None,
        "g11_source": f"g11_weather_surface_{route_id}.json" if g11 else None,
        "g12_source": f"g12_surface_overridden_{route_id}.json" if g12_data else None,
        "weather": g11.get("weather") if g11 else None,
        "weather_stats": g11.get("weather_stats") if g11 else None,
        "problem_count": len(segments),
        "problems": segments,
        "decisions": decisions.get("decisions", []),
        "generated_at": _iso_now(),
        "generator": "g13_risk_briefing.py",
    }


def build_md_output(
    route_id: str,
    inputs: dict,
    segments: list[dict],
    decisions: dict,
    mode: str,
) -> str:
    """Build a human-readable Markdown briefing."""
    lines = []
    route_name = inputs.get("route_name", "?")
    distance_km = inputs.get("distance_km", 0)
    g11 = inputs.get("g11")

    lines.append(f"# Risk-aware Briefing: {route_name}")
    lines.append("")
    lines.append(f"**Route ID:** {route_id}")
    lines.append(f"**Distance:** {distance_km:.2f} km")
    lines.append(f"**Mode:** {mode}")
    lines.append(f"**Generated:** {_iso_now()}")
    lines.append("")

    # Weather
    if g11 and g11.get("weather"):
        w = g11["weather"]
        lines.append("## 🌤️ Warunki pogodowe")
        lines.append("")
        lines.append(f"| Parametr | Wartość |")
        lines.append(f"|----------|---------|")
        lines.append(f"| Soil condition | {w.get('soil_condition', '?')} |")
        lines.append(f"| Opady 7d | {w.get('precipitation_7d_total_mm', '?')} mm |")
        lines.append(f"| Prognoza 3d | {w.get('forecast_3d_total_mm', '?')} mm |")
        lines.append(f"| Uwagi | {w.get('note', '')} |")
        lines.append("")

    # Summary
    manual_count = sum(1 for s in segments if s.get("manual_override_applied"))
    high_count = sum(1 for s in segments if s.get("severity") == "high")
    crit_count = sum(1 for s in segments if s.get("severity") == "critical")
    unknown_count = sum(1 for s in segments if s.get("risk_type") == "unknown_risk")

    lines.append("## 📋 Podsumowanie")
    lines.append("")
    lines.append(f"| Kategoria | Liczba |")
    lines.append(f"|-----------|--------|")
    lines.append(f"| Potwierdzone przez użytkownika | {manual_count} |")
    lines.append(f"| Critical | {crit_count} |")
    lines.append(f"| High risk | {high_count} |")
    lines.append(f"| Niepotwierdzone (data-risk) | {unknown_count} |")
    lines.append(f"| **Razem problemów** | **{len(segments)}** |")
    lines.append("")

    if not segments:
        lines.append("✅ **Brak segmentów problematycznych.** Trasa wydaje się bezpieczna.")
        lines.append("")

    # Manual confirmed sections
    manual_segs = [s for s in segments if s.get("manual_override_applied")]
    if manual_segs:
        lines.append("## ✅ Potwierdzone przez użytkownika")
        lines.append("")
        lines.append("| # | KM | Długość | Typ | Score | Sugestia |")
        lines.append("|---|-----|---------|------|-------|----------|")
        for s in manual_segs:
            surf = s.get("override_surface") or s.get("risk_type", "?")
            lines.append(
                f"| {s['problem_id']} | {s['start_km']:.1f}–{s['end_km']:.1f} | "
                f"{s['length_km']:.2f} km | {surf} | {s['final_score']:.2f} | "
                f"{s['suggested_default_decision']} |"
            )
        lines.append("")
        for s in manual_segs:
            lines.append(f"**{s['problem_id']}:** {s['human_summary']}")
            lines.append(f"  → Sugerowana decyzja: **{s['suggested_default_decision']}**")
            lines.append(f"  → {s['recommended_action']}")
            if s.get("karoo_warning_name_candidate"):
                lines.append(f"  → Karoo warning: {s['karoo_warning_name_candidate']}")
            lines.append("")

    # Data risk sections
    data_segs = [s for s in segments if not s.get("manual_override_applied") and s.get("severity") in ("high", "critical")]
    if data_segs:
        lines.append("## ⚠️ Ryzyko z danych (high/critical)")
        lines.append("")
        lines.append("| # | KM | Długość | Severity | Score | Sugestia |")
        lines.append("|---|-----|---------|----------|-------|----------|")
        for s in data_segs:
            lines.append(
                f"| {s['problem_id']} | {s['start_km']:.1f}–{s['end_km']:.1f} | "
                f"{s['length_km']:.2f} km | {s['severity']} | {s['final_score']:.2f} | "
                f"{s['suggested_default_decision']} |"
            )
        lines.append("")

    # Unknown / data-risk
    unknown_segs = [s for s in segments if s.get("risk_type") == "unknown_risk"]
    if unknown_segs:
        lines.append("## ❓ Niepotwierdzona nawierzchnia (data-risk)")
        lines.append("")
        lines.append("| # | KM | Długość | Score | Sugestia |")
        lines.append("|---|-----|---------|-------|----------|")
        for s in unknown_segs:
            lines.append(
                f"| {s['problem_id']} | {s['start_km']:.1f}–{s['end_km']:.1f} | "
                f"{s['length_km']:.2f} km | {s['final_score']:.2f} | "
                f"{s['suggested_default_decision']} |"
            )
        lines.append("")

    # Medium/low data risk
    medium_segs = [s for s in segments if not s.get("manual_override_applied") and s.get("severity") in ("medium", "low")]
    if medium_segs:
        lines.append("## 📊 Umiarkowane/niskie ryzyko")
        lines.append("")
        lines.append("| # | KM | Długość | Severity | Score | Sugestia |")
        lines.append("|---|-----|---------|----------|-------|----------|")
        for s in medium_segs:
            lines.append(
                f"| {s['problem_id']} | {s['start_km']:.1f}–{s['end_km']:.1f} | "
                f"{s['length_km']:.2f} km | {s['severity']} | {s['final_score']:.2f} | "
                f"{s['suggested_default_decision']} |"
            )
        lines.append("")

    # Recommendation
    lines.append("## 💡 Rekomendacja")
    lines.append("")
    if len(segments) == 0:
        lines.append("✅ Trasa bezpieczna. Jedź bez obaw.")
    elif manual_count > 0 and crit_count == 0:
        lines.append("Trasa ma potwierdzone odcinki trudne. Zalecam jazdę świadomą (RIDE) z uwzględnieniem warningów.")
    elif crit_count > 0 or high_count > 2:
        lines.append("Trasa zawiera kilka trudnych odcinków. Rozważ objazdy (OMIT) dla krytycznych segmentów. "
                      "Dla pozostałych — ACCEPT_WARNING.")
    elif unknown_count > 2:
        lines.append("Kilka odcinków z niepotwierdzoną nawierzchnią. Sprawdź na mapie (REVIEW) przed jazdą.")
    else:
        lines.append("Jedź świadomie. Zwróć uwagę na oznaczone segmenty.")

    lines.append("")
    lines.append(f"---")
    lines.append(f"*Briefing wygenerowany przez G13 — {_iso_now()}*")
    lines.append(f"*Decyzje: /opt/qbot/artifacts/review/review_decisions_{route_id}.json*")

    return "\n".join(lines)


# ── Main Pipeline ─────────────────────────────────────────────────────────

def run_briefing(route_id: str, mode: str = "dry-run") -> dict:
    """Run the full G13 briefing pipeline."""
    rid = str(route_id)
    print(f"  Loading inputs for {rid}...")

    inputs = load_inputs(rid)
    if not inputs.get("g10"):
        return {"ok": False, "status": "ERROR", "error": f"G10 data not found for {rid}"}

    route_name = inputs.get("route_name", "")
    distance_km = inputs.get("distance_km", 0)
    print(f"  Route: {route_name} ({distance_km:.2f} km)")

    # Build unified samples with final scores
    print(f"  Building unified samples...")
    samples = build_samples(inputs)
    print(f"    {len(samples)} samples processed")

    # Identify problem segments from samples
    print(f"  Identifying problem segments...")
    segments = identify_problems(samples)
    print(f"    {len(segments)} sample-based problem segments")

    # Add override-only segments not covered by samples
    overrides = inputs.get("g12_overrides", []) or inputs.get("overrides_list", [])
    if overrides:
        before = len(segments)
        segments = add_override_only_segments(segments, overrides)
        print(f"    Added {len(segments) - before} override-only segments")

    # Add G8 risk segments not covered
    g8 = inputs.get("g8")
    if g8:
        before = len(segments)
        segments = add_g8_risk_segments(segments, g8)
        print(f"    Added {len(segments) - before} G8 risk segments")

    # Enrich with human-readable fields and suggestions
    segments = enrich_segments(segments, inputs, rid)
    print(f"    Total: {len(segments)} enriched problem segments")

    # Generate default decisions
    decisions = generate_default_decisions(segments, rid)
    print(f"    {len(decisions.get('decisions', []))} default decisions")

    # Build outputs
    json_out = build_json_output(rid, inputs, segments, decisions, mode)
    md_out = build_md_output(rid, inputs, segments, decisions, mode)

    # Write outputs in build mode
    if mode == "build":
        json_path = ARTIFACTS_REVIEW / f"review_briefing_{rid}.json"
        md_path = ARTIFACTS_REVIEW / f"review_briefing_{rid}.md"
        decisions_path = ARTIFACTS_REVIEW / f"review_decisions_{rid}.json"

        _write_json(json_path, json_out)
        _write_md(md_path, md_out)
        _write_json(decisions_path, decisions)

        print(f"  Output written:")
        print(f"    JSON: {json_path}")
        print(f"    MD:   {md_path}")
        print(f"    Decisions: {decisions_path}")

    return json_out


def main():
    p = argparse.ArgumentParser(description="G13 Risk-aware Briefing / Review Workflow")
    p.add_argument("--route-id", required=True, help="Garmin route ID")
    p.add_argument("--mode", choices=["dry-run", "build"], default="dry-run")

    args = p.parse_args()

    print("=" * 70)
    print("G13 Risk-aware Briefing / Review Workflow")
    print("=" * 70)
    print(f"  Route ID: {args.route_id}")
    print(f"  Mode:     {args.mode}")
    print()

    result = run_briefing(args.route_id, mode=args.mode)

    if not result.get("ok"):
        print(f"  ERROR: {result.get('error', 'Unknown error')}")
        sys.exit(1)

    # Print summary
    segments = result.get("problems", [])
    manual_count = sum(1 for s in segments if s.get("manual_override_applied"))
    high_crit = sum(1 for s in segments if s.get("severity") in ("high", "critical"))
    unknown_count = sum(1 for s in segments if s.get("risk_type") == "unknown_risk")

    print()
    print(f"  Total problems: {len(segments)}")
    print(f"    Manual confirmed: {manual_count}")
    print(f"    High/Critical: {high_crit}")
    print(f"    Unknown/data-risk: {unknown_count}")
    print()

    if segments:
        print(f"  {'Problem ID':<30} {'KM':<12} {'Severity':<10} {'Score':<7} {'Decision':<18}")
        print(f"  {'-'*30} {'-'*12} {'-'*10} {'-'*7} {'-'*18}")
        for s in segments[:10]:
            km = f"{s['start_km']:.1f}–{s['end_km']:.1f}"
            flag = "✅" if s.get("manual_override_applied") else " "
            print(f"  {flag} {s['problem_id']:<28} {km:<12} {s['severity']:<10} {s['final_score']:<7.2f} {s['suggested_default_decision']:<18}")
        if len(segments) > 10:
            print(f"  ... and {len(segments) - 10} more")

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
