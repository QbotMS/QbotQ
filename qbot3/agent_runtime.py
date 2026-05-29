#!/usr/bin/env python3
"""QBot3 Agent Runtime (Albert) — context → plan → execute → answer.

Zero legacy router imports. All decisions through LLM provider interface.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from typing import Any

from qbot3.llm import get_llm_provider
from qbot3.tool_registry import lookup, tool_descriptions, _idempotency_key, _resolve_date
from qbot3.context_builder import build_context
from qbot3.plan_validator import validate_plan
from qbot3.observability import log_request, Timer, request_id as rid


def orchestrate_query(question: str, context: str = "", max_rows: int = 500) -> dict[str, Any]:
    _check_qbot3_enabled()
    from qbot3.errors import OK, ERROR, PLAN_INVALID, CAPABILITY_MISSING, PROVIDER_ERROR

    timer = Timer()
    timer.start()
    req_id = rid()
    provider_name = os.getenv("ALBERT_LLM_PROVIDER", "openai")
    model_name = os.getenv("ALBERT_LLM_MODEL", "")

    # Input kind classification — runs before any routing
    input_kind = _classify_input(question)
    if input_kind.get("conversational"):
        try:
            answer = input_kind.get("answer", "Działam.")
            local_ctx = build_context(question)
            result = _build_response(local_ctx, status="ok", answer=answer,
                                     confidence="high")
            result["human_answer"] = answer
            result["request_id"] = req_id
            return result
        except Exception as exc:
            # Fallback: return simple dict directly if _build_response fails
            return {
                "status": "ok",
                "answer": answer,
                "human_answer": answer,
                "request_id": req_id,
                "tool": "qbot.query",
                "orchestrator": {"enabled": True, "name": "Albert", "version": "qbot3", "stage": "final", "fallback_used": False},
            }

    ctx = build_context(question)

    # ── Pre-layer: only context injection, safety envelope, destructive block ──
    # NO intent routing — Albert decides everything.

    # Destructive block (pure safety, not routing)
    if _is_destructive_query(question):
        result = _build_response(ctx, status="BLOCKED", answer="Destrukcyjne operacje są zablokowane. Wymagają osobnej zgody.",
                                limitations=["destructive_blocked"])
        result["request_id"] = req_id
        return result

    # ── LLM-first: Albert decides intent, mode, write vs read ────────────────
    llm = get_llm_provider()
    tools_desc = tool_descriptions()

    plan_result = llm.plan(ctx, tools_desc, question)
    plan = _normalize_plan(plan_result)

    if not plan:
        result = _build_response(ctx, status=ERROR, answer="Nie mogę zaplanować zapytania.", limitations=["invalid_plan"])
        _log(req_id, provider_name, model_name, "unknown", "", [], [], False, ERROR, "plan_generation", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    # ── Post-LLM: Convert write-related intents to mode=write ────────────────
    # Albert may return read_only+no_tools for a write intent (e.g. add_nutrition_entry)
    # because the LLM is not always perfect at mode selection.
    # We resolve: if intent suggests a write action and no tools are planned, convert.
    plan = _resolve_write_intent(plan, question)

    # ── Plan validation ──────────────────────────────────────────────────────
    validation = validate_plan(plan)
    if validation.get("status") == CAPABILITY_MISSING:
        # Before giving up, check if this is really a write intent that was missed
        resolved = _try_resolve_missing_capability_as_write(plan, question)
        if resolved:
            plan = resolved
            validation = {"status": OK, "valid": True}
        else:
            cap_result = _try_execute_capability(plan.get("intent", ""), ctx, question)
            if cap_result:
                result = cap_result
                _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
                     plan.get("tools_to_call", []), [f"capability:{plan.get('intent', '')}"], False,
                     result.get("status", OK), "", timer.elapsed_ms())
                result["request_id"] = req_id
                return result
            proposal = validation.get("capability_proposal", {})
            cap_intent = plan.get("intent", "")
            answer = f"Brak capability dla '{cap_intent}'. "
            if proposal.get("capability_found"):
                answer += f"Znaleziono capability '{proposal.get('needed_capability', '')}', ale nie jest aktywna (state: {proposal.get('promotion_state', 'unknown')})."
            else:
                answer += f"Propozycja: utwórz capability '{cap_intent.replace(' ', '_')}_status' typu READ_ONLY."
            result = _build_response(ctx, status=CAPABILITY_MISSING, answer=answer,
                                    plan=plan, limitations=["capability_missing"])
            _log(req_id, provider_name, model_name, plan.get("mode", "unknown"), plan.get("intent", ""),
                 plan.get("tools_to_call", []), [], False, CAPABILITY_MISSING, "capability_missing", timer.elapsed_ms())
            result["request_id"] = req_id
            return result

    if validation.get("status") != OK:
        result = _build_response(ctx, status=validation.get("status", ERROR), answer=f"Plan odrzucony: {validation.get('error', 'validation failed')}",
                                plan=plan, limitations=[f"plan_validation: {validation.get('status', 'FAILED')}"])
        _log(req_id, provider_name, model_name, plan.get("mode", "unknown"), plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, validation.get("status", ERROR), "plan_validation", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    if plan["needs_clarification"]:
        result = _build_response(ctx, status="clarify", answer=plan.get("clarification_question") or "Doprecyzuj pytanie.", plan=plan)
        _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, "clarify", "", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    if plan["mode"] == "write":
        result = _handle_write(ctx, plan)
        _log(req_id, provider_name, model_name, "write", plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, result.get("status", "draft"), "", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    if plan["mode"] == "plan_only":
        result = _build_response(ctx, status=OK, answer=f"Plan: intent={plan['intent']}, tools={plan.get('tools_to_call', [])}", plan=plan)
        _log(req_id, provider_name, model_name, "plan_only", plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, OK, "", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    tool_results = _execute_tools(plan["tools_to_call"], plan.get("parameters", {}), question)

    if not tool_results:
        cap_result = _try_capability_fallback(plan, ctx, question)
        if cap_result:
            result = cap_result
            _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
                 plan.get("tools_to_call", []), [f"capability:{plan.get('intent', '')}"],
                 False, result.get("status", OK), "", timer.elapsed_ms())
            result["request_id"] = req_id
            return result
        result = _build_response(ctx, status=ERROR, answer="Nie znaleziono narzędzi do wykonania.", plan=plan, limitations=["no_tools_executed"])
        _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, ERROR, "tool_execution", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    if _all_tools_empty(tool_results):
        cap_result = _try_capability_fallback(plan, ctx, question)
        if cap_result:
            result = cap_result
            _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
                 plan.get("tools_to_call", []), [f"capability:{plan.get('intent', '')}"],
                 False, result.get("status", OK), "", timer.elapsed_ms())
            result["request_id"] = req_id
            return result

    # ── DB introspection fallback: if any reader returned SCHEMA_MISMATCH/READER_ERROR ──
    # Albert described the right domain tool but the reader failed on schema.
    # Fall back to DB introspection so Albert can still get the data.
    if _has_reader_error(tool_results):
        db_fallback = _try_db_introspection_fallback(plan, question)
        if db_fallback:
            tool_results.extend(db_fallback)
            plan["tools_to_call"] = list(plan.get("tools_to_call", [])) + ["db_introspection_fallback"]
            plan["db_introspection_used"] = True

    tools_called = [r.get("reader", "") for r in tool_results]
    answer_result = llm.answer(ctx, plan, tool_results)

    result = _build_response(ctx, status=answer_result.status, answer=answer_result.answer, plan=plan,
                            tool_results=tool_results, missing=answer_result.missing_fields,
                            limitations=answer_result.limitations, final_llm=answer_result.raw,
                            confidence=answer_result.confidence)
    _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
         plan.get("tools_to_call", []), tools_called, False, answer_result.status, "", timer.elapsed_ms())
    result["request_id"] = req_id
    return result


def _check_qbot3_enabled() -> None:
    if os.getenv("QBOT3_ENABLED") != "1":
        raise RuntimeError("QBOT3_ENABLED=1 required for QBot3 agent runtime")


# ── Read pre-router domains (dry, safe, for well-known read-only domains) ─
# Kept as a convenience — NOT for final intent routing. Albert still gets
# the final say. This just provides quick answers for obvious known domains.
_PRE_ROUTE_DOMAINS: list[tuple[list[str], str, str]] = [
    (["status qbot", "qbot status", "status systemu"], "status", "status"),
    (["readiness", "gotowość", "readiness qbot"], "readiness", "readiness"),
    (["raport dzienny", "daily report", "email z raportem", "nie przeszedł", "niedostarczony raport",
      "daily_report", "pipeline", "report pipeline", "dlaczego nie dostałem raportu",
      "co z raportem", "stuck", "pending", "block", "report_status"],
     "daily_report_status", "daily_report_status"),
    (["furtk", "gate", "hikconnect", "otwórz bram", "brama", "gate_status", "open gate",
      "unlock", "czy furtka"],
     "gate_status", "gate_status"),
    (["hammerhead", "garmin sync", "transfer aktywno", "karoo", "activity transfer",
      "synchronizacja", "sync status", "hammerhead_sync", "czy przesłał"],
     "hammerhead_sync_status", "hammerhead_sync_status"),
    (["garmin import", "ostatni import", "garmin sync status", "garmin_sync_status",
      "kiedy był import", "data garmin"],
     "garmin_sync_status", "garmin_sync_status"),
    (["llm", "model llm", "jaki model", "jakiego modelu", "provider", "llm_status",
      "ai model", "sztuczna inteligencja", "albert llm", "fallback model"],
     "llm_status", "llm_status"),
]

# ── Write intent ↔ action type mapping (post-LLM resolver) ─────────────
# Used when LLM returns read_only+no_tools for an intent that is actually a write.
# Not a pre-router — runs AFTER Albert, only as a safety net for LLM mode mistakes.

_WRITE_INTENT_MAP: dict[str, str] = {
    "add_nutrition_entry": "nutrition_log_add",
    "nutrition_log_add": "nutrition_log_add",
    "add_calendar_event": "calendar_event_add",
    "calendar_event_add": "calendar_event_add",
    "add_reminder": "reminder_add",
    "reminder_add": "reminder_add",
    "add_planning_fact": "planning_fact_add",
    "planning_fact_add": "planning_fact_add",
    "add_memory_fact": "memory_confirmed_fact_add",
    "memory_confirmed_fact_add": "memory_confirmed_fact_add",
    "append_doc": "qbot_doc_append",
    "qbot_doc_append": "qbot_doc_append",
}

# Destructive patterns — blocked before Albert (pure safety)
_DESTRUCTIVE_PATTERNS = [
    "usuń wszystko", "usuń wszystkie", "wyczyść", "skasuj wszystko", "delete all",
    "usuń", "skasuj", "delete", "remove", "usun",
]


def _is_destructive_query(question: str) -> bool:
    ql = question.lower().strip()
    for pat in _DESTRUCTIVE_PATTERNS:
        if ql.startswith(pat) or pat in ql.split()[:3]:
            return True
    return False


def _resolve_write_intent(plan: dict[str, Any], question: str) -> dict[str, Any]:
    """Post-LLM resolver: if plan looks like a misclassified write intent, fix it."""
    plan = dict(plan)
    intent = plan.get("intent", "")
    mode = plan.get("mode", "read_only")
    tools = plan.get("tools_to_call", [])

    # If mode=write already, nothing to resolve
    if mode == "write":
        return plan

    # If intent maps to a write action and no tools were planned
    if intent in _WRITE_INTENT_MAP and not tools:
        write_action = _WRITE_INTENT_MAP[intent]
        plan["mode"] = "write"
        plan["write_action"] = write_action
        plan["requires_confirm"] = True
        plan["write_payload"] = _extract_write_payload(write_action, question)
        plan["tools_to_call"] = []
        return plan

    # If intent is generic write-like (starts with add_, create_, save_, log_, insert_)
    # and no tools, try to infer the write action
    generic_write_prefixes = ("add_", "create_", "save_", "log_", "insert_", "new_", "set_", "write_")
    if mode == "read_only" and not tools and any(intent.startswith(p) for p in generic_write_prefixes):
        for known_intent, known_action in _WRITE_INTENT_MAP.items():
            if intent.startswith(known_intent.rstrip("_").split("_")[0]):
                plan["mode"] = "write"
                plan["write_action"] = known_action
                plan["requires_confirm"] = True
                plan["write_payload"] = _extract_write_payload(known_action, question)
                plan["tools_to_call"] = []
                return plan

    return plan


def _try_resolve_missing_capability_as_write(plan: dict[str, Any], question: str) -> dict[str, Any] | None:
    """When plan gets CAPABILITY_MISSING, check if it's really a write intent."""
    intent = plan.get("intent", "")
    if intent in _WRITE_INTENT_MAP:
        write_action = _WRITE_INTENT_MAP[intent]
        return {
            "intent": intent,
            "mode": "write",
            "tools_to_call": [],
            "write_action": write_action,
            "write_payload": _extract_write_payload(write_action, question),
            "requires_confirm": True,
            "confidence": plan.get("confidence", 0.5),
            "needs_clarification": False,
            "clarification_question": "",
        }
    return None


