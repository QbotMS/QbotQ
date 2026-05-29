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

_LOG_DIR = Path(os.getenv("QBOT3_LOG_DIR", "/tmp/qbot3"))
_LOG_FILE = _LOG_DIR / "qbot3_agent.log"


def _ensure_dir() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


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
