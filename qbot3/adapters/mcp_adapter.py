#!/usr/bin/env python3
"""QBot3 MCP Adapter — exactly 2 public tools.

No hidden tool selection, no procedural orchestration.
qbot.query → agent_runtime.orchestrate_query()
qbot.action_execute → safety.validate() + exec
"""

from __future__ import annotations

import json
from typing import Any

from qbot3.agent_runtime import orchestrate_query
from qbot3.safety import validate, exec_doc_append


def handle_qbot3_mcp(payload: dict[str, Any]) -> dict[str, Any]:
    method = payload.get("method", "")
    req_id = payload.get("id")

    if method == "tools/list":
        return _list_tools(req_id)
    if method == "tools/call":
        return _call_tool(req_id, payload.get("params", {}))
    return _error(req_id, -32601, f"Method not found: {method}")


def _list_tools(req_id: Any) -> dict[str, Any]:
    tools = [
        {
            "name": "qbot.query",
            "description": "JEDYNE wejście do QBot3. Przekaż oryginalne pytanie użytkownika bez modyfikacji. NIE dopisuj action_type, writer name, payload schema. Albert sam rozpoznaje intent, wybiera narzędzia i buduje odpowiedź. Domyślny odczyt danych to transparentny DB/connector read-only; snapshoty/dashboardy tylko dla wyraźnych pytań o dzisiejszy dashboard albo podsumowanie dnia. Dla zapisów zwraca action_draft — wywołaj qbot.action_execute aby wykonać.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Oryginalne pytanie użytkownika — NIE modyfikuj"},
                    "context": {"type": "string", "description": "Optional JSON: source, timezone, date"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "qbot.action_execute",
            "description": "WYKONAJ action_draft z qbot.query. WYMAGA: action_type z allowlisty, payload_json, idempotency_key, confirm=true.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string", "enum": ["nutrition_log_add", "calendar_event_add", "reminder_add", "planning_fact_add", "memory_confirmed_fact_add", "qbot_doc_append"]},
                    "payload_json": {"type": "object"},
                    "idempotency_key": {"type": "string"},
                    "confirm": {"type": "boolean"},
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["action_type", "payload_json", "idempotency_key", "confirm"],
            },
        },
    ]
    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}


def _call_tool(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name", "")
    args = params.get("arguments", {})

    if name == "qbot.query":
        query = str(args.get("query", "")).strip()
        if not query:
            return _result(req_id, {"error": "empty query"})
        result = orchestrate_query(query, context=args.get("context", ""))
        from qbot3.response_normalizer import normalize_response
        result = normalize_response(result)
        return _result(req_id, result)

    if name == "qbot.action_execute":
        return _handle_action_execute(req_id, args)

    return _error(req_id, -32602, f"Tool not found: {name}")


def _handle_action_execute(req_id: Any, args: dict[str, Any]) -> dict[str, Any]:
    action_type = str(args.get("action_type", "")).strip()
    payload = args.get("payload_json", {})
    idem_key = str(args.get("idempotency_key", "")).strip()
    confirm = args.get("confirm", False)
    dry_run = args.get("dry_run", False)

    if not confirm:
        return _result(req_id, {"tool": "qbot.action_execute", "status": "BLOCKED", "error": "confirm must be true"})

    validation = validate(action_type, payload, idem_key, dry_run=dry_run)
    if validation["status"] != "OK":
        return _result(req_id, {"tool": "qbot.action_execute", **validation})

    if validation.get("dry_run"):
        return _result(req_id, {
            "tool": "qbot.action_execute", "status": "DRY_RUN_OK",
            "execution_mode": "dry_run", "write_committed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "note": "dry_run — walidacja OK, żaden zapis nie został wykonany",
        })

    # ── Real execute ──────────────────────────────────────────────────
    if action_type == "qbot_doc_append":
        result = exec_doc_append(action_type, payload, idem_key)
        real_write = result.get("status") == "OK"
        return _result(req_id, {
            "tool": "qbot.action_execute",
            "status": "OK" if real_write else result.get("status", "ERROR"),
            "execution_mode": "real_write" if real_write else "error",
            "write_committed": real_write,
            **result,
        })

    # Non-doc write actions — try real writer
    if action_type == "nutrition_log_add":
        write_result = _execute_nutrition_write(action_type, payload, idem_key)
        return _result(req_id, write_result)

    if action_type in ("calendar_event_add", "reminder_add", "planning_fact_add", "memory_confirmed_fact_add"):
        return _result(req_id, {
            "tool": "qbot.action_execute", "status": "WRITE_NOT_AVAILABLE",
            "execution_mode": "mock", "write_committed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "note": f"{action_type} nie ma jeszcze realnego writera w QBot3. "
                     "Draft został przygotowany, ale wykonanie wymaga implementacji backendu.",
        })

    return _result(req_id, {
        "tool": "qbot.action_execute", "status": "BLOCKED",
        "execution_mode": "unknown", "write_committed": False,
        "action_type": action_type, "error": f"Unknown action_type: {action_type}",
    })


def _execute_nutrition_write(action_type: str, payload: dict[str, Any], idem_key: str) -> dict[str, Any]:
    """Execute nutrition log write via existing legacy writer."""
    try:
        from qbot_nutrition_tools import _tool_qbot_nutrition_intake_log
        from datetime import date, datetime
        meal_name = payload.get("meal_name", "")
        if not meal_name:
            return {"tool": "qbot.action_execute", "status": "BLOCKED",
                    "execution_mode": "error", "write_committed": False,
                    "error": "meal_name is required", "action_type": action_type, "idempotency_key": idem_key}

        items = [{
            "food": meal_name,
            "food_name": meal_name,
            "amount": payload.get("amount", 0) or payload.get("quantity", 0) or 1,
            "unit": payload.get("unit", "szt"),
            "kcal": payload.get("kcal_total"),
            "carbs_g": payload.get("carbs_g"),
            "protein_g": payload.get("protein_g"),
            "fat_g": payload.get("fat_g"),
            "sodium_mg": payload.get("salt_g"),
        }]

        result = _tool_qbot_nutrition_intake_log({
            "text": meal_name,
            "meal_type": "meal",
            "note": payload.get("description", ""),
            "context": f"qbot3 action_execute {action_type}",
        })

        if result.get("status") == "OK" and result.get("meal_id"):
            return {
                "tool": "qbot.action_execute", "status": "OK",
                "execution_mode": "real_write", "write_committed": True,
                "db_inserted": True, "inserted_id": result["meal_id"],
                "action_type": action_type, "idempotency_key": idem_key,
                "meal_log_id": result["meal_id"],
                "storage_backend": "postgresql (meal_logs + meal_log_items via qbot_nutrition_db.meal_log_create)",
                "note": "Posiłek zapisany przez qbot_nutrition_tools._tool_qbot_nutrition_intake_log",
            }

        return {
            "tool": "qbot.action_execute", "status": "WRITE_ERROR",
            "execution_mode": "error", "write_committed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "error": f"Writer returned: {result.get('status')} — {result.get('error', 'unknown')}",
        }

    except Exception as exc:
        return {
            "tool": "qbot.action_execute", "status": "WRITE_ERROR",
            "execution_mode": "error", "write_committed": False,
            "action_type": action_type, "idempotency_key": idem_key,
            "error": str(exc)[:500],
        }


def _result(req_id: Any, data: dict) -> dict[str, Any]:
    normalized = json.loads(json.dumps(data, ensure_ascii=False, default=str))
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(normalized, ensure_ascii=False)}],
            "structuredContent": normalized,
        },
    }


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