def _deterministic_write_pre_route(question: str) -> dict[str, Any] | None:
    """Intercept write intents before LLM planner.

    Returns a write plan dict if matched, None to continue with LLM planner.
    """
    from qbot3.write_router import build_draft, validate_action_type, classify_input_kind, WRITE_DRAFT_TASK

    ql = question.lower().strip()
    cls = classify_input_kind(question)

    # If classification is ambiguous but question contains write keywords, try harder
    if cls["input_kind"] in (WRITE_DRAFT_TASK, "AMBIGUOUS_WRITE") and cls.get("confidence", 0) < 0.9:
        # Check against write pre-router keywords directly
        for keywords, at in _WRITE_PRE_ROUTE_KEYWORDS:
            if any(kw in ql for kw in keywords):
                if at == "DESTRUCTIVE":
                    return _build_destructive_block()
                cls = {"input_kind": WRITE_DRAFT_TASK, "action_type": at, "confidence": 0.85}
                break

    if cls["input_kind"] == "UNSUPPORTED_OR_DESTRUCTIVE":
        if cls.get("action_type") == "DESTRUCTIVE":
            return _build_destructive_block()
        return {
            "intent": "destructive_write_blocked",
            "mode": "plan_only",
            "tools_to_call": [],
            "write_action": None,
            "write_payload": {},
            "requires_confirm": False,
            "confidence": 1.0,
            "needs_clarification": False,
            "clarification_question": "",
            "_pre_routed_write": True,
            "_write_classification": "DESTRUCTIVE_WRITE",
            "_write_blocked": True,
            "_write_message": "Destrukcyjne operacje są zablokowane. Wymagają osobnej zgody.",
            "answer": "Destrukcyjne operacje są zablokowane bez osobnej zgody.",
        }

    if cls["input_kind"] == WRITE_DRAFT_TASK and cls.get("action_type"):
        at = cls["action_type"]
        is_valid, error, _ = validate_action_type(at), None, None
        v = validate_action_type(at)
        if not v["valid"]:
            return {
                "intent": f"{at}_draft",
                "mode": "plan_only",
                "tools_to_call": [],
                "_pre_routed_write": True,
                "_write_classification": "UNSUPPORTED_ACTION_TYPE",
                "answer": f"Akcja '{at}' nie jest na allowliście. Dostępne: {v['allowed']}.",
            }
        # Extract payload from question
        payload = _extract_write_payload(at, question)
        draft = build_draft(at, payload, question)
        needs_clarification = bool(draft.get("missing_fields"))
        answer_parts = [f"Przygotowałem draft: {draft['human_summary']}"]
        if needs_clarification:
            answer_parts.append(draft.get("clarification_question", ""))
        answer_parts.append("Zapis wymaga potwierdzenia przez qbot.action_execute.")
        return {
            "intent": f"{at}_draft",
            "mode": "write",
            "tools_to_call": [],
            "write_action": at,
            "write_payload": draft["payload"],
            "requires_confirm": True,
            "confidence": 0.9,
            "needs_clarification": needs_clarification,
            "clarification_question": draft.get("clarification_question", ""),
            "_pre_routed_write": True,
            "_write_classification": "WRITE_DRAFT_REQUEST",
            "_write_action_draft": draft,
            "answer": " ".join(answer_parts),
        }

    return None


