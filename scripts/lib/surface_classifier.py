#!/usr/bin/env python3
"""surface_classifier.py — OSM Cascade Surface Scoring dla Gravel Intelligence.

Kaskada klasyfikacji nawierzchni:
  Level 1: surface tag
  Level 2: tracktype tag
  Level 3: smoothness tag
  Level 4: highway heuristic
  Level 5: regional fallback (Mazowsze)

Każda klasyfikacja zwraca:
  - score 0.0–1.0
  - class_label: good|acceptable|caution|risk|avoid
  - source_level: surface|tracktype|smoothness|highway_landuse|fallback
  - reason
  - confidence: high|medium|low
"""
from __future__ import annotations


# ── Surface tag direct mapping ─────────────────────────────────────────────

SURFACE_SCORES: dict[str, float] = {
    "asphalt": 0.05,
    "paved": 0.08,
    "concrete": 0.05,
    "concrete:lanes": 0.07,
    "cobblestone": 0.10,
    "sett": 0.12,
    "paving_stones": 0.10,
    "chipseal": 0.10,
    "metal": 0.15,
    "wood": 0.30,
    "gravel": 0.20,
    "fine_gravel": 0.25,
    "pebblestone": 0.22,
    "compacted": 0.15,
    "unpaved": 0.40,
    "dirt": 0.60,
    "ground": 0.60,
    "earth": 0.60,
    "mud": 0.85,
    "clay": 0.65,
    "sand": 0.90,
    "grass": 0.85,
    "grass_paver": 0.75,
    "gravel_turf": 0.70,
    "woodchips": 0.55,
    "salt": 0.90,
    "snow": 0.95,
    "ice": 0.95,
}

SURFACE_CATEGORY: dict[str, str] = {
    "asphalt": "good",
    "paved": "good",
    "concrete": "good",
    "concrete:lanes": "good",
    "cobblestone": "acceptable",
    "sett": "acceptable",
    "paving_stones": "acceptable",
    "chipseal": "acceptable",
    "metal": "caution",
    "wood": "caution",
    "gravel": "acceptable",
    "fine_gravel": "acceptable",
    "pebblestone": "acceptable",
    "compacted": "acceptable",
    "unpaved": "caution",
    "dirt": "risk",
    "ground": "risk",
    "earth": "risk",
    "mud": "avoid",
    "clay": "risk",
    "sand": "avoid",
    "grass": "avoid",
    "grass_paver": "risk",
    "gravel_turf": "risk",
    "woodchips": "caution",
    "salt": "avoid",
    "snow": "avoid",
    "ice": "avoid",
}


def classify_surface_tag(surface: str | None) -> dict:
    if not surface:
        return {"score": None, "class_label": None, "source_level": None,
                "reason": "no surface tag", "confidence": None}
    raw = surface.lower().strip()
    score = SURFACE_SCORES.get(raw)
    if score is not None:
        label = SURFACE_CATEGORY.get(raw, "caution")
        return {"score": score, "class_label": label, "source_level": "surface",
                "reason": f"surface={raw}", "confidence": "high"}
    # Unknown surface value — try heuristic
    if any(k in raw for k in ("asphalt", "paved", "concrete")):
        return {"score": 0.10, "class_label": "good", "source_level": "surface",
                "reason": f"surface={raw} (heuristic paved)", "confidence": "medium"}
    if any(k in raw for k in ("gravel", "stone", "rock", "crush")):
        return {"score": 0.25, "class_label": "acceptable", "source_level": "surface",
                "reason": f"surface={raw} (heuristic gravel)", "confidence": "medium"}
    if any(k in raw for k in ("dirt", "ground", "earth", "soil", "mud")):
        return {"score": 0.65, "class_label": "risk", "source_level": "surface",
                "reason": f"surface={raw} (heuristic dirt)", "confidence": "medium"}
    return {"score": 0.50, "class_label": "caution", "source_level": "surface",
            "reason": f"surface={raw} (unrecognized)", "confidence": "low"}


# ── Tracktype mapping ─────────────────────────────────────────────────────

TRACKTYPE_SCORES: dict[str, float] = {
    "grade1": 0.10,
    "grade2": 0.25,
    "grade3": 0.50,
    "grade4": 0.70,
    "grade5": 0.85,
}

TRACKTYPE_LABEL: dict[str, str] = {
    "grade1": "good",
    "grade2": "acceptable",
    "grade3": "caution",
    "grade4": "risk",
    "grade5": "avoid",
}


