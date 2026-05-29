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
    """Extract food name, amount, unit, macros from a nutrition query.

    Simple:           '200g ryżu' → meal_name='ryż', amount=200, unit='g'
    Complex:          'Brokuł Sport 2000: 1 zestaw, 2011 kcal, białko 118 g, ...'
    With template:    'template_id=4'
    Relative date:    'dzisiaj', 'jutro'
    """
    ql = question.lower()
    payload: dict[str, Any] = {}

    # ── 1. Template ID ──────────────────────────────────────────────────
    tmpl = re.search(r'template_id\s*[=:]\s*(\d+)', ql)
    if tmpl:
        payload["template_id"] = int(tmpl.group(1))

    # ── 2. Macros: kcal, protein, carbs, fat, salt ─────────────────────
    macro_patterns = [
        (r'(\d+[.,]?\d*)\s*kcal', "kcal_total"),
        (r'białko\s+(\d+[.,]?\d*)\s*g', "protein_g"),
        (r'protein\s+(\d+[.,]?\d*)\s*g', "protein_g"),
        (r'węglowodany\s+(\d+[.,]?\d*)\s*g', "carbs_g"),
        (r'carbs\s+(\d+[.,]?\d*)\s*g', "carbs_g"),
        (r'węgle\s+(\d+[.,]?\d*)\s*g', "carbs_g"),
        (r'tłuszcz\s+(\d+[.,]?\d*)\s*g', "fat_g"),
        (r'fat\s+(\d+[.,]?\d*)\s*g', "fat_g"),
        (r'sól\s+(\d+[.,]?\d*)\s*g', "salt_g"),
        (r'salt\s+(\d+[.,]?\d*)\s*g', "salt_g"),
        (r'sodium\s+(\d+[.,]?\d*)\s*mg', "salt_g"),
        (r'błonnik\s+(\d+[.,]?\d*)\s*g', "fiber_g"),
        (r'fiber\s+(\d+[.,]?\d*)\s*g', "fiber_g"),
    ]
    has_any_macro = False
    for pat, key in macro_patterns:
        m = re.search(pat, ql)
        if m:
            val = float(m.group(1).replace(",", "."))
            payload[key] = val
            has_any_macro = True

    # ── 3. Quantity/ servings: "1 zestaw", "5 pudełek", "2 porcje" ─────
    # Also match "X zestaw / Y pudełek" compound
    compound = re.search(r'(\d+[.,]?\d*)\s*(zestaw|porcj|pudełek|sztuk|szt|szt\.)\s*[\/]\s*(\d+[.,]?\d*)\s*(pudełek|sztuk|szt|szt\.|porcj)', ql)
    if compound:
        payload["quantity"] = float(compound.group(1).replace(",", "."))
        payload["unit"] = compound.group(2)
        payload["servings"] = float(compound.group(3).replace(",", "."))
    else:
        quantity_match = re.search(r'(\d+[.,]?\d*)\s*(zestaw|porcj|pudełek|sztuk|szt|szt\.|kg|g|ml|l|gram|litr)', ql)
        if quantity_match:
            payload["quantity"] = float(quantity_match.group(1).replace(",", "."))
            payload["unit"] = quantity_match.group(2)

    # ── 4. Amount + unit + food (e.g., "200g ryżu", "0,5 kg truskawek") ─
    amount_unit_food = re.search(
        r'(\d+[.,]?\d*)\s*(kg|g|ml|l|szt|porcji|sztuk)\s+(.+?)(?:\s+jako|\s+bez|\s+do|\s+action|\s*$|,|\s+i\s|\s+\d+)',
        ql
    )
    if amount_unit_food and not payload.get("meal_name"):
        amount_raw = amount_unit_food.group(1).replace(",", ".")
        payload["amount"] = float(amount_raw)
        if "unit" not in payload:
            payload["unit"] = amount_unit_food.group(2)
        food = amount_unit_food.group(3).strip().rstrip(".,;")
        if len(food) > 1:
            payload["meal_name"] = food
            payload["food_name"] = food

    # ── 5. Meal/food name from complex query (before colon, or after "dieta") ─
    if not payload.get("meal_name"):
        # Pattern: "Brokuł Sport 2000: 1 zestaw, 5 pudełek, 2011 kcal..."
        name_from_colon = re.search(r'(?:dodaj|dopisz|zjedz|jadł)\s+(?:do\s+)?(?:dzisiejszego\s+)?(?:jadłospisu\s+)?(?:wpis\s+z\s+szablonu\s+)?[""]?(.+?)[""]?\s*[:\n,]+\s*(?:\d+|zestaw|porcj|pudełek|kcal|białko|tłuszcz|węglowod)', ql)
        if name_from_colon:
            name = name_from_colon.group(1).strip()
            # Clean trailing noise
            for suffix in ["action_draft", "bez zapisu", "jako draft", "draft"]:
                if name.lower().endswith(suffix):
                    name = name[:-len(suffix)].strip()
            if name and len(name) > 1:
                payload["meal_name"] = name

    if not payload.get("meal_name"):
        # Pattern: "dieta ..." or "... jako dieta" — extract meal template name
        diet_match = re.search(r'(?:dieta|posiłek|meal|szablon)\s+[""]?(.+?)[""]?\s*(?:[:\n]|\d|$)', ql)
        if diet_match:
            name = diet_match.group(1).strip()
            if name and len(name) > 1:
                payload["meal_name"] = name

    # ── 6. Description: everything between meal name and macros ──────────
    if payload.get("meal_name") and has_any_macro:
        mn = re.escape(payload["meal_name"])
        desc_match = re.search(rf'{mn}\s*[:\s]+(.+?)(?:\d+\s*kcal|\d+\s*g\s+białko|\d+\s*g\s+protein|\d+\s*g\s+tłuszcz)', ql, re.I)
        if desc_match:
            desc = desc_match.group(1).strip().rstrip(",:;-")
            if desc and len(desc) > 2:
                payload["description"] = desc

    # ── 7. Date ──────────────────────────────────────────────────────────
    if "dzisiaj" in ql or "dziś" in ql or "dzisiejsz" in ql:
        from datetime import date as dt_date
        payload["date"] = dt_date.today().isoformat()
    elif "jutro" in ql:
        from datetime import date as dt_date, timedelta
        payload["date"] = (dt_date.today() + timedelta(days=1)).isoformat()

    # ── 8. Fallback food name from known food words ──────────────────────
    if not payload.get("meal_name"):
        food_candidates = re.findall(r'(?:ryż|ryżu|truskaw|truskawek|makaron|mięso|kurczak|wołow|wieprzow|jajk|jajko|jaja|mleko|chleb|masło|ser|warzyw|owoc|banan|jabłk|pomidor|ogór|sałat|płatki|owsian|brokuł|szpinak|ziemniak)', ql)
        if food_candidates:
            payload["meal_name"] = food_candidates[-1]
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

    # Try various patterns — use original case for final title
    patterns = [
        r'(?:fakt|fact)[:\s]+(?:projektowy|projekt|plan|info|informat)?[:\s]*([A-Z].+?)(?:\s+bez|\s*$)',
        r'(?:zapamiętaj|zanotuj|notuj)\s+(?:jako\s+)?(?:fakt|fact|info|informacja|notatk)[:\s]+(.+?)(?:\s+bez|\s*$)',
        r'(?:zapamiętaj|zanotuj|notuj)\s+(?:jako\s+)?(.+?)(?:\s+bez|\s*$)',
    ]
    
    for pat in patterns:
        match = re.search(pat, question, re.I)
        if match:
            title = match.group(1).strip().rstrip(".,;:")
            # Clean up leading adjectives (case-insensitive)
            for skip in ["projektowy", "projekt", "plan", "info", "ważny", "roboczy"]:
                if title.lower().startswith(skip):
                    title = title[len(skip):].strip().lstrip(": ,;")
            # Extract meaningful content — take from first capital letter if exists
            cap_match = re.search(r'[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]', title)
            if cap_match:
                title = title[cap_match.start():]
            if title:
                payload["title"] = title
            break

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