def _extract_write_payload(action_type: str, question: str) -> dict[str, Any]:
    """Extract payload fields from a natural language write query.

    Uses domain-specific slot extractors from write_router.
    Extracts from domain_task_text (control directives removed).
    """
    from qbot3.write_router import (
        extract_nutrition_slots, extract_calendar_slots,
        extract_reminder_slots, extract_planning_fact_slots,
    )
    from qbot3.query_decomposer import decompose_query, is_payload_contaminated, clean_payload

    # Decompose query first
    decomposition = decompose_query(question)
    domain_task = decomposition.get("domain_task_text", question)
    control_directives = decomposition.get("control_directives", [])
    execution_intent = decomposition.get("execution_intent", "unknown")

    payload: dict[str, Any] = {}
    if action_type == "nutrition_log_add":
        payload = extract_nutrition_slots(domain_task)
        if "meal_name" not in payload and "amount" not in payload:
            quoted = re.findall(r'"([^"]+)"', question)
            if quoted:
                payload["meal_name"] = quoted[0]
    elif action_type in ("calendar_event_add",):
        payload = extract_calendar_slots(domain_task)
    elif action_type in ("reminder_add",):
        payload = extract_reminder_slots(domain_task)
    elif action_type in ("planning_fact_add", "memory_confirmed_fact_add"):
        payload = extract_planning_fact_slots(domain_task)

    # Contamination check + clean
    contamination = is_payload_contaminated(payload, decomposition, action_type)
    if contamination:
        payload = clean_payload(payload, contamination, action_type)
        payload["_contamination_cleaned"] = True

    # Attach decomposition metadata
    payload["_decomposition"] = {
        "execution_intent": execution_intent,
        "control_directives": [d["text"] for d in control_directives],
        "domain_task_text": domain_task,
    }

    return payload


