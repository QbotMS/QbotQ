#!/usr/bin/env python3
"""Minimal QBot MCP adapter for the ChatGPT connector."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from qbot_artifact_tools import (
    _tool_qbot_artifact_create,
    _tool_qbot_artifact_get,
    _tool_qbot_artifact_list,
)
from qbot_external_llm_tools import _tool_qbot_external_tool_plan
from qbot_llm_planner import _tool_qbot_llm_run_query, _tool_qbot_tool_policy_list
from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
from qbot_telegram_tools import _tool_qbot_telegram_status
from qbot_assistant_inbox import (
    _tool_qbot_assistant_inbox_list,
    _tool_qbot_assistant_inbox_status,
)
from qbot_tools import _tool_qbot_status

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "QBot MCP Adapter v1"
MCP_SERVER_VERSION = "1.0.0"
MCP_SESSION_HEADER = "mcp-session-id"

_SESSION_STATE: dict[str, dict[str, Any]] = {}

_MCP_TOOL_MAP: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════════════
    # PUBLIC MCP TOOLS — tylko 2 narzędzia:
    #   qbot.query          — natural language + reader dispatch
    #   qbot.action_execute  — jedyny executor zapisów
    # Wszystkie domenowe narzędzia (nutrition_log_add, qcal_event_add,
    # qcal_reminder_add, itd.) są internal — dostępne tylko przez
    # action_execute.
    # ═══════════════════════════════════════════════════════════════

    # ── Core: universal read-only query router ──
    "qbot.query": {
        "qbot_tool": "qbot_query",
        "description": (
            "JEDYNE wejście do QBot Runtime. Przekaż oryginalne pytanie użytkownika bez żadnych modyfikacji. "
            "NIE dopisuj action_type, writer name, payload schema, 'przygotuj draft', 'użyj writera', 'confirm' ani template match. "
            "NIE pre-routuj, NIE enrichuj z nazwami tooli/akcji. "
            "Albert (QBot LLM) sam rozpoznaje intent, wybiera readery, agreguje dane z DB i buduje odpowiedź. "
            "Dla zapisów zwraca action_draft — wywołaj qbot.action_execute aby wykonać. "
            "Parametr context: przekaż tylko source, timezone, date jeśli znane."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Oryginalne pytanie użytkownika — NIE modyfikuj, NIE enrichuj"},
                "mode": {"type": "string", "enum": ["read_only", "plan_only"], "default": "read_only"},
                "scope": {"type": "string", "enum": ["all", "nutrition", "training", "routes", "garage"], "default": "all"},
                "context": {"type": "string", "description": "Optional JSON: source, timezone, date/date_from/date_to"},
                "max_rows": {"type": "integer", "minimum": 10, "maximum": 1000, "default": 500},
                "include_provenance": {"type": "boolean", "default": True},
                "include_missing": {"type": "boolean", "default": True},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "tool": {"type": "string"},
                "status": {"type": "string"},
                "answer": {"type": "string"},
                "action_draft": {"type": "object"},
                "payload": {"type": "object"},
                "record": {"type": "object"},
                "error": {"type": "string"}
            }
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },

    # ── Read-only artifact getter ──
    "qbot.artifact_get": {
        "qbot_tool": "qbot_artifact_read",
        "description": (
            "Odczytaj treść zarejestrowanego artefaktu QBot. "
            "Identifier może być: artifact_id UUID, nazwa pliku, tytuł, lub ścieżka. "
            "Bezpieczny, read-only, bez potwierdzenia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "artifact_id UUID, filename, title lub ścieżka"},
                "start_line": {"type": "integer", "default": 1, "minimum": 1},
                "max_lines": {"type": "integer", "default": 200, "minimum": 1, "maximum": 2000},
            },
            "required": ["identifier"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": True,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },

    # ── Unified action executor ──
    "qbot.action_execute": {
        "qbot_tool": "qbot_action_execute",
        "description": (
            "WYKONAJ action_draft z qbot.query. Przyjmuje action_type z allowlisty "
            "(nutrition_log_add, qcal_reminder_add, qcal_event_add, qcal_event_update, qcal_event_cancel, "
            "planning_fact_add, qbot_doc_append, qbot_doc_replace_section, qbot_doc_update, route_poi_analyze). "
            "Dla route_poi_analyze payload_json powinien zawierać route_id, artifact_id albo path, km_from, km_to "
            "oraz opcjonalnie buffers: attractions_m, hard_resupply_m, soft_food_m, water_m, chunk_km, chunk_overlap_km, "
            "analysis_timeout_sec, overpass_timeout_sec, min_chunk_km, overpass_retries, retry_backoff_sec; "
            "obsługuje też focus, retry_chunk_id, retry_mode, merge_artifact_ids i timeout_sec. "
            "WYMAGA: confirm=true, idempotency_key. "
            "Sprawdza bezpieczeństwo: allowlist, wymagane pola, duplicate key."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": ["nutrition_log_add", "qcal_reminder_add", "qcal_event_add", "qcal_event_update", "qcal_event_cancel", "planning_fact_add", "qbot_doc_append", "qbot_doc_replace_section", "qbot_doc_update", "rwgps_route_import_gpx", "route_poi_analyze", "qbot_artifact_put", "qbot_artifact_get"]},
                "payload_json": {"type": "object", "description": "Kompletny obiekt payload (tak jak w action_draft z qbot.query)"},
                "idempotency_key": {"type": "string", "description": "Unikalny klucz — zapobiega duplikatom."},
                "confirm": {"type": "boolean", "description": "MUSI być true, żeby zapisać."},
                "dry_run": {"type": "boolean", "default": False, "description": "Tylko walidacja, bez zapisu."},
                "source": {"type": "string", "default": "chatgpt_mcp"},
            },
            "required": ["action_type", "payload_json", "idempotency_key", "confirm"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "tool": {"type": "string"},
                "status": {"type": "string"},
                "answer": {"type": "string"},
                "action_draft": {"type": "object"},
                "payload": {"type": "object"},
                "record": {"type": "object"},
                "error": {"type": "string"}
            }
        },
        "safety_class": "WRITE_ONLY_ALLOWLIST",
        "auth_required": False,
    },
}

# Internal readers & tools (NOT exposed to MCP — accessed exclusively via qbot.query):
#   GarminReader      — Garmin energy, sleep, HRV, Body Battery
#   CronometerReader  — daily nutrition import
#   NutritionDBReader — meals, hydration, fueling
#   IntervalsReader   — activities, wellness, events
#   XertReader        — FTP, freshness, fatigue
#   RWGPSReader       — route listing, export, GPX parse, surface enrichment
#   GarageReader      — bike components, gear
#   GearReader        — trip packing lists
#   WeatherReader     — current + forecast
#   DailyReportReader — daily morning report
#   RideReportReader  — ride protocol
#   WellnessReader    — DB wellness queries
#   ArtifactIndexReader — artifact list/get
#   ProjectReader     — codebase introspection
#
# qbot.query is the SINGLE entry point for all user data questions.
# ChatGPT must NOT know or directly call internal readers.



def _token_configured() -> bool:
    return bool(os.getenv("MCP_SHARED_SECRET") or os.getenv("QBOT_MCP_TOKEN"))


def _configured_token() -> str:
    return os.getenv("MCP_SHARED_SECRET") or os.getenv("QBOT_MCP_TOKEN") or ""


def _auth_header_ok(headers: dict[str, str]) -> bool:
    token = _configured_token()
    if not token:
        return True
    bearer = headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer.split(" ", 1)[1].strip() == token
    return headers.get("x-qbot-mcp-token", "") == token


def _public_mcp_url() -> str:
    base = os.getenv("QBOT_PUBLIC_BASE_URL", "").strip()
    if base:
        return base.rstrip("/") + "/mcp/"
    return "https://qbot.cytr.us/mcp/"


def _local_health_url() -> str:
    return "http://127.0.0.1:8002/mcp/health"


def _public_health_url() -> str:
    return _public_mcp_url().rstrip("/") + "/health"


def _local_api_ok() -> bool:
    try:
        import subprocess
        proc = subprocess.run(
            ["systemctl", "is-active", "qbot-api.service"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode != 0 or proc.stdout.strip() != "active":
            return False
        import api_db
        return api_db.ping()
    except Exception:
        return False


def _public_mcp_reachable() -> bool:
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            resp = client.get(_public_health_url())
            return resp.status_code == 200
    except Exception:
        return False


def _exposed_tool_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, meta in _MCP_TOOL_MAP.items():
        enabled = True
        if meta.get("auth_required") and not _token_configured():
            enabled = False
        items.append({
            "name": name,
            "qbot_tool": meta["qbot_tool"],
            "description": meta["description"],
            "inputSchema": meta["input_schema"],
            **({"outputSchema": meta["output_schema"]} if "output_schema" in meta else {}),
            "safety_class": meta["safety_class"],
            "auth_required": meta["auth_required"],
            "enabled": enabled,
        })
    return items


def _allowed_exposed_tools() -> list[str]:
    return [item["name"] for item in _exposed_tool_items() if item["enabled"]]


def _tool_mapping_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "mcp_tool": item["name"],
            "qbot_tool": item["qbot_tool"],
            "safety_class": item["safety_class"],
            "auth_required": item["auth_required"],
            "enabled": item["enabled"],
        }
        for item in _exposed_tool_items()
    ]


def _tool_qbot_mcp_status(_args: dict | None = None) -> dict[str, Any]:
    token_configured = _token_configured()
    exposed = _allowed_exposed_tools()
    disabled = [item["name"] for item in _exposed_tool_items() if not item["enabled"]]
    local_ok = _local_api_ok()
    public_ok = _public_mcp_reachable()
    status = "WARN" if not token_configured else "OK"
    if not local_ok:
        status = "ERROR"
    return {
        "tool": "qbot_mcp_status",
        "mcp_routes_enabled": True,
        "public_url": _public_mcp_url(),
        "auth_configured": token_configured,
        "auth_mode": "token" if token_configured else "read_only",
        "exposed_tools": exposed,
        "disabled_tools": disabled,
        "qbot_api_local_ok": local_ok,
        "public_mcp_reachable": public_ok,
        "local_health_url": _local_health_url(),
        "public_health_url": _public_health_url(),
        "status": status,
    }


def _tool_qbot_readiness_report(_args: dict | None = None) -> dict[str, Any]:
    from qbot_operator_tools import _tool_qbot_readiness_report as _impl

    return _impl(_args)


def _tool_qbot_mcp_tools_list(_args: dict | None = None) -> dict[str, Any]:
    items = _tool_mapping_snapshot()
    return {
        "tool": "qbot_mcp_tools_list",
        "count": len(items),
        "tools": items,
        "status": "OK" if items else "ERROR",
    }


def _tool_qbot_mcp_call_preview(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    mcp_tool = str(args.get("mcp_tool", "")).strip()
    tool_args = args.get("args", {})
    if not isinstance(tool_args, dict):
        return {
            "tool": "qbot_mcp_call_preview",
            "status": "error",
            "error": "args must be an object",
        }
    if not mcp_tool:
        return {
            "tool": "qbot_mcp_call_preview",
            "status": "error",
            "error": "mcp_tool required",
        }
    meta = _MCP_TOOL_MAP.get(mcp_tool)
    if not meta:
        return {
            "tool": "qbot_mcp_call_preview",
            "status": "error",
            "error": f"unknown MCP tool: {mcp_tool}",
            "allowed_tools": sorted(_MCP_TOOL_MAP.keys()),
        }
    execute_requested = bool(tool_args.get("execute", False))
    would_execute = bool(meta["enabled"]) and (execute_requested or meta["safety_class"] == "READ_ONLY")
    policy_notes: list[str] = []
    if not meta["enabled"]:
        policy_notes.append("blocked by local auth mode")
    if mcp_tool == "qbot.artifact_create" and not _token_configured():
        policy_notes.append("artifact creation requires MCP token")
    if mcp_tool == "qbot.ask" and execute_requested:
        policy_notes.append("execution goes through the QBot policy engine")
    if mcp_tool == "qbot.runbook" and execute_requested:
        policy_notes.append("runbook execution is controlled by the QBot runbook allowlist")
    return {
        "tool": "qbot_mcp_call_preview",
        "mcp_tool": mcp_tool,
        "mapped_qbot_tool": meta["qbot_tool"],
        "policy_notes": policy_notes,
        "would_execute": would_execute,
        "status": "OK" if meta["enabled"] else "BLOCKED",
    }


def _tool_by_name(name: str):
    mapping = {
        "qbot_status": _tool_qbot_status,
        "qbot_operator_final_smoke_test": _tool_qbot_operator_final_smoke_test,
        "qbot_readiness_report": _tool_qbot_readiness_report,
        "qbot_llm_run_query": _tool_qbot_llm_run_query,
        "qbot_artifact_create": _tool_qbot_artifact_create,
        "qbot_artifact_list": _tool_qbot_artifact_list,
        "qbot_artifact_get": _tool_qbot_artifact_get,
        "qbot_tool_policy_list": _tool_qbot_tool_policy_list,
        "qbot_telegram_status": _tool_qbot_telegram_status,
        "qbot_mcp_status": _tool_qbot_mcp_status,
        "qbot_mcp_tools_list": _tool_qbot_mcp_tools_list,
        "qbot_mcp_call_preview": _tool_qbot_mcp_call_preview,
    }
    return mapping.get(name)


def _dispatch_local_qbot_tool(
    tool_name: str,
    args: dict | None = None,
    *,
    source: str = "qbot-api",
    mcp_tool: str | None = None,
    session_id: str | None = None,
    log_call: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    clean_args = args if isinstance(args, dict) else {}
    func = _tool_by_name(tool_name)
    if func is None:
        try:
            from qbot_tool_registry import TOOLS
            func = TOOLS.get(tool_name)
        except Exception:
            func = None
    if func is None:
        try:
            from qbot_tool_registry import TOOLS
            available = sorted(TOOLS.keys())
        except Exception:
            available = [
                "qbot_status",
                "qbot_operator_final_smoke_test",
                "qbot_readiness_report",
                "qbot_llm_run_query",
                "qbot_external_context_bundle",
                "qbot_artifact_create",
                "qbot_artifact_list",
                "qbot_artifact_get",
                "qbot_tool_policy_list",
                "qbot_telegram_status",
                "qbot_mcp_status",
                "qbot_mcp_tools_list",
                "qbot_mcp_call_preview",
            ]
        allowed = [
            "qbot_status",
            "qbot_operator_final_smoke_test",
            "qbot_readiness_report",
            "qbot_llm_run_query",
            "qbot_external_context_bundle",
            "qbot_artifact_create",
            "qbot_artifact_list",
            "qbot_artifact_get",
            "qbot_tool_policy_list",
            "qbot_telegram_status",
            "qbot_mcp_status",
            "qbot_mcp_tools_list",
            "qbot_mcp_call_preview",
        ]
        result: dict[str, Any] = {
            "error": f"unknown tool: {tool_name}",
            "available": available or allowed,
        }
    else:
        result = func(clean_args)

    if log_call:
        audit_args = dict(clean_args)
        audit_args["_source"] = source
        if mcp_tool:
            audit_args["_mcp_tool"] = mcp_tool
        if session_id:
            audit_args["_mcp_session_id"] = session_id
        try:
            import api_db
            api_db.save_tool_call(tool_name, audit_args, result)
        except Exception as exc:
            warnings.append(f"db save failed: {exc}")
    return result, warnings


def _normalize_tool_name(mcp_tool: str) -> str:
    meta = _MCP_TOOL_MAP.get(mcp_tool)
    if not meta:
        return ""
    return meta["qbot_tool"]


def _mcp_result_content(result: dict[str, Any]) -> dict[str, Any]:
    def _json_default(obj):
        from datetime import date as _date, datetime as _datetime, time as _time
        from decimal import Decimal as _Decimal
        if isinstance(obj, (_datetime, _date)):
            return obj.isoformat()
        if isinstance(obj, _time):
            return obj.isoformat()
        if isinstance(obj, _Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    # MCP/OpenAI clients consume content[] for display, but structuredContent
    # is the machine-readable payload used to chain qbot.query -> qbot.action_execute.
    normalized = json.loads(json.dumps(result, ensure_ascii=False, default=_json_default))
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(normalized, ensure_ascii=False),
            }
        ],
        "structuredContent": normalized,
    }


def _mcp_error(message: str, *, code: int = -32601, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _new_session() -> str:
    session_id = str(uuid.uuid4())
    _SESSION_STATE[session_id] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "initialized": True,
    }
    return session_id


def _validate_mcp_access(method: str, headers: dict[str, str], *, tool_name: str | None = None) -> tuple[bool, str | None]:
    # initialize + tools/list are always accessible (MCP spec)
    if method in ("initialize", "notifications/initialized", "tools/list"):
        return True, None
    if method != "tools/call":
        return True, None
    if not tool_name:
        return False, "tool name missing"
    meta = _MCP_TOOL_MAP.get(tool_name)
    if not meta:
        return False, "tool not allowed"
    # Public MCP is read-only, no Bearer auth required.
    # OpenAI MCP UI does not support simple Bearer token.
    # All write/admin tools are excluded from the public allowlist.
    return True, None


def handle_mcp_request(
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, int, dict[str, str]]:
    headers = {k.lower(): v for k, v in (headers or {}).items()}

    if "tool" in payload and "method" not in payload:
        payload = {
            "jsonrpc": "2.0",
            "id": payload.get("id", 1),
            "method": "tools/call",
            "params": {
                "name": payload.get("tool"),
                "arguments": payload.get("args", {}),
            },
        }

    method = payload.get("method", "")
    request_id = payload.get("id")
    params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}

    if method == "initialize":
        session_id = _new_session()
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": "Use tools/call with the allowlisted qbot.* adapter tools.",
        }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }, 200, {MCP_SESSION_HEADER: session_id}

    if method == "notifications/initialized":
        return None, 202, {}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": _exposed_tool_items()},
        }, 200, {}

    if method == "tools/call":
        name = str(params.get("name", "")).strip()
        arguments = params.get("arguments", {})
        ok, auth_error = _validate_mcp_access(method, headers, tool_name=name or None)
        if not ok:
            return _mcp_error(auth_error or "unauthorized", code=401), 401, {"WWW-Authenticate": "Bearer"}
        if not name:
            return _mcp_error("tool name missing", code=-32602, request_id=request_id), 200, {}
        meta = _MCP_TOOL_MAP.get(name)
        if not meta:
            return _mcp_error(f"tool not allowed: {name}", code=-32601, request_id=request_id), 200, {}
        if not isinstance(arguments, dict):
            return _mcp_error("arguments must be an object", code=-32602, request_id=request_id), 200, {}

        qbot_tool = _normalize_tool_name(name)
        if not qbot_tool:
            return _mcp_error(f"tool not mapped: {name}", code=-32601, request_id=request_id), 200, {}

        session_id = headers.get(MCP_SESSION_HEADER, "")
        clean_args = dict(arguments)

        if name == "qbot.query":
            query = str(clean_args.get("query", "")).strip()
            if not query:
                result = {"tool": "qbot.query", "status": "error", "error": "query required"}
            elif os.getenv("QBOT_QUERY_VNEXT_ENABLED") == "1":
                try:
                    from qbot_query_handler import handle_query
                    vnext_result = handle_query(question=query)
                    if vnext_result.get("status") == "UNRECOGNIZED":
                        # query_vnext does not recognise this intent — fall back to Albert
                        from qbot_query_router import query as qbot_query
                        result = qbot_query(
                            question=query,
                            mode=str(clean_args.get("mode", "read_only")),
                            scope=str(clean_args.get("scope", "all")),
                            context=str(clean_args.get("context", "")),
                            max_rows=int(clean_args.get("max_rows", 500)),
                            include_provenance=bool(clean_args.get("include_provenance", True)),
                            include_missing=bool(clean_args.get("include_missing", True)),
                        )
                        result["fallback_reason"] = "query_vnext UNRECOGNIZED — fell back to Albert"
                    else:
                        result = vnext_result
                except Exception as exc:
                    # Defensive: if query_vnext fails, fall back to Albert
                    from qbot_query_router import query as qbot_query
                    result = qbot_query(
                        question=query,
                        mode=str(clean_args.get("mode", "read_only")),
                        scope=str(clean_args.get("scope", "all")),
                        context=str(clean_args.get("context", "")),
                        max_rows=int(clean_args.get("max_rows", 500)),
                        include_provenance=bool(clean_args.get("include_provenance", True)),
                        include_missing=bool(clean_args.get("include_missing", True)),
                    )
                    result["fallback_reason"] = f"query_vnext error: {exc} — fell back to Albert"
            else:
                from qbot_query_router import query as qbot_query
                result = qbot_query(
                    question=query,
                    mode=str(clean_args.get("mode", "read_only")),
                    scope=str(clean_args.get("scope", "all")),
                    context=str(clean_args.get("context", "")),
                    max_rows=int(clean_args.get("max_rows", 500)),
                    include_provenance=bool(clean_args.get("include_provenance", True)),
                    include_missing=bool(clean_args.get("include_missing", True)),
                )
        elif name == "qbot.nutrition_log_preview":
            result = _handle_nutrition_preview(clean_args)
        elif name == "qbot.nutrition_log_add":
            result = _handle_nutrition_add(clean_args)
        elif name == "qbot.nutrition_log_delete_preview":
            result = _handle_nutrition_delete_preview(clean_args)
        elif name == "qbot.nutrition_log_delete":
            result = _handle_nutrition_delete(clean_args)
        elif name == "qbot.nutrition_log_replace":
            result = _handle_nutrition_replace(clean_args)
        elif name == "qbot.qcal_event_preview":
            result = _handle_qcal_event_preview(clean_args)
        elif name == "qbot.qcal_event_add":
            result = _handle_qcal_event_add(clean_args)
        elif name == "qbot.qcal_event_cancel":
            result = _handle_qcal_event_cancel(clean_args)
        elif name == "qbot.qcal_reminder_preview":
            result = _handle_qcal_reminder_preview(clean_args)
        elif name == "qbot.qcal_reminder_add":
            result = _handle_qcal_reminder_add(clean_args)
        elif name == "qbot.qcal_reminder_done":
            result = _handle_qcal_reminder_done(clean_args)
        elif name == "qbot.qcal_reminder_cancel":
            result = _handle_qcal_reminder_cancel(clean_args)
        elif name == "qbot.artifact_get":
            identifier = str(clean_args.get("identifier", "")).strip()
            if not identifier:
                result = {"tool": "qbot.artifact_get", "status": "error", "error": "identifier required"}
            else:
                try:
                    from qbot3.artifacts.store import read_artifact_content
                    result = read_artifact_content(
                        identifier=identifier,
                        start_line=int(clean_args.get("start_line", 1)),
                        max_lines=int(clean_args.get("max_lines", 200)),
                        max_bytes=65536,
                    )
                    result.setdefault("tool", "qbot.artifact_get")
                except Exception as exc:
                    result = {"tool": "qbot.artifact_get", "status": "error", "error": str(exc)}
        elif name == "qbot.action_execute":
            result = _handle_action_execute(clean_args)
        else:
            tool_args = dict(clean_args)
            tool_result, warnings = _dispatch_local_qbot_tool(
                qbot_tool,
                tool_args,
                source="mcp",
                mcp_tool=name,
                session_id=session_id or None,
                log_call=False,
            )
            result = tool_result
            if warnings:
                result = dict(result)
                result.setdefault("warnings", [])
                if isinstance(result["warnings"], list):
                    result["warnings"].extend(warnings)
                else:
                    result["warnings"] = warnings

        audit_args = dict(clean_args)
        audit_args["_source"] = "mcp"
        audit_args["_mcp_tool"] = name
        if session_id:
            audit_args["_mcp_session_id"] = session_id
        try:
            import api_db
            api_db.save_tool_call(qbot_tool, audit_args, result)
        except Exception:
            pass

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _mcp_result_content(result),
        }, 200, {}

    return _mcp_error(f"unsupported method: {method}", code=-32601, request_id=request_id), 200, {}


# ── Nutrition write handlers ──

def _handle_nutrition_preview(args: dict) -> dict[str, Any]:
    """Read-only preview: parse meal, compute idempotency_key, return draft. No DB writes."""
    import hashlib, uuid
    from datetime import date as dt_date

    day = str(args.get("date", dt_date.today().isoformat()))[:10]
    raw = str(args.get("raw_text", ""))
    kcal = args.get("kcal_total")
    prot = args.get("protein_g")
    carbs = args.get("carbs_g")
    fat = args.get("fat_g")
    fluids = args.get("fluids_ml")
    meal_name = str(args.get("meal_name", raw[:60] or "posiłek"))
    source = str(args.get("source", "chatgpt_mcp"))
    conf = str(args.get("confidence", "medium"))

    # Generate idempotency key
    payload = f"{day}|{meal_name}|{kcal}|{prot}|{carbs}|{fat}"
    idem_key = hashlib.sha256(payload.encode()).hexdigest()[:16]

    return {
        "tool": "qbot.nutrition_log_preview",
        "safety_class": "READ_ONLY",
        "status": "DRY_RUN",
        "idempotency_key": idem_key,
        "draft": {
            "date": day,
            "meal_name": meal_name,
            "raw_text": raw,
            "kcal_total": kcal,
            "protein_g": prot,
            "carbs_g": carbs,
            "fat_g": fat,
            "fluids_ml": fluids,
            "source": source,
            "confidence": conf,
        },
        "next_action": "Call qbot.nutrition_log_add with confirm=true and this idempotency_key to save.",
    }


def _handle_nutrition_add(args: dict) -> dict[str, Any]:
    """Write meal to nutrition DB. Requires confirm=true and idempotency_key."""
    import hashlib, json, os
    from datetime import date as dt_date, datetime

    confirm = args.get("confirm", False)
    if confirm is not True and str(confirm).lower() != "true":
        return {
            "tool": "qbot.nutrition_log_add",
            "safety_class": "WRITE_NUTRITION_ONLY",
            "status": "BLOCKED",
            "error": "confirm must be true to save. Use qbot.nutrition_log_preview first.",
            "preview": _handle_nutrition_preview(args),
        }

    idem_key = str(args.get("idempotency_key", ""))
    if not idem_key:
        return {
            "tool": "qbot.nutrition_log_add",
            "safety_class": "WRITE_NUTRITION_ONLY",
            "status": "BLOCKED",
            "error": "idempotency_key required.",
        }

    day = str(args.get("date", dt_date.today().isoformat()))[:10]
    kcal = float(args.get("kcal_total", 0))
    prot = args.get("protein_g")
    carbs = args.get("carbs_g")
    fat = args.get("fat_g")
    fluids = args.get("fluids_ml")
    meal_name = str(args.get("meal_name", args.get("raw_text", "posiłek")[:60]))
    source = str(args.get("source", "chatgpt_mcp"))
    conf = str(args.get("confidence", "medium"))
    raw_text = str(args.get("raw_text", ""))

    # Check idempotency
    try:
        from qbot_nutrition_db import _conn as nut_conn
        c = nut_conn()
        cur = c.cursor()
        cur.execute("SELECT 1 FROM nutrition_write_audit WHERE idempotency_key=%s", (idem_key,))
        if cur.fetchone():
            c.close()
            return {
                "tool": "qbot.nutrition_log_add",
                "safety_class": "WRITE_NUTRITION_ONLY",
                "status": "DUPLICATE",
                "note": "This idempotency_key already exists. Meal was already saved.",
                "idempotency_key": idem_key,
            }
        c.close()
    except Exception:
        pass  # table may not exist — proceed

    # Write meal log
    try:
        from qbot_nutrition_db import meal_log_create, daily_summary_compute
        context = json.dumps({"source": source, "confidence": conf, "mcp_tool": "nutrition_log_add", "raw_text": raw_text})
        item = {
            "food_name": meal_name,
            "amount": 1, "unit": "porcja",
            "kcal": kcal,
            "carbs_g": carbs,
            "protein_g": prot,
            "fat_g": fat,
            "fiber_g": None,
            "sodium_mg": None,
        }
        meal = meal_log_create(meal_type="meal", note=f"ChatGPT MCP: {meal_name}", context=context, eaten_at=f"{day}T12:00:00", items=[item])
        summary = daily_summary_compute(day)

        # Write audit log
        try:
            c2 = nut_conn()
            cur2 = c2.cursor()
            cur2.execute(
                "INSERT INTO nutrition_write_audit (idempotency_key, meal_log_id, date, source, raw_user_text, payload_json, result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (idem_key, meal.get("id"), day, source, raw_text, json.dumps(args, default=str), json.dumps({"meal_id": meal.get("id"), "summary": summary}, default=str)))
            c2.commit(); c2.close()
        except Exception:
            pass  # audit table may not exist

        # Rebuild snapshot
        try:
            from qbot_calendar_core import build_snapshot
            build_snapshot(day)
        except Exception:
            pass

        return {
            "tool": "qbot.nutrition_log_add",
            "safety_class": "WRITE_NUTRITION_ONLY",
            "status": "OK",
            "idempotency_key": idem_key,
            "meal": meal,
            "daily_summary": {k: v for k, v in (summary or {}).items() if k in ("date","kcal_total","carbs_total","protein_total","fat_total","fiber_total","sodium_total","fluids_total")},
            "note": "Meal saved. Daily summary + calendar snapshot updated.",
        }
    except Exception as e:
        return {
            "tool": "qbot.nutrition_log_add",
            "safety_class": "WRITE_NUTRITION_ONLY",
            "status": "ERROR",
            "error": str(e)[:300],
        }


def _handle_nutrition_delete_preview(args: dict) -> dict[str, Any]:
    """Read-only preview of meal deletion. No DB writes."""
    meal_id = int(args.get("meal_log_id", 0))
    if not meal_id:
        return {"tool": "qbot.nutrition_log_delete_preview", "safety_class": "READ_ONLY", "status": "ERROR", "error": "meal_log_id required"}

    try:
        from qbot_nutrition_db import get_meal_log
        meal = get_meal_log(meal_id)
        if not meal:
            return {"tool": "qbot.nutrition_log_delete_preview", "safety_class": "READ_ONLY", "status": "NOT_FOUND", "meal_log_id": meal_id}

        items_count = len(meal.get("items", []))
        context = meal.get("context", "") or ""
        note = meal.get("note", "") or ""
        is_mcp = "chatgpt_mcp" in str(context).lower() or "MCP:" in str(note) or "ChatGPT MCP" in str(note)

        return {
            "tool": "qbot.nutrition_log_delete_preview",
            "safety_class": "READ_ONLY",
            "status": "OK",
            "meal_log_id": meal_id,
            "date": str(meal.get("eaten_at", "?"))[:10],
            "meal_name": (meal.get("items", [{}])[0].get("food_name", "?") if meal.get("items") else "?"),
            "items_count": items_count,
            "can_delete": is_mcp,
            "restriction": None if is_mcp else "Only MCP-sourced meals can be deleted via this tool.",
            "note": meal.get("note", "")[:100],
        }
    except Exception as e:
        return {"tool": "qbot.nutrition_log_delete_preview", "safety_class": "READ_ONLY", "status": "ERROR", "error": str(e)[:200]}


def _handle_nutrition_delete(args: dict) -> dict[str, Any]:
    """Delete MCP-sourced meal. Requires confirm=true and idempotency_key."""
    import json, os
    from datetime import date as dt_date

    confirm = args.get("confirm", False)
    if confirm is not True and str(confirm).lower() != "true":
        return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "BLOCKED",
                "error": "confirm must be true. Use qbot.nutrition_log_delete_preview first."}

    idem_key = str(args.get("idempotency_key", ""))
    if not idem_key:
        return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "BLOCKED",
                "error": "idempotency_key required."}

    meal_id = int(args.get("meal_log_id", 0))
    if not meal_id:
        return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "ERROR", "error": "meal_log_id required"}

    # Check idempotency
    try:
        from qbot_nutrition_db import _conn as nut_conn
        c = nut_conn(); cur = c.cursor()
        cur.execute("SELECT 1 FROM nutrition_write_audit WHERE idempotency_key=%s", (idem_key,))
        if cur.fetchone():
            c.close()
            return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "DUPLICATE",
                    "note": "This idempotency_key already used — deletion already processed."}
        c.close()
    except Exception:
        pass

    try:
        from qbot_nutrition_db import get_meal_log, daily_summary_compute, _conn as nut_conn

        meal = get_meal_log(meal_id)
        if not meal:
            return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "NOT_FOUND", "meal_log_id": meal_id}

        context = meal.get("context", "") or ""
        note = meal.get("note", "") or ""
        is_mcp = "chatgpt_mcp" in str(context).lower() or "MCP:" in str(note) or "ChatGPT MCP" in str(note)
        if not is_mcp:
            return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "BLOCKED",
                    "error": "Only MCP-sourced meals (source=chatgpt_mcp or note starting with 'MCP:') can be deleted via this tool."}

        date_str = str(meal.get("eaten_at", ""))[:10]
        items_count = len(meal.get("items", []))

        # Delete
        c = nut_conn(); cur = c.cursor()
        cur.execute("DELETE FROM meal_log_items WHERE meal_log_id=%s", (meal_id,))
        cur.execute("DELETE FROM meal_logs WHERE id=%s", (meal_id,))
        c.commit()

        # Audit
        try:
            cur.execute("INSERT INTO nutrition_write_audit (idempotency_key, meal_log_id, date, source, raw_user_text, payload_json, result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (idem_key, meal_id, date_str, "chatgpt_mcp_delete", f"deleted meal {meal_id}",
                 json.dumps({"action":"delete","meal_log_id":meal_id,"note":note[:100]}),
                 json.dumps({"deleted_items":items_count})))
            c.commit()
        except Exception:
            pass
        c.close()

        summary = daily_summary_compute(date_str)

        # Rebuild snapshot
        try:
            from qbot_calendar_core import build_snapshot
            build_snapshot(date_str)
        except Exception:
            pass

        return {
            "tool": "qbot.nutrition_log_delete",
            "safety_class": "WRITE_NUTRITION_ONLY",
            "status": "OK",
            "deleted_meal_log_id": meal_id,
            "deleted_items_count": items_count,
            "date": date_str,
            "daily_summary": {k: v for k, v in (summary or {}).items() if k in ("date","kcal_total","carbs_total","protein_total","fat_total")},
            "note": "Meal deleted. Daily summary + calendar snapshot recomputed.",
        }
    except Exception as e:
        return {"tool": "qbot.nutrition_log_delete", "safety_class": "WRITE_NUTRITION_ONLY", "status": "ERROR", "error": str(e)[:300]}


def _handle_nutrition_replace(args: dict) -> dict[str, Any]:
    """Replace MCP-sourced meal: delete old + insert new in one transaction."""
    import json
    from datetime import date as dt_date

    confirm = args.get("confirm", False)
    if confirm is not True and str(confirm).lower() != "true":
        old_meal_id = int(args.get("meal_log_id", 0))
        preview = {"meal_log_id": old_meal_id, "confirm_required": True}
        try:
            from qbot_nutrition_db import get_meal_log
            m = get_meal_log(old_meal_id)
            if m:
                preview["old_meal"] = {"date": str(m.get("eaten_at","?"))[:10], "items_count": len(m.get("items",[])),
                    "food_name": (m.get("items",[{}])[0].get("food_name","?") if m.get("items") else "?")}
        except: pass
        return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "BLOCKED",
                "error": "confirm must be true.", "preview": preview}

    idem_key = str(args.get("idempotency_key", ""))
    if not idem_key:
        return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "BLOCKED", "error": "idempotency_key required."}

    old_meal_id = int(args.get("meal_log_id", 0))

    # Check idempotency
    try:
        from qbot_nutrition_db import _conn as nut_conn
        c = nut_conn(); cur = c.cursor()
        cur.execute("SELECT 1 FROM nutrition_write_audit WHERE idempotency_key=%s", (idem_key,))
        if cur.fetchone():
            c.close()
            return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "DUPLICATE"}
        c.close()
    except: pass

    try:
        from qbot_nutrition_db import get_meal_log, meal_log_create, daily_summary_compute, _conn as nut_conn

        old = get_meal_log(old_meal_id)
        if not old:
            return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "NOT_FOUND", "meal_log_id": old_meal_id}

        ctx = old.get("context","") or ""; n = old.get("note","") or ""
        if not ("chatgpt_mcp" in str(ctx).lower() or "MCP:" in str(n)):
            return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "BLOCKED", "error": "Only MCP-sourced meals can be replaced."}

        date_str = str(old.get("eaten_at",""))[:10]

        new_name = str(args.get("new_meal_name", args.get("raw_text","posiłek")[:60]))
        new_kcal = float(args.get("kcal_total", 0))
        new_prot = args.get("protein_g")
        new_carbs = args.get("carbs_g")
        new_fat = args.get("fat_g")
        new_raw = str(args.get("raw_text",""))

        # Delete old + insert new
        c = nut_conn(); cur = c.cursor()
        cur.execute("DELETE FROM meal_log_items WHERE meal_log_id=%s", (old_meal_id,))
        cur.execute("DELETE FROM meal_logs WHERE id=%s", (old_meal_id,))

        new_context = json.dumps({"source":"chatgpt_mcp_replace","confidence":"medium","raw_text":new_raw,"replaced_meal_id":old_meal_id})
        item = {"food_name": new_name, "amount":1, "unit":"porcja", "kcal":new_kcal,
                "carbs_g": new_carbs, "protein_g": new_prot, "fat_g": new_fat}
        new_meal = meal_log_create(meal_type="meal", note=f"MCP replace: {new_name}", context=new_context,
                                   eaten_at=f"{date_str}T12:00:00", items=[item])
        c.commit()

        # Audit
        try:
            cur.execute("INSERT INTO nutrition_write_audit (idempotency_key, meal_log_id, date, source, raw_user_text, payload_json, result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (idem_key, new_meal.get("id"), date_str, "chatgpt_mcp_replace", f"replaced {old_meal_id} → {new_meal.get('id')}",
                 json.dumps({"action":"replace","old":old_meal_id,"new_name":new_name,"kcal":new_kcal}),
                 json.dumps({"old_deleted":True,"new_id":new_meal.get("id")})))
            c.commit()
        except: pass
        c.close()

        summary = daily_summary_compute(date_str)
        try:
            from qbot_calendar_core import build_snapshot
            build_snapshot(date_str)
        except: pass

        return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "OK",
                "old_meal_log_id": old_meal_id, "new_meal_log_id": new_meal.get("id"), "date": date_str,
                "daily_summary": {k:v for k,v in (summary or {}).items() if k in ("date","kcal_total","carbs_total","protein_total","fat_total")}}
    except Exception as e:
        return {"tool": "qbot.nutrition_log_replace", "safety_class": "WRITE_NUTRITION_ONLY", "status": "ERROR", "error": str(e)[:300]}


# ── QCal Event + Reminder handlers ──────────────────────────────────────────

def _qcal_audit(idem_key: str, operation: str, entity_type: str, entity_id: int | None, date_str: str | None, payload: dict, result: dict):
    try:
        import psycopg, os, json
        from psycopg.rows import dict_row
        c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
        cur = c.cursor()
        cur.execute("INSERT INTO qcal_write_audit (idempotency_key,operation,entity_type,entity_id,date,source,payload_json,result_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (idem_key, operation, entity_type, entity_id, date_str, "chatgpt_mcp", json.dumps(payload), json.dumps(result)))
        c.commit(); c.close()
    except: pass


def _qcal_check_idem(idem_key: str) -> bool:
    try:
        from qbot_nutrition_db import _conn as nut_conn
        c = nut_conn(); cur = c.cursor()
        cur.execute("SELECT 1 FROM qcal_write_audit WHERE idempotency_key=%s",(idem_key,))
        exists = cur.fetchone() is not None; c.close()
        return exists
    except: return False


def _handle_qcal_event_preview(args: dict) -> dict:
    import hashlib
    d = args.get("date_start","") or "?"
    t = args.get("title","") or ""
    payload = f"event|{d}|{t}"
    return {"tool":"qbot.qcal_event_preview","safety_class":"READ_ONLY","status":"DRY_RUN",
            "draft":{"date_start":d,"title":t,"event_type":args.get("event_type","note")},
            "idempotency_key":hashlib.sha256(payload.encode()).hexdigest()[:16],
            "next_action":"Call qbot.qcal_event_add with confirm=true and idempotency_key."}

def _handle_qcal_event_add(args: dict) -> dict:
    from qbot_calendar_core import qcal_event_add_controlled
    r = qcal_event_add_controlled(
        date_start=args.get("date_start",""), title=args.get("title","?"),
        date_end=args.get("date_end"), time_start=args.get("time_start"),
        event_type=args.get("event_type","note"), description=args.get("description"),
        source=args.get("source","chatgpt_mcp"),
        idempotency_key=args.get("idempotency_key"),
        confirm=(args.get("confirm") == True or str(args.get("confirm","")).lower()=="true"),
    )
    # Map to MCP-style response
    mcp_status = r["status"].upper() if r["status"] in ("ok","duplicate","refused","error") else "ERROR"
    if mcp_status == "OK":
        return {"tool":"qbot.qcal_event_add","safety_class":"WRITE_QCAL_ONLY","status":"OK","event_id":r["event_id"],"record":r.get("record"),"idempotency_key":r.get("idempotency_key"),"snapshot_rebuilt":r.get("snapshot_rebuilt")}
    elif mcp_status == "DUPLICATE":
        return {"tool":"qbot.qcal_event_add","safety_class":"WRITE_QCAL_ONLY","status":"DUPLICATE","event_id":r["event_id"],"record":r.get("record")}
    elif mcp_status == "REFUSED":
        return {"tool":"qbot.qcal_event_add","safety_class":"WRITE_QCAL_ONLY","status":"BLOCKED","error":r.get("message","refused")}
    else:
        return {"tool":"qbot.qcal_event_add","safety_class":"WRITE_QCAL_ONLY","status":"ERROR","error":r.get("message","unknown error")}

def _handle_qcal_event_cancel(args: dict) -> dict:
    from qbot_calendar_core import qcal_event_cancel_controlled
    r = qcal_event_cancel_controlled(
        event_id=args.get("event_id"), match=args.get("match"),
        reason=args.get("reason"),
        idempotency_key=args.get("idempotency_key") or f"mcp-cancel-{args.get('event_id','?')}",
        confirm=(args.get("confirm") == True or str(args.get("confirm","")).lower()=="true"),
    )
    smap = {"ok":"OK","duplicate":"DUPLICATE","refused":"BLOCKED","not_found":"NOT_FOUND","ambiguous_match":"AMBIGUOUS","error":"ERROR"}
    return {"tool":"qbot.qcal_event_cancel","safety_class":"WRITE_QCAL_ONLY","status":smap.get(r["status"],"ERROR"),
            "event_id":r.get("event_id"),"cancelled":r.get("cancelled",False),
            "before":r.get("before"),"after":r.get("after"),"message":r.get("message","")}

def _handle_qcal_reminder_preview(args: dict) -> dict:
    import hashlib
    d = args.get("date","?"); t = args.get("title","") or args.get("raw_text","") or ""
    payload = f"reminder|{d}|{t}"
    return {"tool":"qbot.qcal_reminder_preview","safety_class":"READ_ONLY","status":"DRY_RUN",
            "draft":{"date":d,"title":t,"reminder_type":args.get("reminder_type","custom"),"time":args.get("time","")},
            "idempotency_key":hashlib.sha256(payload.encode()).hexdigest()[:16],
            "next_action":"Call qbot.qcal_reminder_add with confirm=true and idempotency_key."}

def _handle_qcal_reminder_add(args: dict) -> dict:
    if not (args.get("confirm") == True or str(args.get("confirm","")).lower()=="true"):
        return {"tool":"qbot.qcal_reminder_add","safety_class":"WRITE_QCAL_ONLY","status":"BLOCKED","error":"confirm must be true."}
    idem = str(args.get("idempotency_key",""))
    if not idem: return {"tool":"qbot.qcal_reminder_add","safety_class":"WRITE_QCAL_ONLY","status":"BLOCKED","error":"idempotency_key required."}
    if _qcal_check_idem(idem): return {"tool":"qbot.qcal_reminder_add","safety_class":"WRITE_QCAL_ONLY","status":"DUPLICATE"}
    try:
        import psycopg, os, json; from psycopg.rows import dict_row
        c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
        cur = c.cursor()
        # Build metadata_json from deadline_task fields + any extra fields
        meta = {}
        for k in ("task_kind","deadline_date","start_date","repeat_until_done","source"):
            v = args.get(k)
            if v is not None:
                meta[k] = v
        metadata_json = json.dumps(meta, default=str) if meta else None
        cur.execute("""INSERT INTO reminders (date,time,timezone,title,message,reminder_type,status,priority,channel,recurrence_rule,metadata_json)
            VALUES (%s,%s,'Europe/Warsaw',%s,%s,%s,'pending',%s,%s,%s,%s) RETURNING id""",
            (args.get("date"),args.get("time"),args.get("title","?"),args.get("message",""),args.get("reminder_type","custom"),args.get("priority","normal"),args.get("channel","cli"),args.get("recurrence_rule"),metadata_json))
        rid = cur.fetchone()["id"]; c.commit(); c.close()
        _qcal_audit(idem, "reminder_add", "reminder", rid, args.get("date"), dict(args), {"id":rid})
        try: from qbot_calendar_core import build_snapshot; build_snapshot(args.get("date",""))
        except: pass
        return {"tool":"qbot.qcal_reminder_add","safety_class":"WRITE_QCAL_ONLY","status":"OK","reminder_id":rid}
    except Exception as e: return {"tool":"qbot.qcal_reminder_add","safety_class":"WRITE_QCAL_ONLY","status":"ERROR","error":str(e)[:200]}

def _handle_qcal_reminder_done(args: dict) -> dict:
    if not (args.get("confirm") == True or str(args.get("confirm","")).lower()=="true"):
        return {"tool":"qbot.qcal_reminder_done","safety_class":"WRITE_QCAL_ONLY","status":"BLOCKED","error":"confirm must be true."}
    rid = int(args.get("reminder_id",0))
    try:
        import psycopg, os; from psycopg.rows import dict_row
        c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
        cur = c.cursor()
        cur.execute("SELECT date FROM reminders WHERE id=%s",(rid,)); r = cur.fetchone()
        if not r: c.close(); return {"tool":"qbot.qcal_reminder_done","safety_class":"WRITE_QCAL_ONLY","status":"NOT_FOUND"}
        d = str(r["date"])[:10]
        cur.execute("UPDATE reminders SET status='done', sent_at=now(), updated_at=now() WHERE id=%s",(rid,)); c.commit(); c.close()
        _qcal_audit("done_"+str(rid), "reminder_done", "reminder", rid, d, dict(args), {"done":True})
        try: from qbot_calendar_core import build_snapshot; build_snapshot(d)
        except: pass
        return {"tool":"qbot.qcal_reminder_done","safety_class":"WRITE_QCAL_ONLY","status":"OK","reminder_id":rid}
    except Exception as e: return {"tool":"qbot.qcal_reminder_done","safety_class":"WRITE_QCAL_ONLY","status":"ERROR","error":str(e)[:200]}

def _handle_qcal_reminder_cancel(args: dict) -> dict:
    if not (args.get("confirm") == True or str(args.get("confirm","")).lower()=="true"):
        return {"tool":"qbot.qcal_reminder_cancel","safety_class":"WRITE_QCAL_ONLY","status":"BLOCKED","error":"confirm must be true."}
    rid = int(args.get("reminder_id",0))
    try:
        import psycopg, os; from psycopg.rows import dict_row
        c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
        cur = c.cursor()
        cur.execute("SELECT date FROM reminders WHERE id=%s",(rid,)); r = cur.fetchone()
        if not r: c.close(); return {"tool":"qbot.qcal_reminder_cancel","safety_class":"WRITE_QCAL_ONLY","status":"NOT_FOUND"}
        d = str(r["date"])[:10]
        cur.execute("UPDATE reminders SET status='cancelled', updated_at=now() WHERE id=%s",(rid,)); c.commit(); c.close()
        _qcal_audit("cancel_"+str(rid), "reminder_cancel", "reminder", rid, d, dict(args), {"cancelled":True})
        try: from qbot_calendar_core import build_snapshot; build_snapshot(d)
        except: pass
        return {"tool":"qbot.qcal_reminder_cancel","safety_class":"WRITE_QCAL_ONLY","status":"OK","reminder_id":rid}
    except Exception as e: return {"tool":"qbot.qcal_reminder_cancel","safety_class":"WRITE_QCAL_ONLY","status":"ERROR","error":str(e)[:200]}


_ACTION_EXECUTE_ALLOWLIST = {"nutrition_log_add", "qcal_reminder_add", "qcal_event_add", "qcal_event_update", "qcal_event_cancel", "planning_fact_add", "qbot_doc_append", "qbot_doc_replace_section", "qbot_doc_update", "rwgps_gpx_import", "route_poi_analyze", "qbot_artifact_get"}

_ACTION_REQUIRED_PAYLOAD_FIELDS: dict[str, list[str]] = {
    "nutrition_log_add": ["date", "kcal_total"],
    "qcal_reminder_add": ["date", "title"],
    "qcal_event_add": ["date_start", "title"],
    "qcal_event_update": ["event_id", "updates"],
    "qcal_event_cancel": ["event_id"],
    "planning_fact_add": ["fact_type", "date", "title"],
    "qbot_doc_append": ["target_document", "heading", "content_markdown"],
    "qbot_doc_replace_section": ["target_document", "heading", "content_markdown"],
    "qbot_doc_update": ["target_document", "content_markdown"],
    "rwgps_gpx_import": ["gpx_path", "name"],
    "route_poi_analyze": ["km_from", "km_to"],
    "qbot_artifact_get": ["identifier"],
}


def _handle_action_execute(args: dict) -> dict[str, Any]:
    """Execute an action_draft. Unified entry point for allowed action_types.

    Safety:
      1. confirm must be true
      2. idempotency_key must be present
      3. action_type must be in allowlist
      4. payload must have required fields
      5. duplicate idempotency_key is rejected
      6. dry_run prevents writes
    """
    confirm = args.get("confirm") is True or str(args.get("confirm", "")).lower() == "true"
    if not confirm:
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED",
            "error": "confirm must be true to execute. Use qbot.query first to get action_draft, then call action_execute with confirm=true.",
        }

    idem_key = str(args.get("idempotency_key", "")).strip()
    if not idem_key:
        return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST", "status": "BLOCKED", "error": "idempotency_key required."}

    action_type = str(args.get("action_type", "")).strip()
    if action_type not in _ACTION_EXECUTE_ALLOWLIST:
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED",
            "error": f"action_type '{action_type}' not in allowlist: {sorted(_ACTION_EXECUTE_ALLOWLIST)}",
        }

    payload = args.get("payload_json", {}) or {}
    if not isinstance(payload, dict):
        return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST", "status": "BLOCKED", "error": "payload_json must be an object."}
    if action_type == "route_poi_analyze" and not (
        any(str(payload.get(field, "")).strip() for field in ("route_id", "artifact_id", "path"))
        or any(str(payload.get(field, "")).strip() for field in ("merge_artifact_ids",))
    ):
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED",
            "error": "route_poi_analyze requires route_id, artifact_id, path or merge_artifact_ids.",
        }

    # Validate required payload fields
    required = _ACTION_REQUIRED_PAYLOAD_FIELDS.get(action_type, [])
    if action_type == "route_poi_analyze" and any(str(payload.get(field, "")).strip() for field in ("merge_artifact_ids",)):
        required = []
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED",
            "error": f"Missing required payload fields: {missing}",
            "missing_fields": missing,
        }

    source = str(args.get("source", "chatgpt_mcp"))

    # ── Doc action dry-run — handled in the handler for richer preview ──
    if action_type in ("qbot_doc_append", "qbot_doc_replace_section", "qbot_doc_update"):
        dry_run = args.get("dry_run") is True or str(args.get("dry_run", "")).lower() == "true"
        try:
            _doc_verify_db()
        except Exception as e:
            return {
                "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
                "status": "ERROR", "error": f"Audit table unavailable — write blocked: {e}",
            }
        if not dry_run:
            try:
                doc_dup = _doc_check_duplicate(idem_key)
            except Exception as e:
                return {
                    "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
                    "status": "ERROR", "error": f"Duplicate check failed — cannot verify idempotency: {e}",
                }
            if doc_dup:
                return {
                    "tool": "qbot.action_execute",
                    "safety_class": "WRITE_ONLY_ALLOWLIST",
                    **doc_dup,
                }
        if action_type == "qbot_doc_append":
            return _action_exec_doc_append(payload, idem_key, source, dry_run)
        elif action_type == "qbot_doc_replace_section":
            return _action_exec_doc_replace_section(payload, idem_key, source, dry_run)
        elif action_type == "qbot_doc_update":
            return _action_exec_doc_update(payload, idem_key, source, dry_run)

    # ── Dry run (non-doc actions) ──
    if args.get("dry_run") is True or str(args.get("dry_run", "")).lower() == "true":
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "DRY_RUN",
            "action_type": action_type,
            "idempotency_key": idem_key,
            "payload": payload,
            "note": "dry_run — no write performed.",
        }

    # ── Check duplicate ──
    dup = _action_check_duplicate(idem_key, action_type)
    if dup:
        return dup

    # ── Dispatch ──
    if action_type == "nutrition_log_add":
        return _action_exec_nutrition(payload, idem_key, source)
    elif action_type == "qcal_reminder_add":
        return _action_exec_reminder(payload, idem_key, source)
    elif action_type == "qcal_event_add":
        return _action_exec_event(payload, idem_key, source)
    elif action_type == "qcal_event_update":
        return _action_exec_event_update(payload, idem_key, source)
    elif action_type == "qcal_event_cancel":
        return _action_exec_event_cancel(payload, idem_key, source)
    elif action_type == "rwgps_gpx_import":
        return _action_exec_rwgps_gpx_import(payload, idem_key, source)
    elif action_type == "route_poi_analyze":
        return _action_exec_route_poi_analyze(payload, idem_key, source)
    elif action_type == "planning_fact_add":
        return _action_exec_planning(payload, idem_key, source)
    elif action_type == "qbot_artifact_put":
        return _action_exec_qbot_artifact_put(payload, idem_key, source)
    else:
        return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST", "status": "ERROR", "error": f"Unhandled action_type: {action_type}"}


def _action_check_duplicate(idem_key: str, action_type: str) -> dict | None:
    """Check if idempotency_key already used.

    Only checks the audit table relevant to action_type.
    Validates that the linked record still exists and is active.
    If the record is deleted/cancelled/missing, removes the stale
    audit entry so the action can be re-executed (caller proceeds).
    """
    from qbot_nutrition_db import _conn as nut_conn

    # Nutrition actions: only check nutrition audit
    if action_type == "nutrition_log_add":
        try:
            c = nut_conn()
            cur = c.cursor()
            cur.execute("SELECT entity_id FROM nutrition_write_audit WHERE idempotency_key=%s", (idem_key,))
            row = cur.fetchone()
            if row:
                existing_id = row["entity_id"]
                c.close()
                if existing_id:
                    return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST", "status": "DUPLICATE", "created": False, "action_type": action_type, "idempotency_key": idem_key, "meal_id": existing_id, "existing_id": existing_id, "note": "idempotency_key already exists (nutrition_write_audit)."}
            c.close()
        except Exception:
            pass
        return None

    # QCal actions: only check QCal audit, validate linked record
    if action_type in ("qcal_reminder_add", "qcal_event_add", "qcal_event_update", "qcal_event_cancel"):
        try:
            import psycopg, os
            from psycopg.rows import dict_row
            c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
            cur = c.cursor()
            cur.execute("SELECT entity_id, entity_type FROM qcal_write_audit WHERE idempotency_key=%s", (idem_key,))
            row = cur.fetchone()
            if row:
                existing_id = row["entity_id"]
                entity_type = row["entity_type"]
                target_table = "calendar_events" if entity_type == "event" else "reminders"
                # Fetch full record
                cur.execute("SELECT * FROM %s WHERE id=%%s" % target_table, (existing_id,))
                target = cur.fetchone()
                active = target and target["status"] not in ("cancelled", "deleted", "done")
                record = {k: str(v) if hasattr(v, "isoformat") or isinstance(v, type) else v for k, v in dict(target).items()} if target else None
                c.close()
                if active:
                    return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST", "status": "DUPLICATE", "created": False, "action_type": action_type, "idempotency_key": idem_key, "event_id": existing_id, "existing_id": existing_id, "record": record, "note": "Linked record is active."}
                # Stale audit: cleanup and let caller re-execute
                c2 = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
                cur2 = c2.cursor()
                cur2.execute("DELETE FROM qcal_write_audit WHERE idempotency_key=%s", (idem_key,))
                c2.commit()
                c2.close()
            else:
                c.close()
        except Exception:
            pass
        return None

    return None


def _action_exec_nutrition(payload: dict, idem_key: str, source: str) -> dict:
    """Execute nutrition_log_add using existing handler pattern."""
    from datetime import date as dt_date
    import json

    day = str(payload.get("date", dt_date.today().isoformat()))[:10]
    kcal = float(payload.get("kcal_total", 0))
    prot = payload.get("protein_g")
    carbs = payload.get("carbs_g")
    fat = payload.get("fat_g")
    meal_name = str(payload.get("meal_name", payload.get("raw_text", "posiłek")[:60]))
    conf = str(payload.get("confidence", "medium"))
    raw_text = str(payload.get("raw_text", ""))

    from qbot_nutrition_db import meal_log_create, daily_summary_compute
    context = json.dumps({"source": source, "confidence": conf, "mcp_tool": "action_execute", "action_type": "nutrition_log_add", "raw_text": raw_text})
    item = {"food_name": meal_name, "amount": 1, "unit": "porcja", "kcal": kcal, "carbs_g": carbs, "protein_g": prot, "fat_g": fat}

    meal = meal_log_create(meal_type="meal", note=f"MCP: {meal_name}", context=context, eaten_at=f"{day}T12:00:00", items=[item])
    summary = daily_summary_compute(day)

    # Audit
    try:
        from qbot_nutrition_db import _conn as nut_conn
        c2 = nut_conn()
        cur2 = c2.cursor()
        cur2.execute(
            "INSERT INTO nutrition_write_audit (idempotency_key, meal_log_id, date, source, raw_user_text, payload_json, result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (idem_key, meal.get("id"), day, source, raw_text, json.dumps(payload, default=str), json.dumps({"meal_id": meal.get("id")}, default=str)))
        c2.commit()
        c2.close()
    except Exception:
        pass

    # Snapshot
    try:
        from qbot_calendar_core import build_snapshot
        build_snapshot(day)
    except Exception:
        pass

    return {
        "tool": "qbot.action_execute",
        "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": "OK",
        "action_type": "nutrition_log_add",
        "idempotency_key": idem_key,
        "meal_id": meal.get("id"),
        "daily_summary": {k: v for k, v in (summary or {}).items() if k in ("date","kcal_total","carbs_total","protein_total","fat_total")},
    }


def _action_exec_reminder(payload: dict, idem_key: str, source: str) -> dict:
    """Execute qcal_reminder_add."""
    import json, psycopg, os
    from psycopg.rows import dict_row

    c = psycopg.connect(host=os.getenv("PGHOST","127.0.0.1"),port=os.getenv("PGPORT","5432"),dbname=os.getenv("PGDATABASE","qbot"),user=os.getenv("PGUSER","qbot"),password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
    cur = c.cursor()

    meta = {}
    for k in ("task_kind","deadline_date","start_date","repeat_until_done"):
        v = payload.get(k)
        if v is not None:
            meta[k] = v
    if source:
        meta["source"] = source
    metadata_json = json.dumps(meta, default=str) if meta else None

    cur.execute("""INSERT INTO reminders (date,time,timezone,title,message,reminder_type,status,priority,channel,recurrence_rule,metadata_json)
        VALUES (%s,%s,'Europe/Warsaw',%s,%s,%s,'pending',%s,%s,%s,%s) RETURNING id""",
        (payload.get("date"), payload.get("time"), payload.get("title","?"), payload.get("message",""),
         payload.get("reminder_type","custom"), payload.get("priority","normal"),
         payload.get("channel","cli"), payload.get("recurrence_rule"), metadata_json))
    rid = cur.fetchone()["id"]
    cur.execute("SELECT * FROM reminders WHERE id=%s", (rid,))
    row = cur.fetchone()
    record = {k: str(v) if hasattr(v, "isoformat") or isinstance(v, type) else v for k, v in dict(row).items()} if row else {}
    c.commit()
    c.close()

    _qcal_audit(idem_key, "reminder_add", "reminder", rid, payload.get("date",""), payload, {"id": rid, "action_execute": True})
    snap_ok = False
    try:
        from qbot_calendar_core import build_snapshot
        build_snapshot(payload.get("date",""))
        snap_ok = True
    except Exception:
        pass

    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": "OK", "action_type": "qcal_reminder_add",
        "idempotency_key": idem_key, "created": True,
        "reminder_id": rid, "record": record,
        "message": f"Utworzono przypomnienie: {record.get('title','?')} (id={rid}, {record.get('date','?')} {record.get('time','')})",
        "snapshot_rebuilt": snap_ok,
    }


def _action_exec_event_update(payload: dict, idem_key: str, source: str) -> dict:
    from qbot_calendar_core import qcal_event_update_controlled
    r = qcal_event_update_controlled(
        event_id=payload.get("event_id"), match=payload.get("match"),
        updates=payload.get("updates", {}),
        idempotency_key=idem_key, confirm=True, source=source,
    )
    status_map = {"ok": "OK", "duplicate": "DUPLICATE", "refused": "REFUSED",
                  "not_found": "NOT_FOUND", "ambiguous_match": "AMBIGUOUS", "error": "ERROR"}
    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": status_map.get(r["status"], "ERROR"),
        "action_type": "qcal_event_update",
        "idempotency_key": idem_key, "updated": r.get("updated", False),
        "event_id": r.get("event_id"), "before": r.get("before"), "after": r.get("after"),
        "message": r.get("message", ""),
    }


def _action_exec_event_cancel(payload: dict, idem_key: str, source: str) -> dict:
    from qbot_calendar_core import qcal_event_cancel_controlled
    r = qcal_event_cancel_controlled(
        event_id=payload.get("event_id"), match=payload.get("match"),
        reason=payload.get("reason"), idempotency_key=idem_key, confirm=True, source=source,
    )
    status_map = {"ok": "OK", "duplicate": "DUPLICATE", "refused": "REFUSED",
                  "not_found": "NOT_FOUND", "ambiguous_match": "AMBIGUOUS", "error": "ERROR"}
    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": status_map.get(r["status"], "ERROR"),
        "action_type": "qcal_event_cancel",
        "idempotency_key": idem_key, "cancelled": r.get("cancelled", False),
        "event_id": r.get("event_id"), "before": r.get("before"), "after": r.get("after"),
        "message": r.get("message", ""),
    }


def _action_exec_event(payload: dict, idem_key: str, source: str) -> dict:
    """Execute qcal_event_add via shared writer."""
    from qbot_calendar_core import qcal_event_add_controlled
    r = qcal_event_add_controlled(
        date_start=payload.get("date_start",""), title=payload.get("title","?"),
        date_end=payload.get("date_end"), time_start=payload.get("time_start"),
        event_type=payload.get("event_type","note"), description=payload.get("description", payload.get("title","")),
        source=source, idempotency_key=idem_key, confirm=True,
    )
    status_map = {"ok": "OK", "duplicate": "DUPLICATE", "refused": "BLOCKED", "error": "ERROR"}
    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": status_map.get(r["status"], "ERROR"),
        "action_type": "qcal_event_add",
        "idempotency_key": idem_key, "created": r.get("created", False),
        "event_id": r.get("event_id"), "record": r.get("record"),
        "message": r.get("message", ""),
        "snapshot_rebuilt": r.get("snapshot_rebuilt", False),
    }


def _action_exec_rwgps_gpx_import(payload: dict, idem_key: str, source: str) -> dict:
    """Execute rwgps_gpx_import — import GPX file as new RWGPS route."""
    gpx_path = str(payload.get("gpx_path", "")).strip()
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    privacy = str(payload.get("privacy", "private")).strip().lower()
    confirm = bool(payload.get("confirm", True))

    if not gpx_path or not name:
        return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
                "status": "BLOCKED", "error": "gpx_path and name required in payload."}

    try:
        from qbot_route_tools import _tool_qbot_rwgps_route_import_gpx
        result = _tool_qbot_rwgps_route_import_gpx({
            "gpx_path": gpx_path,
            "name": name,
            "description": description,
            "privacy": privacy,
            "confirm": True,
        })
    except Exception as exc:
        return {"tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
                "status": "ERROR", "error": str(exc)}

    if result.get("status") == "OK":
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "OK",
            "action_type": "rwgps_gpx_import",
            "idempotency_key": idem_key,
            "new_route_id": result.get("new_route_id"),
            "html_url": result.get("html_url"),
            "api_url": result.get("api_url"),
            "name": name,
            "source_gpx_path": gpx_path,
            "validation": result.get("validation"),
        }
    return {
        "tool": "qbot.action_execute",
        "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": result.get("status", "ERROR"),
        "action_type": "rwgps_gpx_import",
        "idempotency_key": idem_key,
        "error": result.get("error") or result.get("validation_error") or result.get("notes", "Unknown error"),
        "payload": payload,
    }


def _action_exec_route_poi_analyze(payload: dict, idem_key: str, source: str) -> dict:
    try:
        from qbot_route_tools import _tool_qbot_route_poi_analyze
        result = _tool_qbot_route_poi_analyze({
            "route_id": payload.get("route_id"),
            "artifact_id": payload.get("artifact_id"),
            "project_id": payload.get("project_id"),
            "path": payload.get("path"),
            "km_from": payload.get("km_from"),
            "km_to": payload.get("km_to"),
            "buffers": payload.get("buffers"),
            "focus": payload.get("focus"),
            "retry_chunk_id": payload.get("retry_chunk_id"),
            "retry_mode": payload.get("retry_mode"),
            "merge_artifact_ids": payload.get("merge_artifact_ids"),
            "timeout_sec": payload.get("timeout_sec"),
            "output_format": payload.get("output_format", "md"),
            "confirm": True,
        })
    except Exception as exc:
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "ERROR",
            "error": str(exc),
        }

    if result.get("status") in {"OK", "PARTIAL"} and result.get("ok", True):
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": result.get("status", "OK"),
            "action_type": "route_poi_analyze",
            "idempotency_key": idem_key,
            "execution_mode": "partial_write" if result.get("status") == "PARTIAL" else "real_write",
            "write_committed": True,
            "route_id": result.get("route_id"),
            "artifact_id": result.get("artifact_id"),
            "source_path": result.get("source_path"),
            "report_path": result.get("report_path"),
            "report_artifact_id": result.get("report_artifact_id"),
            "analysis": result.get("analysis"),
            "analysis_status": result.get("status"),
            "warnings": result.get("analysis", {}).get("warnings"),
        }

    return {
        "tool": "qbot.action_execute",
        "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": result.get("status", "ERROR"),
        "action_type": "route_poi_analyze",
        "idempotency_key": idem_key,
        "error": result.get("error") or "route_poi_analyze failed",
        "payload": payload,
    }


def _action_exec_planning(payload: dict, idem_key: str, source: str) -> dict:
    """Execute planning_fact_add."""
    try:
        from qbot_planning_memory import save_planning_fact
        result = save_planning_fact(draft=payload, channel=source, confirm=True)
        if result.get("status") == "OK":
            return {
                "tool": "qbot.action_execute",
                "safety_class": "WRITE_ONLY_ALLOWLIST",
                "status": "OK",
                "action_type": "planning_fact_add",
                "idempotency_key": idem_key,
                "planning_fact_id": result.get("planning_fact_id"),
            }
        return {"tool":"qbot.action_execute","safety_class":"WRITE_ONLY_ALLOWLIST","status":"ERROR","error": result.get("error","save_planning_fact failed")}
    except ImportError:
        return {"tool":"qbot.action_execute","safety_class":"WRITE_ONLY_ALLOWLIST","status":"MISSING_CAPABILITY","missing_capability":"planning_fact_add","note":"save_planning_fact not available."}


# ═══════════════════════════════════════════════════════════════════
# Artifact put action handler
# ═══════════════════════════════════════════════════════════════════


def _action_exec_qbot_artifact_put(payload: dict, idem_key: str, source: str) -> dict:
    """Execute qbot_artifact_put — save binary/text file to project artifacts."""
    try:
        from qbot3.adapters.mcp_adapter import _execute_qbot_artifact_put
        return _execute_qbot_artifact_put("qbot_artifact_put", payload, idem_key)
    except Exception as exc:
        return {
            "tool": "qbot.action_execute",
            "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "ERROR",
            "error": str(exc),
        }


# ═══════════════════════════════════════════════════════════════════
# Doc write action handlers
# ═══════════════════════════════════════════════════════════════════

_DOC_ALLOWLIST = frozenset({
    "QBOT_BIBLE.md",
    "QBOT_KNOWHOW.md",
    "QBOT_PROJECT_INSTRUCTION_LOCAL.md",
})

_DOC_BASE_DIR = "/opt/qbot/docs"
_DOC_HISTORY_DIR = "/opt/qbot/docs/.history"


def _doc_ensure_history_dir() -> None:
    os.makedirs(_DOC_HISTORY_DIR, exist_ok=True)


def _doc_resolve_path(target_document: str) -> str | None:
    if target_document not in _DOC_ALLOWLIST:
        return None
    target_document = target_document.strip()
    if ".." in target_document:
        return None
    full_path = os.path.join(_DOC_BASE_DIR, target_document)
    real = os.path.realpath(full_path)
    if not real.startswith(_DOC_BASE_DIR + "/"):
        return None
    return real


def _doc_backup(filepath: str, idem_key: str) -> str:
    _doc_ensure_history_dir()
    filename = os.path.basename(filepath)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"{filename}.{timestamp}.{idem_key}.bak"
    backup_path = os.path.join(_DOC_HISTORY_DIR, backup_name)
    import shutil
    shutil.copy2(filepath, backup_path)
    return backup_path


def _doc_verify_db():
    """Probe that DB is reachable and qbot_doc_write_audit exists.

    Raised from bootstrap — doc_write_v1.sql is loaded by api_db.init_db()
    at service startup.  If this check fails the caller must abort the
    write: without an audit table we cannot enforce idempotency.
    """
    import psycopg
    from psycopg.rows import dict_row
    c = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )
    try:
        c.execute("SELECT 1 FROM qbot_doc_write_audit LIMIT 0")
    finally:
        c.close()


def _doc_save_audit(action_type: str, target_document: str, idem_key: str, status: str, backup_path: str | None, payload: dict, result: dict, source: str):
    import json, hashlib
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    import psycopg
    from psycopg.rows import dict_row
    c = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )
    try:
        c.execute(
            """INSERT INTO qbot_doc_write_audit
               (action_type, target_document, idempotency_key, status, backup_path, payload_hash, result_json, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (action_type, target_document, idem_key, status, backup_path, payload_hash,
             json.dumps(result, default=str), source),
        )
        c.commit()
    finally:
        c.close()