def classify_tracktype(tracktype: str | None) -> dict:
    if not tracktype:
        return {"score": None, "class_label": None, "source_level": None,
                "reason": "no tracktype tag", "confidence": None}
    raw = tracktype.lower().strip()
    if raw in TRACKTYPE_SCORES:
        return {"score": TRACKTYPE_SCORES[raw], "class_label": TRACKTYPE_LABEL[raw],
                "source_level": "tracktype", "reason": f"tracktype={raw}",
                "confidence": "medium"}
    # Fuzzy match
    for key, score in TRACKTYPE_SCORES.items():
        if key in raw or raw in key:
            return {"score": score, "class_label": TRACKTYPE_LABEL[key],
                    "source_level": "tracktype", "reason": f"tracktype≈{key}",
                    "confidence": "low"}
    return {"score": 0.50, "class_label": "caution", "source_level": "tracktype",
            "reason": f"tracktype={raw} (unrecognized)", "confidence": "low"}


# ── Smoothness mapping ────────────────────────────────────────────────────

SMOOTHNESS_SCORES: dict[str, float] = {
    "excellent": 0.05,
    "good": 0.10,
    "intermediate": 0.35,
    "bad": 0.75,
    "very_bad": 0.85,
    "horrible": 0.90,
    "very_horrible": 0.95,
    "impassable": 1.00,
}

SMOOTHNESS_LABEL: dict[str, str] = {
    "excellent": "good",
    "good": "good",
    "intermediate": "acceptable",
    "bad": "risk",
    "very_bad": "risk",
    "horrible": "avoid",
    "very_horrible": "avoid",
    "impassable": "avoid",
}


def classify_smoothness(smoothness: str | None) -> dict:
    if not smoothness:
        return {"score": None, "class_label": None, "source_level": None,
                "reason": "no smoothness tag", "confidence": None}
    raw = smoothness.lower().strip()
    if raw in SMOOTHNESS_SCORES:
        return {"score": SMOOTHNESS_SCORES[raw], "class_label": SMOOTHNESS_LABEL[raw],
                "source_level": "smoothness", "reason": f"smoothness={raw}",
                "confidence": "medium"}
    if any(k in raw for k in ("excell", "good")):
        return {"score": 0.10, "class_label": "good", "source_level": "smoothness",
                "reason": f"smoothness≈{raw}", "confidence": "low"}
    if "inter" in raw:
        return {"score": 0.35, "class_label": "acceptable", "source_level": "smoothness",
                "reason": f"smoothness≈{raw}", "confidence": "low"}
    return {"score": 0.75, "class_label": "risk", "source_level": "smoothness",
            "reason": f"smoothness={raw} (assumed bad)", "confidence": "low"}


# ── Highway + landuse heuristic ──────────────────────────────────────────

HIGHWAY_SCORES: dict[str, float] = {
    "motorway": 0.05,
    "motorway_link": 0.05,
    "trunk": 0.08,
    "trunk_link": 0.08,
    "primary": 0.10,
    "primary_link": 0.10,
    "secondary": 0.12,
    "secondary_link": 0.12,
    "tertiary": 0.15,
    "tertiary_link": 0.15,
    "unclassified": 0.20,
    "residential": 0.20,
    "living_street": 0.20,
    "service": 0.35,
    "track": 0.65,
    "path": 0.70,
    "footway": 0.70,
    "bridleway": 0.70,
    "cycleway": 0.25,
    "pedestrian": 0.20,
    "steps": 0.90,
    "corridor": 0.60,
    "road": 0.30,
    "bus_guideway": 0.15,
    "raceway": 0.10,
    "escape": 0.15,
    "construction": 0.60,
}

HIGHWAY_LABEL: dict[str, str] = {
    "motorway": "good",
    "motorway_link": "good",
    "trunk": "good",
    "trunk_link": "good",
    "primary": "good",
    "primary_link": "good",
    "secondary": "good",
    "secondary_link": "good",
    "tertiary": "good",
    "tertiary_link": "good",
    "unclassified": "acceptable",
    "residential": "good",
    "living_street": "good",
    "service": "acceptable",
    "track": "caution",
    "path": "caution",
    "footway": "caution",
    "bridleway": "caution",
    "cycleway": "good",
    "pedestrian": "good",
    "steps": "avoid",
    "corridor": "caution",
    "road": "acceptable",
    "bus_guideway": "good",
    "raceway": "good",
    "escape": "good",
    "construction": "caution",
}


def classify_highway_landuse(highway: str | None, region: str = "default") -> dict:
    if not highway:
        return {"score": None, "class_label": None, "source_level": None,
                "reason": "no highway tag", "confidence": None}
    raw = highway.lower().strip()
    score = HIGHWAY_SCORES.get(raw)
    if score is not None:
        label = HIGHWAY_LABEL.get(raw, "caution")
        return {"score": score, "class_label": label, "source_level": "highway_landuse",
                "reason": f"highway={raw}", "confidence": "low"}
    if any(k in raw for k in ("path", "track", "bridle", "foot")):
        return {"score": 0.70, "class_label": "caution", "source_level": "highway_landuse",
                "reason": f"highway≈{raw}", "confidence": "low"}
    return {"score": 0.50, "class_label": "caution", "source_level": "highway_landuse",
            "reason": f"highway={raw} (unknown)", "confidence": "low"}


