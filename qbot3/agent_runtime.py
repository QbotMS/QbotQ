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

    # ── Plan validation ──────────────────────────────────────────────────────
    validation = validate_plan(plan)
    if validation.get("status") == CAPABILITY_MISSING:
        intent = plan.get("intent", "")
        answer = f"Brak capability dla '{intent}'. "
        proposal = validation.get("capability_proposal", {})
        if proposal.get("capability_found"):
            answer += f"Znaleziono capability '{proposal.get('needed_capability', '')}', ale nie jest aktywna."
        else:
            answer += f"Propozycja: utwórz capability '{intent.replace(' ', '_')}'."
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

    if plan["mode"] == "read_only" and not plan.get("tools_to_call"):
        answer_result = llm.answer(ctx, plan, [])
        result = _build_response(
            ctx,
            status=answer_result.status,
            answer=answer_result.answer,
            plan=plan,
            tool_results=[],
            missing=answer_result.missing_fields,
            limitations=answer_result.limitations,
            final_llm=answer_result.raw,
            confidence=answer_result.confidence,
        )
        _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
             [], [], False, answer_result.status, "", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    tool_results = _execute_tools(plan["tools_to_call"], plan.get("parameters", {}), question)

    if not tool_results:
        result = _build_response(ctx, status=ERROR, answer="Nie znaleziono narzędzi do wykonania.", plan=plan, limitations=["no_tools_executed"])
        _log(req_id, provider_name, model_name, plan.get("mode", "read_only"), plan.get("intent", ""),
             plan.get("tools_to_call", []), [], False, ERROR, "tool_execution", timer.elapsed_ms())
        result["request_id"] = req_id
        return result

    if _all_tools_empty(tool_results):
        pass

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
    Only uses tables confirmed by db_schema_list or known domain maps.
    Never guesses table names from arbitrary words in queries or descriptions.
    """
    from qbot3.db_introspection import db_table_describe, db_select_readonly, db_schema_list
    from qbot3.tool_registry import lookup
    import re

    ql = question.lower()
    results = []

    # 1. Determine which tables might be relevant from the query
    #    Only known domain → table mappings, no guessing.
    domain_table_map: list[tuple[list[str], str, str]] = [
        (["kalendarz", "event", "wydarzen", "calendar", "toskan", "bikepack", "qcal"], "public", "calendar_events"),
        (["jadł", "jedzeni", "posiłk", "meal", "nutrition", "kalor"], "public", "meal_logs"),
        (["jadł", "jedzeni", "posiłk", "meal", "nutrition", "kalor"], "public", "meal_log_items"),
        (["reminder", "przypomn"], "public", "reminders"),
        (["xert", "readiness", "ftp", "training", "fitness"], "public", "training_sessions"),
        (["xert", "readiness", "ftp", "training", "fitness"], "public", "xert_metrics"),
    ]
    table_candidates: list[tuple[str, str]] = []
    seen = set()
    for keywords, schema, table in domain_table_map:
        if any(k in ql for k in keywords):
            key = (schema, table)
            if key not in seen:
                seen.add(key)
                table_candidates.append(key)

    if not table_candidates:
        # Map known tool names to database tables
        tool_to_table: dict[str, tuple[str, str]] = {
            "qcal_events_range": ("public", "calendar_events"),
            "qcal_events_upcoming": ("public", "calendar_events"),
            "qcal_reminders_upcoming": ("public", "reminders"),
            "nutrition_day_summary": ("public", "meal_logs"),
            "nutrition_log_add": ("public", "meal_logs"),
            "xert_readiness": ("public", "training_sessions"),
            "xert_config": ("public", "xert_metrics"),
        }
        for tool_name in plan.get("tools_to_call", []):
            if tool_name in tool_to_table:
                key = tool_to_table[tool_name]
                if key not in seen:
                    seen.add(key)
                    table_candidates.append(key)

    if not table_candidates:
        return None

    # 1b. Verify candidates against actual DB schema — only keep real tables
    schema_result = db_schema_list()
    real_tables: set[str] = set()
    if schema_result.get("status") == "OK":
        for schema_name, tables_list in schema_result.get("schemas", {}).items():
            for t in tables_list:
                real_tables.add(f"{schema_name}.{t}")
    table_candidates = [
        (s, t) for s, t in table_candidates
        if f"{s}.{t}" in real_tables
    ]

    if not table_candidates:
        # No real tables found — return a clear diagnostic instead of guessing
        xert_keywords = ["xert", "readiness", "ftp", "training", "fitness"]
        if any(k in ql for k in xert_keywords):
            results.append({
                "reader": "db_introspection_fallback",
                "category": "db",
                "status": "DATA_MISSING",
                "data": {
                    "status": "DATA_MISSING",
                    "note": "No Xert tables found in DB schema. Expected tables: training_sessions, xert_metrics.",
                    "tables_available": sorted(real_tables) if real_tables else ["(none — schema check failed or empty)"],
                },
            })
            return results
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
