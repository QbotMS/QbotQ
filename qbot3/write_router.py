#!/usr/bin/env python3
"""QBot3 Write Router — write intent classification, slot extraction, payload validation.

qbot.query NEVER executes writes. It returns action_draft.
qbot.action_execute is the only commit path, after confirm=true + idempotency_key.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from qbot3.safety import _ACTION_ALLOWLIST

# ── Input kind classification ──────────────────────────────────────────

CONVERSATIONAL_PING = "CONVERSATIONAL_PING"
SMALLTALK = "SMALLTALK"
GENERAL_QUESTION = "GENERAL_QUESTION"
READ_ONLY_TASK = "READ_ONLY_TASK"
WRITE_DRAFT_TASK = "WRITE_DRAFT_TASK"
WRITE_EXECUTE_REQUEST = "WRITE_EXECUTE_REQUEST"
WORKFLOW_AUDIT_REQUEST = "WORKFLOW_AUDIT_REQUEST"
UNKNOWN_TASK_REQUIRES_CAPABILITY = "UNKNOWN_TASK_REQUIRES_CAPABILITY"
UNSUPPORTED_OR_DESTRUCTIVE = "UNSUPPORTED_OR_DESTRUCTIVE"

# Conversational ping patterns (short, no task content)
_PING_PATTERNS = [
    r"^(test|hej|halo|elo|siema|czesc|cześć|dzien dobry|dzień dobry|dobry|witaj| hello|hi|hey)\W*$",
    r"^(dzi.?a|czy dzialasz|czy działasz|jestes tam|jesteś tam|co slychac|co słychać)\W*$",
    r"^ok|ok\.|okay|spoko|dobra|super|git|fajnie$",
]

# Write intent keywords (first-match priority)
_WRITE_KEYWORDS: list[tuple[list[str], str, str | None]] = [
    (["usuń wszystko", "usuń wszystkie", "wyczyść", "skasuj wszystko", "delete all"], UNSUPPORTED_OR_DESTRUCTIVE, None),
    (["usuń", "skasuj", "delete", "remove", "usun"], UNSUPPORTED_OR_DESTRUCTIVE, None),
    (["dodaj posiłek", "dodaj jedzenie", "dodaj do spożycia", "log food", "nutrition_log_add",
      "zjedz", "jadłem", "jadłam", "zjadł", "zjadłam",
      "posiłek", "ryż", "makaron", "mięso", "kalorii", "jedzenie", "truskawek"], WRITE_DRAFT_TASK, "nutrition_log_add"),
    (["dodaj event", "dodaj wydarzenie", "zaplanuj event", "zapisz do kalendarza",
      "dodaj do kalendarza", "calendar_event_add", "qcal_event_add", "zapisz event"], WRITE_DRAFT_TASK, "calendar_event_add"),
    (["przypomnij", "reminder", "dodaj przypomnienie", "reminder_add",
      "qcal_reminder_add", "przypomnij mi"], WRITE_DRAFT_TASK, "reminder_add"),
    (["zapamiętaj fakt", "zapamiętaj", "zapisz fakt", "planning_fact_add",
      "notuj", "zanotuj", "do zapamiętania"], WRITE_DRAFT_TASK, "planning_fact_add"),
    (["zapisz do dokumentu", "dopisz do bibili", "dopisz do knowhow",
      "qbot_doc_append", "doc append", "update doc"], WRITE_DRAFT_TASK, "qbot_doc_append"),
    (["zapisz", "dodaj", "utwórz", "stwórz", "draft"], WRITE_DRAFT_TASK, None),
]


def classify_input_kind(question: str) -> dict[str, Any]:
    """Classify what kind of input the user sent.

    Returns input_kind and action_type if applicable.
    """
    ql = question.lower().strip()

    # 1. Conversational ping — very short, no task
    for pat in _PING_PATTERNS:
        if re.match(pat, ql):
            return {"input_kind": CONVERSATIONAL_PING, "action_type": None, "confidence": 0.95}

    # 2. Smalltalk — casual greetings, check-ins, but not purely ping
    smalltalk_words = ["hej", "cześć", "siema", "witam", "dzien", "dobry", "jak leci",
                       "co tam", "dzieki", "dzięki", "ok", "spoko", "super"]
    word_count = len(ql.split())
    if word_count <= 4 and any(w in ql for w in smalltalk_words):
        return {"input_kind": SMALLTALK, "action_type": None, "confidence": 0.85}

    # 3. Check if it's a question (read intent) — overrides write keywords
    question_starters = ("co ", "czy ", "jaki ", "jaka ", "jakie ", "jaka ", "jacy ", "kiedy ", "gdzie ", "dlaczego ", "po co ", "ile ")
    if ql.startswith(question_starters):
        return {"input_kind": READ_ONLY_TASK, "action_type": None, "confidence": 0.8}

    # 4. Write intent — check keywords
    for keywords, cls, suggested_at in _WRITE_KEYWORDS:
        if any(kw in ql for kw in keywords):
            action_type = suggested_at
            if cls == UNSUPPORTED_OR_DESTRUCTIVE and not suggested_at:
                action_type = "DESTRUCTIVE"
            return {"input_kind": cls, "action_type": action_type, "confidence": 0.9}

    # 4. Default — task or general question
    return {"input_kind": READ_ONLY_TASK, "action_type": None, "confidence": 0.5}


# ── Conversation responses ─────────────────────────────────────────────

_CONVERSATION_RESPONSES = {
    CONVERSATIONAL_PING: "Działam. Jestem podłączony.",
    SMALLTALK: "Hej. Jestem.",
}


def get_conversation_response(input_kind: str) -> str | None:
    return _CONVERSATION_RESPONSES.get(input_kind)


# ── Write slot extraction ──────────────────────────────────────────────

def extract_nutrition_slots(question: str) -> dict[str, Any]:
    """Extract food name, amount, unit from a nutrition query.

    '200g ryżu' → meal_name='ryż', amount=200, unit='g'
    '0,5 kg truskawek' → meal_name='truskawki', amount=0.5, unit='kg'
    """
    ql = question.lower()
    payload: dict[str, Any] = {}

    # Match amount + unit + food (e.g., "200g ryżu", "0,5 kg truskawek")
    amount_unit_food = re.search(
        r'(\d+[.,]?\d*)\s*(kg|g|ml|l|szt|porcji|sztuk)\s+(.+?)(?:\s+jako|\s+bez|\s+do|\s+action|\s*$|,|\s+i\s)',
        ql
    )
    if amount_unit_food:
        amount_raw = amount_unit_food.group(1).replace(",", ".")
        payload["amount"] = float(amount_raw)
        payload["unit"] = amount_unit_food.group(2)
        food = amount_unit_food.group(3).strip().rstrip(".,;")
        payload["meal_name"] = food
        payload["food_name"] = food
        return payload

    # Match amount + unit only (e.g., "200g")
    amount_unit = re.search(r'(\d+[.,]?\d*)\s*(kg|g|ml|l|szt)', ql)
    if amount_unit:
        amount_raw = amount_unit.group(1).replace(",", ".")
        payload["amount"] = float(amount_raw)
        payload["unit"] = amount_unit.group(2)

    # Match food name after amount or as standalone
    food_candidates = re.findall(r'(?:ryż|ryżu|truskaw|truskawek|makaron|mięso|kurczak|wołow|wieprzow|jajk|jajko|jaja|mleko|chleb|masło|ser|warzyw|owoc|banan|jabłk|pomidor|ogór|sałat|płatki|owsian|brokuł|szpinak|ziemniak)', ql)
    if food_candidates:
        payload["meal_name"] = food_candidates[-1]  # last mention is most specific
        payload["food_name"] = food_candidates[-1]

    # If no food found but amount exists, the query needs clarification
    if "amount" in payload and "meal_name" not in payload:
        payload["_missing_food"] = True

    return payload


def extract_calendar_slots(question: str) -> dict[str, Any]:
    """Extract title, date, time from a calendar event query."""
    ql = question.lower()
    payload: dict[str, Any] = {}

    # Extract title: text between quotes or after "event" / "wydarzenie"
    quoted = re.findall(r'"([^"]+)"', question)
    if quoted:
        payload["title"] = quoted[0]
    else:
        # Pattern: "event <date/time> <title>" — use original case for title
        event_match = re.search(r'(?:event|wydarzenie|spotkanie)\s+(.+?)$', ql)
        if event_match:
            # Extract the same segment from the original question (preserves case)
            raw_segment = question[event_match.start(1):]
            parts = raw_segment.split()
            stop_words = {"jutro", "dzisiaj", "dziś", "pojutrze", "o", "na", "10:00", "11:00", "12:00",
                         "8:00", "9:00", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"}
            filtered = [w for w in parts if w.lower() not in stop_words and not re.match(r'^\d{1,2}:\d{2}$', w)]
            if filtered:
                title = " ".join(filtered).strip().rstrip(".,;: ")
                for stop in ["bez", "zapisu", "wykonania", "jako", "action_draft"]:
                    if title.lower().endswith(stop):
                        title = title[:-len(stop)].strip().rstrip(".,;: ")
                if title:
                    payload["title"] = title

    # Date: explicit or relative
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', question)
    if date_match:
        payload["date_start"] = date_match.group(1)
    elif "jutro" in ql:
        payload["date_start"] = (date.today() + timedelta(days=1)).isoformat()
    elif "dzisiaj" in ql or "dziś" in ql:
        payload["date_start"] = date.today().isoformat()

    # Time
    time_match = re.search(r'(\d{1,2}:\d{2})', question)
    if time_match:
        payload["time_start"] = time_match.group(1)

    return payload


def extract_reminder_slots(question: str) -> dict[str, Any]:
    """Extract title/message, date, time from a reminder query."""
    ql = question.lower()
    payload: dict[str, Any] = {}

    # Extract reminder message
    # Pattern: "(przypomnij mi) <action> o <time> <date>"
    msg_match = re.search(r'(?:nawoskować|przypomnij\s+mi|żeby|aby|na)\s+(.+?)(?:\s+(?:o|na|o godz)\s+\d|\s+jutro|\s+dzisiaj|\s+bez|\s*$)', ql)
    if msg_match:
        candidate = msg_match.group(1).strip().rstrip(".,")
        # Filter out pure date/time words
        if candidate.lower() not in ("jutro", "dzisiaj", "dziś", "pojutrze", "o", "na"):
            payload["title"] = candidate
            payload["message"] = candidate
    if not payload.get("title"):
        # Fallback: take everything except noise words
        words = ql.split()
        noise = {"przypomnij","mi","o","na","bez","jako","action_draft","zapisu","wykonania",
                 "jutro","dzisiaj","dziś","pojutrze","the","a","an"}
        important = [w for w in words if w.lower() not in noise and not re.match(r'^\d{1,2}:\d{2}$', w)]
        if important:
            title = " ".join(important).strip().rstrip(".,;: ")
            for stop in ["bez", "zapisu", "wykonania", "jako", "action_draft"]:
                if title.lower().endswith(stop):
                    title = title[:-len(stop)].strip().rstrip(".,;: ")
            if title:
                payload["title"] = title
                payload["message"] = title

    # Date
    if "jutro" in ql:
        payload["date"] = (date.today() + timedelta(days=1)).isoformat()
    elif "dzisiaj" in ql or "dziś" in ql:
        payload["date"] = date.today().isoformat()

    # Time
    time_match = re.search(r'(\d{1,2}:\d{2})', question)
    if time_match:
        payload["time"] = time_match.group(1)

    return payload


def extract_planning_fact_slots(question: str) -> dict[str, Any]:
    """Extract fact/title from a planning fact query."""
    ql = question.lower()
    payload: dict[str, Any] = {}

    title_match = re.search(r'(?:fakt|fact|notatka|info|informacja)[:\s]+(.+?)(?:\s+bez|\s*$)', ql, re.IGNORECASE)
    if title_match:
        payload["title"] = title_match.group(1).strip().rstrip(".,")
    else:
        # Take everything after "zapamiętaj" or "zanotuj"
        kw_match = re.search(r'(?:zapamiętaj|zanotuj|notuj)\s+(.+?)(?:\s+bez|\s*$)', ql, re.IGNORECASE)
        if kw_match:
            payload["title"] = kw_match.group(1).strip().rstrip(".,")

    return payload


# ── Payload quality validator ──────────────────────────────────────────

def validate_payload_quality(action_type: str, payload: dict[str, Any], question: str) -> dict[str, Any]:
    """Validate that key entities from the query made it into the payload.

    Returns:
      ok: True if payload quality is acceptable
      issues: list of quality warnings
      missing_food: True if nutrition query has amount but no food name
    """
    issues: list[str] = []
    ql = question.lower()

    if action_type == "nutrition_log_add":
        # Must have food name if query mentions food words
        food_words = ["ryż", "truskawk", "makaron", "mięso", "kurczak", "jajk", "mleko",
                      "chleb", "ser", "banan", "jabłk", "pomidor", "płatki", "owsian", "brokuł"]
        has_food_word = any(fw in ql for fw in food_words)
        if has_food_word and not any(k in str(payload.get("meal_name", "")).lower() for k in food_words):
            issues.append("food_name_missing: query mentions food but payload lost it")
        # If amount is present but no food name
        if payload.get("amount") is not None and not payload.get("meal_name"):
            issues.append("amount_without_food")
        # Mark nutrients as unknown
        if not payload.get("kcal_total"):
            payload["nutrients_unknown"] = True
            payload["requires_lookup"] = True

    elif action_type == "calendar_event_add":
        # Must have title if query has specific words
        if re.search(r'"(Test\s*QBot)"', question) and payload.get("title") != "Test QBot3":
            issues.append("title_mismatch")

    elif action_type == "reminder_add":
        # Must capture the action to be reminded about
        action_words = ["nawoskować", "zrobić", "kupić", "wysłać", "odebrać", "zapłacić"]
        has_action = any(aw in ql for aw in action_words)
        if has_action and not payload.get("title"):
            issues.append("reminder_action_missing")

    return {"ok": len(issues) == 0, "issues": issues}


# ── Action type validation ────────────────────────────────────────────

def validate_action_type(action_type: str) -> dict[str, Any]:
    if action_type in _ACTION_ALLOWLIST:
        return {"valid": True, "action_type": action_type}
    return {"valid": False, "action_type": action_type,
            "error": f"action_type '{action_type}' not in allowlist",
            "allowed": sorted(_ACTION_ALLOWLIST)}


# ── Action draft builder ──────────────────────────────────────────────

_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "nutrition_log_add": {
        "required": [],
        "optional": ["meal_name", "food_name", "amount", "unit", "kcal_total",
                     "protein_g", "carbs_g", "fat_g", "template_id",
                     "nutrients_unknown", "requires_lookup"],
        "description": "Log a meal entry",
    },
    "calendar_event_add": {
        "required": ["title"],
        "optional": ["date_start", "date_end", "time_start", "description", "event_type", "all_day"],
        "description": "Add a calendar event",
    },
    "reminder_add": {
        "required": ["title"],
        "optional": ["date", "time", "message"],
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
    from qbot3.tool_registry import _idempotency_key as _idk

    schema = _ACTION_SCHEMAS.get(action_type, {})
    required = schema.get("required", [])

    # Run quality validation
    quality = validate_payload_quality(action_type, payload, question)
    if not quality.get("ok"):
        for issue in quality["issues"]:
            if issue.startswith("food_name_missing") or issue.startswith("amount_without_food"):
                # Amount without food name — add to required
                if "meal_name" not in required:
                    required = required + ["meal_name"]

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

    if quality.get("issues"):
        draft["quality_warnings"] = quality["issues"]

    return draft


def _build_human_summary(action_type: str, payload: dict[str, Any], question: str) -> str:
    summaries = {
        "nutrition_log_add": f"Dodanie posiłku: {payload.get('meal_name', '?')} ({payload.get('amount', '?')} {payload.get('unit', '')})",
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
