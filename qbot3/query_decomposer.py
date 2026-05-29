#!/usr/bin/env python3
"""QBot3 Query Decomposer — separates domain task from control/meta directives.

Raw query → {domain_task_text, execution_intent, safety_intent,
             control_directives, excluded_spans, confidence}
"""

from __future__ import annotations

import re
from typing import Any

# ── Control directive patterns ─────────────────────────────────────────
# Each entry: regex pattern, directive_type, field

_CONTROL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Execution intent
    (re.compile(r'\b(?:bez zapisu|nie zapisuj|nie wysyłaj|nie zapisuj tego)\b', re.I), "no_write", "execution"),
    (re.compile(r'\b(?:tylko przygotuj draft|przygotuj draft|zrób draft|draft)\b', re.I), "draft_only", "execution"),
    (re.compile(r'\b(?:dry.run|dry_run|tryb suchy)\b', re.I), "dry_run", "execution"),
    (re.compile(r'\b(?:bez wykonywania|bez wykonania|nie wykonuj|nie wykonuj akcji)\b', re.I), "no_execute", "execution"),
    (re.compile(r'\b(?:tylko plan|pokaż plan|pokaż tylko plan)\b', re.I), "plan_only", "execution"),

    # Safety intent
    (re.compile(r'\b(?:nie otwieraj|bez otwierania|nie otwieraj furtki)\b', re.I), "no_unlock", "safety"),
    (re.compile(r'\b(?:nie wysyłaj|bez wysyłania|nie wysyłaj maila)\b', re.I), "no_send", "safety"),
    (re.compile(r'\b(?:nie uploaduj|bez uploadu|nie wysyłaj do garmin|bez wysyłania do garmin)\b', re.I), "no_upload", "safety"),
    (re.compile(r'\b(?:nie usuwaj|nie kasuj|bez usuwania|bez kasowania)\b', re.I), "no_delete", "safety"),
    (re.compile(r'\b(?:bez commitu|nie commit|nie commituj)\b', re.I), "no_commit", "safety"),
    (re.compile(r'\b(?:bez akcji|nie dotykaj danych|tylko sprawdź|tylko odczyt)\b', re.I), "read_only", "safety"),
    (re.compile(r'\b(?:zapytaj przed|potwierdź przed|wymaga potwierdzenia)\b', re.I), "require_confirm", "safety"),

    # Response format
    (re.compile(r'\b(?:pokaż json|jako json|jako json)\b', re.I), "show_json", "response"),
    (re.compile(r'\b(?:bez json|bez jsona|czytelnie|ludzkim językiem)\b', re.I), "human_only", "response"),
    (re.compile(r'\b(?:krótko|zwięźle|w skrócie|jedno zdanie)\b', re.I), "concise", "response"),
    (re.compile(r'\b(?:debug|trace|technical)\b', re.I), "debug_ok", "response"),

    # Test / probe
    (re.compile(r'\b(?:testowo|test|na próbę|próbny)\b', re.I), "test_probe", "test"),
    (re.compile(r'\b(?:smoke|smoke test)\b', re.I), "smoke", "test"),

    # Action draft marker (contextual — not always control)
    (re.compile(r'\b(?:action_draft|action draft)\b', re.I), "action_draft_marker", "execution"),
]

# Words that are exclusively control directives (not domain content)
_CONTROL_WORDS = {
    "bez", "nie", "tylko", "jako", "na", "ale",
    "zapisu", "wykonania", "wykonywania", "uploadu", "otwierania",
    "wysyłania", "commitu", "akcji",
    "action_draft", "dry", "run", "dry_run",
    "draft", "testowo", "próbny", "test", "smoke",
}