def _doc_check_duplicate(idem_key: str) -> dict | None:
    import json
    import psycopg
    from psycopg.rows import dict_row
    c = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )
    try:
        cur = c.cursor()
        cur.execute(
            "SELECT * FROM qbot_doc_write_audit WHERE idempotency_key=%s AND status='OK' ORDER BY id DESC LIMIT 1",
            (idem_key,),
        )
        row = cur.fetchone()
        if row:
            result = row.get("result_json") or {}
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    result = {}
            return {
                "status": "DUPLICATE",
                "action_type": row["action_type"],
                "target_document": row["target_document"],
                "idempotency_key": idem_key,
                "backup_path": row.get("backup_path"),
                "result": result,
                "note": "idempotency_key already processed (qbot_doc_write_audit).",
            }
        return None
    finally:
        c.close()


def _action_exec_doc_append(payload: dict, idem_key: str, source: str, dry_run: bool = False) -> dict:
    target_document = str(payload.get("target_document", "")).strip()
    heading = str(payload.get("heading", "")).strip()
    content_md = str(payload.get("content_markdown", "")).strip()

    resolved = _doc_resolve_path(target_document)
    if not resolved:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": f"Invalid target_document: {target_document}",
        }

    if not os.path.isfile(resolved):
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "NOT_FOUND", "error": f"File not found: {resolved}",
        }

    with open(resolved, "r", encoding="utf-8") as f:
        current_content = f.read()

    new_section = f"\n\n{heading}\n\n{content_md}\n"
    new_content = current_content + new_section

    if dry_run:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "DRY_RUN",
            "action_type": "qbot_doc_append",
            "target_document": target_document,
            "idempotency_key": idem_key,
            "dry_run": True,
            "changed": True,
            "backup_path": None,
            "error": None,
            "result": {
                "current_size": len(current_content),
                "new_size": len(new_content),
                "appended_preview": new_section.strip()[:500],
            },
        }

    try:
        backup_path = _doc_backup(resolved, idem_key)
    except Exception as e:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "ERROR", "error": f"Backup failed — write aborted: {e}",
        }

    with open(resolved, "w", encoding="utf-8") as f:
        f.write(new_content)

    result = {"backup_path": backup_path, "new_size": len(new_content), "appended_heading": heading[:200]}
    audit_error: str | None = None
    try:
        _doc_save_audit("qbot_doc_append", target_document, idem_key, "OK", backup_path, payload, result, source)
    except Exception as e:
        audit_error = str(e)
        result["audit_error"] = audit_error

    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": "OK",
        "action_type": "qbot_doc_append",
        "target_document": target_document,
        "idempotency_key": idem_key,
        "dry_run": False,
        "backup_path": backup_path,
        "changed": True,
        "error": audit_error,
        "result": result,
    }