def _classify_input(question: str) -> dict[str, Any]:
    """Classify input kind - conversational, task, or destructive.

    Returns dict with conversational flag and answer for conversational inputs.
    """
    from qbot3.write_router import classify_input_kind, get_conversation_response, CONVERSATIONAL_PING, SMALLTALK

    kind = classify_input_kind(question)
    ik = kind.get("input_kind")
    if ik in (CONVERSATIONAL_PING, SMALLTALK):
        answer = get_conversation_response(ik) or "Działam."
        return {"conversational": True, "kind": ik, "answer": answer}
    return {"conversational": False, "kind": ik}


def _build_destructive_block() -> dict[str, Any]:
    return {
        "intent": "destructive_write_blocked",
        "mode": "plan_only",
        "tools_to_call": [],
        "_pre_routed_write": True,
        "_write_classification": "DESTRUCTIVE_WRITE",
        "_write_message": "Destrukcyjne operacje są zablokowane. Wymagają osobnej zgody.",
        "answer": "Destrukcyjne operacje są zablokowane bez osobnej zgody.",
    }


def _deterministic_pre_route(question: str) -> dict[str, Any] | None:
    """Check if question matches a deterministic pre-route domain.
    
    Returns a plan dict if matched, None to continue with LLM planner.
    """
    ql = question.lower().strip()
    for keywords, intent, tool_name in _PRE_ROUTE_DOMAINS:
        if any(kw in ql for kw in keywords):
            tool_spec = lookup(tool_name)
            if not tool_spec:
                continue
            return {
                "intent": intent,
                "mode": "read_only",
                "tools_to_call": [tool_name],
                "parameters": {},
                "write_action": None,
                "write_payload": {},
                "requires_confirm": False,
                "confidence": 1.0,
                "needs_clarification": False,
                "clarification_question": "",
                "needed_context": [],
                "_pre_routed": True,
            }
    return None


