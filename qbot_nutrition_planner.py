#!/usr/bin/env python3
"""Nutrition Day Planner v1 — deterministic meal plan builder.

Read-only planning logic. Does NOT write to nutrition_db.
Used by: qbot.query (via nutrition_planning intent) and qbot nutrition plan-day CLI.
"""

from __future__ import annotations

import json
from typing import Any

# ── Default macro targets ───────────────────────────────────────────────────

_DEFAULT_DEFICITS: dict[str, float] = {
    "rest": 500,
    "light_training": 400,
    "normal_training": 300,
    "long_ride": 150,
    "hard_training": 100,
    "recovery": 300,
}

_MIN_INTAKE_KCAL = 1200
_PROTEIN_G_PER_KG = 1.8
_DEFAULT_WEIGHT_KG = 78


def _estimate_tdee(
    base_kcal: float | None = None,
    activity_kcal: float | None = None,
    day_type: str = "rest",
    planned_ride_km: float | None = None,
) -> tuple[float, str]:
    """Return (estimated_tdee, confidence) for the day."""
    if base_kcal and activity_kcal:
        return base_kcal + activity_kcal, "high"
    if base_kcal:
        return base_kcal + (planned_ride_km or 0) * 30, "medium"
    # Fallback — use BMR × activity factor
    weight = _DEFAULT_WEIGHT_KG
    bmr = weight * 24  # rough estimate
    factors = {
        "rest": 1.2, "recovery": 1.3, "light_training": 1.5,
        "normal_training": 1.7, "long_ride": 2.0, "hard_training": 2.0,
    }
    factor = factors.get(day_type, 1.4)
    tdee = bmr * factor
    if planned_ride_km:
        tdee += planned_ride_km * 30
    return tdee, "low"


def _select_meals_from_templates(
    target_kcal: float,
    templates: list[dict],
    meals_count: int = 3,
    available_foods: list[str] | None = None,
) -> list[dict]:
    """Simple meal selection from available templates.

    Strategy: split target_kcal across meals_count meals,
    prefer templates with matching keywords from available_foods.
    Returns list of meal dicts with {template_name, template_id, kcal, ...}
    """
    if not templates:
        return _plan_fallback_meals(target_kcal, meals_count)

    # Filter by available_foods if given
    candidates = templates
    if available_foods:
        avail_lower = [f.strip().lower() for f in available_foods]
        scored = []
        for t in templates:
            tname = t["name"].lower()
            score = sum(1 for a in avail_lower if a in tname)
            scored.append((score, t))
        scored.sort(key=lambda x: -x[0])
        candidates = [t for _, t in scored]

    kcal_per_meal = target_kcal / max(meals_count, 1)
    meals: list[dict] = []
    used = 0

    for i in range(meals_count):
        # Find closest template to remaining kcal/meal target
        remaining = target_kcal - used
        remaining_meals = meals_count - i
        target = remaining / max(remaining_meals, 1)

        best = None
        best_diff = float("inf")
        for t in candidates:
            diff = abs(t["kcal"] - target)
            if diff < best_diff:
                best_diff = diff
                best = t

        if best is None:
            best = candidates[0] if candidates else None

        if best:
            meals.append({
                "template_name": best["name"],
                "template_id": best["id"],
                "meal_name": best["name"],
                "kcal": best["kcal"],
                "carbs_g": best.get("carbs_g", 0) or 0,
                "protein_g": best.get("protein_g", 0) or 0,
                "fat_g": best.get("fat_g", 0) or 0,
                "fiber_g": best.get("fiber_g", 0) or 0,
                "sodium_mg": best.get("sodium_mg", 0) or 0,
            })
            used += best["kcal"]
            # Re-score to avoid repeating
            candidates = [c for c in candidates if c.get("id") != best.get("id")] or candidates
        else:
            fallback = _plan_fallback_meals(target, 1)
            meals.extend(fallback)
            used += fallback[0]["kcal"] if fallback else 0

    return meals


def _plan_fallback_meals(target_kcal: float, count: int) -> list[dict]:
    """Generate generic meals when no templates available."""
    kcal_per = max(target_kcal / max(count, 1), 200)
    meals = []
    labels = ["Śniadanie", "Obiad", "Kolacja", "Przekąska"]
    for i in range(count):
        meals.append({
            "template_name": None,
            "template_id": None,
            "meal_name": labels[i] if i < len(labels) else f"Posiłek {i+1}",
            "kcal": kcal_per,
            "carbs_g": kcal_per * 0.45 / 4,
            "protein_g": kcal_per * 0.25 / 4,
            "fat_g": kcal_per * 0.30 / 9,
            "fiber_g": 0,
            "sodium_mg": 0,
        })
    return meals


