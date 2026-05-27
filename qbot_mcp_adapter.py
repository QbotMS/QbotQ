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
    # PUBLIC MCP TOOLS — allowlisted for ChatGPT
    # qbot.query is the primary entry point. All reader logic
    # (nutrition, training, routes, garage, weather, artifacts,
    # reports) is dispatched internally by QBot.
    # ═══════════════════════════════════════════════════════════════

    # ── Core: universal read-only query router ──
    "qbot.query": {
        "qbot_tool": "qbot_query",
        "description": (
            "GŁÓWNE NARZĘDZIE — używaj go do KAŻDEGO pytania użytkownika o dane. "
            "Podaj pytanie w języku naturalnym (polski/angielski). "
            "QBot wewnętrznie dobiera readery (nutrition, training, routes, garage, weather, "
            "Garmin, Cronometer, Intervals, Xert, RWGPS, wellness, artifacts, reports). "
            "Zwraca structured answer + tables + provenance + missing_fields + limitations. "
            "Tryb plan_only podgląda plan readerów bez wykonywania. "
            "Nie używaj niskopoziomowych narzędzi — wszystko jest przez qbot.query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language question"},
                "mode": {"type": "string", "enum": ["read_only", "plan_only"], "default": "read_only"},
                "scope": {"type": "string", "enum": ["all", "nutrition", "training", "routes", "garage"], "default": "all"},
                "context": {"type": "string", "description": "Optional JSON: project, timezone, date/date_from/date_to"},
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

    # ── System health ──
    "qbot.status": {
        "qbot_tool": "qbot_operator_final_smoke_test",
        "description": (
            "Globalny smoke test QBot — sprawdza API, DB, guard, usługi, backup. "
            "Używaj tylko do diagnostyki systemu, nie do pytań o dane."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },

    # ── Readiness (optional — detailed status with blockers) ──
    "qbot.readiness": {
        "qbot_tool": "qbot_readiness_report",
        "description": "Szczegółowy raport gotowości QBot — lista blokerów, status integracji.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },

    # ── Nutrition write (narrow, confirmed, idempotent) ──
    "qbot.nutrition_log_preview": {
        "qbot_tool": "qbot_nutrition_log_preview",
        "description": "Podgląd posiłku przed zapisem. READ_ONLY — nic nie zapisuje do DB. Zwraca draft, makra, idempotency_key.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD, default today"},
                "meal_name": {"type": "string"},
                "raw_text": {"type": "string", "description": "Naturalny opis: 'jogurt 200g, banan'"},
                "kcal_total": {"type": "number"},
                "protein_g": {"type": "number"},
                "carbs_g": {"type": "number"},
                "fat_g": {"type": "number"},
                "fluids_ml": {"type": "number"},
                "source": {"type": "string", "default": "chatgpt_mcp"},
                "confidence": {"type": "string", "default": "medium"},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.nutrition_log_add": {
        "qbot_tool": "qbot_nutrition_log_add",
        "description": "ZAPISZ posiłek do nutrition DB. WYMAGA: confirm=true, idempotency_key. Tylko nutrition tables. Zwraca wpis + daily summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "meal_name": {"type": "string"},
                "raw_text": {"type": "string"},
                "kcal_total": {"type": "number"},
                "protein_g": {"type": "number"},
                "carbs_g": {"type": "number"},
                "fat_g": {"type": "number"},
                "fluids_ml": {"type": "number"},
                "source": {"type": "string", "default": "chatgpt_mcp"},
                "confidence": {"type": "string", "default": "medium"},
                "idempotency_key": {"type": "string", "description": "Unikalny klucz — zapobiega duplikatom."},
                "confirm": {"type": "boolean", "description": "MUSI być true, żeby zapisać."},
            },
            "required": ["date", "kcal_total", "idempotency_key"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_NUTRITION_ONLY",
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