# ── Action contracts ──────────────────────────────────────────────────
# Each contract defines what qbot.action_execute requires to execute.

_ACTION_CONTRACTS: dict[str, dict[str, Any]] = {
    "nutrition_log_add": {
        "required_fields": ["meal_name"],
        "optional_fields": ["food_name", "amount", "unit", "kcal_total",
                            "protein_g", "carbs_g", "fat_g", "template_id",
                            "nutrients_unknown", "requires_lookup"],
        "forbidden_fields": [],
        "semantic_requirements": [
            "if amount provided, meal_name must also be provided",
            "if query mentions food, meal_name must contain that food",
            "nutrients_unknown=true when no kcal lookup available",
        ],
        "entity_retention": [
            "food_name or meal_name must retain the food type from query",
            "amount+unit must retain quantity from query if provided",
        ],
        "date_time_requirements": [],
        "destructive": False,
        "description": "Log a meal entry. food_name/meal_name jest wymagane.",
    },
    "calendar_event_add": {
        "required_fields": ["title"],
        "optional_fields": ["date_start", "date_end", "time_start",
                            "description", "event_type", "all_day"],
        "forbidden_fields": [],
        "semantic_requirements": [
            "date_start always required for calendar events",
            "if query specifies time, time_start must be present or missing_fields",
            "timezone=Europe/Warsaw assumed",
        ],
        "entity_retention": [
            "title must retain event name from query",
        ],
        "date_time_requirements": [
            "date_start: ISO 8601 or relative (jutro → +1 day)",
        ],
        "always_require": ["date_start"],
        "destructive": False,
        "description": "Add a calendar event. title + date_start wymagane do wykonania.",
    },
    "reminder_add": {
        "required_fields": ["title"],
        "optional_fields": ["date", "time", "message"],
        "forbidden_fields": [],
        "semantic_requirements": [
            "if query specifies time, time must be in payload",
            "title/message must contain the action to be reminded about",
        ],
        "entity_retention": [
            "title or message must retain the reminder action from query",
        ],
        "date_time_requirements": [
            "date: ISO 8601 or relative (jutro → +1 day)",
        ],
        "destructive": False,
        "description": "Add a reminder. title + date wymagane do wykonania.",
    },
    "planning_fact_add": {
        "required_fields": ["title"],
        "optional_fields": ["fact_type", "date", "fact_json"],
        "forbidden_fields": [],
        "semantic_requirements": [
            "title must retain the fact content from query",
        ],
        "entity_retention": [
            "title must retain the fact content from query",
        ],
        "date_time_requirements": [],
        "destructive": False,
        "description": "Save a planning fact. title (treść faktu) wymagane.",
    },
    "memory_confirmed_fact_add": {
        "required_fields": ["key", "value"],
        "optional_fields": ["memory_type"],
        "forbidden_fields": [],
        "semantic_requirements": [
            "key must encode the fact domain",
            "value must encode the fact content",
        ],
        "entity_retention": [],
        "date_time_requirements": [],
        "destructive": False,
        "description": "Save a confirmed fact. key+value wymagane.",
    },
    "qbot_doc_append": {
        "required_fields": ["target_document", "content_markdown"],
        "optional_fields": ["heading"],
        "forbidden_fields": [],
        "semantic_requirements": [
            "target_document must be an allowed doc name",
            "content_markdown must be non-empty",
        ],
        "entity_retention": [],
        "date_time_requirements": [],
        "destructive": False,
        "description": "Append to a QBot doc. target_document + content wymagane.",
    },
}


