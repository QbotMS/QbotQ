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


# Compatibility shim for qbot_mcp_adapter import.
# Added because qbot_mcp_adapter imports is_route_domain_query,
# but current fallback_policy.py does not expose it.
def is_route_domain_query(query: str) -> bool:
    q = (query or "").lower()
    route_keywords = (
        "rwgps",
        "ridewithgps",
        "route",
        "trasa",
        "trasy",
        "gpx",
        "profil",
        "nawierzchnia",
        "surface",
        "podjazd",
        "podjazdy",
        "etap",
        "etapy",
    )
    return any(k in q for k in route_keywords)

def should_use_albert_fallback(question: str) -> bool:
    """Compat shim for qbot_mcp_adapter import.
    qbot_api.py imports qbot_mcp_adapter at module load. Albert-first no longer
    uses this for routing, so keep the legacy import alive and return False."""
    return False

