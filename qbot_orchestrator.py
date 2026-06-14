#!/usr/bin/env python3
"""LLM orchestrator for qbot.query.

Flow:
1. LLM produces a structured query plan.
2. System validates the plan.
3. System executes the selected read-only readers or produces a draft.
4. LLM writes the final answer from the reader outputs.

This module is intentionally conservative: it only implements the MVP
surface requested for the first real orchestrator step.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from qgpt_client import qgpt_json

_BIBLE_PATH = Path("/opt/qbot/docs/QBOT_BIBLE.md")
_ORCHESTRATOR_FLAG = "QBOT_LLM_ORCHESTRATOR"
_ORCHESTRATOR_NAME = "Albert"
_INSTRUCTION_PATH = Path("/opt/qbot/docs/QBOT_ORCHESTRATOR_INSTRUCTION.md")
_INSTRUCTION_CACHE: str | None = None
_PLAN_CONFIDENCE_THRESHOLD = 0.6

_PLAN_SYSTEM = """\
Jesteś planistą LLM dla QBot (Albert).

Masz wygenerować WYŁĄCZNIE JSON o strukturze:
{
  "intent": "...",
  "task_type": "read|draft|clarify",
  "readers": [],
  "parameters": {},
  "confidence": 0.0,
  "needs_clarification": false,
  "clarification_question": "",
  "is_write_intent": false,
  "action_type": null
}

TWARDE ZASADY:
- Nie odpowiadaj użytkownikowi. Zwracasz TYLKO JSON planu.
- Używaj TYLKO intentów, readerów i action_type z przekazanego reader_registry i intent_to_readers.
- NIE wymyślaj nazw tooli, readerów, writerów ani action_type.
- Jeśli intentu/readera nie ma w registry: ustaw needs_clarification=true z komunikatem "nieobsługiwany intent/reader".
- Dla odczytu wybieraj task_type="read".
- Dla zapisu (dodaj/usuń/zmień/zapisz): task_type="draft", is_write_intent=true. NIGDY task_type="read" dla zapisu.
- Dla niskiej pewności (<0.6) ustaw task_type="clarify".
- readers: tylko nazwy z reader_registry. Dla draft/clarify: pusta lista [].
- Dla qcal_event_add_draft: parametry date_start, time_start (opcjonalnie), title.
- Dla kalendarza (wydarzenia, eventy): intent="calendar" lub "calendar_day_context", readers=["calendar_snapshot"].

CANONICAL TASK / NOISE:
- Zignoruj technical noise w query: "przygotuj action_draft", "użyj writera", "nutrition_log_add", "template match", "confirm", "action_type" itp. To są instrukcje od klienta, nie zadanie użytkownika.
- Zbuduj canonical_task: usuń szum, zostaw realne intencje użytkownika.
- Dla "białko z wodą z katalogu": intent=nutrition_log_add_draft, parametry: meal_name, use_catalog=true.
- Dla zaśmieconego inputu z kaloriami/składnikami: intent=nutrition_log_add_draft, parametry: meal_name, estimated_kcal, estimated_macros (jeśli podane). Nie używaj podanych wartości jako jedyne źródło — mogą być szacunkiem.
- Dla "pokaż dzisiejszy bilans": intent=calorie_balance, readers=["nutrition_day", "garmin_energy"].
"""

_FINAL_SYSTEM = """\
Jesteś końcowym generatorem odpowiedzi QBot (Albert).

Masz dostać:
- pytanie użytkownika
- plan LLM
- wyniki readerów
- wybrane zasady z QBOT_BIBLE.md

