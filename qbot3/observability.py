#!/usr/bin/env python3
"""QBot3 Observability — structured request logging.

Every qbot.query call produces one log entry with:
  request_id, timestamp, provider, model, mode, intent,
  tools_planned, tools_called, fallback_used, status, error_stage, duration_ms

No secrets logged. No full private data unless needed.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 2026-10-04: log przeniesiony z /tmp/qbot3 (znikal przy restarcie serwera) do
# /opt/qbot/logs. Kazdy wpis ma tez pytanie, poczatek odpowiedzi i KAZDE wywolanie
# narzedzia (argumenty, status, blad, skrot wyniku) - zeby twierdzenia Alberta
# (np. "blad parsera FIT") dalo sie sprawdzic po request_id.
_LOG_DIR = Path(os.getenv("QBOT3_LOG_DIR", "/opt/qbot/logs"))
_LOG_FILE = _LOG_DIR / "qbot3_agent.log"
_MAX_BYTES = 20 * 1024 * 1024  # rotacja: > 20 MB -> qbot3_agent.log.1 (jedna kopia)
_ARGS_MAX = 300
_RESULT_MAX = 500


def _ensure_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def _rotate_if_big() -> None:
    try:
        if _LOG_FILE.stat().st_size > _MAX_BYTES:
            os.replace(_LOG_FILE, _LOG_FILE.with_name(_LOG_FILE.name + ".1"))
    except OSError:
        pass


def _clip(value: Any, limit: int) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = repr(value)
    return text if len(text) <= limit else text[:limit] + f"...(+{len(text) - limit})"


def summarize_tool_results(tool_results: list[dict] | None) -> list[dict]:
    """Skrot wywolan narzedzi do logu: narzedzie, argumenty, status, blad, wynik."""
    out: list[dict] = []
    for tr in tool_results or []:
        if not isinstance(tr, dict):
            continue
        data = tr.get("data")
        err = None
        if isinstance(data, dict):
            err = data.get("error") or data.get("error_code") or data.get("warning")
        out.append({
            "tool": tr.get("reader"),
            "args": _clip(tr.get("args", {}), _ARGS_MAX),
            "status": tr.get("status"),
            "error": _clip(err, _ARGS_MAX) if err else None,
            "result": _clip(data, _RESULT_MAX),
        })
    return out


def request_id() -> str:
    return str(uuid.uuid4())[:8]


def log_request(
    req_id: str,
    provider: str,
    model: str | None,
    mode: str,
    intent: str,
    tools_planned: list[str] | None,
    tools_called: list[str] | None,
    fallback_used: bool,
    status: str,
    error_stage: str | None,
    duration_ms: int,
    **extra: Any,
) -> None:
    _ensure_dir()
    entry = {
        "request_id": req_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model or "",
        "mode": mode,
        "intent": intent,
        "tools_planned": tools_planned or [],
        "tools_called": tools_called or [],
        "fallback_used": fallback_used,
        "status": status,
        "error_stage": error_stage or "",
        "duration_ms": duration_ms,
    }
    if extra:
        safe_extra = {k: v for k, v in extra.items() if k not in ("secret", "password", "api_key", "token")}
        entry.update(safe_extra)
    try:
        _rotate_if_big()
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


class Timer:
    def __init__(self) -> None:
        self._start: float | None = None

    def start(self) -> None:
        self._start = time.monotonic()

    def elapsed_ms(self) -> int:
        if self._start is None:
            return 0
        return int((time.monotonic() - self._start) * 1000)