def _execute_pre_routed(
    plan: dict[str, Any], question: str,
    req_id: str, provider_name: str, model_name: str,
    timer: Timer,
) -> dict[str, Any]:
    """Execute a pre-routed plan without LLM planner."""
    from qbot3.errors import OK, ERROR
    ctx = build_context(question)
    tools = plan.get("tools_to_call", [])
    tool_results = _execute_tools(tools, plan.get("parameters", {}), question)
    if tool_results:
        # Build answer from tool results directly
        answer_parts = []
        for tr in tool_results:
            data = tr.get("data", {})
            if isinstance(data, dict):
                summary = data.get("summary", "")
                if summary:
                    answer_parts.append(summary)
                # Extract human-readable info
                state = data.get("state", {})
                if state:
                    pipe = state.get("pipeline_stage", "")
                    if pipe:
                        answer_parts.insert(0, f"Raport zatrzymał się na etapie: {pipe}.")
                    ch = state.get("channels", {})
                    tel = ch.get("telegram", "?")
                    eml = ch.get("email", "?")
                    answer_parts.append(f"Telegram: {tel}. Email: {eml}.")
                    last_err = state.get("last_error", "")
                    if last_err:
                        answer_parts.append(f"Ostatni błąd: {last_err}")
        if not answer_parts:
            answer_parts.append(str(data)[:300] if isinstance(data, dict) else str(data))
        answer = " ".join(answer_parts)
    else:
        answer = "Nie znaleziono narzędzia dla pre-routed plan."
    result = _build_response(ctx, status=OK, answer=answer, plan=plan, tool_results=tool_results,
                            limitations=["pre_routed"])
    _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
         tools, [t.get("reader", "") for t in (tool_results or [])],
         False, result.get("status", OK), "", timer.elapsed_ms())
    return result


def _normalize_plan(plan_result: Any) -> dict[str, Any] | None:
    if not plan_result:
        return None
    intent = str(getattr(plan_result, "intent", "") or "").strip()
    mode = str(getattr(plan_result, "mode", "read_only") or "read_only").strip().lower()
    if not intent:
        return {"intent": "", "mode": mode, "needs_clarification": True, "clarification_question": "Nie rozpoznano intencji."}
    tools = getattr(plan_result, "tools_to_call", [])
    if not isinstance(tools, list):
        tools = []
    # Normalize: support both ["tool_name"] and [{"name": "tool_name", "args": {...}}]
    normalized_tools = []
    merged_params = dict(getattr(plan_result, "parameters", {}))
    for t in tools:
        if isinstance(t, dict):
            name = str(t.get("name", "")).strip()
            if name:
                normalized_tools.append(name)
            args = t.get("args", {})
            if isinstance(args, dict):
                merged_params.update(args)
        else:
            name = str(t).strip()
            if name:
                normalized_tools.append(name)
    tools = normalized_tools
    params = merged_params
    if not isinstance(params, dict):
        params = {}
    return {
        "intent": intent,
        "mode": mode,
        "tools_to_call": tools,
        "parameters": params,
        "write_action": getattr(plan_result, "write_action", None),
        "write_payload": getattr(plan_result, "write_payload", {}),
        "requires_confirm": getattr(plan_result, "requires_confirm", False),
        "confidence": getattr(plan_result, "confidence", 0.0),
        "needs_clarification": getattr(plan_result, "needs_clarification", False),
        "clarification_question": getattr(plan_result, "clarification_question", ""),
    }