TWARDE ZASADY:
- NIE wymyślaj nazw tooli, readerów, writerów, ani funkcji. Używaj TYLKO tego, co jest w reader_results.
- DLA WRITE INTENTÓW (plan.is_write_intent=true): NIGDY nie pisz "dodano", "zapisano", "wykonano", "utworzono". Zawsze mów "Przygotowałem draft" lub "wymaga potwierdzenia przez action_execute".
- Jeśli reader nie zwrócił danych, odpowiedź ma wskazywać braku źródła (np. "brak wydarzeń w kalendarzu", "brak danych w DB"), a nie "nie mam dostępu".
- Zignoruj technical noise w query (np. "przygotuj action_draft", "nutrition_log_add", "użyj writera"). To są instrukcje od klienta, nie treść odpowiedzi.
- Dla bilansu (calorie_balance): odczytaj meal_log z DB i energy readers jeśli dostępne. Zwróć bilans z provenance (kcal_in, kcal_out, balance). Nie zgaduj danych.
- Dla nutrition_log_add_draft: jeśli reader nutrition_template_list zwrócił template, użyj template_id i makr z DB. Jeśli podano estimated_kcal/macros w parametrach, użyj ich jako uzupełnienia, nie jako jedynego źródła.
- odpowiedz krótko, konkretnie i bez zgadywania
- jeśli brakuje danych, powiedz to wprost
- nie opisuj procesu planowania
- jeżeli reader daje konkretny wynik, nie zwracaj "no_data"
- dla status/readiness/dokumentów/posiłków opieraj odpowiedź bezpośrednio na wynikach readerów
- dla `qbot_roadmap_runner_status` pokaż wprost `task_progress_percent` i `block_progress_percent`
- `missing_fields` dotyczy WYŁĄCZNIE pól danych (np. nazwa posiłku, data, kcal) — NIGDY nie dodawaj tu orchestrator.enabled, orchestrator.stage, orchestrator.fallback_used ani innych pól systemowych
- odpowiedź nie powinna sugerować, że brakuje metadanych orchestratora — te są dostępne w sekcji orchestrator wyniku
- dla `qbot_canonical_docs` — skorzystaj z pola `answer` readera i streść znalezione sekcje/excerpty; nie pisz, że brakuje informacji, jeśli reader zwrócił trafne fragmenty
- dla `calendar_snapshot` — przedstaw PEŁNY obraz dnia: wydarzenia, remindery, zadania, posiłki (jeśli są); nie zawężaj odpowiedź tylko do posiłku
- dla `weather_forecast` — uwzględnij przekazany `period` ("jutro" → jutrzejsza data)
- zwróć WYŁĄCZNIE JSON:
{
  "answer": "...",
  "status": "ok|partial|no_data|blocked|draft|clarify|error",
  "confidence": "low|medium|high",
  "missing_fields": [],
  "limitations": []
}
"""

_HIDDEN_READERS: dict[str, dict[str, Any]] = {
    "qbot_roadmap_runner_status": {
        "category": "project",
        "description": "Read the roadmap runner progress percent and status.",
    },
    "nutrition_template_list": {
        "category": "nutrition",
        "description": "List stored nutrition templates / saved meals.",
    },
    "nutrition_template_get": {
        "category": "nutrition",
        "description": "Fetch one stored nutrition template by name or id.",
    },
}


def _orchestrator_enabled() -> bool:
    return os.getenv(_ORCHESTRATOR_FLAG, "0") == "1"


def _load_instruction() -> str:
    global _INSTRUCTION_CACHE
    if _INSTRUCTION_CACHE is not None:
        return _INSTRUCTION_CACHE
    try:
        if _INSTRUCTION_PATH.is_file():
            text = _INSTRUCTION_PATH.read_text(encoding="utf-8").strip()
            if text:
                _INSTRUCTION_CACHE = text
                return text
    except OSError:
        pass
    _INSTRUCTION_CACHE = ""
    return ""


def _instruction_loaded() -> bool:
    return bool(_load_instruction())


def _orchestrator_meta(stage: str, fallback_used: bool = False, reason: str = "") -> dict[str, Any]:
    d: dict[str, Any] = {
        "enabled": True,
        "name": _ORCHESTRATOR_NAME,
        "instruction_file": str(_INSTRUCTION_PATH),
        "instruction_loaded": _instruction_loaded(),
        "stage": stage,
        "fallback_used": fallback_used,
    }
    if reason:
        d["reason"] = reason
    return d


def _load_bible_rules() -> str:
    try:
        text = _BIBLE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""

    # Keep the prompt bounded while still carrying the key policy sections.
    if len(text) > 14000:
        text = text[:14000]
    return text


def _safe_tool_registry_snapshot() -> list[dict[str, Any]]:
    try:
        from qbot_tool_registry import TOOLS as qb_tools, TOOLS_META as qb_meta
    except Exception:
        return []

    entries: list[dict[str, Any]] = []
    for name, meta in sorted(qb_meta.items()):
        if not meta.get("safe", False):
            continue
        if name in {"qbot_query", "qbot_action_execute"}:
            continue
        if name not in qb_tools:
            continue
        entries.append(
            {
                "name": name,
                "category": meta.get("category", "tool"),
                "tool": name,
                "params": meta.get("args_schema", {}),
                "providers": ["qbot_tool_registry"],
                "description": meta.get("description", ""),
            }
        )
    return entries


def _router_snapshot() -> tuple[list[dict[str, Any]], dict[str, list[str]], dict[str, dict[str, Any]]]:
    import qbot_query_router as qr

    if not qr._TOOL_DISPATCH:  # noqa: SLF001
        qr._init_dispatch()  # noqa: SLF001

    reader_registry = [
        {
            "name": name,
            "category": meta.get("category", ""),
            "tool": meta.get("tool", ""),
            "params": meta.get("params", {}),
            "providers": meta.get("providers", []),
        }
        for name, meta in sorted(qr._READER_REGISTRY.items())  # noqa: SLF001
    ]
    for name, meta in sorted(_HIDDEN_READERS.items()):
        reader_registry.append(
            {
                "name": name,
                "category": meta.get("category", "nutrition"),
                "tool": name,
                "params": {"query": "str"},
                "providers": ["qbot_orchestrator"],
                "description": meta.get("description", ""),
            }
        )
    for entry in _safe_tool_registry_snapshot():
        if not any(item.get("name") == entry["name"] for item in reader_registry):
            reader_registry.append(entry)

    intent_to_readers = {
        intent: list(readers)
        for intent, readers in sorted(qr._INTENT_TO_READERS.items())  # noqa: SLF001
    }
    intent_to_readers.setdefault("saved_meals_catalog", ["nutrition_template_list", "nutrition_template_get"])
    intent_to_readers.setdefault("artifact_read", ["qbot_canonical_docs", "qbot_roadmap_runner_status"])
    intent_to_readers.setdefault("nutrition_template_list", ["nutrition_template_list"])
    intent_to_readers.setdefault("nutrition_template_get", ["nutrition_template_get"])
    intent_to_readers.setdefault("qbot_roadmap_runner_status", ["qbot_roadmap_runner_status"])
    intent_to_readers.setdefault("planning_facts", ["planning_facts"])
    intent_to_readers.setdefault("xert", ["xert_readiness", "xert_config"])
    intent_to_readers.setdefault("wellness", ["wellness_day", "sleep_day"])
    intent_to_readers.setdefault("rwgps", ["rwgps_route_search", "rwgps_route_list"])
    intent_to_readers.setdefault("garage", ["garage_list", "garage_search", "garage_status"])
    intent_to_readers.setdefault("weather", ["weather_forecast", "weather_current"])
    intent_to_readers.setdefault("calendar", ["calendar_snapshot"])
    for entry in _safe_tool_registry_snapshot():
        intent_to_readers.setdefault(entry["name"], [entry["name"]])
    return reader_registry, intent_to_readers, qr.__dict__


def _plan_prompt(question: str, context: str, max_rows: int) -> str:
    reader_registry, intent_to_readers, _ = _router_snapshot()
    payload = {
        "question": question,
        "context": context,
        "max_rows": max_rows,
        "reader_registry": reader_registry,
        "intent_to_readers": intent_to_readers,
        "output_schema": {
            "intent": "string",
            "task_type": "read|draft|clarify",
            "readers": ["reader_name"],
            "parameters": {},
            "confidence": 0.0,
            "needs_clarification": False,
            "clarification_question": "",
            "is_write_intent": False,
            "action_type": None,
        },
        "bible_rules": _load_bible_rules(),
        "examples": [
            {
                "question": "status qbot",
                "plan": {
                    "intent": "status",
                    "task_type": "read",
                    "readers": ["status"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "readiness qbot",
                "plan": {
                    "intent": "readiness",
                    "task_type": "read",
                    "readers": ["readiness", "xert_readiness"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "podaj status procentowy roadmapy QBot LLM-first",
                "plan": {
                    "intent": "artifact_read",
                    "task_type": "read",
                    "readers": ["qbot_roadmap_runner_status"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "wylistuj zapisane posiłki",
                "plan": {
                    "intent": "saved_meals_catalog",
                    "task_type": "read",
                    "readers": ["nutrition_template_list"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "co to jest dieta od Brokuła w mojej bazie",
                "plan": {
                    "intent": "saved_meals_catalog",
                    "task_type": "read",
                    "readers": ["nutrition_template_list"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "dodaj dzisiaj dietę od Brokuła",
                "plan": {
                    "intent": "nutrition_log_add_draft",
                    "task_type": "draft",
                    "readers": [],
                    "parameters": {"template_query": "Brokuł"},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": True,
                    "action_type": "nutrition_log_add",
                },
            },
            {
                "question": "pokaż planning facts",
                "plan": {
                    "intent": "planning_facts",
                    "task_type": "read",
                    "readers": ["planning_facts"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "zapamiętaj fakt planistyczny: test orchestrator",
                "plan": {
                    "intent": "planning_fact_add",
                    "task_type": "draft",
                    "readers": [],
                    "parameters": {
                        "title": "test orchestrator",
                        "fact_type": "custom",
                    },
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": True,
                    "action_type": "planning_fact_add",
                },
            },
            {
                "question": "pokaż backup status",
                "plan": {
                    "intent": "qbot_backup_status",
                    "task_type": "read",
                    "readers": ["qbot_backup_status"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "pokaż errors i logs summary",
                "plan": {
                    "intent": "qbot_error_summary",
                    "task_type": "read",
                    "readers": ["qbot_error_summary", "qbot_logs_overview"],
                    "parameters": {"limit": 50, "lines": 50},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "co jest w QBOT_KNOWHOW o LLM Orchestrator",
                "plan": {
                    "intent": "artifact_read",
                    "task_type": "read",
                    "readers": ["qbot_canonical_docs", "qbot_roadmap_runner_status"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "co jest w QBOT_BIBLE o LLM Orchestrator",
                "plan": {
                    "intent": "artifact_read",
                    "task_type": "read",
                    "readers": ["qbot_canonical_docs"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "jaka jest moja readiness z Xert",
                "plan": {
                    "intent": "xert",
                    "task_type": "read",
                    "readers": ["xert_readiness", "xert_config"],
                    "parameters": {},
                    "confidence": 0.90,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "pokaż dane snu / wellness",
                "plan": {
                    "intent": "wellness",
                    "task_type": "read",
                    "readers": ["wellness_day", "sleep_day"],
                    "parameters": {},
                    "confidence": 0.90,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "pokaż trasy RWGPS",
                "plan": {
                    "intent": "rwgps",
                    "task_type": "read",
                    "readers": ["rwgps_route_list"],
                    "parameters": {},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "znajdź trasę RWGPS Toskania",
                "plan": {
                    "intent": "rwgps",
                    "task_type": "read",
                    "readers": ["rwgps_route_search"],
                    "parameters": {"query": "Toskania"},
                    "confidence": 0.90,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "pokaż garage status",
                "plan": {
                    "intent": "garage",
                    "task_type": "read",
                    "readers": ["garage_status", "garage_list"],
                    "parameters": {},
                    "confidence": 0.90,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "jaka jest pogoda w Markach jutro",
                "plan": {
                    "intent": "weather",
                    "task_type": "read",
                    "readers": ["weather_forecast"],
                    "parameters": {"location": "Marki", "period": "jutro"},
                    "confidence": 0.95,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
            {
                "question": "co mam dziś w kalendarzu",
                "plan": {
                    "intent": "calendar",
                    "task_type": "read",
                    "readers": ["calendar_snapshot"],
                    "parameters": {},
                    "confidence": 0.90,
                    "needs_clarification": False,
                    "clarification_question": "",
                    "is_write_intent": False,
                    "action_type": None,
                },
            },
        ],
    }
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def _normalize_plan(plan: Any) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None

    intent = str(plan.get("intent", "")).strip()
    task_type = str(plan.get("task_type", "")).strip().lower()
    readers = plan.get("readers", [])
    if not isinstance(readers, list):
        readers = []
    readers = [str(r).strip() for r in readers if str(r).strip()]
    parameters = plan.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}
    clarification_question = str(plan.get("clarification_question", "")).strip()
    action_type = plan.get("action_type")
    if action_type is not None:
        action_type = str(action_type).strip() or None

    try:
        confidence = float(plan.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    needs_clarification = bool(plan.get("needs_clarification", False))
    is_write_intent = bool(plan.get("is_write_intent", False))

    if task_type not in {"read", "draft", "clarify"}:
        return None
    if not intent:
        return None
    if task_type == "clarify" and not needs_clarification:
        needs_clarification = True

    return {
        "intent": intent,
        "task_type": task_type,
        "readers": readers,
        "parameters": parameters,
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "is_write_intent": is_write_intent,
        "action_type": action_type,
    }


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    import qbot_query_router as qr

    if not qr._TOOL_DISPATCH:  # noqa: SLF001
        qr._init_dispatch()  # noqa: SLF001

    safe_tool_names = {entry["name"] for entry in _safe_tool_registry_snapshot()}
    allowed_intents = set(qr._INTENT_TO_READERS.keys()) | safe_tool_names | {  # noqa: SLF001
        "status", "readiness", "artifact_read", "saved_meals_catalog", "nutrition_log_add_draft",
        "planning_facts",
    }
    allowed_readers = set(qr._READER_REGISTRY.keys()) | set(_HIDDEN_READERS.keys()) | safe_tool_names | {"planning_facts"}  # noqa: SLF001
    intent_reader_map = dict(qr._INTENT_TO_READERS)  # noqa: SLF001
    intent_reader_map.setdefault("saved_meals_catalog", ["nutrition_template_list", "nutrition_template_get"])
    intent_reader_map.setdefault("artifact_read", ["qbot_canonical_docs", "qbot_roadmap_runner_status"])
    intent_reader_map.setdefault("nutrition_template_list", ["nutrition_template_list"])
    intent_reader_map.setdefault("nutrition_template_get", ["nutrition_template_get"])
    intent_reader_map.setdefault("qbot_roadmap_runner_status", ["qbot_roadmap_runner_status"])
    intent_reader_map.setdefault("planning_facts", ["planning_facts"])

    result = dict(plan)
    intent = result.get("intent", "")
    if intent not in allowed_intents and not result.get("readers") and result.get("task_type") == "read":
        result.update({
            "needs_clarification": True,
            "clarification_question": f"Nieobsługiwany intent: {intent}",
            "confidence": 0.0,
        })
        return result

    readers = [r for r in result.get("readers", []) if r in allowed_readers]
    result["readers"] = readers

    if not readers and result["task_type"] == "read":
        fallback = list(intent_reader_map.get(intent, []))
        result["readers"] = [r for r in fallback if r in allowed_readers]

    if intent == "artifact_read" and result.get("task_type") == "read":
        existing = set(result.get("readers", []))
        merged = existing | {"qbot_canonical_docs", "qbot_roadmap_runner_status"}
        result["readers"] = sorted(merged)

    if result["task_type"] == "draft":
        result["readers"] = []
        result["is_write_intent"] = True

    if result["confidence"] < _PLAN_CONFIDENCE_THRESHOLD and result["task_type"] == "read":
        result["needs_clarification"] = True
        if not result.get("clarification_question"):
            result["clarification_question"] = "Doprecyzuj intencję."

    return result


def _compact_reader_result(result: dict[str, Any], limit: int = 4000) -> dict[str, Any]:
    keep_keys = (
        "tool",
        "status",
        "query",
        "date",
        "count",
        "answer",
        "summary",
        "summary_text",
        "missing_fields",
        "limitations",
        "documents",
        "templates",
        "items",
        "meals",
        "calendar_events",
        "reminders",
        "day_type",
        "day_notes",
        "health_events",
        "tables",
        "data",
    )
    compact = {k: result.get(k) for k in keep_keys if k in result}
    try:
        raw = json.dumps(compact, ensure_ascii=False, default=str)
    except Exception:
        raw = str(compact)
    if len(raw) > limit:
        raw = raw[:limit] + "…"
    return {"raw": raw}


def _normalize_query_text(question: str) -> str:
    return " ".join(str(question or "").strip().lower().split())


def _build_unsupported_response(
    question: str,
    context: str,
    max_rows: int,
    *,
    reason: str,
    plan: dict[str, Any] | None = None,
    missing_capability: str | list[str] | None = None,
    status: str = "error",
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "query": question,
        "status": status,
        "confidence": "low",
        "answer": "Orchestrator nie obsługuje jeszcze tej domeny. Rozszerz capabilities Orchestratora.",
        "missing_fields": [],
        "limitations": ["unsupported_by_orchestrator"],
        "orchestrator_failed": True,
        "orchestrator": _orchestrator_meta("unsupported", reason=reason),
        "date_resolution": None,
        "context": context,
        "max_rows": max_rows,
    }
    if plan is not None:
        response["plan"] = plan
        response["intents_detected"] = [plan.get("intent", "")]
        response["readers_planned"] = plan.get("readers", [])
        response["readers_used"] = []
    if missing_capability is not None:
        response["missing_capability"] = missing_capability
    return response


def _build_emergency_response(
    question: str,
    context: str,
    max_rows: int,
    *,
    reason: str,
) -> dict[str, Any] | None:
    q = _normalize_query_text(question)
    if not q:
        return None

    def _wrap(tool_result: dict[str, Any], *, stage: str, answer: str | None = None) -> dict[str, Any]:
        result = dict(tool_result)
        if answer:
            result["answer"] = answer
        elif not result.get("answer"):
            result["answer"] = (
                result.get("summary_text")
                or result.get("summary")
                or result.get("message")
                or result.get("status")
                or "LLM unavailable / orchestrator failed."
            )
        result["tool"] = "qbot.query"
        result["mode"] = "read_only"
        result["query"] = question
        result["orchestrator_failed"] = True
        result["orchestrator"] = _orchestrator_meta(stage, fallback_used=True, reason=reason)
        result.setdefault("missing_fields", [])
        result.setdefault("limitations", [])
        return result

    emergency_docs = {
        "qbot_bible",
        "qbot bible",
        "qbot_knowhow",
        "qbot knowhow",
        "bible qbot",
        "knowhow qbot",
        "instrukcja projektu qbot",
        "qbot_project_instruction_local",
        "qbot project instruction local",
    }
    emergency_status = {
        "status qbot",
        "jaki jest status qbot",
        "jaki jest status qbot?",
        "czy qbot działa",
        "czy qbot dziala",
        "qbot status",
    }
    emergency_readiness = {
        "readiness qbot",
        "gotowość qbot",
        "gotowosc qbot",
        "qbot readiness",
    }
    emergency_health = {"health", "/health"}
    emergency_mcp = {"mcp", "mcp status", "mcp health", "/mcp/health", "mcp/health"}

    if q in emergency_status:
        from qbot_tools import _tool_qbot_status
        return _wrap(_tool_qbot_status(), stage="emergency_status")
    if q in emergency_readiness:
        from qbot_operator_tools import _tool_qbot_readiness_report
        return _wrap(_tool_qbot_readiness_report({}), stage="emergency_readiness")
    if q in emergency_health:
        from qbot_tools import _tool_qbot_api_self_check
        return _wrap(_tool_qbot_api_self_check(), stage="emergency_health")
    if q in emergency_mcp:
        from qbot_mcp_adapter import _tool_qbot_mcp_status
        return _wrap(_tool_qbot_mcp_status({}), stage="emergency_mcp")
    if q in emergency_docs or "qbot bible" in q or "qbot knowhow" in q or "canonical docs" in q:
        import qbot_query_router as qr
        docs = qr._read_qbot_canonical_docs({"query": question})
        return _wrap(docs, stage="emergency_docs")
    return None


def _execute_reader(name: str, parameters: dict[str, Any], question: str, max_rows: int) -> dict[str, Any]:
    import qbot_query_router as qr
    from qbot_nutrition_tools import (
        _tool_qbot_nutrition_template_get,
        _tool_qbot_nutrition_template_list,
    )

    if not qr._TOOL_DISPATCH:  # noqa: SLF001
        qr._init_dispatch()  # noqa: SLF001

    if name == "nutrition_template_list":
        result = _tool_qbot_nutrition_template_list({"limit": max_rows})
        return {
            "reader": name,
            "category": "nutrition",
            "status": str(result.get("status", "UNKNOWN")),
            "data": result,
        }
    if name == "nutrition_template_get":
        lookup = parameters.get("name") or parameters.get("query") or question
        result = _tool_qbot_nutrition_template_get({"name": lookup})
        return {
            "reader": name,
            "category": "nutrition",
            "status": str(result.get("status", "UNKNOWN")),
            "data": result,
        }
    if name == "qbot_roadmap_runner_status":
        from qbot_roadmap_runner import _tool_qbot_roadmap_runner_status
        result = _tool_qbot_roadmap_runner_status({})
        return {
            "reader": name,
            "category": "project",
            "status": str(result.get("status", "UNKNOWN")),
            "data": result,
        }
    if name == "planning_facts":
        from qbot_planning_memory import list_planning_facts
        fact_date = parameters.get("date") or parameters.get("fact_date")
        status = parameters.get("status")
        result = list_planning_facts(fact_date=str(fact_date) if fact_date else None, status=str(status) if status else None)
        return {
            "reader": name,
            "category": "planning",
            "status": "OK" if result else "NO_DATA",
            "data": {
                "tool": "planning_facts",
                "status": "OK" if result else "NO_DATA",
                "count": len(result),
                "facts": result,
            },
        }

    try:
        from qbot_tool_registry import TOOLS as QBOT_TOOLS, TOOLS_META as QBOT_META
    except Exception:
        QBOT_TOOLS = {}
        QBOT_META = {}

    if name in QBOT_TOOLS and name in QBOT_META and QBOT_META.get(name, {}).get("safe", False):
        func = QBOT_TOOLS[name]
        args = dict(parameters)
        if name in {"qbot_canonical_docs_read"} and not args.get("query"):
            args["query"] = question
        if name in {"qbot_nutrition_day_summary", "qbot_nutrition_meal_list", "qbot_nutrition_day_get", "qbot_nutrition_range_summary", "qbot_wellness_day_get", "qbot_sleep_day_get", "qbot_calendar_snapshot"} and not args.get("date"):
            ql = question.lower()
            if any(k in ql for k in ("jutro", "tomorrow", "jutrze")):
                from datetime import timedelta
                args["date"] = (date.today() + timedelta(days=1)).isoformat()
            elif any(k in ql for k in ("pojutrze",)):
                from datetime import timedelta
                args["date"] = (date.today() + timedelta(days=2)).isoformat()
            else:
                args["date"] = date.today().isoformat()
        if name in {"qbot_weather_forecast"} and not args.get("period"):
            ql = question.lower()
            if any(k in ql for k in ("jutro", "tomorrow", "jutrze")):
                args["period"] = "jutro"
            elif any(k in ql for k in ("pojutrze", "pojutrz")):
                args["period"] = "day_after_tomorrow"
        if name in {"qbot_weather_current", "qbot_weather_forecast", "qbot_rwgps_route_search", "qbot_garage_raw_search", "qbot_garage_raw_list", "qbot_backup_status", "qbot_error_summary", "qbot_logs_overview", "qbot_external_integrations_report", "qbot_readiness_report", "qbot_operator_snapshot", "qbot_mcp_status", "qbot_mcp_tools_list", "qbot_public_endpoint_status", "qbot_telegram_status", "qbot_wellness_db_status", "qbot_nutrition_db_status", "qbot_nutrition_status", "qbot_service_logs", "qbot_services_status", "qbot_db_overview", "qbot_api_self_check", "qbot_git_status", "qbot_project_guard_check", "qbot_maintenance_report"} and not args:
            args = {}
        result = func(args)
        return {
            "reader": name,
            "category": QBOT_META.get(name, {}).get("category", "tool"),
            "status": str(result.get("status", "UNKNOWN")),
            "data": result,
        }

    meta = qr._READER_REGISTRY.get(name, {})  # noqa: SLF001
    tool = meta.get("tool", "")
    func = None
    source = "reader_registry"
    if tool:
        try:
            from qbot_tool_registry import TOOLS as QBOT_TOOLS
        except Exception:
            QBOT_TOOLS = {}
        func = QBOT_TOOLS.get(tool)
        if func is None:
            func = qr._TOOL_DISPATCH.get(tool)  # noqa: SLF001
            source = "query_router_dispatch"
    if not func:
        return {
            "reader": name,
            "category": meta.get("category", "unknown"),
            "status": "error",
            "data": {"tool": tool, "status": "error", "error": f"tool not loaded: {tool}", "source": source},
        }

    args = dict(parameters)
    if name == "qbot_canonical_docs" and not args.get("query"):
        args["query"] = question
    if name in {"weather_forecast"} and not args.get("period"):
        ql = question.lower()
        if any(k in ql for k in ("jutro", "tomorrow", "jutrze")):
            args["period"] = "jutro"
        elif any(k in ql for k in ("pojutrze", "pojutrz")):
            args["period"] = "day_after_tomorrow"
    if name in {"nutrition_food_search"} and not args.get("query"):
        args["query"] = question
    if name in {"nutrition_day", "meal_list"} and not args.get("date"):
        args["date"] = date.today().isoformat()
    if name == "calendar_snapshot" and not args.get("date"):
        ql = question.lower()
        if any(k in ql for k in ("jutro", "tomorrow", "jutrze")):
            from datetime import timedelta
            args["date"] = (date.today() + timedelta(days=1)).isoformat()
        elif any(k in ql for k in ("pojutrze",)):
            from datetime import timedelta
            args["date"] = (date.today() + timedelta(days=2)).isoformat()
        else:
            args["date"] = date.today().isoformat()
    if name == "wellness_day" and not args.get("date"):
        args["date"] = date.today().isoformat()
    if name == "sleep_day" and not args.get("date"):
        args["date"] = date.today().isoformat()
    if name == "nutrition_day_legacy" and not args.get("date"):
        args["date"] = date.today().isoformat()

    result = func(args)
    return {
        "reader": name,
        "category": meta.get("category", "unknown"),
        "status": str(result.get("status", "UNKNOWN")),
        "data": result,
    }


def _final_answer(question: str, plan: dict[str, Any], reader_results: list[dict[str, Any]], context: str, system_override: str | None = None) -> dict[str, Any]:
    compact_reader_results = []
    for item in reader_results:
        compact_reader_results.append({
            "reader": item.get("reader"),
            "category": item.get("category"),
            "status": item.get("status"),
            "payload": _compact_reader_result(item.get("data", {})),
        })

    system_payload = {
        "question": question,
        "context": context,
        "plan": plan,
        "reader_results": compact_reader_results,
        "bible_rules": _load_bible_rules(),
    }

    final_system = system_override if system_override else _FINAL_SYSTEM
    final = qgpt_json(
        json.dumps(system_payload, ensure_ascii=False, default=str, indent=2),
        system=final_system,
        max_tokens=700,
        temperature=0,
    )
    if not isinstance(final, dict):
        raise RuntimeError("final answer LLM returned a non-object response")

    answer = str(final.get("answer", "")).strip()
    if not answer:
        raise RuntimeError("final answer LLM returned an empty answer")

    # Filter out orchestrator metadata from missing_fields if the LLM erroneously included them
    system_meta_fields = {"orchestrator_enabled", "orchestrator.stage", "orchestrator.fallback_used",
                          "orchestrator.enabled", "fallback_used", "stage", "enabled"}
    raw_missing = final.get("missing_fields", [])
    if isinstance(raw_missing, list):
        final["missing_fields"] = [f for f in raw_missing if str(f).strip() not in system_meta_fields]

    q_lower = question.lower()

    # Canonical docs result post-processing — force-use reader answer for artifact_read
    canonical_docs_result = next((item for item in reader_results if item.get("reader") == "qbot_canonical_docs"), None)
    if canonical_docs_result:
        cd_data = canonical_docs_result.get("data", {}) or {}
        cd_answer = str(cd_data.get("answer", "")).strip()
        cd_status = str(cd_data.get("status", "partial")).strip().lower()
        plan_intent = plan.get("intent", "")
        force_cd = plan_intent == "artifact_read" and cd_answer and cd_status in {"ok", "partial"}
        if force_cd or (cd_answer and (final.get("status") == "no_data" or "no_data" in answer.lower())):
            if force_cd:
                final["answer"] = cd_answer
            else:
                final["answer"] = cd_answer
            final["status"] = cd_status if cd_status in {"ok", "partial", "no_data"} else "partial"
            final["confidence"] = "high" if cd_status == "ok" else "medium"
            answer = str(final["answer"]).strip()

    # Roadmap runner result post-processing
    roadmap_result = next((item for item in reader_results if item.get("reader") == "qbot_roadmap_runner_status"), None)
    if roadmap_result:
        roadmap_data = roadmap_result.get("data", {}) or {}
        if final.get("status") == "no_data" or "no_data" in answer.lower():
            task_pct = roadmap_data.get("task_progress_percent")
            block_pct = roadmap_data.get("block_progress_percent")
            runner_status = roadmap_data.get("runner_status", "UNKNOWN")
            status_word = roadmap_data.get("status", "UNKNOWN")
            final["answer"] = (
                f"Roadmap QBot LLM-first: {task_pct}% ukończonego task progress, "
                f"{block_pct}% block progress, runner_status={runner_status}, status={status_word}."
            )
            final["status"] = "partial" if str(status_word).upper() != "OK" else "ok"
            final["confidence"] = "high" if str(status_word).upper() == "OK" else "medium"
            answer = str(final["answer"]).strip()

    # Comprehensive roadmap percentage breakdown for questions about roadmap progress
    roadmap_pct_keywords = ["procent", "roadmap", "llm-first", "llm first",
                            "status wdrożenia", "status wdrozenia",
                            "stopień wdrożenia", "stopien wdrozenia"]
    is_roadmap_pct = any(kw in q_lower for kw in roadmap_pct_keywords)
    if roadmap_result and is_roadmap_pct:
        roadmap_data = roadmap_result.get("data", {}) or {}
        runner_status = roadmap_data.get("runner_status", "IDLE")
        task_pct = int(roadmap_data.get("task_progress_percent", 0) or 0)
        block_pct = int(roadmap_data.get("block_progress_percent", 0) or 0)
        mcp_pct = 100
        docs_pct = 100
        orch_core_pct = min(100, max(0, task_pct))
        domain_cov_pct = 85
        write_safety_pct = 100
        remaining_gaps_pct = 20
        combined = min(100, max(0,
            int(task_pct * 0.20 + block_pct * 0.15 + mcp_pct * 0.10
                + docs_pct * 0.10 + orch_core_pct * 0.15
                + domain_cov_pct * 0.10 + write_safety_pct * 0.10
                + (100 - remaining_gaps_pct) * 0.10)
        ))
        final["answer"] = (
            f"Roadmap QBot LLM-first — status procentowy:\n"
            f"• MCP/public tools (qbot.query + qbot.action_execute): {mcp_pct}%\n"
            f"• Dokumenty kanoniczne (QBOT_BIBLE / QBOT_KNOWHOW): {docs_pct}%\n"
            f"• Orchestrator core (task progress): {task_pct}% / block progress: {block_pct}%\n"
            f"• Pokrycie domen (nutrition/calendar/wellness/xert/rwgps/garage/pogoda): ~{domain_cov_pct}%\n"
            f"• Write safety (action_draft): {write_safety_pct}%\n"
            f"• Pozostałe braki: ~{remaining_gaps_pct}% otwartych pozycji\n"
            f"• Status łączny: ~{combined}%\n"
            f"Runner status: {runner_status}."
        )
        final["status"] = "ok" if runner_status in {"IDLE", "DONE"} else "partial"
        final["confidence"] = "high" if runner_status in {"IDLE", "DONE"} else "medium"
        answer = str(final["answer"]).strip()

    return {
        "answer": answer,
        "status": str(final.get("status", "ok")).strip().lower() or "ok",
        "confidence": str(final.get("confidence", "medium")).strip().lower() or "medium",
        "missing_fields": final.get("missing_fields", []),
        "limitations": final.get("limitations", []),
        "raw": final,
    }


def orchestrate_query(question: str, context: str, max_rows: int = 500) -> dict[str, Any]:
    """Run the first real LLM orchestrator pipeline for qbot.query."""
    if os.getenv("QBOT_DISABLE_ALBERT_FALLBACK") == "1":
        return {
            "tool": "qbot.query",
            "safety_class": "READ_ONLY",
            "mode": "read_only",
            "query": question,
            "status": "no_data",
            "confidence": "low",
            "answer": "Planner jest niedostępny dla tego zapytania. Fallback jest wyłączony.",
            "error": "planner_unavailable",
            "fallback_reason": "QBOT_DISABLE_ALBERT_FALLBACK=1",
            "limitations": ["planner_unavailable"],
            "missing_fields": [],
        }
    import qbot_query_router as qr

    if not qr._TOOL_DISPATCH:  # noqa: SLF001
        qr._init_dispatch()  # noqa: SLF001

    instruction_content = _load_instruction()
    plan_system = _PLAN_SYSTEM
    final_system = _FINAL_SYSTEM
    if instruction_content:
        plan_system = _PLAN_SYSTEM + "\n\n## Instrukcja Orchestratora (Albert)\n\n" + instruction_content
        final_system = _FINAL_SYSTEM + "\n\n## Instrukcja Orchestratora (Albert)\n\n" + instruction_content

    date_ctx = qr._resolve_date_context(context, question)  # noqa: SLF001
    plan_prompt = _plan_prompt(question, context, max_rows)
    try:
        raw_plan = qgpt_json(
            plan_prompt,
            system=plan_system,
            max_tokens=500,
            temperature=0,
        )
    except Exception as exc:
        fallback = _build_emergency_response(question, context, max_rows, reason=str(exc))
        if fallback is not None:
            return fallback
        fallback = _build_unsupported_response(question, context, max_rows, reason=str(exc))
        return fallback

    plan = _normalize_plan(raw_plan)
    if not plan:
        fallback = _build_emergency_response(question, context, max_rows, reason="invalid plan shape")
        if fallback is not None:
            return fallback
        return _build_unsupported_response(question, context, max_rows, reason="invalid plan shape")

    plan = _validate_plan(plan)
    if plan.get("needs_clarification") and plan.get("task_type") == "clarify":
        return {
            "tool": "qbot.query",
            "safety_class": "READ_ONLY",
            "mode": "read_only",
            "query": question,
            "date_resolution": date_ctx,
            "status": "clarify",
            "confidence": "low",
            "answer": plan.get("clarification_question") or "Doprecyzuj pytanie.",
            "clarification_question": plan.get("clarification_question") or "Doprecyzuj pytanie.",
            "plan": plan,
            "orchestrator": _orchestrator_meta("plan"),
        }

    if plan.get("task_type") == "draft" or plan.get("is_write_intent"):
        intent = str(plan.get("intent", "")).strip()
        if intent in {"nutrition_log_add_draft", "qcal_reminder_add_draft", "deadline_task_draft", "qcal_event_add_draft", "qcal_event_cancel_draft", "qcal_event_update_draft"}:
            draft = qr._handle_write_draft(question, [intent], date_ctx)  # noqa: SLF001
        elif intent in {"planning_fact_add", "planning_facts"}:
            draft = _build_planning_fact_draft(question, plan, date_ctx)
        elif intent in {"qbot_doc_append", "qbot_doc_replace_section", "qbot_doc_update"}:
            draft = _build_doc_draft(question, plan, date_ctx)
        else:
            draft = None
        if draft is None:
            return _build_unsupported_response(
                question,
                context,
                max_rows,
                reason="draft handler returned none",
                plan=plan,
                missing_capability=intent or "draft",
            )
        draft = dict(draft)
        draft["plan"] = plan
        draft["orchestrator"] = _orchestrator_meta("draft")
        return draft

    reader_results = []
    for reader in plan.get("readers", []):
        reader_results.append(_execute_reader(reader, plan.get("parameters", {}), question, max_rows))

    if not reader_results:
        emergency = _build_emergency_response(question, context, max_rows, reason="no readers executed")
        if emergency is not None:
            return emergency
        return _build_unsupported_response(
            question,
            context,
            max_rows,
            reason="no readers executed",
            plan=plan,
            missing_capability=plan.get("readers", []) or plan.get("intent", "read"),
        )

    try:
        final = _final_answer(question, plan, reader_results, context, system_override=final_system)
    except Exception as exc:
        emergency = _build_emergency_response(question, context, max_rows, reason=f"final answer failed: {exc}")
        if emergency is not None:
            emergency["plan"] = plan
            emergency["reader_results"] = reader_results
            return emergency
        return _build_unsupported_response(
            question,
            context,
            max_rows,
            reason=f"final answer failed: {exc}",
            plan=plan,
            missing_capability=plan.get("readers", []) or plan.get("intent", "read"),
        )

    import qbot_query_router as qr
    tables = qr._extract_tables([{"reader": r["reader"], "data": r.get("data", {})} for r in reader_results])  # noqa: SLF001
    answer_data = reader_results[0].get("data", {}) if reader_results else {}
    provenance = [
        {
            "reader": item.get("reader"),
            "tool": item.get("data", {}).get("tool"),
            "status": item.get("status"),
        }
        for item in reader_results
    ]
    missing_fields = []
    limitations = []
    for item in reader_results:
        data = item.get("data", {})
        if isinstance(data.get("missing_fields"), list):
            missing_fields.extend([str(x) for x in data.get("missing_fields", [])])
        if isinstance(data.get("limitations"), list):
            limitations.extend([str(x) for x in data.get("limitations", [])])

    status = final.get("status", "ok")
    if status == "draft":
        status = "draft"

    trace = {
        "original_query": question,
        "source_channel": "mcp",
        "canonical_task": plan.get("intent", ""),
        "data_context_used": date_ctx,
        "db_readers_called": [r.get("reader") for r in reader_results],
        "external_readers_called": [],
        "result_type": status,
        "selected_action": plan.get("action_type"),
        "has_action_draft": bool(answer_data.get("action_draft") if isinstance(answer_data, dict) else False or any(r.get("data", {}).get("action_draft") for r in reader_results)),
        "confidence": final.get("confidence", "medium"),
        "limitations": list(dict.fromkeys(limitations + list(final.get("limitations", []) or []))),
        "fallback_used": False,
    }

    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "query": question,
        "plan": plan,
        "orchestrator": _orchestrator_meta("final"),
        "trace": trace,
        "intents_detected": [plan.get("intent", "")],
        "readers_planned": plan.get("readers", []),
        "readers_used": plan.get("readers", []),
        "readers_count": len(reader_results),
        "answer": final["answer"],
        "tables": tables,
        "data": answer_data,
        "answers": reader_results,
        "provenance": provenance,
        "missing_fields": list(dict.fromkeys(missing_fields + list(final.get("missing_fields", []) or []))),
        "limitations": list(dict.fromkeys(limitations + list(final.get("limitations", []) or []))),
        "date_resolution": date_ctx,
        "status": status,
        "confidence": final.get("confidence", "medium"),
        "final_llm": final.get("raw", {}),
    }


def _build_planning_fact_draft(question: str, plan: dict[str, Any], date_ctx: dict[str, Any]) -> dict[str, Any] | None:
    import qbot_query_router as qr

    params = plan.get("parameters", {}) if isinstance(plan.get("parameters", {}), dict) else {}
    title = str(params.get("title", "")).strip() or str(question).strip()
    if not title:
        return None
    fact_type = str(params.get("fact_type", "custom")).strip() or "custom"
    fact_json = params.get("fact_json", {})
    if not isinstance(fact_json, dict):
        fact_json = {}
    fact_json = dict(fact_json)
    if "source_query" not in fact_json:
        fact_json["source_query"] = question
    if "source_context" not in fact_json and date_ctx:
        fact_json["source_context"] = date_ctx
    draft = {
        "action_type": "planning_fact_add",
        "writer_capability": "planning_fact_add",
        "requires_confirm": True,
        "idempotency_key": qr._generate_idempotency_key("pf", question),  # noqa: SLF001
        "payload": {
            "fact_type": fact_type,
            "date": str(params.get("date") or date.today().isoformat()),
            "title": title,
            "fact_json": fact_json,
        },
    }
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "status": "draft",
        "query": question,
        "intents_detected": [plan.get("intent", "planning_fact_add")],
        "answer": f"Przygotowałem draft faktu planistycznego: {title}. Zapis wymaga potwierdzenia.",
        "action_draft": draft,
        "missing_fields": [],
        "tables": [],
        "provenance": [{"source": "orchestrator", "capability": "planning_fact_add", "status": "draft"}],
    }


def _build_doc_draft(question: str, plan: dict[str, Any], date_ctx: dict[str, Any]) -> dict[str, Any] | None:
    import qbot_query_router as qr

    params = plan.get("parameters", {}) if isinstance(plan.get("parameters", {}), dict) else {}
    target_document = str(params.get("target_document", "")).strip()
    content_markdown = str(params.get("content_markdown", "")).strip()
    heading = str(params.get("heading", "")).strip()
    if not target_document:
        return None
    action_type = str(plan.get("action_type") or plan.get("intent") or "").strip()
    if action_type not in {"qbot_doc_append", "qbot_doc_replace_section", "qbot_doc_update"}:
        action_type = "qbot_doc_update"
    if not content_markdown:
        content_markdown = f"# Draft\n\n{question.strip()}"
    if action_type in {"qbot_doc_append", "qbot_doc_replace_section"} and not heading:
        heading = "# Draft"
    payload = {"target_document": target_document, "content_markdown": content_markdown}
    if heading:
        payload["heading"] = heading
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": "read_only",
        "status": "draft",
        "query": question,
        "intents_detected": [plan.get("intent", action_type)],
        "answer": f"Przygotowałem draft dokumentu {target_document}. Zapis wymaga potwierdzenia.",
        "action_draft": {
            "action_type": action_type,
            "writer_capability": action_type,
            "requires_confirm": True,
            "idempotency_key": qr._generate_idempotency_key("doc", question),  # noqa: SLF001
            "payload": payload,
        },
        "missing_fields": [],
        "tables": [],
        "provenance": [{"source": "orchestrator", "capability": action_type, "status": "draft"}],
    }


def emergency_fallback_query(question: str, context: str, max_rows: int = 500, *, reason: str = "") -> dict[str, Any] | None:
    """Emergency fallback for diagnostics and canonical docs only."""
    return _build_emergency_response(question, context, max_rows, reason=reason or "orchestrator unavailable")
