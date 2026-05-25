#!/usr/bin/env python3
"""Cienka warstwa FastAPI Q — /health, /q."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from qbot_mcp_adapter import (
    _dispatch_local_qbot_tool,
    _tool_qbot_mcp_status,
    _tool_qbot_mcp_tools_list,
    handle_mcp_request,
    _validate_mcp_access,
)

load_dotenv(Path(__file__).parent / ".env")

DB_AVAILABLE = False

app = FastAPI(title="Q API", version="0.1.0")


def _db_check():
    global DB_AVAILABLE
    try:
        import api_db
        DB_AVAILABLE = api_db.ping()
    except Exception:
        DB_AVAILABLE = False


@app.on_event("startup")
def startup():
    try:
        import api_db
        api_db.init_db()
    except Exception:
        pass
    _db_check()


@app.get("/health")
def health():
    _db_check()
    return {
        "status": "ok",
        "db": "connected" if DB_AVAILABLE else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/q")
async def q_endpoint(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {
            "result": {"error": "invalid JSON"},
            "warnings": [],
        }

    tool = (payload or {}).get("tool", "")
    args = payload.get("args", {})
    result, warnings = _dispatch_local_qbot_tool(tool, args, source="q")
    if not DB_AVAILABLE:
        warnings.append("database unavailable, call not logged")

    return {"result": result, "warnings": warnings}


@app.post("/telegram/webhook/{webhook_secret}")
async def telegram_webhook(webhook_secret: str, request: Request):
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected_secret or webhook_secret != expected_secret:
        return JSONResponse(content={"status": "forbidden", "detail": "invalid webhook secret"}, status_code=403)

    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret_header and secret_header != expected_secret:
        return JSONResponse(content={"status": "forbidden", "detail": "invalid secret header"}, status_code=403)

    try:
        update = await request.json()
    except Exception:
        return JSONResponse(content={"status": "error", "detail": "invalid JSON"}, status_code=400)

    from qbot_telegram_client import validate_update, extract_chat_id, extract_message_text, is_allowed_chat
    valid, err = validate_update(update)
    if not valid:
        return JSONResponse(content={"status": "ignored", "detail": err}, status_code=200)

    chat_id = extract_chat_id(update)
    if not chat_id or not is_allowed_chat(chat_id):
        return JSONResponse(content={"status": "forbidden", "detail": f"chat_id not allowed"}, status_code=403)

    text = extract_message_text(update).strip()
    if not text:
        return JSONResponse(content={"status": "ignored", "detail": "empty message"}, status_code=200)

    cmd = text.strip().lower()
    if not cmd.startswith("/"):
        cmd = "/ask " + text

    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    query = parts[1].strip() if len(parts) > 1 else ""

    result: dict = {}

    if command == "/start":
        from qbot_telegram_tools import _tool_qbot_telegram_command_help
        result = {"command": "/start", "response": _tool_qbot_telegram_command_help()}
    elif command == "/help":
        from qbot_telegram_tools import _tool_qbot_telegram_command_help
        result = {"command": "/help", "response": _tool_qbot_telegram_command_help()}
    elif command == "/status":
        from qbot_telegram_tools import _tool_qbot_telegram_status
        result = {"command": "/status", "response": _tool_qbot_telegram_status()}
    elif command == "/ready":
        from qbot_operator_tools import _tool_qbot_readiness_report
        result = {"command": "/ready", "response": _tool_qbot_readiness_report()}
    elif command == "/smoke":
        from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
        result = {"command": "/smoke", "response": _tool_qbot_operator_final_smoke_test()}
    elif command == "/backup":
        from qbot_ops_tools import _tool_qbot_backup_status
        result = {"command": "/backup", "response": _tool_qbot_backup_status()}
    elif command == "/errors":
        from qbot_operator_tools import _tool_qbot_error_summary
        result = {"command": "/errors", "response": _tool_qbot_error_summary({"limit": 20})}
    elif command == "/takeover":
        from qbot_legacy_cutover_tools import _tool_qbot_legacy_takeover_status
        result = {"command": "/takeover", "response": _tool_qbot_legacy_takeover_status()}
    elif command == "/ask":
        if not query:
            result = {"command": "/ask", "response": {"status": "error", "error": "empty query"}}
        else:
            from qbot_query_processor import process_query
            result = {"command": "/ask", "response": process_query(query, execute=True)}
    else:
        result = {"command": command, "response": {"status": "unknown_command", "text": text}}

    return JSONResponse(content={"status": "ok", "received": True, "command": command, "result": result}, status_code=200)


def _mcp_response(payload: dict | None, status_code: int, headers: dict[str, str] | None = None):
    headers = headers or {}
    if payload is None:
        return JSONResponse(content=None, status_code=status_code, headers=headers)
    return JSONResponse(content=payload, status_code=status_code, headers=headers)


def _mcp_auth_guard(request: Request):
    ok, err = _validate_mcp_access({k.lower(): v for k, v in request.headers.items()})
    if ok:
        return None
    return JSONResponse(
        content={"status": "error", "detail": err or "unauthorized"},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.get("/mcp/")
@app.get("/mcp")
def mcp_root(request: Request):
    denied = _mcp_auth_guard(request)
    if denied is not None:
        return denied
    status = _tool_qbot_mcp_status({})
    tools = _tool_qbot_mcp_tools_list({})
    return {
        "status": status.get("status", "UNKNOWN"),
        "service": "qbot-mcp-adapter",
        "version": "v1",
        "health": "/mcp/health",
        "tools": "/mcp/tools",
        "public_url": status.get("public_url"),
        "auth_configured": status.get("auth_configured"),
        "exposed_tools": status.get("exposed_tools", []),
        "tool_count": tools.get("count", 0),
    }


@app.get("/mcp/health")
@app.get("/mcp/health/")
def mcp_health(request: Request):
    denied = _mcp_auth_guard(request)
    if denied is not None:
        return denied
    return _tool_qbot_mcp_status({})


@app.get("/mcp/tools")
@app.get("/mcp/tools/")
def mcp_tools(request: Request):
    denied = _mcp_auth_guard(request)
    if denied is not None:
        return denied
    return _tool_qbot_mcp_tools_list({})


@app.post("/mcp/")
@app.post("/mcp")
async def mcp_post(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}, status_code=400)

    response_payload, status_code, headers = handle_mcp_request(payload if isinstance(payload, dict) else {}, dict(request.headers))
    return _mcp_response(response_payload, status_code, headers)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Q API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
