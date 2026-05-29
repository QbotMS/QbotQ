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

    # Write pre-router: intercepts write intents BEFORE read pre-router
    # Write has priority — if matched, skip read pre-router entirely
    ctx = build_context(question)
    write_routed = _deterministic_write_pre_route(question)
    if write_routed:
        wc = write_routed.get("_write_classification", "")
        if wc == "DESTRUCTIVE_WRITE":
            result = _build_response(ctx, status="BLOCKED", answer=write_routed.get("_write_message", "Destrukcyjne operacje zablokowane."),
                                    limitations=["destructive_blocked"])
            result["request_id"] = req_id
            return result
        if write_routed.get("_pre_routed_write"):
            draft = write_routed.get("_write_action_draft")
            if draft:
                answer_parts = [f"Przygotowałem draft: {draft['human_summary']}"]
                if draft.get("missing_fields"):
                    answer_parts.append(draft.get("clarification_question", ""))
                else:
                    answer_parts.append("Zapis wymaga potwierdzenia przez qbot.action_execute.")
                human_answer = " ".join(answer_parts)
                result = _build_response(ctx, status="draft", answer=human_answer,
                                        plan={"intent": write_routed.get("intent", ""), "mode": "write",
                                              "tools": []},
                                        limitations=["write_draft"])
                result["action_draft"] = draft
                result["human_answer"] = human_answer
                result["request_id"] = req_id
                return result
            result = _build_response(ctx, status="CAPABILITY_MISSING", answer=write_routed.get("answer", "Nieobsługiwany typ akcji."),
                                    limitations=["write_draft"])
            result["request_id"] = req_id
            return result

    # Read pre-router: intercepts obvious domain matches before LLM planner
    pre_routed = _deterministic_pre_route(question)
    if pre_routed:
        result = _execute_pre_routed(pre_routed, question, req_id, provider_name, model_name, timer)
        result["request_id"] = req_id
        return result

    llm = get_llm_provider()
    ctx = build_context(question)
    tools_desc = tool_descriptions()

    plan_result = llm.plan(ctx, tools_desc, question)
    plan = _normalize_plan(plan_result)

    if not plan:
        result = _build_response(ctx, status=ERROR, answer="Nie mogę zaplanować zapytania.", limitations=["invalid_plan"])
        _log(req_id, provider_name, model_name, "unknown", "", [], [], False, ERROR, "plan_generation", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    validation = validate_plan(plan)
    if validation.get("status") == CAPABILITY_MISSING:
        # Try to use internal capability
        cap_result = _try_execute_capability(plan.get("intent", ""), ctx, question)
        if cap_result:
            result = cap_result
            _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
                 plan.get("tools_to_call", []), [f"capability:{plan.get('intent', '')}"], False,
                 result.get("status", OK), "", timer.elapsed_ms())
            result["request_id"] = req_id
            return result
        # No capability or not active — return proposal
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
        # Try capability fallback before giving up
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

    # Check if all tool results are effectively empty/no_data — capability fallback
    if _all_tools_empty(tool_results):
        cap_result = _try_capability_fallback(plan, ctx, question)
        if cap_result:
            result = cap_result
            _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
                 plan.get("tools_to_call", []), [f"capability:{plan.get('intent', '')}"],
                 False, result.get("status", OK), "", timer.elapsed_ms())
            result["request_id"] = req_id
            return result

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


# ── Deterministic pre-router ───────────────────────────────────────────
# Runs BEFORE the LLM planner for obvious domain matches.
# LLM-first principle preserved: only intercepts well-defined domains
# where the LLM historically routes incorrectly.

_PRE_ROUTE_DOMAINS: list[tuple[list[str], str, str]] = [
    # (keywords, intent, tool_name)
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

# Write pre-router — intercepts write intents before LLM planner
_WRITE_PRE_ROUTE_KEYWORDS: list[tuple[list[str], str]] = [
    (["dodaj posiłek", "dodaj jedzenie", "dodaj do spożycia", "zjedz", "jadłem", "nutrition_log_add"], "nutrition_log_add"),
    (["dodaj event", "dodaj wydarzenie", "zaplanuj event", "zapisz do kalendarza", "dodaj do kalendarza", "calendar_event_add", "zapisz event", "dodaj do kalendarza"], "calendar_event_add"),
    (["przypomnij", "przypomnij mi", "reminder", "dodaj przypomnienie", "reminder_add"], "reminder_add"),
    (["zapamiętaj fakt", "zapamiętaj", "zapisz fakt", "planning_fact_add", "notuj", "zanotuj"], "planning_fact_add"),
    (["usuń wszystko", "usuń wszystkie", "wyczyść", "delete all"], "DESTRUCTIVE"),
]


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
    """
    from qbot3.write_router import (
        extract_nutrition_slots, extract_calendar_slots,
        extract_reminder_slots, extract_planning_fact_slots,
    )

    payload: dict[str, Any] = {}

    if action_type == "nutrition_log_add":
        payload = extract_nutrition_slots(question)
        # If no food name extracted, add to payload as missing
        if "meal_name" not in payload and "amount" not in payload:
            quoted = re.findall(r'"([^"]+)"', question)
            if quoted:
                payload["meal_name"] = quoted[0]

    elif action_type in ("calendar_event_add",):
        payload = extract_calendar_slots(question)

    elif action_type in ("reminder_add",):
        payload = extract_reminder_slots(question)

    elif action_type in ("planning_fact_add", "memory_confirmed_fact_add"):
        payload = extract_planning_fact_slots(question)

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
        results.append({"reader": name, "category": spec.get("category", ""), "status": "OK", "data": result})
    return results


def _all_tools_empty(tool_results: list[dict[str, Any]]) -> bool:
    """Check if all tool results are effectively empty (no useful data).

    A result is 'empty' if:
      - status is DATA_MISSING/CONNECTOR_MISSING/NO_DATA/NOT_IMPLEMENTED, or
      - the dict has no meaningful keys beyond status, or
      - the result is None/empty string.
    """
    if not tool_results:
        return True
    empty_count = 0
    for tr in tool_results:
        data = tr.get("data", {})
        if not isinstance(data, dict):
            empty_count += 1
            continue
        status = data.get("status", "")
        if status in ("DATA_MISSING", "CONNECTOR_MISSING", "NO_DATA", "NOT_IMPLEMENTED"):
            empty_count += 1
            continue
        # Has explicit error
        if data.get("error"):
            empty_count += 1
            continue
        # Check if it has actual data content beyond status/error
        meaningful_keys = [k for k in data if k not in ("status", "tool", "safety_class")]
        if not meaningful_keys:
            empty_count += 1
            continue
        # Has at least some data — not empty
        return False
    return empty_count == len(tool_results)


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
        "plan": {"intent": plan["intent"] if plan else "", "mode": plan["mode"] if plan else "read_only", "tools": plan.get("tools_to_call", []) if plan else []},
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