def _execute_tools(tool_names: list[str], params: dict[str, Any], question: str) -> list[dict[str, Any]]:
    results = []
    for name in tool_names:
        spec = lookup(name)
        if not spec:
            results.append({"reader": name, "status": "error", "data": {"error": f"tool not found: {name}"}})
            continue
        callable_fn = spec["callable"]
        wrapped = spec.get("wrapped")
        args = dict(params)
        if "_question" not in args:
            args["_question"] = question
        try:
            if wrapped:
                result = callable_fn(wrapped, args)
            else:
                result = callable_fn(args)
        except Exception as exc:
            result = {"status": "error", "error": str(exc)[:300]}
        # Propagate error status from tool result — do NOT mask as OK
        data_status = result.get("status", "OK") if isinstance(result, dict) else "OK"
        if data_status in ("SQL_ERROR", "SCHEMA_MISMATCH", "TIMEOUT", "BLOCKED", "ERROR", "CONNECTOR_MISSING", "READER_ERROR"):
            results.append({"reader": name, "category": spec.get("category", ""), "status": data_status, "data": result})
        elif "error" in result and isinstance(result, dict) and result.get("error"):
            results.append({"reader": name, "category": spec.get("category", ""), "status": "error", "data": result})
        else:
            results.append({"reader": name, "category": spec.get("category", ""), "status": "OK", "data": result})
    return results


def _all_tools_empty(tool_results: list[dict[str, Any]]) -> bool:
    """Check if all tool results are effectively empty (no useful data).

    A result is 'empty' if:
      - status is DATA_MISSING/CONNECTOR_MISSING/NO_DATA/NOT_IMPLEMENTED, or
      - the dict has no meaningful keys beyond status, or
      - the result is None/empty string.

    ERROR/SCHEMA_MISMATCH/SQL_ERROR/TIMEOUT/BLOCKED are NOT empty —
    they contain diagnostic info that Albert needs to see.
    """
    if not tool_results:
        return True
    empty_count = 0
    for tr in tool_results:
        wrapper_status = tr.get("status", "OK")
        # Error statuses contain diagnostic info — NOT empty
        if wrapper_status in ("error", "SQL_ERROR", "SCHEMA_MISMATCH", "TIMEOUT", "BLOCKED", "CONNECTOR_MISSING"):
            return False
        data = tr.get("data", {})
        if not isinstance(data, dict):
            empty_count += 1
            continue
        status = data.get("status", "")
        if status in ("DATA_MISSING", "NO_DATA", "NOT_IMPLEMENTED"):
            empty_count += 1
            continue
        # Has explicit error
        if data.get("error"):
            return False
        # Check if it has actual data content beyond status/error
        meaningful_keys = [k for k in data if k not in ("status", "tool", "safety_class")]
        if not meaningful_keys:
            empty_count += 1
            continue
        # Has at least some data — not empty
        return False
    return empty_count == len(tool_results)


def _has_reader_error(tool_results: list[dict[str, Any]]) -> bool:
    """Check if any tool result has a reader error (schema mismatch, SQL error, etc.)."""
    error_statuses = ("SCHEMA_MISMATCH", "READER_ERROR", "SQL_ERROR", "CONNECTOR_MISSING", "TIMEOUT", "error")
    for tr in tool_results:
        ws = tr.get("status", "")
        if ws in error_statuses:
            return True
        data = tr.get("data", {})
        if isinstance(data, dict):
            ds = data.get("status", "")
            if ds in error_statuses:
                return True
    return False


