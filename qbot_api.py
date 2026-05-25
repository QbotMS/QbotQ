#!/usr/bin/env python3
"""Cienka warstwa FastAPI Q — /health, /q."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request

from qbot_tool_registry import TOOLS

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
