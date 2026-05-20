#!/usr/bin/env python3
"""Shared MCP client helpers for QBot local scripts."""
import json
from typing import Any, Callable

import httpx
from qbot_config import MCP_URL

DEFAULT_MCP_URL = MCP_URL
PROTOCOL_VERSION = "2024-11-05"


def _parse_response_text(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            return json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_tool_content(payload: dict[str, Any]) -> Any:
    if payload.get("error"):
        err = payload["error"]
        raise RuntimeError(err.get("message") or str(err))

    content = payload.get("result", {}).get("content", [])
    for block in content:
        if block.get("type") != "text":
            continue
        text = block.get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return None


def mcp_call(
    tool: str,
    args: dict[str, Any] | None = None,
    *,
    client_name: str = "qbot-script",
    client_version: str = "1.0",
    base_url: str = DEFAULT_MCP_URL,
    timeout: float = 30,
    logger: Callable[[str], None] | None = None,
    strict: bool = False,
) -> Any:
    """Call a local QBot MCP tool and return decoded text/JSON content."""
    args = args or {}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    try:
        init = httpx.post(
            base_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": client_name, "version": client_version},
                },
            },
            timeout=15,
        )
        init.raise_for_status()
        sid = init.headers.get("mcp-session-id")
        if sid:
            headers["mcp-session-id"] = sid

        ready = httpx.post(
            base_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
            timeout=15,
        )
        if ready.status_code not in (200, 202):
            ready.raise_for_status()

        response = httpx.post(
            base_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = _parse_response_text(response.text)
        if not payload:
            raise RuntimeError("empty MCP response")
        return _extract_tool_content(payload)
    except Exception as exc:
        if logger:
            logger(f"⚠️  mcp_call({tool}): {exc}")
        if strict:
            raise
        return None