def _try_db_introspection_fallback(plan: dict[str, Any], question: str) -> list[dict[str, Any]] | None:
    """When a reader fails, try DB introspection to get the data.

    Inspects the DB schema and runs a safe SELECT on relevant tables.
    """
    from qbot3.db_introspection import db_table_describe, db_select_readonly, db_schema_list
    from qbot3.tool_registry import lookup
    import re

    ql = question.lower()
    results = []

    # 1. Determine which tables might be relevant from the query
    table_candidates = []
    if any(k in ql for k in ("kalendarz", "event", "wydarzen", "calendar", "toskan", "bikepack", "qcal")):
        table_candidates.append(("public", "calendar_events"))
    if any(k in ql for k in ("jadł", "jedzeni", "posiłk", "meal", "nutrition", "kalor")):
        table_candidates.append(("public", "meal_logs"))
        table_candidates.append(("public", "meal_log_items"))
    if any(k in ql for k in ("reminder", "przypomn")):
        table_candidates.append(("public", "reminders"))

    if not table_candidates:
        # Map known tool names to database tables
        tool_to_table = {
            "qcal_events_range": ("public", "calendar_events"),
            "qcal_events_upcoming": ("public", "calendar_events"),
            "qcal_reminders_upcoming": ("public", "reminders"),
            "nutrition_day_summary": ("public", "meal_logs"),
            "nutrition_log_add": ("public", "meal_logs"),
        }
        for tool_name in plan.get("tools_to_call", []):
            if tool_name in tool_to_table:
                table_candidates.append(tool_to_table[tool_name])

    if not table_candidates:
        # Try to extract table name from the failed tool's description
        for tool_name in plan.get("tools_to_call", []):
            spec = lookup(tool_name)
            if spec:
                desc = spec.get("description", "").lower()
                for tbl in re.findall(r'\b(\w+)\b', desc):
                    if tbl.endswith("s") and tbl not in ("parameters", "status", "data", "class", "type"):
                        table_candidates.append(("public", tbl))

    if not table_candidates:
        return None

    # 2. Describe tables and build safe SELECTs
    explored = set()
    for schema, table in table_candidates:
        key = f"{schema}.{table}"
        if key in explored:
            continue
        explored.add(key)

        # Describe the table to discover actual columns
        describe_args = {"table": table, "schema": schema}
        results.append({
            "reader": "db_table_describe",
            "category": "db",
            "status": "OK",
            "data": {"args": describe_args, "query": "DB introspection fallback — describe table"},
        })
        desc = db_table_describe(describe_args)
        if desc.get("status") != "OK":
            results.append({
                "reader": f"db_introspection_fallback.{table}",
                "category": "db",
                "status": "error",
                "data": {
                    "status": desc.get("status", "ERROR"),
                    "error": desc.get("error", f"cannot describe table {table}"),
                    "table": table,
                    "note": "DB introspection fallback attempted but table describe failed",
                },
            })
            continue
        cols = [c["name"] for c in desc.get("columns", [])]

        # Build a safe SELECT with all columns
        if not cols:
            continue

        # Detect date range from query for calendar tables
        where_clause = ""
        if "calendar_events" in table:
            date_from = None
            date_to = None
            m = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', question)
            if m:
                date_from = f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
            m2 = re.search(r'od\s+(\d{1,2}[./]\d{1,2}[./]\d{4})', ql)
            m3 = re.search(r'do\s+(\d{1,2}[./]\d{1,2}[./]\d{4})', ql)
            if m2:
                parts = re.split(r'[./]', m2.group(1))
                if len(parts) == 3:
                    date_from = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            if m3:
                parts = re.split(r'[./]', m3.group(1))
                if len(parts) == 3:
                    date_to = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

            if date_from and date_to and "date_start" in cols:
                where_clause = f" WHERE date_start >= '{date_from}' AND date_start <= '{date_to}'"
            elif date_from and "date_start" in cols:
                where_clause = f" WHERE date_start >= '{date_from}'"

        cols_sql = ", ".join(cols[:20])
        sql = f"SELECT {cols_sql} FROM \"{table}\"{where_clause} ORDER BY 1 LIMIT 50"

        select_args = {"sql": sql}
        results.append({
            "reader": "db_select_readonly",
            "category": "db",
            "status": "OK",
            "data": {"args": select_args, "query": "DB introspection fallback — safe SELECT"},
        })
        select_result = db_select_readonly(select_args)
        if select_result.get("status") == "OK":
            rrows = select_result.get("rows", [])
            note = f"db_introspection_fallback for {table}: {len(rrows)} rows via db_select_readonly"
            results.append({
                "reader": f"db_introspection_fallback.{table}",
                "category": "db",
                "status": "OK",
                "data": {
                    "status": "OK",
                    "note": note,
                    "table": table,
                    "columns_used": cols[:20],
                    "rows": rrows,
                    "row_count": len(rrows),
                    "fallback_from": "reader_error",
                },
            })
        else:
            results.append({
                "reader": f"db_introspection_fallback.{table}",
                "category": "db",
                "status": "error",
                "data": select_result,
            })

    return results if results else None


def _try_capability_fallback(plan: dict[str, Any], ctx: dict[str, Any], question: str) -> dict[str, Any] | None:
    """When LLM-chosen tools fail, try capability matching the intent."""
    from qbot3.errors import OK, ERROR
    intent = plan.get("intent", "")
    if not intent:
        return None
    try:
        from qbot3.capabilities import find_capability_by_intent
        cap = find_capability_by_intent(intent)
        if not cap or not cap.is_active():
            return None
        context = {
            "question": question,
            "date": ctx.get("date", ""),
            "timezone": ctx.get("timezone", "Europe/Warsaw"),
        }
        result = cap.run(context)
        if not isinstance(result, dict):
            return None
        data = result.get("data", result)
        status = result.get("status", OK)
        answer = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)[:300]
        cap_plan = dict(plan)
        cap_plan["tools_to_call"] = list(plan.get("tools_to_call", [])) + [f"capability:{cap.definition.name}"]
        return _build_response(ctx, status=status, answer=answer,
                              plan=cap_plan,
                              tool_results=[{"reader": f"capability:{cap.definition.name}",
                                            "category": "capability",
                                            "status": "OK", "data": data}],
                              limitations=["capability_fallback"],
                              confidence="high")
    except ImportError:
        return None
    except Exception as exc:
        return _build_response(ctx, status=ERROR, answer=f"Capability fallback error: {str(exc)[:200]}",
                              limitations=["capability_error"])