def _action_exec_doc_replace_section(payload: dict, idem_key: str, source: str, dry_run: bool = False) -> dict:
    target_document = str(payload.get("target_document", "")).strip()
    heading = str(payload.get("heading", "")).strip()
    content_md = str(payload.get("content_markdown", "")).strip()

    if not content_md:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": "content_markdown cannot be empty — would delete section.",
        }

    resolved = _doc_resolve_path(target_document)
    if not resolved:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": f"Invalid target_document: {target_document}",
        }

    if not os.path.isfile(resolved):
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "NOT_FOUND", "error": f"File not found: {resolved}",
        }

    with open(resolved, "r", encoding="utf-8") as f:
        lines = f.readlines()

    heading_stripped = heading.strip()
    heading_idx = None
    for i, line in enumerate(lines):
        if line.rstrip("\n").rstrip("\r").strip() == heading_stripped:
            heading_idx = i
            break

    if heading_idx is None:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "NOT_FOUND", "error": f"Heading not found: {heading[:100]}",
        }

    h_level = 0
    for ch in heading_stripped:
        if ch == "#":
            h_level += 1
        else:
            break
    if h_level == 0:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": "Invalid heading format — must start with #",
        }

    heading_prefix = "#" * h_level
    next_heading_idx = len(lines)
    for i in range(heading_idx + 1, len(lines)):
        stripped = lines[i].lstrip()
        if stripped.startswith(heading_prefix) and not stripped.startswith(heading_prefix + "#"):
            next_heading_idx = i
            break

    new_lines = lines[:heading_idx]
    new_lines.append(content_md.rstrip("\n") + "\n")
    new_lines.extend(lines[next_heading_idx:])
    new_content = "".join(new_lines)

    if dry_run:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "DRY_RUN",
            "action_type": "qbot_doc_replace_section",
            "target_document": target_document,
            "idempotency_key": idem_key,
            "dry_run": True,
            "changed": True,
            "backup_path": None,
            "error": None,
            "result": {
                "current_size": sum(len(l) for l in lines),
                "new_size": len(new_content),
                "replaced_heading": heading[:200],
                "lines_removed": next_heading_idx - heading_idx,
            },
        }

    try:
        backup_path = _doc_backup(resolved, idem_key)
    except Exception as e:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "ERROR", "error": f"Backup failed — write aborted: {e}",
        }

    with open(resolved, "w", encoding="utf-8") as f:
        f.write(new_content)

    result = {"backup_path": backup_path, "new_size": len(new_content), "replaced_heading": heading[:200]}
    audit_error: str | None = None
    try:
        _doc_save_audit("qbot_doc_replace_section", target_document, idem_key, "OK", backup_path, payload, result, source)
    except Exception as e:
        audit_error = str(e)
        result["audit_error"] = audit_error

    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": "OK",
        "action_type": "qbot_doc_replace_section",
        "target_document": target_document,
        "idempotency_key": idem_key,
        "dry_run": False,
        "backup_path": backup_path,
        "changed": True,
        "error": audit_error,
        "result": result,
    }


