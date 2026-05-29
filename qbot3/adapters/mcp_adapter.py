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
            "description": "JEDYNE wejście do QBot3. Przekaż oryginalne pytanie użytkownika bez modyfikacji. NIE dopisuj action_type, writer name, payload schema. Albert sam rozpoznaje intent, wybiera narzędzia i buduje odpowiedź. Dla zapisów zwraca action_draft — wywołaj qbot.action_execute aby wykonać.",
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
                    "action_type": {"type": "string", "enum": ["nutrition_log_add", "calendar_event_add", "reminder_add", "qbot_doc_append"]},
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
        return _result(req_id, {"tool": "qbot.action_execute", "status": "OK", "dry_run": True, "action_type": action_type, "idempotency_key": idem_key, "note": "dry_run — no actual write performed"})

    if action_type == "qbot_doc_append":
        result = exec_doc_append(action_type, payload, idem_key)
        return _result(req_id, {"tool": "qbot.action_execute", **result})

    return _result(req_id, {"tool": "qbot.action_execute", "status": "OK", "action_type": action_type, "idempotency_key": idem_key, "note": "write executed (mock for non-doc actions)"})


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
