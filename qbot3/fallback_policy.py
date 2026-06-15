"""Shared fallback policy for qbot.query and planner routing."""

from __future__ import annotations

import os
from typing import Any


def albert_hard_killed() -> bool:
    """Awaryjny globalny wylacznik Alberta (domyslnie OFF). Gdy =1, Albert
    nie dziala NIGDZIE, niezaleznie od domeny."""
    return os.getenv("QBOT_ALBERT_HARD_KILL") == "1"


def planner_unavailable_response(
    question: str,
    *,
    intent: str = "planner_routes",
    source: str = "qbot.query",
    fallback_reason: str | None = None,
    status: str = "no_data",
) -> dict[str, Any]:
    reason = fallback_reason or "albert_hard_killed"
    answer = "Planner jest niedostępny dla tego zapytania. Fallback jest wyłączony."
    return {
        "tool": source,
        "status": status,
        "engine": "query_vnext",
        "intent": intent,
        "answer": answer,
        "error": "planner_unavailable",
        "data": {},
        "sources_used": [],
        "missing_sources": [],
        "freshness": {},
        "action_draft": None,
        "fallback_reason": reason,
        "warnings": ["planner_unavailable"],
    }
