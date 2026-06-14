"""Climb detection and categorization from RWGPS track_points.

Uses classic climb scoring: score = elevation_gain * (avg_grade/10)^2
Categories: HC>=8000, Cat1>=5000, Cat2>=3000, Cat3>=1500, Cat4>=500
"""
from __future__ import annotations
from typing import Any
import math

MIN_GRADE = 2.0   # min avg grade % (podwyzszone z 1% — eliminuje mikro)
MIN_LENGTH_M = 300.0  # min 300m (podwyzszone z 100m)
MIN_ELEV_M = 10.0     # min 10m gain (podwyzszone z 5m)
GAP_FILL_M = 80.0     # lacz segmenty przedzielone <80m plaszczyzny

def _categorize(length_m: float, avg_grade: float) -> str:
    """Prosta kategoryzacja jak RWGPS: dlugosc x nachylenie."""
    score = length_m * avg_grade / 100.0
    if score >= 500: return "trudny"
    if score >= 200: return "sredni"
    if score >= 50:  return "lekki"
    return "lekki"

def detect_climbs(track_points: list[dict], km_from: float = 0.0, km_to: float | None = None) -> list[dict]:
    """Detect climbs from RWGPS track_points (x, y, e, d format).
    
    Returns list of climb dicts sorted by start_km.
    Each: start_km, end_km, length_m, elevation_gain_m, avg_grade_pct,
          max_grade_pct, score, category, estimated_time_sec
    """
    if not track_points:
        return []

    # filter by km range
    km_from_m = km_from * 1000
    km_to_m = (km_to * 1000) if km_to else float("inf")
    pts = [p for p in track_points if km_from_m <= float(p.get("d") or 0) <= km_to_m]
    if len(pts) < 2:
        return []

    climbs = []
    in_climb = False
    climb_start = None

    for i in range(1, len(pts)):
        prev, curr = pts[i-1], pts[i]
        d_dist = float(curr.get("d",0)) - float(prev.get("d",0))
        d_ele = float(curr.get("e",0)) - float(prev.get("e",0))
        if d_dist <= 0:
            continue
        grade = (d_ele / d_dist) * 100.0

        if grade >= MIN_GRADE:
            if not in_climb:
                in_climb = True
                climb_start = i - 1
        else:
            if in_climb:
                in_climb = False
                climb = _build_climb(pts, climb_start, i)
                if climb:
                    climbs.append(climb)
                climb_start = None

    if in_climb and climb_start is not None:
        climb = _build_climb(pts, climb_start, len(pts) - 1)
        if climb:
            climbs.append(climb)

    # Gap-fill: łącz podjazdy przedzielone krótką plażą (<GAP_FILL_M)
    merged = []
    for c in climbs:
        if merged and (c["start_km"] - merged[-1]["end_km"]) * 1000 <= GAP_FILL_M:
            prev = merged[-1]
            # Merge
            combined_len = (c["end_km"] - prev["start_km"]) * 1000
            combined_gain = prev["elevation_gain_m"] + c["elevation_gain_m"]
            if combined_len > 0:
                merged[-1] = {
                    "start_km": prev["start_km"],
                    "end_km": c["end_km"],
                    "length_m": round(combined_len),
                    "elevation_gain_m": round(combined_gain, 1),
                    "avg_grade_pct": round(combined_gain / combined_len * 100, 1),
                    "max_grade_pct": max(prev["max_grade_pct"], c["max_grade_pct"]),
                    "score": round(combined_gain * (combined_gain / combined_len * 10) ** 2, 1),
                    "category": _categorize(combined_len, combined_gain / combined_len * 100),
                    "estimated_time_sec": prev["estimated_time_sec"] + c["estimated_time_sec"],
                }
        else:
            merged.append(c)
    return merged

def _build_climb(pts: list[dict], start_i: int, end_i: int) -> dict | None:
    start = pts[start_i]
    end = pts[end_i]
    length_m = float(end.get("d",0)) - float(start.get("d",0))
    ele_gain = float(end.get("e",0)) - float(start.get("e",0))
    if length_m < MIN_LENGTH_M or ele_gain < MIN_ELEV_M:
        return None
    avg_grade = (ele_gain / length_m) * 100.0
    if avg_grade < MIN_GRADE:
        return None
    # max grade
    grades = []
    for i in range(start_i+1, end_i+1):
        d = float(pts[i].get("d",0)) - float(pts[i-1].get("d",0))
        e = float(pts[i].get("e",0)) - float(pts[i-1].get("e",0))
        if d > 0:
            grades.append((e/d)*100.0)
    max_grade = max(grades) if grades else avg_grade
    score = ele_gain * (avg_grade / 10.0) ** 2
    # estimated time: assume 15 km/h on flat, -0.5km/h per 1% grade
    speed_kmh = max(5.0, 15.0 - avg_grade * 0.8)
    est_sec = int((length_m / 1000.0) / speed_kmh * 3600)
    return {
        "start_km": round(float(start.get("d",0)) / 1000.0, 2),
        "end_km": round(float(end.get("d",0)) / 1000.0, 2),
        "length_m": round(length_m),
        "elevation_gain_m": round(ele_gain, 1),
        "avg_grade_pct": round(avg_grade, 1),
        "max_grade_pct": round(max_grade, 1),
        "score": round(score, 1),
        "category": _categorize(length_m, avg_grade),
        "estimated_time_sec": est_sec,
    }

def format_climbs_report(climbs: list[dict]) -> str:
    if not climbs:
        return "Brak podjazdow na tym odcinku."
    lines = ["PODJAZDY:", "─" * 60]
    for c in climbs:
        mins = c["estimated_time_sec"] // 60
        secs = c["estimated_time_sec"] % 60
        lines.append(
            "km{:.1f}–{:.1f} │ {}m │ +{}m │ avg {:.1f}% │ max {:.1f}% │ ~{}:{:02d} │ [{}]".format(
                c["start_km"], c["end_km"], c["length_m"],
                c["elevation_gain_m"], c["avg_grade_pct"], c["max_grade_pct"],
                mins, secs, c["category"]
            )
        )
    return "\n".join(lines)