def _try_execute_capability(intent: str, ctx: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Try to execute an internal capability for the given intent."""
    from qbot3.errors import OK, ERROR
    try:
        from qbot3.capabilities import find_capability_by_intent
        cap = find_capability_by_intent(intent)
        if not cap or not cap.is_active():
            return None
        context = {
            "question": question,
            "date": ctx.get("date", ""),
            "timezone": ctx.get("timezone", "Europe/Warsaw"),
        }
        result = cap.run(context)
        if not isinstance(result, dict):
            return None
        data = result.get("data", result)
        status = result.get("status", OK)
        answer = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)[:300]
        return _build_response(ctx, status=status, answer=answer,
                              limitations=["capability_executed"] if status != OK else [],
                              confidence="high")
    except ImportError:
        return None
    except Exception as exc:
        return _build_response(ctx, status=ERROR, answer=f"Capability error: {str(exc)[:200]}",
                              limitations=["capability_error"])


def _handle_write(ctx: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    write_action = plan.get("write_action", "")
    write_payload = dict(plan.get("write_payload", {}))
    q = ctx.get("question", "")
    if not write_payload.get("date"):
        d, _ = _resolve_date(q)
        write_payload["date"] = d.isoformat()
    idem_key = _idempotency_key(write_action[:8] if write_action else "wr", q)
    action_draft = _build_action_draft(write_action, write_payload, idem_key, q)
    answer_parts = ["Przygotowałem draft:"]
    for k, v in write_payload.items():
        answer_parts.append(f"- {k}: {v}")
    answer_parts.append("Zapis wymaga potwierdzenia przez qbot.action_execute.")

    trace = {
        "original_query": ctx.get("question", ""),
        "canonical_task": plan["intent"],
        "date_context": {"date": ctx.get("date"), "timezone": ctx.get("timezone")},
        "tools_called": plan.get("tools_to_call", []),
        "result_type": "draft",
        "write_action": write_action,
        "confidence": "high",
    }
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "query": ctx.get("question", ""),
        "plan": {"intent": plan["intent"], "mode": plan["mode"], "tools": plan.get("tools_to_call", [])},
        "trace": trace,
        "orchestrator": {"enabled": True, "name": "Albert", "version": "qbot3", "stage": "draft", "fallback_used": False},
        "status": "draft",
        "answer": "\n".join(answer_parts),
        "action_draft": action_draft,
        "missing_fields": [],
        "tables": [],
        "date_resolution": {"date": ctx.get("date"), "timezone": ctx.get("timezone")},
    }


def _build_action_draft(
    action_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    question: str,
) -> dict[str, Any]:
    """Standardized action_draft format per P4 contract."""
    return {
        "action_type": action_type,
        "payload": dict(payload),
        "requires_confirm": True,
        "idempotency_key_suggestion": idempotency_key,
        "dry_run_available": True,
        "safety_notes": [f"write action: {action_type}"],
        "human_summary": f"{action_type}: {json.dumps(payload, ensure_ascii=False)[:200]}",
    }


def _log(
    req_id: str, provider: str, model: str, mode: str, intent: str,
    tools_planned: list[str], tools_called: list[str],
    fallback_used: bool, status: str, error_stage: str, duration_ms: int,
) -> None:
    try:
        log_request(req_id, provider, model, mode, intent, tools_planned,
                    tools_called, fallback_used, status, error_stage, duration_ms)
    except Exception:
        pass


def _build_response(ctx: dict[str, Any], *, status: str, answer: str,
                    plan: dict[str, Any] | None = None, tool_results: list[dict[str, Any]] | None = None,
                    missing: list[str] | None = None, limitations: list[str] | None = None,
                    final_llm: dict | None = None, confidence: str = "medium") -> dict[str, Any]:
    if missing is None:
        missing = []
    if limitations is None:
        limitations = []
    if tool_results is None:
        tool_results = []
    missing_final = list(missing)
    limitations_final = list(limitations)

    for item in tool_results:
        data = item.get("data", {})
        if isinstance(data.get("missing_fields"), list):
            missing_final.extend(data["missing_fields"])
        if isinstance(data.get("limitations"), list):
            limitations_final.extend(data["limitations"])

    trace = {
        "original_query": ctx.get("question", ""),
        "canonical_task": plan["intent"] if plan else "",
        "date_context": {"date": ctx.get("date"), "timezone": ctx.get("timezone")},
        "tools_called": plan.get("tools_to_call", []) if plan else [],
        "result_type": status,
        "write_action": plan.get("write_action") if plan else None,
        "confidence": confidence,
    }
    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "query": ctx.get("question", ""),
        "plan": dict(plan) if plan else {},
        "trace": trace,
        "orchestrator": {"enabled": True, "name": "Albert", "version": "qbot3", "stage": "final", "fallback_used": False},
        "answer": answer,
        "status": status,
        "confidence": confidence,
        "missing_fields": list(dict.fromkeys(missing_final)),
        "limitations": list(dict.fromkeys(limitations_final)),
        "date_resolution": {"date": ctx.get("date"), "timezone": ctx.get("timezone")},
        "final_llm": final_llm or {},
        "tool_results": tool_results,
    }
