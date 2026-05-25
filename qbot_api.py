#!/usr/bin/env python3
"""Cienka warstwa FastAPI Q — /health, /q."""
from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request

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


def _tool_qbot_status(_args: dict | None = None) -> dict[str, Any]:
    try:
        hostname = subprocess.run(
            ["hostname"], capture_output=True, text=True, timeout=2
        ).stdout.strip()
    except Exception:
        hostname = "unknown"

    return {
        "tool": "qbot_status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": hostname,
        "python": platform.python_version(),
        "pid": os.getpid(),
    }


_SERVICES = [
    "q-bot.service",
    "qbot-qlab-server.service",
    "qbot-api.service",
    "postgresql.service",
]


def _tool_qbot_services_status(_args: dict | None = None) -> dict[str, Any]:
    results = []
    for svc in _SERVICES:
        try:
            proc = subprocess.run(
                ["systemctl", "show", svc,
                 "--property=ActiveState,SubState,LoadState,UnitFileState"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:
            results.append({"name": svc, "error": str(exc), "status": "ERROR"})
            continue

        props = {}
        for line in proc.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v

        active_state = props.get("ActiveState", "unknown")
        sub_state = props.get("SubState", "unknown")
        load_state = props.get("LoadState", "unknown")
        unit_file_state = props.get("UnitFileState")

        if active_state == "active" and sub_state in ("running", "exited"):
            status = "OK"
        elif active_state == "active":
            status = "WARN"
        else:
            status = "ERROR"

        entry: dict[str, Any] = {
            "name": svc,
            "active_state": active_state,
            "sub_state": sub_state,
            "load_state": load_state,
            "status": status,
        }
        if unit_file_state is not None:
            entry["unit_file_state"] = unit_file_state
        results.append(entry)

    return {"tool": "qbot_services_status", "services": results}


def _tool_qbot_recent_tool_calls(args: dict | None = None) -> dict[str, Any]:
    limit_raw = (args or {}).get("limit", 10)
    try:
        limit = int(limit_raw)
    except (ValueError, TypeError):
        return {
            "tool": "qbot_recent_tool_calls",
            "error": f"invalid limit: {limit_raw!r}, must be integer",
        }
    if limit < 1:
        return {
            "tool": "qbot_recent_tool_calls",
            "error": f"limit {limit} below minimum 1",
        }
    if limit > 50:
        return {
            "tool": "qbot_recent_tool_calls",
            "error": f"limit {limit} above maximum 50",
        }

    _db_check()
    if not DB_AVAILABLE:
        return {
            "tool": "qbot_recent_tool_calls",
            "error": "database unavailable",
        }

    try:
        import api_db
        rows = api_db.select_tool_calls(limit)
    except Exception as exc:
        return {
            "tool": "qbot_recent_tool_calls",
            "error": f"query failed: {exc}",
        }

    entries = []
    for r in rows:
        entry = {
            "id": r["id"],
            "tool": r["tool"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        result = r.get("result")
        if isinstance(result, str):
            import json
            try:
                result = json.loads(result)
            except Exception:
                pass
        if isinstance(result, dict):
            entry["status"] = "ok" if "error" not in result else "error"
        else:
            entry["status"] = "ok"
        entries.append(entry)

    return {"tool": "qbot_recent_tool_calls", "count": len(entries), "calls": entries}


TOOLS: dict[str, Any] = {
    "qbot_status": _tool_qbot_status,
    "qbot_services_status": _tool_qbot_services_status,
    "qbot_recent_tool_calls": _tool_qbot_recent_tool_calls,
}


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

    if tool in TOOLS:
        result = TOOLS[tool](args)
    else:
        result = {"error": f"unknown tool: {tool}", "available": sorted(TOOLS.keys())}

    warnings: list[str] = []
    _db_check()
    if DB_AVAILABLE:
        try:
            import api_db
            api_db.save_tool_call(tool, args, result)
        except Exception as exc:
            warnings.append(f"db save failed: {exc}")
    else:
        warnings.append("database unavailable, call not logged")

    return {"result": result, "warnings": warnings}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Q API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
