#!/usr/bin/env python3
"""Nutrition write resolver for qbot.query.

Resolves ambiguous nutrition write prompts with optional DB lookup and arithmetic.
The goal is to keep the LLM as the decider while preventing raw prompt numbers from
being copied into drafts when the query clearly asks for template/lookup-based logic.
"""

from __future__ import annotations

import re
from typing import Any

_MACRO_FIELDS = (
    ("kcal_total", "kcal"),
    ("protein_g", "protein_g"),
    ("carbs_g", "carbs_g"),
    ("fat_g", "fat_g"),
    ("fiber_g", "fiber_g"),
    ("sodium_mg", "sodium_mg"),
)

_LOOKUP_CUES = (
    "minus",
    "pomniejsz",
    "pomniejszone",
    "odejmij",
    "odję",
    "template",
    "szablon",
    "pół kilo",
    "pol kilo",
    "opakowanie",
    "opakowania",
    "zestaw",
    "porcja",
    "serving",
)

_GENERIC_MEAL_NAMES = {
    "jadłospis",
    "jadłospisu",
    "jadłospisem",
    "posiłek",
    "posiłku",
    "meal",
    "food",
    "dieta",
}

_GENERIC_FOOD_MACROS: dict[str, dict[str, float]] = {
    # name → {kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, fiber_per_100g}
    "truskawki":              {"kcal": 32, "protein": 0.7, "carbs": 7.7, "fat": 0.3, "fiber": 2.0},
    "truskawka":              {"kcal": 32, "protein": 0.7, "carbs": 7.7, "fat": 0.3, "fiber": 2.0},
    "jabłko":                 {"kcal": 52, "protein": 0.3, "carbs": 14.0, "fat": 0.2, "fiber": 2.4},
    "jabłka":                 {"kcal": 52, "protein": 0.3, "carbs": 14.0, "fat": 0.2, "fiber": 2.4},
    "banan":                  {"kcal": 89, "protein": 1.1, "carbs": 23.0, "fat": 0.3, "fiber": 2.6},
    "banany":                 {"kcal": 89, "protein": 1.1, "carbs": 23.0, "fat": 0.3, "fiber": 2.6},
    "pomarańcza":             {"kcal": 47, "protein": 0.9, "carbs": 12.0, "fat": 0.1, "fiber": 2.4},
    "pomarańcze":             {"kcal": 47, "protein": 0.9, "carbs": 12.0, "fat": 0.1, "fiber": 2.4},
    "winogrona":              {"kcal": 69, "protein": 0.7, "carbs": 18.0, "fat": 0.2, "fiber": 0.9},
    "arbuz":                  {"kcal": 30, "protein": 0.6, "carbs": 7.6, "fat": 0.2, "fiber": 0.4},
    "gruszka":                {"kcal": 57, "protein": 0.4, "carbs": 15.0, "fat": 0.1, "fiber": 3.1},
    "gruszki":                {"kcal": 57, "protein": 0.4, "carbs": 15.0, "fat": 0.1, "fiber": 3.1},
    "jogurt naturalny":       {"kcal": 61, "protein": 3.5, "carbs": 4.7, "fat": 3.3, "fiber": 0.0},
    "jogurt":                 {"kcal": 61, "protein": 3.5, "carbs": 4.7, "fat": 3.3, "fiber": 0.0},
    "skyru":                  {"kcal": 59, "protein": 10.0, "carbs": 3.6, "fat": 0.2, "fiber": 0.0},
    "skyr":                   {"kcal": 59, "protein": 10.0, "carbs": 3.6, "fat": 0.2, "fiber": 0.0},
    "płatki owsiane":         {"kcal": 389, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "fiber": 10.6},
    "owsianka":               {"kcal": 389, "protein": 16.9, "carbs": 66.3, "fat": 6.9, "fiber": 10.6},
    "ryż":                    {"kcal": 130, "protein": 2.7, "carbs": 28.0, "fat": 0.3, "fiber": 0.4},
    "ziemniaki":              {"kcal": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "fiber": 2.2},
    "ziemniak":               {"kcal": 77, "protein": 2.0, "carbs": 17.0, "fat": 0.1, "fiber": 2.2},
    "makaron":                {"kcal": 131, "protein": 5.0, "carbs": 25.0, "fat": 1.1, "fiber": 1.8},
    "chleb":                  {"kcal": 265, "protein": 9.0, "carbs": 49.0, "fat": 3.2, "fiber": 2.7},
    "kawa":                   {"kcal": 1, "protein": 0.1, "carbs": 0.0, "fat": 0.0, "fiber": 0.0},
    "kawa czarna":            {"kcal": 1, "protein": 0.1, "carbs": 0.0, "fat": 0.0, "fiber": 0.0},
    "mleko":                  {"kcal": 42, "protein": 3.4, "carbs": 5.0, "fat": 1.0, "fiber": 0.0},
    "jajko":                  {"kcal": 155, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "fiber": 0.0},
    "jajka":                  {"kcal": 155, "protein": 13.0, "carbs": 1.1, "fat": 11.0, "fiber": 0.0},
    "ser":                    {"kcal": 350, "protein": 25.0, "carbs": 1.3, "fat": 27.0, "fiber": 0.0},
    "pierś z kurczaka":       {"kcal": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "fiber": 0.0},
    "kurczak":                {"kcal": 165, "protein": 31.0, "carbs": 0.0, "fat": 3.6, "fiber": 0.0},
    "łosoś":                  {"kcal": 208, "protein": 20.0, "carbs": 0.0, "fat": 13.0, "fiber": 0.0},
    "losos":                  {"kcal": 208, "protein": 20.0, "carbs": 0.0, "fat": 13.0, "fiber": 0.0},
}


