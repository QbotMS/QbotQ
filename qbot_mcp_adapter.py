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
from qbot_external_llm_tools import _tool_qbot_external_context_bundle
from qbot_external_llm_tools import _tool_qbot_external_tool_plan
from qbot_llm_planner import _tool_qbot_llm_run_query, _tool_qbot_tool_policy_list
from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
from qbot_roadmap_runner import (
    _tool_qbot_roadmap_runner_list_tasks,
    _tool_qbot_roadmap_runner_next_task,
    _tool_qbot_roadmap_runner_status,
)
from qbot_telegram_tools import _tool_qbot_telegram_status
from qbot_assistant_inbox import (
    _tool_qbot_assistant_inbox_list,
    _tool_qbot_assistant_inbox_status,
)
from qbot_route_tools import _tool_qbot_gpx_artifact_parse
from qbot_route_tools import _tool_qbot_route_artifact_enrich
from qbot_route_tools import _tool_qbot_rwgps_artifact_store_status
from qbot_tools import _tool_qbot_status

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "QBot MCP Adapter v1"
MCP_SERVER_VERSION = "1.0.0"
MCP_SESSION_HEADER = "mcp-session-id"

_SESSION_STATE: dict[str, dict[str, Any]] = {}

_MCP_TOOL_MAP: dict[str, dict[str, Any]] = {
    # ── Core / read-only ──
    "qbot.query": {
        "qbot_tool": "qbot_query",
        "description": "Universal read-only query router. QBot classifies intent, selects allowlisted internal readers, executes, and returns structured answer with provenance. No DB writes. ChatGPT should NOT know internal reader names — just ask in natural language.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language question in any language"},
                "mode": {"type": "string", "enum": ["read_only", "plan_only"], "default": "read_only", "description": "read_only: execute readers and return data. plan_only: return which readers would be used, without executing."},
                "scope": {"type": "string", "enum": ["all", "nutrition", "training", "routes", "garage"], "default": "all", "description": "Limit to specific domain."},
                "context": {"type": "string", "description": "Optional hint: timezone, project name, location"},
                "max_rows": {"type": "integer", "minimum": 10, "maximum": 1000, "default": 500},
                "include_provenance": {"type": "boolean", "default": True},
                "include_missing": {"type": "boolean", "default": True},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.ask": {
        "qbot_tool": "qbot_llm_run_query",
        "description": "Safe question routing through QBot LLM policy/planner. Use qbot.query for direct data reads.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "execute": {"type": "boolean", "default": False},
                "style": {"type": "string", "enum": ["concise", "operator", "detailed"], "default": "concise"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    # ── System status ──
    "qbot.status": {
        "qbot_tool": "qbot_operator_final_smoke_test",
        "description": "Final operational smoke test for QBot.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.readiness": {
        "qbot_tool": "qbot_readiness_report",
        "description": "Readiness report for the local QBot stack.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.tool_policy": {
        "qbot_tool": "qbot_tool_policy_list",
        "description": "List QBot tool policy metadata.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    # ── Operator ──
    "qbot.runbook": {
        "qbot_tool": "qbot_operator_runbook",
        "description": "Execute or preview a curated QBot operator runbook.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "execute": {"type": "boolean", "default": False},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.context_bundle": {
        "qbot_tool": "qbot_external_context_bundle",
        "description": "Build a sanitized context bundle for external ChatGPT usage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 20000, "default": 12000},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    # ── Artifacts ──
    "qbot.artifact_read": {
        "qbot_tool": "qbot_artifact_read",
        "description": "Read a QBot artifact file by relative path (e.g. 'exports/rwgps/rwgps_55256628.gpx'). Returns content as text or base64.",
        "input_schema": {
            "type": "object",
            "properties": {
                "relative_path": {"type": "string"},
                "return_mode": {"type": "string", "enum": ["text", "base64"], "default": "text"},
            },
            "required": ["relative_path"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifact_create": {
        "qbot_tool": "qbot_artifact_create",
        "description": "Create a safe PostgreSQL artifact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_type": {"type": "string", "default": "report"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source_plan_id": {"type": "integer"},
            },
            "required": ["title", "content"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_SAFE",
        "auth_required": True,
    },
    # ── Task queue ──
    "qbot.task_queue_add": {
        "qbot_tool": "qbot_task_queue_add",
        "description": "Add a task to QBot queue for CLI execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "What to do"},
                "style": {"type": "string", "default": "short"},
                "tools_to_use": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_SAFE",
        "auth_required": True,
    },
    "qbot.task_queue_list": {
        "qbot_tool": "qbot_task_queue_list",
        "description": "List tasks in the QBot queue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "default": "pending"},
                "limit": {"type": "integer", "default": 50},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.task_queue_next": {
        "qbot_tool": "qbot_task_queue_next",
        "description": "Get the next pending task for CLI execution.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.task_queue_status": {
        "qbot_tool": "qbot_task_queue_status",
        "description": "Update task status after execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string", "enum": ["pass", "blocked", "fail", "in_progress"]},
                "result_summary": {"type": "string"},
                "error": {"type": "string"},
            },
            "required": ["task_id", "status"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_SAFE",
        "auth_required": True,
    },
    # ── RWGPS exports ──
    "qbot.rwgps_route_export_file": {
        "qbot_tool": "qbot_rwgps_route_export_file",
        "description": "Export a RWGPS route to a local GPX/TCX/JSON artifact file. Supports return_mode: metadata, text, base64.",
        "input_schema": {
            "type": "object",
            "properties": {
                "route_id": {"type": "string"},
                "format": {"type": "string", "enum": ["gpx", "tcx", "json"], "default": "gpx"},
                "return_mode": {"type": "string", "enum": ["metadata", "text", "base64"], "default": "metadata"},
            },
            "required": ["route_id"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_route_export_links": {
        "qbot_tool": "qbot_rwgps_route_export_links",
        "description": "Get RWGPS export availability and download links for GPX/TCX/FIT by route_id.",
        "input_schema": {
            "type": "object",
            "properties": {"route_id": {"type": "string"}},
            "required": ["route_id"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    # ── Technical route tools ──
    "qbot.gpx_artifact_parse": {
        "qbot_tool": "qbot_gpx_artifact_parse",
        "description": "Parse a stored GPX artifact and return normalized track metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string"},
                "return_mode": {"type": "string", "enum": ["summary"], "default": "summary"},
            },
            "required": ["artifact_path"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.route_artifact_enrich": {
        "qbot_tool": "qbot_route_artifact_enrich",
        "description": "Enrich a route artifact with summary metadata and optional surface profile.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string"},
                "enrich": {"type": "array", "items": {"type": "string"}, "default": ["summary"]},
                "surface_source": {"type": "string", "enum": ["auto", "gpx", "rwgps", "osm", "unknown"], "default": "auto"},
                "sample_every_m": {"type": "integer", "minimum": 100, "maximum": 5000, "default": 100},
                "return_mode": {"type": "string", "enum": ["summary"], "default": "summary"},
            },
            "required": ["artifact_path"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
}

# Internal readers (not exposed as MCP tools, accessed via qbot.query):
#   GarminReader, CronometerReader, NutritionDBReader, IntervalsReader, XertReader,
#   RWGPSReader, GarageReader, GearReader, WeatherReader, DailyReportReader,
#   RideReportReader, WellnessReader, ArtifactIndexReader, ProjectReader



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
        "qbot_external_context_bundle": _tool_qbot_external_context_bundle,
        "qbot_artifact_create": _tool_qbot_artifact_create,
        "qbot_artifact_list": _tool_qbot_artifact_list,
        "qbot_artifact_get": _tool_qbot_artifact_get,
        "qbot_gpx_artifact_parse": _tool_qbot_gpx_artifact_parse,
        "qbot_route_artifact_enrich": _tool_qbot_route_artifact_enrich,
        "qbot_rwgps_artifact_store_status": _tool_qbot_rwgps_artifact_store_status,
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
        from datetime import date as _date, datetime as _datetime
        if isinstance(obj, (_datetime, _date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=_json_default)}]}


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
    if meta.get("auth_required", False) and _token_configured() and not _auth_header_ok(headers):
        return False, "missing or invalid MCP token"
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

        if name == "qbot.ask":
            query = str(clean_args.get("query", "")).strip()
            execute = bool(clean_args.get("execute", False))
            style = str(clean_args.get("style", "concise"))
            if not query:
                result = {"tool": name, "status": "error", "error": "query required"}
            else:
                if execute:
                    result = _tool_qbot_llm_run_query({"query": query, "execute": True})
                else:
                    from qbot_query_processor import process_query
                    result = process_query(query, execute=False)
                result["tool"] = "qbot.ask"
                result["style"] = style
        elif name == "qbot.query":
            query = str(clean_args.get("query", "")).strip()
            if not query:
                result = {"tool": "qbot.query", "status": "error", "error": "query required"}
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
        elif name == "qbot.runbook":
            runbook_name = str(clean_args.get("name", "")).strip()
            execute = bool(clean_args.get("execute", False))
            from qbot_operator_tools import _tool_qbot_operator_runbook
            result = _tool_qbot_operator_runbook({"name": runbook_name, "execute": execute})
            result["tool"] = "qbot.runbook"
        elif name == "qbot.context_bundle":
            topic = str(clean_args.get("topic", "")).strip()
            max_chars = clean_args.get("max_chars", 12000)
            if not topic:
                result = {"tool": "qbot.context_bundle", "status": "error", "error": "topic required"}
            else:
                result = _tool_qbot_external_context_bundle({"topic": topic, "max_chars": max_chars})
                result["tool"] = "qbot.context_bundle"
        elif name == "qbot.rwgps_route_export_file":
            route_id = str(clean_args.get("route_id", "")).strip()
            fmt = str(clean_args.get("format", "gpx")).strip().lower() or "gpx"
            if not route_id:
                result = {"tool": "qbot.rwgps_route_export_file", "status": "error", "error": "route_id required"}
            else:
                from tools.rwgps.client import export_route_to_artifact as rwgps_export_route_to_artifact
                return_mode = clean_args.get("return_mode")
                result = rwgps_export_route_to_artifact(route_id, fmt=fmt, return_mode=return_mode)
                result["tool"] = "qbot.rwgps_route_export_file"
        elif name == "qbot.artifact_read":
            relative_path = str(clean_args.get("relative_path", "")).strip()
            return_mode = str(clean_args.get("return_mode", "text")).strip().lower() or "text"
            if not relative_path:
                result = {"tool": "qbot.artifact_read", "status": "error", "error": "relative_path required"}
            else:
                from mcp_server import validate_artifact_relative_path, ARTIFACT_ROOT
                try:
                    normalized = validate_artifact_relative_path(relative_path)
                    artifact_path = ARTIFACT_ROOT / normalized
                    if not artifact_path.exists():
                        result = {"tool": "qbot.artifact_read", "status": "NOT_FOUND", "error": "artifact does not exist", "relative_path": relative_path}
                    elif not os.access(artifact_path, os.R_OK):
                        result = {"tool": "qbot.artifact_read", "status": "PERMISSION_DENIED", "error": "artifact not readable", "relative_path": relative_path}
                    else:
                        data = artifact_path.read_bytes()
                        if return_mode == "base64":
                            import base64
                            result = {
                                "tool": "qbot.artifact_read",
                                "status": "ok",
                                "relative_path": relative_path,
                                "size_bytes": len(data),
                                "content_base64": base64.b64encode(data).decode("ascii"),
                            }
                        else:
                            text = data.decode("utf-8", errors="replace")
                            result = {
                                "tool": "qbot.artifact_read",
                                "status": "ok",
                                "relative_path": relative_path,
                                "size_bytes": len(data),
                                "content": text,
                            }
                except ValueError as exc:
                    result = {"tool": "qbot.artifact_read", "status": "INVALID_PATH", "error": str(exc), "relative_path": relative_path}
                except FileNotFoundError as exc:
                    result = {"tool": "qbot.artifact_read", "status": "NOT_FOUND", "error": str(exc), "relative_path": relative_path}
                except PermissionError as exc:
                    result = {"tool": "qbot.artifact_read", "status": "PERMISSION_DENIED", "error": str(exc), "relative_path": relative_path}
        elif name == "qbot.artifact_create" and not _token_configured():
            result = {
                "tool": name,
                "status": "BLOCKED",
                "execute": False,
                "policy_status": "BLOCKED",
                "reason": "MCP token not configured",
            }
        else:
            tool_args = dict(clean_args)
            if name == "qbot.artifact_create":
                if "tags" in tool_args and isinstance(tool_args["tags"], str):
                    tool_args["tags"] = [tool_args["tags"]]
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