def decompose_query(raw_query: str) -> dict[str, Any]:
    """Decompose a raw user query into domain task + control directives.

    Returns:
      raw_query: original query
      domain_task_text: query with control directives removed
      execution_intent: read_only | draft_only | dry_run | execute_requested | destructive | unknown
      safety_intent: list of safety flags
      response_intent: list of response format flags
      test_intent: test_probe | smoke | production_request
      control_directives: list of {text, type, field, span}
      excluded_spans: list of (start, end) tuples to exclude from payload extraction
    """
    ql = raw_query
    directives: list[dict[str, Any]] = []
    excluded_spans: list[tuple[int, int]] = []
    execution_flags: set[str] = set()
    safety_flags: set[str] = set()
    response_flags: set[str] = set()
    test_flags: set[str] = set()

    for pattern, directive_type, field in _CONTROL_PATTERNS:
        for match in pattern.finditer(ql):
            start, end = match.start(), match.end()
            # Avoid overlapping spans
            if any(s <= start < e or s < end <= e for s, e in excluded_spans):
                continue
            directives.append({
                "text": match.group(),
                "type": directive_type,
                "field": field,
                "span": [start, end],
            })
            excluded_spans.append((start, end))
            if field == "execution":
                execution_flags.add(directive_type)
            elif field == "safety":
                safety_flags.add(directive_type)
            elif field == "response":
                response_flags.add(directive_type)
            elif field == "test":
                test_flags.add(directive_type)

    # Build domain_task_text by removing control spans
    if excluded_spans:
        merged_spans = _merge_spans(excluded_spans)
        parts = []
        pos = 0
        for s, e in sorted(merged_spans):
            if pos < s:
                parts.append(ql[pos:s])
            pos = e
        if pos < len(ql):
            parts.append(ql[pos:])
        domain_task_text = "".join(parts).strip().rstrip(" ,;:")
    else:
        domain_task_text = ql.strip()

    # Determine primary execution intent
    execution_intent = _resolve_execution_intent(execution_flags)

    test_intent = "production_request"
    if "test_probe" in test_flags or "smoke" in test_flags:
        test_intent = test_flags.pop() if test_flags else "test_probe"

    return {
        "raw_query": raw_query,
        "domain_task_text": domain_task_text,
        "execution_intent": execution_intent,
        "safety_intent": sorted(safety_flags),
        "response_intent": sorted(response_flags),
        "test_intent": test_intent,
        "control_directives": directives,
        "excluded_spans": sorted(excluded_spans),
        "confidence": 0.9 if directives else 0.5,
    }


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    sorted_spans = sorted(spans)
    merged = [sorted_spans[0]]
    for s, e in sorted_spans[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _resolve_execution_intent(flags: set[str]) -> str:
    if "no_execute" in flags:
        return "read_only"
    if "no_write" in flags or "draft_only" in flags:
        return "draft_only"
    if "dry_run" in flags:
        return "dry_run"
    if "destructive" in flags:
        return "destructive_requested"
    return "execute_requested"


def is_payload_contaminated(payload: dict[str, Any], decomposition: dict[str, Any], action_type: str) -> list[str]:
    """Check if payload fields contain control directive text.

    Returns list of contamination warnings.
    """
    warnings: list[str] = []
    directives = decomposition.get("control_directives", [])
    if directives and isinstance(directives[0], dict):
        directive_texts = [d.get("text", "").lower() for d in directives]
    else:
        directive_texts = [d.lower() for d in directives if isinstance(d, str)]

    if not directive_texts:
        return warnings

    # Fields to check for contamination
    sensitive_fields = {
        "nutrition_log_add": ["meal_name", "food_name"],
        "calendar_event_add": ["title", "description"],
        "reminder_add": ["title", "message"],
        "planning_fact_add": ["title"],
        "qbot_doc_append": ["content_markdown"],
    }

    for field in sensitive_fields.get(action_type, []):
        val = str(payload.get(field, "")).lower().strip()
        for dt in directive_texts:
            dt_clean = dt.strip()
            if dt_clean and dt_clean in val and len(dt_clean) > 3:
                warnings.append(f"contamination:{field} contains directive '{dt_clean[:30]}'")
                break

    return warnings


def clean_payload(payload: dict[str, Any], contamination_warnings: list[str], action_type: str,
                  decomposition: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove contaminated parts from payload fields."""
    cleaned = dict(payload)
    sensitive_fields = {
        "nutrition_log_add": ["meal_name", "food_name"],
        "calendar_event_add": ["title", "description"],
        "reminder_add": ["title", "message"],
        "planning_fact_add": ["title"],
        "qbot_doc_append": ["content_markdown"],
    }

    for warning in contamination_warnings:
        if "contamination:" not in warning:
            continue
        parts = warning.split(":", 1)
        if len(parts) < 2:
            continue
        field_info = parts[1]
        field_name = field_info.split(" ")[0] if " " in field_info else field_info
        field_name = field_name.replace("contains", "").strip()
        # Remove the directives from field value
        val = str(cleaned.get(field_name, ""))
        if not val:
            continue
        for field in sensitive_fields.get(action_type, []):
            if field_name.endswith(field) or field in field_name:
                # Remove known directive patterns from value
                for pat, _, _ in _CONTROL_PATTERNS:
                    new_val = pat.sub("", val).strip()
                    if new_val != val:
                        val = new_val
                val = re.sub(r'\s+,?\s*$', '', val).strip()
                val = re.sub(r'^,\s*', '', val).strip()
                if val:
                    cleaned[field_name] = val
                else:
                    cleaned.pop(field_name, None)
                break
        break  # Process one warning at a time

    return cleaned