# ── Regional fallback ─────────────────────────────────────────────────────

REGIONAL_BOOST: dict[str, dict] = {
    "mazowsze": {
        "track_path_forest_score": 0.75,
        "track_path_forest_reason": "Mazowsze: track/path w lesie bez surface — wysokie ryzyko piachu",
    },
}


def classify_regional_fallback(
    highway: str | None,
    surface: str | None,
    region: str = "default",
) -> dict:
    if region not in REGIONAL_BOOST:
        return {"score": None, "class_label": None, "source_level": None,
                "reason": f"no regional data for {region}", "confidence": None}
    if not highway or surface:
        return {"score": None, "class_label": None, "source_level": None,
                "reason": "no boost needed", "confidence": None}

    hw = highway.lower().strip()
    rb = REGIONAL_BOOST[region]
    if hw in ("track", "path", "bridleway", "footway"):
        return {"score": rb["track_path_forest_score"],
                "class_label": "risk",
                "source_level": "fallback",
                "reason": rb["track_path_forest_reason"],
                "confidence": "low"}
    return {"score": None, "class_label": None, "source_level": None,
            "reason": "no boost applicable", "confidence": None}


# ── Cascade orchestrator ─────────────────────────────────────────────────

SCORE_TO_LABEL: list[tuple[float, str]] = [
    (0.10, "good"),
    (0.30, "acceptable"),
    (0.55, "caution"),
    (0.75, "risk"),
    (1.00, "avoid"),
]


def score_to_label(score: float) -> str:
    for threshold, label in SCORE_TO_LABEL:
        if score <= threshold:
            return label
    return "avoid"


def classify_osm_cascade(tags: dict, region: str = "default") -> dict:
    surface = tags.get("surface")
    tracktype = tags.get("tracktype")
    smoothness = tags.get("smoothness")
    highway = tags.get("highway")

    # Level 1: surface tag
    r1 = classify_surface_tag(surface)
    if r1["score"] is not None:
        return r1

    # Level 2: tracktype
    r2 = classify_tracktype(tracktype)
    if r2["score"] is not None:
        return r2

    # Level 3: smoothness
    r3 = classify_smoothness(smoothness)
    if r3["score"] is not None:
        return r3

    # Level 4: highway heuristic
    r4 = classify_highway_landuse(highway, region)
    if r4["score"] is not None:
        # Apply regional boost on top of highway heuristic
        r5 = classify_regional_fallback(highway, surface, region)
        if r5["score"] is not None:
            final_score = max(r4["score"], r5["score"])
            return {"score": final_score,
                    "class_label": score_to_label(final_score),
                    "source_level": r5["source_level"],
                    "reason": f"{r4['reason']}; {r5['reason']}",
                    "confidence": r5["confidence"],
                    "cascade_chain": ["surface_miss", "tracktype_miss",
                                      "smoothness_miss", "highway", "regional_fallback"]}
        return r4

    # Level 5: regional fallback (even without highway info)
    r5 = classify_regional_fallback(None, None, region)
    if r5["score"] is not None:
        return r5

    return {"score": 0.50, "class_label": "caution", "source_level": "fallback",
            "reason": "no OSM tags available — assumed caution",
            "confidence": "very_low",
            "cascade_chain": ["surface_miss", "tracktype_miss",
                              "smoothness_miss", "highway_miss", "fallback"]}


# ── Aggregate cascade stats ──────────────────────────────────────────────

def aggregate_cascade(sample_results: list[dict]) -> dict:
    if not sample_results:
        return {}

    scores = [r["score"] for r in sample_results if r.get("score") is not None]
    levels = [r["source_level"] for r in sample_results if r.get("source_level")]

    level_counts: dict[str, int] = {}
    for lv in levels:
        if lv:
            level_counts[lv] = level_counts.get(lv, 0) + 1

    total = len(sample_results)
    avg_score = sum(scores) / len(scores) if scores else 0
    high_risk = sum(1 for s in scores if s >= 0.65)
    caution = sum(1 for s in scores if 0.35 <= s < 0.65)
    good = sum(1 for s in scores if s < 0.35)

    return {
        "avg_cascade_score": round(avg_score, 4),
        "samples_good": good,
        "samples_caution": caution,
        "samples_high_risk": high_risk,
        "cascade_level_breakdown": {
            k: {"count": v, "pct": round(v / total * 100, 1)}
            for k, v in sorted(level_counts.items(), key=lambda x: -x[1])
        },
        "cascade_levels_used": sorted(level_counts.keys()),
    }
