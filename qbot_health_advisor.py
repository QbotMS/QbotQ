#!/usr/bin/env python3
"""QBot Health Advisor v1 — weight, nutrition, recovery, supplement advice.

Read-only advisor. Returns reports, recommendations, warnings, missing_fields.
Does NOT modify DB.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any


def advisor_check(period_days: int = 14) -> dict[str, Any]:
    """Run all advisor checks and return a merged report."""
    today = date.today().isoformat()
    start = (date.today() - timedelta(days=period_days)).isoformat()

    weight = _weight_advice()
    nutrition = _nutrition_advice(start, today)
    recovery = _recovery_advice()
    supplements = _supplement_advice()
    illness = _illness_advice()
    risks = _risk_notes_advice()

    recommendations = []
    warnings_list = []
    assumptions = {"checked_at": today, "period_days": period_days}
    missing = []

    for section, result in [("weight", weight), ("nutrition", nutrition),
                              ("recovery", recovery), ("supplements", supplements),
                              ("illness", illness), ("risks", risks)]:
        if result.get("recommendations"):
            recommendations.extend(result["recommendations"])
        if result.get("warnings"):
            warnings_list.extend(result["warnings"])
        if result.get("missing_fields"):
            missing.extend(result.get("missing_fields", []))
        if result.get("assumptions"):
            assumptions[section] = result["assumptions"]
        if result.get("confidence"):
            assumptions[f"{section}_confidence"] = result["confidence"]

    confidences = [v for k, v in assumptions.items() if k.endswith("_confidence")]
    overall_confidence = "low"
    if all(c == "high" for c in confidences):
        overall_confidence = "high"
    elif any(c in ("medium", "high") for c in confidences):
        overall_confidence = "medium"

    return {
        "tool": "qbot_health_advisor_check",
        "safety_class": "READ_ONLY",
        "status": "OK",
        "date": today,
        "period_days": period_days,
        "sections": {"weight": weight, "nutrition": nutrition, "recovery": recovery,
                      "supplements": supplements, "illness": illness, "risks": risks},
        "recommendations": recommendations,
        "warnings": warnings_list,
        "assumptions": assumptions,
        "missing_fields": missing,
        "confidence": overall_confidence,
    }


def _weight_advice() -> dict[str, Any]:
    """Weight trend advice based on goals."""
    try:
        from qbot_health_db import goal_list
        goals = goal_list("active")
    except Exception:
        goals = []

    recommendations = []
    warnings_list = []
    missing = []

    if not goals:
        return {
            "recommendations": ["Set a weight goal to track progress."],
            "warnings": [], "missing_fields": ["health_goals", "weight_history"],
            "assumptions": {}, "confidence": "low",
        }

    g = goals[0]
    target = g.get("target_weight_kg")
    target_date = g.get("target_date")
    start_weight = g.get("start_weight_kg")

    if not target or not target_date:
        missing.append("target_weight or target_date not set on goal")
        return {"recommendations": ["Ustaw target_weight_kg i target_date w health_goals."],
                "warnings": [], "missing_fields": missing, "assumptions": {}, "confidence": "low"}

    # Estimate rate
    days_left = None
    if target_date:
        try:
            days_left = (date.fromisoformat(str(target_date)[:10]) - date.today()).days
        except Exception:
            pass

    if start_weight and days_left and days_left > 0:
        kg_to_lose = start_weight - target
        rate = kg_to_lose / (days_left / 7)  # kg/week
        if rate > 1.0:
            recommendations.append(f"Zalecane tempo: {rate:.1f} kg/tydz. — agresywne ale realne przy dużym treningu.")
            if rate > 1.5:
                warnings_list.append(f"Tempo {rate:.1f} kg/tydz jest bardzo agresywne. Rozważ wydłużenie deadline'u.")
        elif rate > 0.5:
            recommendations.append(f"Tempo {rate:.1f} kg/tydz jest realne przy deficycie 500-700 kcal/dzień.")
        else:
            recommendations.append(f"Tempo {rate:.1f} kg/tydz jest bezpieczne i osiągalne.")

    if days_left is not None and days_left < 0:
        recommendations.append(f"Target date ({target_date}) minął. Zaktualizuj goal lub ustaw nowy target.")

    return {
        "recommendations": recommendations,
        "warnings": warnings_list,
        "missing_fields": missing,
        "assumptions": {"goal_name": g.get("goal_name"), "target_kg": target, "target_date": target_date},
        "confidence": "medium" if start_weight else "low",
    }


def _nutrition_advice(period_from: str, period_to: str) -> dict[str, Any]:
    """Nutrition check — protein, carbs, deficit."""
    recommendations = []
    warnings_list = []
    missing = []
    try:
        from qbot_nutrition_db import daily_summary_range
        summaries = daily_summary_range(period_from, period_to)
    except Exception:
        summaries = []

    if not summaries:
        return {"recommendations": ["Brak danych nutrition — zaloguj kilka dni posiłków."],
                "warnings": [], "missing_fields": ["nutrition_daily_summary"],
                "assumptions": {}, "confidence": "low"}

    avg_kcal = sum(s.get("kcal_total", 0) or 0 for s in summaries) / len(summaries)
    avg_protein = sum(s.get("protein_total", 0) or 0 for s in summaries) / len(summaries)
    avg_carbs = sum(s.get("carbs_total", 0) or 0 for s in summaries) / len(summaries)

    weight = 78  # fallback
    protein_target = weight * 1.8

    if avg_protein < protein_target * 0.8:
        recommendations.append(f"Białko: średnio {avg_protein:.0f}g/dzień — za mało. Cel: ~{protein_target:.0f}g.")
    elif avg_protein > protein_target * 1.3:
        recommendations.append(f"Białko: {avg_protein:.0f}g/dzień — powyżej celu. OK jeżeli w deficycie.")

    if avg_kcal > 3000:
        recommendations.append(f"Średnie kcal: {avg_kcal:.0f}/dzień. Sprawdź, czy mieści się w TDEE + cel.")

    return {
        "recommendations": recommendations,
        "warnings": warnings_list,
        "missing_fields": missing,
        "assumptions": {"avg_kcal": avg_kcal, "avg_protein": avg_protein, "avg_carbs": avg_carbs, "weight_kg_estimated": weight},
        "confidence": "medium",
    }


def _recovery_advice() -> dict[str, Any]:
    """Recovery check — sleep, HRV, resting HR."""
    missing = ["sleep_data", "hrv_data", "resting_hr"]
    return {
        "recommendations": [
            "Brak danych regeneracyjnych (sen, HRV, RHR) w QBot. Zaimportuj dane z Garmin/Intervals."
        ],
        "warnings": [],
        "missing_fields": missing,
        "assumptions": {},
        "confidence": "low",
    }


def _supplement_advice() -> dict[str, Any]:
    """Supplement check — inventory, protocols, warnings."""
    recommendations = []
    warnings_list = []
    missing = []
    inventory = []
    protocols = []

    try:
        from qbot_health_db import supp_list, prot_list, intake_list
        inventory = supp_list()
        protocols = prot_list()
    except Exception:
        pass

    if not inventory and not protocols:
        return {"recommendations": ["Dodaj suplementy do inventory i protokoły."],
                "warnings": [], "missing_fields": ["supplement_inventory", "supplement_protocols"],
                "assumptions": {}, "confidence": "low"}

    today = date.today()

    for s in inventory:
        name = s.get("name", "?")
        remaining = s.get("units_remaining")
        expiry = s.get("expiry_date")

        if not remaining:
            warnings_list.append(f"{name}: brak units_remaining — nie można oszacować zapasu.")
            continue
        if not expiry:
            warnings_list.append(f"{name}: brak expiry_date.")
        elif isinstance(expiry, str):
            try:
                exp = date.fromisoformat(expiry[:10])
                if exp < today:
                    warnings_list.append(f"{name}: data ważności minęła ({expiry[:10]}).")
                elif (exp - today).days < 30:
                    recommendations.append(f"{name}: kończy się za {(exp - today).days} dni — rozważ zakup.")
            except Exception:
                pass

        # Estimate days left
        daily_use = 0
        for p in protocols:
            if p.get("supplement_name", "").lower() == name.lower() and p.get("status") == "active":
                daily_use += 1

        if daily_use > 0 and remaining:
            days_left = remaining / daily_use
            if days_left < 14:
                recommendations.append(f"{name}: zostało ~{days_left:.0f} dni (protocol: {daily_use}/dzień).")
            if days_left < 0:
                warnings_list.append(f"{name}: units_remaining < 0 — sprawdź inventory.")

    for p in protocols:
        name = p.get("supplement_name", "?")
        freq = p.get("frequency", "")
        if not p.get("goal") or p.get("goal") == "general_health" and not p.get("reason"):
            recommendations.append(f"Protokół '{name}' — dodaj cel stosowania (goal/reason).")
        if freq == "as_needed" and not p.get("cautions"):
            warnings_list.append(f"Protokół '{name}' — as_needed bez zasad stosowania. Dodaj cautions.")

        # Melatonin warning
        if "melaton" in name.lower() and freq == "daily":
            recommendations.append(f"{name}: długotrwałe codzienne stosowanie melatoniny może wpływać na naturalną produkcję. Rozważ cykliczne przerwy.")

    # Check for active protocols without inventory
    prot_names = {p.get("supplement_name", "").lower() for p in protocols if p.get("status") == "active"}
    inv_names = {s.get("name", "").lower() for s in inventory}
    for pn in prot_names - inv_names:
        recommendations.append(f"Protokół '{pn}' aktywny, ale brak w inventory. Dodaj lub kup suplement.")

    return {
        "recommendations": recommendations,
        "warnings": warnings_list,
        "missing_fields": missing,
        "assumptions": {"inventory_count": len(inventory), "protocols_count": len(protocols)},
        "confidence": "medium" if inventory else "low",
    }


def supplement_inventory_report() -> dict[str, Any]:
    """Detailed supplement inventory + protocol report."""
    inventory = []
    protocols = []
    try:
        from qbot_health_db import supp_list, prot_list
        inventory = supp_list()
        protocols = prot_list()
    except Exception:
        pass

    items = []
    for s in inventory:
        name = s.get("name", "?")
        remaining = s.get("units_remaining")
        dose_pu = s.get("dose_per_unit", 1) or 1
        dose_unit = s.get("dose_unit", "?")

        active_prots = [p for p in protocols if p.get("supplement_name", "").lower() == name.lower() and p.get("status") == "active"]
        daily_doses = len(active_prots)
        days_left = (remaining / daily_doses) if (daily_doses and remaining) else None

        items.append({
            "name": name,
            "brand": s.get("brand"),
            "form": s.get("form"),
            "dose_per_unit": dose_pu,
            "dose_unit": dose_unit,
            "units_remaining": remaining,
            "expiry_date": s.get("expiry_date"),
            "status": s.get("status"),
            "active_protocols": len(active_prots),
            "days_left_est": round(days_left, 0) if days_left else None,
        })

    return {
        "tool": "qbot_health_supplement_inventory",
        "safety_class": "READ_ONLY",
        "status": "OK",
        "items": items,
        "protocols": protocols,
        "warnings": [s.get("notes") for s in inventory if s.get("notes") and "warn" in str(s.get("notes", "")).lower()],
    }


# ── Illness & Wellbeing ──

def _illness_advice() -> dict[str, Any]:
    """Check active health events and their impact."""
    try:
        from qbot_health_db import active_health_events
        events = active_health_events()
    except Exception:
        return {"recommendations": [], "warnings": [], "missing_fields": ["health_events_db"],
                "assumptions": {}, "confidence": "low"}

    if not events:
        return {"recommendations": [], "warnings": [], "missing_fields": [],
                "assumptions": {"active_events": 0}, "confidence": "high"}

    recs = []
    warns = []

    for ev in events:
        sev = ev.get("severity", "mild")
        etype = ev.get("event_type", "illness")
        title = ev.get("title", "?")
        symptoms_raw = ev.get("symptoms_json")
        symptoms = symptoms_raw if isinstance(symptoms_raw, list) else []

        if sev in ("high", "severe"):
            warns.append(f"{title} (severity={sev}) — nie rekomenduj treningu. Rozważ konsultację medyczną.")
        elif sev == "moderate":
            warns.append(f"{title} (severity={sev}) — ogranicz intensywność treningu, preferuj regenerację.")
        else:
            recs.append(f"{title} — łagodne. Lekki ruch OK, priorytet: sen i nawodnienie.")

        alarm_words = ["gorączka", "fever", "duszność", "breath", "ból w klatce", "chest pain"]
        for sym in (symptoms if isinstance(symptoms, list) else []):
            if any(a in str(sym).lower() for a in alarm_words):
                warns.append(f"Objaw alarmowy '{sym}' — zasugeruj konsultację lekarską. Nie diagnozuj.")

        if etype == "illness" and ev.get("affects_nutrition"):
            recs.append(f"{title}: nie proponuj agresywnego deficytu. Preferuj łatwostrawne posiłki, nawodnienie.")

    return {
        "recommendations": recs, "warnings": warns, "missing_fields": [],
        "assumptions": {"active_events": len(events)},
        "confidence": "high" if events else "medium",
    }


def _risk_notes_advice() -> dict[str, Any]:
    try:
        from qbot_health_db import risk_list
        risks = risk_list("active")
    except Exception:
        return {"recommendations": [], "warnings": [], "missing_fields": ["health_risk_notes"], "assumptions": {}, "confidence": "low"}
    if not risks:
        return {"recommendations": [], "warnings": [], "missing_fields": [], "assumptions": {"active_risks": 0}, "confidence": "high"}
    recs = []
    for r in risks:
        title = r.get("title", "?")
        constraints = r.get("constraints_json")
        if isinstance(constraints, str):
            try: constraints = __import__("json").loads(constraints)
            except Exception: pass
        if r.get("risk_type") == "metabolic":
            recs.append(f"Ryzyko: {title} — unikaj ekstremalnych skoków węgli, preferuj węgle z błonnikiem i białkiem.")
    return {"recommendations": recs, "warnings": [], "missing_fields": [], "assumptions": {"active_risks": len(risks)}, "confidence": "medium"}


def recovery_anomaly_check() -> dict[str, Any]:
    missing = ["hrv_data", "resting_hr", "sleep_duration"]
    try:
        from qbot_health_db import active_health_events
        events = active_health_events()
    except Exception:
        events = []
    return {
        "tool": "qbot_health_recovery_anomaly_check", "safety_class": "READ_ONLY", "status": "OK",
        "question": "Czy czujesz się OK? Brak danych HRV/senu do automatycznej oceny regeneracji.",
        "active_events": len(events),
        "missing_fields": missing,
        "confidence": "low",
    }


def get_planning_constraints() -> dict[str, Any]:
    events = []
    try: from qbot_health_db import active_health_events; events = active_health_events()
    except: pass
    risks = []
    try: from qbot_health_db import active_constraints; risks = active_constraints()
    except: pass

    avoid_aggressive_deficit = False
    avoid_hard_training = False
    avoid_carb_spikes = False
    prefer_fiber_protein = False
    warnings_list = []

    for ev in events:
        sev = ev.get("severity", "mild")
        if sev in ("high", "severe", "moderate"):
            avoid_aggressive_deficit = True
            avoid_hard_training = True
            warnings_list.append(f"Active health event: {ev.get('title','?')} ({sev})")
        elif sev == "mild" and ev.get("affects_nutrition"):
            avoid_aggressive_deficit = True
            warnings_list.append(f"Mild event: {ev.get('title','?')} — consider lighter deficit.")

    for rc in risks:
        if isinstance(rc, dict):
            if rc.get("avoid_extreme_carb_spikes"): avoid_carb_spikes = True
            if rc.get("prefer_fiber_protein_with_carbs"): prefer_fiber_protein = True

    return {
        "active_health_events": len(events), "active_risk_notes": len(risks),
        "avoid_aggressive_deficit": avoid_aggressive_deficit,
        "avoid_hard_training": avoid_hard_training,
        "avoid_carb_spikes": avoid_carb_spikes,
        "prefer_fiber_protein_with_carbs": prefer_fiber_protein,
        "warnings": warnings_list,
    }
