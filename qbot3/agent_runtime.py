#!/usr/bin/env python3
"""QBot3 Agent Runtime (Albert) — context → plan → execute → answer.

Zero legacy router imports. All decisions through LLM provider interface.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

from qbot3.llm import get_llm_provider
from qbot3.tool_registry import lookup, tool_descriptions, _idempotency_key, _resolve_date
from qbot3.context_builder import build_context
from qbot3.plan_validator import validate_plan
from qbot3.observability import log_request, Timer, request_id as rid


def orchestrate_query(question: str, context: str = "", max_rows: int = 500) -> dict[str, Any]:
    _check_qbot3_enabled()
    from qbot3.errors import OK, ERROR, PLAN_INVALID, PROVIDER_ERROR

    timer = Timer()
    timer.start()
    req_id = rid()
    provider_name = os.getenv("ALBERT_LLM_PROVIDER", "openai")
    model_name = os.getenv("ALBERT_LLM_MODEL", "")

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
        result = _build_response(ctx, status=ERROR, answer="Nie znaleziono narzędzi do wykonania.", plan=plan, limitations=["no_tools_executed"])
        _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, ERROR, "tool_execution", timer.elapsed_ms())
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
