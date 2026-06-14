"""Shared fallback policy for qbot.query and planner routing."""

from __future__ import annotations

import os
from typing import Any

_ROUTE_DOMAIN_HINTS = (
    "rwgps",
    "ridewithgps",
    "ride with gps",
    "rout",
    "tras",
    "gpx",
    "stage",
    "etap",
    "profil",
    "profile",
)


def albert_fallback_disabled() -> bool:
    return os.getenv("QBOT_DISABLE_ALBERT_FALLBACK") == "1"


def is_route_domain_query(question: str) -> bool:
    ql = (question or "").lower()
    return any(hint in ql for hint in _ROUTE_DOMAIN_HINTS)


def planner_unavailable_response(
    question: str,
    *,
    intent: str = "planner_routes",
    source: str = "qbot.query",
    fallback_reason: str | None = None,
    status: str = "no_data",
) -> dict[str, Any]:
    reason = fallback_reason or (
        "QBOT_DISABLE_ALBERT_FALLBACK=1" if albert_fallback_disabled() else "planner_unavailable"
    )
    answer = "Planner jest niedostępny dla tego zapytania. Fallback jest wyłączony."
    if is_route_domain_query(question):
        answer = "Planner tras jest niedostępny. Fallback jest wyłączony."
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


def should_use_albert_fallback(question: str) -> bool:
    return not albert_fallback_disabled() and not is_route_domain_query(question)
