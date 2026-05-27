#!/usr/bin/env python3
"""QBot Nutrition Tools — MCP / /q wrappers for nutrition DB operations."""
from __future__ import annotations

import json
from typing import Any


def _tool_qbot_nutrition_food_search(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    query = str(_args.get("query", "")).strip()
    limit = int(_args.get("limit", 20))
    try:
        from qbot_nutrition_db import food_item_search
        items = food_item_search(query, limit=limit)
        return {
            "tool": "qbot_nutrition_food_search",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "query": query,
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_food_search", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_food_list(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    limit = int(_args.get("limit", 50))
    try:
        from qbot_nutrition_db import food_item_list
        items = food_item_list(limit=limit)
        return {
            "tool": "qbot_nutrition_food_list",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_food_list", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_food_create(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    name = str(_args.get("name", "")).strip()
    if not name:
        return {"tool": "qbot_nutrition_food_create", "status": "ERROR", "error": "name required"}
    try:
        from qbot_nutrition_db import food_item_create
        food = food_item_create(
            name=name,
            brand=_args.get("brand"),
            default_unit=_args.get("default_unit", "g"),
            kcal_per_100g=_args.get("kcal_per_100g"),
            carbs_per_100g=_args.get("carbs_per_100g"),
            sugar_per_100g=_args.get("sugar_per_100g"),
            protein_per_100g=_args.get("protein_per_100g"),
            fat_per_100g=_args.get("fat_per_100g"),
            fiber_per_100g=_args.get("fiber_per_100g"),
            sodium_per_100g=_args.get("sodium_per_100g"),
            source=_args.get("source", "qbot"),
            verified=bool(_args.get("verified", False)),
        )
        return {
            "tool": "qbot_nutrition_food_create",
            "safety_class": "WRITE_SAFE",
            "status": "OK",
            "food": food,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_food_create", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_intake_parse(_args: dict | None = None) -> dict[str, Any]:
    """Parse natural language intake text without saving."""
    _args = _args or {}
    text = str(_args.get("text", "")).strip()
    if not text:
        return {"tool": "qbot_nutrition_intake_parse", "status": "ERROR", "error": "text required"}
    try:
        from qbot_nutrition_parser import parse_intake
        result = parse_intake(text)
        result["tool"] = "qbot_nutrition_intake_parse"
        result["safety_class"] = "READ_ONLY"
        return result
    except Exception as exc:
        return {"tool": "qbot_nutrition_intake_parse", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_intake_log(_args: dict | None = None) -> dict[str, Any]:
    """Parse natural language intake AND save to DB."""
    _args = _args or {}
    text = str(_args.get("text", "")).strip()
    meal_type = str(_args.get("meal_type", "meal")).strip() or "meal"
    note = _args.get("note")
    context = _args.get("context")

    if not text:
        return {"tool": "qbot_nutrition_intake_log", "status": "ERROR", "error": "text required"}

    try:
        from qbot_nutrition_parser import parse_intake
        from qbot_nutrition_db import meal_log_create, hydration_event_create, fueling_event_create

        parsed = parse_intake(text)
        results: dict[str, Any] = {
            "tool": "qbot_nutrition_intake_log",
            "safety_class": "WRITE_SAFE",
            "status": "OK",
            "raw_text": text,
            "unknown": parsed.get("unknown", []),
        }

        if parsed.get("meal_items"):
            items_for_db = []
            for item in parsed["meal_items"]:
                items_for_db.append({
                    "food": item.get("food_normalized", item.get("food_name")),
                    "amount": item.get("amount", 0),
                    "unit": item.get("unit", "g"),
                    "kcal": item.get("kcal"),
                    "carbs_g": item.get("carbs_g"),
                    "protein_g": item.get("protein_g"),
                    "fat_g": item.get("fat_g"),
                    "fiber_g": item.get("fiber_g"),
                    "sodium_mg": item.get("sodium_mg"),
                })
            meal = meal_log_create(meal_type=meal_type, note=note, context=context, items=items_for_db)
            results["meal"] = meal
            results["meal_id"] = meal["id"]

        for h in parsed.get("hydration", []):
            hyd = hydration_event_create(
                fluid_ml=h["fluid_ml"],
                sodium_mg=h.get("sodium_mg", 0),
                note=h.get("note"),
            )
            results.setdefault("hydration", []).append(hyd)

        for f in parsed.get("fueling", []):
            fuel = fueling_event_create(
                carbs_g=f["carbs_g"],
                context=context,
            )
            results.setdefault("fueling", []).append(fuel)

        return results
    except Exception as exc:
        return {"tool": "qbot_nutrition_intake_log", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_hydration_log(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    fluid_ml = _args.get("fluid_ml", 0)
    if not fluid_ml:
        return {"tool": "qbot_nutrition_hydration_log", "status": "ERROR", "error": "fluid_ml required"}
    try:
        from qbot_nutrition_db import hydration_event_create
        event = hydration_event_create(
            fluid_ml=float(fluid_ml),
            sodium_mg=float(_args.get("sodium_mg", 0)),
            note=_args.get("note"),
            source=_args.get("source", "qbot"),
        )
        return {
            "tool": "qbot_nutrition_hydration_log",
            "safety_class": "WRITE_SAFE",
            "status": "OK",
            "event": event,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_hydration_log", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_fueling_log(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    carbs_g = _args.get("carbs_g", 0)
    if not carbs_g:
        return {"tool": "qbot_nutrition_fueling_log", "status": "ERROR", "error": "carbs_g required"}
    try:
        from qbot_nutrition_db import fueling_event_create
        event = fueling_event_create(
            carbs_g=float(carbs_g),
            source=_args.get("source", "qbot"),
            context=_args.get("context"),
        )
        return {
            "tool": "qbot_nutrition_fueling_log",
            "safety_class": "WRITE_SAFE",
            "status": "OK",
            "event": event,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_fueling_log", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_day_summary(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    date_str = str(_args.get("date", "")).strip()
    recompute = bool(_args.get("recompute", False))
    if not date_str:
        from datetime import date as dt_date
        date_str = dt_date.today().isoformat()
    try:
        from qbot_nutrition_db import daily_summary_get, daily_summary_compute
        if recompute:
            summary = daily_summary_compute(date_str)
        else:
            summary = daily_summary_get(date_str)
            if not summary:
                summary = daily_summary_compute(date_str)

        # Also grab detailed items
        from qbot_nutrition_db import meal_log_list, hydration_list, fueling_list
        meals = meal_log_list(date_str=date_str)
        hydration = hydration_list(date_str=date_str)
        fueling = fueling_list(date_str=date_str)

        return {
            "tool": "qbot_nutrition_day_summary",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "date": date_str,
            "summary": summary,
            "meals": meals,
            "meals_count": len(meals),
            "hydration_events": hydration,
            "hydration_count": len(hydration),
            "fueling_events": fueling,
            "fueling_count": len(fueling),
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_day_summary", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_meal_list(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    date_str = _args.get("date")
    limit = int(_args.get("limit", 20))
    try:
        from qbot_nutrition_db import meal_log_list
        meals = meal_log_list(date_str=date_str, limit=limit)
        return {
            "tool": "qbot_nutrition_meal_list",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "date": date_str,
            "count": len(meals),
            "meals": meals,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_meal_list", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_meal_delete(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    meal_id = _args.get("meal_id") or _args.get("id")
    if not meal_id:
        return {"tool": "qbot_nutrition_meal_delete", "status": "ERROR", "error": "meal_id required"}
    dry_run = bool(_args.get("dry_run", False))
    try:
        from qbot_nutrition_db import meal_log_delete, daily_summary_compute
        if dry_run:
            from qbot_nutrition_db import get_meal_log
            meal = get_meal_log(int(meal_id))
            return {
                "tool": "qbot_nutrition_meal_delete",
                "safety_class": "WRITE_SAFE",
                "status": "DRY_RUN",
                "meal_id": int(meal_id),
                "would_delete": meal is not None,
                "meal_preview": meal,
            }
        deleted = meal_log_delete(int(meal_id))
        if deleted:
            date_str = deleted.get("eaten_at", "")[:10]
            try:
                daily_summary_compute(date_str)
            except Exception:
                pass
        return {
            "tool": "qbot_nutrition_meal_delete",
            "safety_class": "WRITE_SAFE",
            "status": "OK" if deleted else "NOT_FOUND",
            "deleted": deleted is not None,
            "meal_id": int(meal_id),
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_meal_delete", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_status(_args: dict | None = None) -> dict[str, Any]:
    """DB readiness check: table counts + date range."""
    try:
        from qbot_nutrition_db import _conn
        with _conn() as conn:
            food_count = conn.execute("SELECT COUNT(*) AS n FROM food_items").fetchone()["n"]
            meal_count = conn.execute("SELECT COUNT(*) AS n FROM meal_logs").fetchone()["n"]
            hyd_count = conn.execute("SELECT COUNT(*) AS n FROM hydration_events").fetchone()["n"]
            fuel_count = conn.execute("SELECT COUNT(*) AS n FROM fueling_events").fetchone()["n"]
            sum_count = conn.execute("SELECT COUNT(*) AS n FROM nutrition_daily_summary").fetchone()["n"]
        return {
            "tool": "qbot_nutrition_status",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "food_items_count": food_count,
            "meal_logs_count": meal_count,
            "hydration_events_count": hyd_count,
            "fueling_events_count": fuel_count,
            "daily_summaries_count": sum_count,
        }
    except Exception as exc:
        return {"tool": "qbot_nutrition_status", "status": "ERROR", "error": str(exc)}


# ── Meal Template tools ─────────────────────────────────────────────────────

def _tool_qbot_nutrition_template_create(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    name = str(_args.get("name", "")).strip()
    if not name:
        return {"tool": "qbot_nutrition_template_create", "status": "ERROR", "error": "name required"}
    try:
        from qbot_nutrition_db import template_create
        tmpl = template_create(
            name=name,
            serving_label=str(_args.get("serving_label", "porcja")),
            kcal=float(_args.get("kcal", 0)),
            carbs_g=float(_args.get("carbs_g", 0)),
            protein_g=float(_args.get("protein_g", 0)),
            fat_g=float(_args.get("fat_g", 0)),
            fiber_g=float(_args.get("fiber_g", 0)),
            sodium_mg=float(_args.get("sodium_mg", 0)),
            source=str(_args.get("source", "manual")),
            confidence=str(_args.get("confidence", "high")),
            notes=_args.get("notes"),
            assumptions_json=_args.get("assumptions_json"),
        )
        return {"tool": "qbot_nutrition_template_create", "safety_class": "WRITE_SAFE", "status": "OK", "template": tmpl}
    except Exception as exc:
        return {"tool": "qbot_nutrition_template_create", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_template_list(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    try:
        from qbot_nutrition_db import template_list
        templates = template_list(limit=int(_args.get("limit", 50)))
        return {"tool": "qbot_nutrition_template_list", "safety_class": "READ_ONLY", "status": "OK", "count": len(templates), "templates": templates}
    except Exception as exc:
        return {"tool": "qbot_nutrition_template_list", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_template_get(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    name = str(_args.get("name", "")).strip()
    tid = _args.get("id")
    try:
        from qbot_nutrition_db import template_get, template_get_by_name
        tmpl = template_get(int(tid)) if tid else template_get_by_name(name)
        if not tmpl:
            return {"tool": "qbot_nutrition_template_get", "status": "NOT_FOUND"}
        return {"tool": "qbot_nutrition_template_get", "safety_class": "READ_ONLY", "status": "OK", "template": tmpl}
    except Exception as exc:
        return {"tool": "qbot_nutrition_template_get", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_template_delete(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    name = str(_args.get("name", "")).strip()
    tid = _args.get("id")
    dry_run = bool(_args.get("dry_run", False))
    try:
        from qbot_nutrition_db import template_get, template_get_by_name, template_delete
        tmpl = template_get(int(tid)) if tid else template_get_by_name(name)
        if not tmpl:
            return {"tool": "qbot_nutrition_template_delete", "status": "NOT_FOUND"}
        if dry_run:
            return {"tool": "qbot_nutrition_template_delete", "safety_class": "WRITE_SAFE", "status": "DRY_RUN", "would_delete": True, "template": tmpl}
        template_delete(tmpl["id"])
        return {"tool": "qbot_nutrition_template_delete", "safety_class": "WRITE_SAFE", "status": "OK", "deleted": True}
    except Exception as exc:
        return {"tool": "qbot_nutrition_template_delete", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_template_import(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    data = _args.get("templates")
    if not isinstance(data, list):
        return {"tool": "qbot_nutrition_template_import", "status": "ERROR", "error": "templates must be a list"}
    dry_run = bool(_args.get("dry_run", False))
    try:
        from qbot_nutrition_db import template_import_batch
        result = template_import_batch(data, dry_run=dry_run)
        result["tool"] = "qbot_nutrition_template_import"
        result["safety_class"] = "READ_ONLY" if dry_run else "WRITE_SAFE"
        result["status"] = "OK"
        return result
    except Exception as exc:
        return {"tool": "qbot_nutrition_template_import", "status": "ERROR", "error": str(exc)}


def _tool_qbot_nutrition_meal_from_template(_args: dict | None = None) -> dict[str, Any]:
    _args = _args or {}
    template_name = str(_args.get("template", "")).strip()
    date_str = str(_args.get("date", ""))
    if not template_name:
        return {"tool": "qbot_nutrition_meal_from_template", "status": "ERROR", "error": "template name required"}
    try:
        from datetime import date as dt_date
        from qbot_nutrition_db import template_get_by_name, meal_log_create, daily_summary_compute
        import json as _json
        tmpl = template_get_by_name(template_name)
        if not tmpl:
            return {"tool": "qbot_nutrition_meal_from_template", "status": "NOT_FOUND", "error": f"template '{template_name}' not found"}
        day = date_str or dt_date.today().isoformat()
        dry_run = bool(_args.get("dry_run", False))
        item = {
            "food_name": tmpl["name"],
            "amount": 1,
            "unit": tmpl.get("serving_label", "porcja"),
            "kcal": tmpl["kcal"],
            "carbs_g": tmpl["carbs_g"],
            "protein_g": tmpl["protein_g"],
            "fat_g": tmpl["fat_g"],
            "fiber_g": tmpl.get("fiber_g", 0),
            "sodium_mg": tmpl.get("sodium_mg", 0),
        }
        if dry_run:
            return {"tool": "qbot_nutrition_meal_from_template", "safety_class": "WRITE_SAFE", "status": "DRY_RUN", "template": template_name, "item": item, "date": day}
        context = _json.dumps({"source":"template","template_id":tmpl["id"],"template_name":tmpl["name"]})
        meal_log_create(meal_type="meal", context=context, note=f"from template: {template_name}", eaten_at=f"{day}T12:00:00", items=[item])
        s = daily_summary_compute(day)
        return {"tool": "qbot_nutrition_meal_from_template", "safety_class": "WRITE_SAFE", "status": "OK", "template": template_name, "date": day, "summary": _serialize_summary(s) if s else None}
    except Exception as exc:
        return {"tool": "qbot_nutrition_meal_from_template", "status": "ERROR", "error": str(exc)}


def _serialize_summary(s: dict) -> dict:
    return {k: v for k, v in s.items() if k in ("kcal_total","carbs_total","protein_total","fat_total","fiber_total","sodium_total","fluids_total")}