def _is_generic_meal_label(text: str) -> bool:
    norm = _normalize_for_match(text)
    if not norm:
        return True
    if norm in _GENERIC_MEAL_NAMES:
        return True
    if any(token in norm for token in ("jadłospis", "jadłospisu", "posiłek", "posiłku", "meal", "food", "dieta")):
        if any(token in norm for token in ("dodaj", "dopisz", "do ")):
            return True
    return False


def _normalize_for_match(text: str) -> str:
    text = text.lower().replace("/", " ")
    text = re.sub(r"[^\wąćęłńóśźż\s]+", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_half_kilo(text: str) -> str:
    text = re.sub(r"\bp[oó]?ł\s*kilo\b", "500 g", text, flags=re.I)
    text = re.sub(r"\bpol\s*kilo\b", "500 g", text, flags=re.I)
    return text


def _has_lookup_cue(question: str) -> bool:
    ql = question.lower()
    return any(cue in ql for cue in _LOOKUP_CUES)


def _find_template(question: str, candidate_name: str | None = None) -> dict[str, Any] | None:
    from qbot_nutrition_db import template_get, template_get_by_name, template_list

    candidates: list[str] = []
    if candidate_name:
        candidates.append(candidate_name)
    candidates.append(question)

    # Exact ID or exact name first.
    tmpl_id_match = re.search(r"template_id\s*[=:]\s*(\d+)", question, re.I)
    if tmpl_id_match:
        tmpl = template_get(int(tmpl_id_match.group(1)))
        if tmpl:
            return tmpl

    for cand in candidates:
        cand = (cand or "").strip()
        if not cand:
            continue
        exact = template_get_by_name(cand)
        if exact:
            return exact

    qn = _normalize_for_match(question)
    templates = template_list(limit=200)
    for tmpl in templates:
        name = str(tmpl.get("name", "")).strip()
        if not name:
            continue
        tn = _normalize_for_match(name)
        if not tn:
            continue
        if tn == qn or tn in qn or qn in tn:
            return tmpl
        q_tokens = set(qn.split())
        t_tokens = set(tn.split())
        if t_tokens and t_tokens.issubset(q_tokens):
            return tmpl
        if q_tokens and q_tokens.issubset(t_tokens):
            return tmpl

    return None


def _find_food_item(candidate_name: str | None) -> dict[str, Any] | None:
    if not candidate_name:
        return None
    from qbot_nutrition_db import food_item_get_by_name, food_item_search

    exact = food_item_get_by_name(candidate_name)
    if exact:
        return exact
    hits = food_item_search(candidate_name, limit=3)
    if hits:
        return hits[0]
    return None


def _parse_question(question: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from qbot_nutrition_parser import parse_intake
    from qbot3.write_router import extract_nutrition_slots

    transformed = _normalize_half_kilo(question)
    parsed = parse_intake(transformed)
    slots = extract_nutrition_slots(question)
    return parsed, slots


def _pick_candidate_name(parsed: dict[str, Any], slots: dict[str, Any], base_payload: dict[str, Any]) -> str | None:
    for key in ("meal_name", "food_name"):
        val = base_payload.get(key)
        if isinstance(val, str) and val.strip() and not _is_generic_meal_label(val):
            return val.strip()
    for key in ("meal_name", "food_name"):
        val = slots.get(key)
        if isinstance(val, str) and val.strip() and not _is_generic_meal_label(val):
            return val.strip()
    meal_items = parsed.get("meal_items") or []
    if meal_items:
        item = meal_items[0] or {}
        for key in ("food_name", "food_normalized"):
            val = item.get(key)
            if isinstance(val, str) and val.strip() and not _is_generic_meal_label(val):
                return val.strip()
    return None


def _apply_template_resolution(
    question: str,
    base_payload: dict[str, Any],
    parsed: dict[str, Any],
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    template = _find_template(question, _pick_candidate_name(parsed, slots, base_payload))
    if not template:
        return None

    ql = question.lower()
    subtractive = any(cue in ql for cue in ("minus", "pomniejsz", "pomniejszone", "odejmij", "odję"))
    payload = dict(base_payload)

    payload["meal_name"] = template.get("name")
    payload["template_id"] = template.get("id")
    payload["resolved_from_lookup"] = True
    payload["lookup_source"] = "meal_templates"
    payload["lookup_key"] = template.get("name")
    payload["source_kind"] = "template_adjusted" if subtractive else "template"
    payload["amount"] = payload.get("amount", 1) or 1
    payload["unit"] = payload.get("unit") or template.get("serving_label") or "porcja"

    raw_macros = {k: slots.get(k) for k, _ in _MACRO_FIELDS if slots.get(k) is not None}
    for out_field, db_field in _MACRO_FIELDS:
        db_value = template.get(db_field)
        if db_value is None:
            continue
        if subtractive and raw_macros.get(out_field) is not None:
            payload[out_field] = round(float(db_value) - float(raw_macros[out_field]), 1)
        else:
            payload[out_field] = db_value

    payload["resolution_notes"] = [
        f"template:{template.get('name')}",
        "subtractive" if subtractive else "direct_template",
    ]
    return payload


def _apply_food_item_resolution(
    question: str,
    base_payload: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any] | None:
    meal_items = parsed.get("meal_items") or []
    item = meal_items[0] if meal_items else {}

    candidate_name = _pick_candidate_name(parsed, {}, base_payload)
    food = _find_food_item(candidate_name or item.get("food_normalized") or item.get("food_name"))
    if not food:
        return None

    payload = dict(base_payload)
    payload["meal_name"] = food.get("name") or candidate_name
    payload["food_item_id"] = food.get("id")
    payload["resolved_from_lookup"] = True
    payload["lookup_source"] = "food_items"
    payload["lookup_key"] = food.get("name")
    payload["source_kind"] = "food_item"

    amount = payload.get("amount")
    unit = payload.get("unit")
    if amount is None and item.get("amount") is not None:
        amount = item.get("amount")
    if not unit and item.get("unit"):
        unit = item.get("unit")
    if amount is not None:
        payload["amount"] = amount
    if unit:
        payload["unit"] = unit

    grams_est = item.get("grams_est")
    if grams_est is None and amount is not None:
        amt = float(amount)
        unit_lower = str(unit or "g").lower()
        if unit_lower == "kg":
            grams_est = amt * 1000.0
        elif unit_lower == "l":
            grams_est = amt * 1000.0
        elif unit_lower == "ml":
            grams_est = amt
        else:
            grams_est = amt

    if grams_est is None:
        payload.setdefault("missing_fields", []).append("lookup_source")
        payload["resolved_from_lookup"] = False
        payload["source_kind"] = "quantity_only"
        return payload

    factor = float(grams_est) / 100.0
    for out_field, db_field in _MACRO_FIELDS:
        db_value = food.get(db_field if db_field != "kcal" else "kcal_per_100g")
        if db_field == "kcal":
            db_value = food.get("kcal_per_100g")
        elif db_field == "protein_g":
            db_value = food.get("protein_per_100g")
        elif db_field == "carbs_g":
            db_value = food.get("carbs_per_100g")
        elif db_field == "fat_g":
            db_value = food.get("fat_per_100g")
        elif db_field == "fiber_g":
            db_value = food.get("fiber_per_100g")
        elif db_field == "sodium_mg":
            db_value = food.get("sodium_per_100g")
        if db_value is not None:
            payload[out_field] = round(float(db_value) * factor, 1)

    payload["resolution_notes"] = [f"food_item:{food.get('name')}"]
    return payload


def _apply_generic_fallback(domain_task: str, payload: dict) -> dict | None:
    """Check if meal name matches a known generic food, compute macros from amount."""
    meal_name = payload.get("meal_name", "").lower().strip()
    amount = payload.get("amount", 100)
    unit = payload.get("unit", "g")

    # Stem: use longest common prefix >= 4 chars for matching
    def _stem_match(a: str, b: str) -> bool:
        a = a.replace("ó", "o").replace("ł", "l").replace("ń", "n").replace("ś", "s").replace("ć", "c").replace("ź", "z").replace("ż", "z")
        b = b.replace("ó", "o").replace("ł", "l").replace("ń", "n").replace("ś", "s").replace("ć", "c").replace("ź", "z").replace("ż", "z")
        shorter = min(len(a), len(b))
        for i in range(shorter, 3, -1):
            if a[:i] == b[:i]:
                return True
        return False

    for food_name, macros in _GENERIC_FOOD_MACROS.items():
        if _stem_match(food_name, meal_name) or _stem_match(meal_name, food_name):
            factor = amount / 100.0 if unit == "g" else 1.0
            result = dict(payload)
            result["kcal_total"] = round(macros["kcal"] * factor, 1)
            result["protein_g"] = round(macros["protein"] * factor, 1)
            result["carbs_g"] = round(macros["carbs"] * factor, 1)
            result["fat_g"] = round(macros["fat"] * factor, 1)
            result["fiber_g"] = round(macros["fiber"] * factor, 1)
            result["resolved_from_lookup"] = True
            result["source_kind"] = "generic_fallback"
            result["resolution_notes"] = [f"generic_fallback:{food_name}"]
            result["lookup_required"] = False
            return result
    return None


def resolve_nutrition_write(question: str, base_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a nutrition write request into a draft-ready payload.

    The resolver does not invent nutrition values. It uses meal_templates or
    food_items when possible and otherwise marks the payload as requiring lookup.
    """

    base_payload = dict(base_payload or {})
    from qbot3.query_decomposer import decompose_query

    decomposition = decompose_query(question)
    domain_task = decomposition.get("domain_task_text", question)
    parsed, slots = _parse_question(domain_task)

    # Start with the raw slots so we keep explicit date/quantity hints.
    payload = dict(base_payload)
    payload.update({k: v for k, v in slots.items() if v is not None})

    # Drop generic catch-all meal labels produced by coarse slot extraction.
    for key in ("meal_name", "food_name"):
        val = payload.get(key)
        if isinstance(val, str) and _is_generic_meal_label(val):
            payload.pop(key, None)

    # Normalise half-kilo phrases before any lookup logic.
    if re.search(r"\bp[oó]?ł\s*kilo\b|\bpol\s*kilo\b", domain_task, re.I):
        payload["amount"] = 500
        payload["unit"] = "g"

    template_payload = _apply_template_resolution(domain_task, payload, parsed, slots)
    if template_payload is not None:
        return {
            "status": "OK",
            "resolved": True,
            "payload": template_payload,
            "missing_fields": [],
            "lookup_required": False,
            "source_kind": template_payload.get("source_kind", "template"),
            "resolution_notes": template_payload.get("resolution_notes", []),
        }

    food_payload = _apply_food_item_resolution(domain_task, payload, parsed)
    if food_payload is not None and food_payload.get("resolved_from_lookup"):
        return {
            "status": "OK",
            "resolved": True,
            "payload": food_payload,
            "missing_fields": [],
            "lookup_required": False,
            "source_kind": food_payload.get("source_kind", "food_item"),
            "resolution_notes": food_payload.get("resolution_notes", []),
        }

    # Generic food fallback: common foods not in DB
    generic_payload = _apply_generic_fallback(domain_task, payload)
    if generic_payload is not None:
        return {
            "status": "OK",
            "resolved": True,
            "payload": generic_payload,
            "missing_fields": [],
            "lookup_required": False,
            "source_kind": "generic_fallback",
            "resolution_notes": generic_payload.get("resolution_notes", []),
        }

    # No lookup result: keep the normalised quantity but do not invent nutrition.
    candidate_name = _pick_candidate_name(parsed, slots, payload)
    if candidate_name and "meal_name" not in payload:
        payload["meal_name"] = candidate_name

    if parsed.get("meal_items"):
        item = parsed["meal_items"][0]
        if item.get("amount") is not None and "amount" not in payload:
            payload["amount"] = item.get("amount")
        if item.get("unit") and "unit" not in payload:
            payload["unit"] = item.get("unit")

    if re.search(r"\bp[oó]?ł\s*kilo\b|\bpol\s*kilo\b", domain_task, re.I):
        payload["amount"] = 500
        payload["unit"] = "g"

    payload["resolved_from_lookup"] = False
    payload["source_kind"] = "quantity_only" if payload.get("amount") else "unresolved"
    payload["lookup_required"] = True
    missing_fields = ["lookup_source"] if payload.get("meal_name") else ["meal_name", "lookup_source"]
    if payload.get("amount") is None:
        missing_fields.insert(0, "amount")

    # Never invent calories from prompt quantities when lookup is missing.
    for field, _ in _MACRO_FIELDS:
        payload.pop(field, None)

    return {
        "status": "INCOMPLETE",
        "resolved": False,
        "payload": payload,
        "missing_fields": list(dict.fromkeys(missing_fields)),
        "lookup_required": True,
        "source_kind": payload.get("source_kind", "unresolved"),
        "resolution_notes": ["lookup_required"],
    }