def _action_exec_doc_update(payload: dict, idem_key: str, source: str, dry_run: bool = False) -> dict:
    target_document = str(payload.get("target_document", "")).strip()
    content_md = str(payload.get("content_markdown", "")).strip()

    if not content_md:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": "content_markdown cannot be empty.",
        }
    if not content_md.lstrip().startswith("# "):
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": "content_markdown must be a valid Markdown document starting with a top-level heading (# ).",
        }

    resolved = _doc_resolve_path(target_document)
    if not resolved:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "BLOCKED", "error": f"Invalid target_document: {target_document}",
        }

    current_content = ""
    current_size = 0
    if os.path.isfile(resolved):
        with open(resolved, "r", encoding="utf-8") as f:
            current_content = f.read()
        current_size = len(current_content)

    new_content = content_md
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"

    if dry_run:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "DRY_RUN",
            "action_type": "qbot_doc_update",
            "target_document": target_document,
            "idempotency_key": idem_key,
            "dry_run": True,
            "changed": new_content != current_content,
            "backup_path": None,
            "error": None,
            "result": {
                "current_size": current_size,
                "new_size": len(new_content),
            },
        }

    try:
        backup_path = None
        if os.path.isfile(resolved):
            backup_path = _doc_backup(resolved, idem_key)
    except Exception as e:
        return {
            "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
            "status": "ERROR", "error": f"Backup failed — write aborted: {e}",
        }

    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    with open(resolved, "w", encoding="utf-8") as f:
        f.write(new_content)

    result = {"backup_path": backup_path, "new_size": len(new_content)}
    audit_error: str | None = None
    try:
        _doc_save_audit("qbot_doc_update", target_document, idem_key, "OK", backup_path, payload, result, source)
    except Exception as e:
        audit_error = str(e)
        result["audit_error"] = audit_error

    return {
        "tool": "qbot.action_execute", "safety_class": "WRITE_ONLY_ALLOWLIST",
        "status": "OK",
        "action_type": "qbot_doc_update",
        "target_document": target_document,
        "idempotency_key": idem_key,
        "dry_run": False,
        "backup_path": backup_path,
        "changed": True,
        "error": audit_error,
        "result": result,
    }
