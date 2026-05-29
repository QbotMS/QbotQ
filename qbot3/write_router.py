#!/usr/bin/env python3
"""QBot3 Write Router — write intent classification, draft validation, pending tasks.

qbot.query NEVER executes writes. It returns action_draft.
qbot.action_execute is the only commit path, after confirm=true + idempotency_key.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from qbot3.safety import _ACTION_ALLOWLIST

# ── Write intent classification ────────────────────────────────────────

READ_ONLY_QUERY = "READ_ONLY_QUERY"
WRITE_DRAFT_REQUEST = "WRITE_DRAFT_REQUEST"
WRITE_EXECUTE_REQUEST = "WRITE_EXECUTE_REQUEST"
AMBIGUOUS_WRITE = "AMBIGUOUS_WRITE"
DESTRUCTIVE_WRITE = "DESTRUCTIVE_WRITE"

# Keywords that signal write intent (first-match priority)
_WRITE_KEYWORDS: list[tuple[list[str], str, str | None]] = [
    # (keywords, classification, suggested_action_type)
    (["usuń wszystko", "usuń wszystkie", "wyczyść", "skasuj wszystko", "delete all"], DESTRUCTIVE_WRITE, None),
    (["usuń", "skasuj", "delete", "remove", "usun"], AMBIGUOUS_WRITE, None),
    (["dodaj posiłek", "dodaj jedzenie", "dodaj do spożycia", "log food", "nutrition_log_add",
      "zjedz", "jadłem", "jadłam", "zjadł", "zjadłam"], WRITE_DRAFT_REQUEST, "nutrition_log_add"),
    (["dodaj event", "dodaj wydarzenie", "zaplanuj event", "zapisz do kalendarza",
      "dodaj do kalendarza", "calendar_event_add", "qcal_event_add"], WRITE_DRAFT_REQUEST, "calendar_event_add"),
    (["przypomnij", "reminder", "dodaj przypomnienie", "reminder_add",
      "qcal_reminder_add", "przypomnij mi"], WRITE_DRAFT_REQUEST, "reminder_add"),
    (["zapamiętaj fakt", "zapamiętaj", "zapisz fakt", "planning_fact_add",
      "notuj", "zanotuj", "do zapamiętania"], WRITE_DRAFT_REQUEST, "planning_fact_add"),
    (["zapisz do dokumentu", "dopisz do bibili", "dopisz do knowhow",
      "qbot_doc_append", "doc append", "update doc"], WRITE_DRAFT_REQUEST, "qbot_doc_append"),
    (["zapisz", "dodaj", "utwórz", "stwórz", "draft"], AMBIGUOUS_WRITE, None),
]


def classify_write_intent(question: str) -> dict[str, Any]:
    """Classify a query's write intent.

    Returns:
      type: READ_ONLY_QUERY | WRITE_DRAFT_REQUEST | WRITE_EXECUTE_REQUEST
            | AMBIGUOUS_WRITE | DESTRUCTIVE_WRITE
      action_type: suggested action type or None
      confidence: 0.0-1.0
    """
    ql = question.lower().strip()

    for keywords, cls, suggested_at in _WRITE_KEYWORDS:
        if any(kw in ql for kw in keywords):
            return {
                "type": cls,
                "action_type": suggested_at,
                "confidence": 0.9,
                "matched_keyword": keywords[0],
            }
    return {"type": READ_ONLY_QUERY, "action_type": None, "confidence": 0.0}


def validate_action_type(action_type: str) -> dict[str, Any]:
    """Check if action_type is valid and in allowlist."""
    if action_type in _ACTION_ALLOWLIST:
        return {"valid": True, "action_type": action_type}
    return {"valid": False, "action_type": action_type,
            "error": f"action_type '{action_type}' not in allowlist",
            "allowed": sorted(_ACTION_ALLOWLIST)}


# ── Action draft builder ──────────────────────────────────────────────

# Known action_types and their required/optional payload fields
_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "nutrition_log_add": {
        "required": [],
        "optional": ["date", "meal_name", "kcal_total", "protein_g", "carbs_g", "fat_g", "template_id"],
        "description": "Log a meal entry",
    },
    "calendar_event_add": {
        "required": ["title"],
        "optional": ["date_start", "date_end", "time_start", "description", "event_type", "all_day"],
        "description": "Add a calendar event",
    },
    "reminder_add": {
        "required": ["title", "date"],
        "optional": ["time", "message"],
        "description": "Add a reminder",
    },
    "planning_fact_add": {
        "required": ["title"],
        "optional": ["fact_type", "date", "fact_json"],
        "description": "Save a planning fact",
    },
    "memory_confirmed_fact_add": {
        "required": ["key", "value"],
        "optional": ["memory_type"],
        "description": "Save a confirmed fact to memory",
    },
    "qbot_doc_append": {
        "required": ["target_document", "content_markdown"],
        "optional": ["heading"],
        "description": "Append content to a QBot document",
    },
}


def get_action_schema(action_type: str) -> dict[str, Any] | None:
    return _ACTION_SCHEMAS.get(action_type)


def build_draft(action_type: str, payload: dict[str, Any], question: str) -> dict[str, Any]:
    """Build a standardized action_draft from a write intent."""
    from qbot3.tool_registry import _idempotency_key as _idk

    schema = _ACTION_SCHEMAS.get(action_type, {})
    required = schema.get("required", [])

    # Detect missing fields
    missing = [f for f in required if not payload.get(f)]
    provided = {k: v for k, v in payload.items() if v is not None and v != ""}

    idem_key = _idk(action_type[:8] if action_type else "wr", question)

    draft = {
        "action_type": action_type,
        "payload": provided,
        "requires_confirm": True,
        "idempotency_key_suggestion": idem_key,
        "dry_run_available": True,
        "safety_notes": [f"write action: {action_type}"],
        "human_summary": _build_human_summary(action_type, provided, question),
    }

    if missing:
        draft["missing_fields"] = missing
        draft["pending_task"] = True
        draft["clarification_question"] = _build_clarification(action_type, missing, question)
    else:
        draft["missing_fields"] = []

    return draft


def _build_human_summary(action_type: str, payload: dict[str, Any], question: str) -> str:
    summaries = {
        "nutrition_log_add": f"Dodanie posiłku: {payload.get('meal_name', '?')} ({payload.get('kcal_total', '?')} kcal)",
        "calendar_event_add": f"Dodanie eventu: {payload.get('title', '?')}",
        "reminder_add": f"Dodanie przypomnienia: {payload.get('title', '?')}",
        "planning_fact_add": f"Zapisanie faktu: {payload.get('title', '?')}",
        "memory_confirmed_fact_add": f"Zapisanie do pamięci: {payload.get('key', '?')}",
        "qbot_doc_append": f"Dopisanie do dokumentu: {payload.get('target_document', '?')}",
    }
    return summaries.get(action_type, f"{action_type}: {str(payload)[:100]}")


def _build_clarification(action_type: str, missing: list[str], question: str) -> str:
    field_names_pl = {
        "title": "tytuł",
        "date": "datę",
        "time": "godzinę",
        "date_start": "datę rozpoczęcia",
        "date_end": "datę zakończenia",
        "time_start": "godzinę rozpoczęcia",
        "meal_name": "nazwę posiłku",
        "key": "klucz (np. nazwa faktu)",
        "value": "wartość",
        "target_document": "nazwę dokumentu docelowego",
        "content_markdown": "treść do dopisania",
    }
    field_strs = [field_names_pl.get(f, f) for f in missing]
    if len(field_strs) == 1:
        return f"Podaj {field_strs[0]}."
    return f"Podaj {', '.join(field_strs[:-1])} i {field_strs[-1]}."