def get_action_contract(action_type: str) -> dict[str, Any] | None:
    return _ACTION_CONTRACTS.get(action_type)


# ── Draft self-review / contract validation ───────────────────────────

def draft_self_review(action_type: str, payload: dict[str, Any], question: str,
                      decomposition: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate a draft against its action contract.

    Returns:
      review_status: "approved" | "needs_clarification" | "incomplete"
      missing_fields: list of fields that must be provided
      semantic_issues: list of semantic requirement violations
      ready_for_execute: True/False
    """
    contract = _ACTION_CONTRACTS.get(action_type)
    if not contract:
        return {"review_status": "approved", "ready_for_execute": True,
                "missing_fields": [], "semantic_issues": []}

    ql = question.lower()
    missing = []
    semantic_issues = []

    # 1. Check required fields
    for field in contract.get("required_fields", []):
        if not payload.get(field):
            missing.append(field)

    # 2. Entity retention: check that query entities made it to payload
    for rule in contract.get("entity_retention", []):
        if "food" in rule and action_type == "nutrition_log_add":
            food_words = ["ryż", "truskawk", "makaron", "mięso", "kurczak", "jajk",
                          "mleko", "chleb", "ser", "banan", "jabłk", "pomidor",
                          "płatki", "owsian", "brokuł", "szpinak", "ziemniak", "sałat"]
            mentioned = [fw for fw in food_words if fw in ql]
            if mentioned:
                pn = (payload.get("meal_name") or "").lower()
                pfn = (payload.get("food_name") or "").lower()
                if not any(m in pn or m in pfn for m in mentioned):
                    if "meal_name" not in missing:
                        missing.append("meal_name")
                    semantic_issues.append(f"food_name_lost: query mentions {mentioned[-1]} but payload has no food name")

        if "title" in rule and action_type in ("calendar_event_add", "reminder_add", "planning_fact_add"):
            has_title = bool(payload.get("title"))
            # If query has specific words but no title extracted
            if not has_title:
                # Check if the query had content that should've become a title
                content_words = [w for w in ql.split() if len(w) > 3]
                task_words = {"dodaj", "zapisz", "zaplanuj", "przypomnij", "event", "kalendarz",
                              "action_draft", "zapisu", "wykonania", "bez", "jako"}
                meaningful = [w for w in content_words if w not in task_words]
                if len(meaningful) >= 2 and "title" not in missing:
                    missing.append("title")
                    semantic_issues.append(f"title_missing: query has content but no title extracted")

    # 3. Semantic requirements
    for req in contract.get("semantic_requirements", []):
        if "meal_name" in req and "amount" in req:
            if payload.get("amount") is not None and not payload.get("meal_name") and "meal_name" not in missing:
                missing.append("meal_name")
                semantic_issues.append("amount_without_meal_name")

        if "query mentions food" in req and action_type == "nutrition_log_add":
            food_words = ["ryż", "truskawk", "makaron", "mięso", "kurczak", "jajk"]
            if any(fw in ql for fw in food_words):
                pn = (payload.get("meal_name") or "").lower()
                if not any(fw in pn for fw in food_words):
                    if "meal_name" not in missing:
                        missing.append("meal_name")
                        semantic_issues.append("food_mentioned_but_not_in_payload")

        if "date_start always required" in req and action_type == "calendar_event_add":
            if not payload.get("date_start") and "date_start" not in missing:
                missing.append("date_start")
                if any(w in ql for w in ("jutro", "dzisiaj", "pojutrze", "202")):
                    semantic_issues.append("date_mentioned_but_not_resolved")

        if "time must be in payload" in req and "reminder" in action_type:
            if re.search(r'\d{1,2}:\d{2}', ql) and not payload.get("time"):
                semantic_issues.append("time_mentioned_but_not_extracted")

    # 4. Contamination check — if decomposition provided
    if decomposition:
        from qbot3.query_decomposer import is_payload_contaminated
        contamination_warnings = is_payload_contaminated(payload, decomposition, action_type)
        if contamination_warnings:
            for w in contamination_warnings:
                semantic_issues.append(w)
            # If contaminated, don't approve regardless of other checks
            if missing:
                ready = False
                status = "needs_clarification"
            else:
                ready = False
                status = "incomplete"

    # 5. Determine status
    if not missing and not semantic_issues:
        ready = True
        status = "approved"
    elif not missing and semantic_issues:
        ready = False
        status = "needs_clarification"
    else:
        ready = False
        status = "needs_clarification" if len(missing) <= 3 else "incomplete"

    return {
        "review_status": status,
        "ready_for_execute": ready,
        "missing_fields": missing,
        "semantic_issues": semantic_issues,
    }


# ── Action draft builder (with mandatory self-review) ─────────────────

def build_draft(action_type: str, payload: dict[str, Any], question: str) -> dict[str, Any]:
    from qbot3.tool_registry import _idempotency_key as _idk

    # 1. Build base payload (strip decomposition metadata from payload)
    decomposition = payload.pop("_decomposition", None) if isinstance(payload, dict) else None
    provided = {k: v for k, v in payload.items() if v is not None and v != "" and not k.startswith("_")}

    # 2. Mandatory self-review with decomposition
    review = draft_self_review(action_type, provided, question, decomposition=decomposition)

    # 3. Merge review findings into missing_fields
    missing = list(dict.fromkeys(review.get("missing_fields", [])))

    # 4. Quality validation
    quality = validate_payload_quality(action_type, provided, question)
    if not quality.get("ok"):
        for issue in quality["issues"]:
            if issue.startswith("food_name_missing") and "meal_name" not in missing:
                missing.append("meal_name")

    idem_key = _idk(action_type[:8] if action_type else "wr", question)

    draft = {
        "action_type": action_type,
        "payload": provided,
        "requires_confirm": True,
        "idempotency_key_suggestion": idem_key,
        "dry_run_available": True,
        "safety_notes": [f"write action: {action_type}"],
        "human_summary": _build_human_summary(action_type, provided, question),
        "ready_for_execute": review.get("ready_for_execute", False),
        "contract_review": review.get("review_status", "approved"),
    }

    if missing:
        draft["missing_fields"] = missing
        draft["pending_task"] = True
        draft["clarification_question"] = _build_clarification(action_type, missing, question)
    else:
        draft["missing_fields"] = []

    if semantic_issues := review.get("semantic_issues", []):
        draft["semantic_issues"] = semantic_issues

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
        "date_start": "datę/czas rozpoczęcia",
        "date_end": "datę zakończenia",
        "time_start": "godzinę rozpoczęcia",
        "meal_name": "nazwę posiłku (np. 'ryż')",
        "key": "klucz (np. nazwa faktu)",
        "value": "wartość",
        "target_document": "nazwę dokumentu docelowego",
        "content_markdown": "treść do dopisania",
    }
    # Context-aware: if it's a calendar or reminder, group date+time
    if action_type == "calendar_event_add":
        if "date_start" in missing or "time_start" in missing:
            field_strs = ["tytuł i datę/czas wydarzenia" if "title" in missing else "datę/czas wydarzenia"]
            field_strs += [field_names_pl.get(f, f) for f in missing if f not in ("title", "date_start", "time_start")]
            return f"Podaj {', '.join(field_strs)}."
    elif action_type == "reminder_add":
        if "date" in missing or "time" in missing:
            field_strs = ["tytuł i datę/czas przypomnienia" if "title" in missing else "datę/czas przypomnienia"]
            field_strs += [field_names_pl.get(f, f) for f in missing if f not in ("title", "date", "time")]
            return f"Podaj {', '.join(field_strs)}."

    field_strs = [field_names_pl.get(f, f) for f in missing]
    if len(field_strs) == 1:
        return f"Podaj {field_strs[0]}."
    return f"Podaj {', '.join(field_strs[:-1])} i {field_strs[-1]}."