def plan_day(
    *,
    goal: str = "deficit",
    day_type: str = "rest",
    date_str: str = "",
    planned_ride_km: float | None = None,
    target_kcal: float | None = None,
    target_deficit_kcal: float | None = None,
    meals_count: int = 3,
    available_foods: list[str] | None = None,
    use_templates: bool = False,
    templates: list[dict] | None = None,
    already_logged_kcal: float = 0,
    base_kcal: float | None = None,
    activity_kcal: float | None = None,
) -> dict[str, Any]:
    """Build a day meal plan. Returns a plan dict (does NOT write to DB)."""

    warnings: list[str] = []
    assumptions: dict[str, Any] = {}

    # Step 1: Estimate TDEE
    tdee, tdee_conf = _estimate_tdee(base_kcal, activity_kcal, day_type, planned_ride_km)

    # Step 2: Determine deficit
    deficit = target_deficit_kcal if target_deficit_kcal is not None else _DEFAULT_DEFICITS.get(day_type, 300)

    # Step 3: Target intake
    if target_kcal is not None:
        intake = target_kcal
        intake_source = "user_specified"
    else:
        intake = max(tdee - deficit, _MIN_INTAKE_KCAL)
        intake_source = "computed_from_tdee"

    if intake < _MIN_INTAKE_KCAL:
        warnings.append(f"Target intake ({intake:.0f} kcal) below minimum ({_MIN_INTAKE_KCAL} kcal); clamped.")
        intake = _MIN_INTAKE_KCAL

    # Step 4: Safety check for high-activity days
    if day_type in ("long_ride", "hard_training") and deficit > 250:
        warnings.append(f"Deficit {deficit:.0f} kcal too aggressive for {day_type} — consider reducing to ≤250 kcal.")

    # Step 5: Remaining after already logged
    remaining = max(intake - already_logged_kcal, 0)

    # Step 6: Macro targets
    protein_target = _PROTEIN_G_PER_KG * _DEFAULT_WEIGHT_KG  # ~140g
    carbs_pct = 0.55 if day_type in ("long_ride", "hard_training") else 0.40
    fat_pct = 0.20 if day_type in ("long_ride", "hard_training") else 0.30
    protein_pct = 0.25

    carbs_target = remaining * carbs_pct / 4
    fat_target = remaining * fat_pct / 9
    protein_target = max(remaining * protein_pct / 4, protein_target)

    # Step 7: Build meals
    used_tmpl = use_templates and templates
    planned_meals = _select_meals_from_templates(
        remaining,
        templates or [],
        meals_count,
        available_foods,
    ) if used_tmpl else _plan_fallback_meals(remaining, meals_count)

    # Step 8: Validate
    total_planned = sum(m["kcal"] for m in planned_meals)
    if total_planned > remaining * 1.3:
        warnings.append(f"Planned meals total ({total_planned:.0f} kcal) exceeds remaining ({remaining:.0f} kcal) significantly.")

    assumptions.update({
        "weight_kg": _DEFAULT_WEIGHT_KG,
        "tdee_method": "estimated",
        "tdee": tdee,
        "tdee_confidence": tdee_conf,
    })

    return {
        "date": date_str,
        "goal": goal,
        "day_type": day_type,
        "status": "draft",
        "planned_ride_km": planned_ride_km,
        "estimated_base_kcal": base_kcal,
        "estimated_activity_kcal": activity_kcal,
        "estimated_total_expenditure": tdee,
        "target_deficit_kcal": deficit,
        "target_intake_kcal": intake,
        "already_logged_kcal": already_logged_kcal,
        "remaining_kcal": remaining,
        "target_protein_g": protein_target,
        "target_carbs_g": carbs_target,
        "target_fat_g": fat_target,
        "planned_meals_count": meals_count,
        "available_foods": ",".join(available_foods) if available_foods else None,
        "used_templates": used_tmpl,
        "confidence": tdee_conf if intake_source == "computed_from_tdee" else "medium",
        "source": "llm_plan",
        "assumptions_json": assumptions,
        "warnings_json": warnings if warnings else None,
        "meals": planned_meals,
        "total_planned_kcal": total_planned,
        "note": "To jest plan/draft. Posiłki NIE zostały zapisane jako zjedzone. Użyj plan-apply aby zapisać.",
    }


def _get_templates_from_db() -> list[dict]:
    """Load all templates from DB (lazy import)."""
    try:
        from qbot_nutrition_db import template_list
        return template_list()
    except Exception:
        return []


def _get_already_logged(date_str: str) -> float:
    """Get kcal already logged for a date."""
    try:
        from qbot_nutrition_db import daily_summary_get, daily_summary_compute
        s = daily_summary_get(date_str) or daily_summary_compute(date_str)
        return s.get("kcal_total", 0) or 0
    except Exception:
        return 0.0
