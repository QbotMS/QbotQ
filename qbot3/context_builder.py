#!/usr/bin/env python3
"""QBot3 Context Builder — gathers relevant context for Albert.

Selector logic is heuristic but MUST NOT execute business decisions.
It only selects what context to load. The LLM plans the action.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

from qbot3.memory import search_memory


def build_context(user_message: str, mode: str = "read_only") -> dict[str, Any]:
    ql = user_message.lower()
    ctx: dict[str, Any] = {
        "question": user_message,
        "date": date.today().isoformat(),
        "timezone": "Europe/Warsaw",
        "memory": [],
        "relevant_docs": [],
        "system_status": {},
    }

    ctx["project_profile"] = {
        "name": "QBot3 / Albert",
        "version": "qbot3",
        "provider": os.getenv("ALBERT_LLM_PROVIDER", "openai"),
        "qbott3_enabled": os.getenv("QBOT3_ENABLED", "0") == "1",
    }

    ctx["system_rules"] = [
        "Albert is the single decision-making brain. No Python code overrides his tool choices.",
        "qbot.query is for reads and write drafts only.",
        "qbot.action_execute executes writes after safety validation.",
        "Never claim 'dodano', 'zapisano', 'wykonano' for writes — always say 'draft'.",
        "If data is missing, say what's missing and why, not 'I don't have access'.",
        "DB read-only is the default source of truth for ordinary data questions.",
        "Use db_schema_list / db_table_describe when the table is unknown, then db_select_readonly for real records.",
        "For local GPX stage-splitting requests, use route_gpx_split and return generated stage files.",
        "Use only tools from the available tools list — never invent tool names.",
        "If unsure, ask for clarification rather than guessing.",
    ]

    # Memory lookup — lightweight keyword-based selector
    memory_keywords = []
    if any(k in ql for k in ("jadłem", "jadł", "zjadł", "jedzeni", "posiłk", "kalor", "nutrition", "dieta", "makro", "bialk", "wegl", "tłusz")):
        memory_keywords.append("nutrition")
    if any(k in ql for k in ("kalendarz", "calendar", "event", "wydarzen", "przypomn", "reminder", "spotkan")):
        memory_keywords.append("calendar")
    if any(k in ql for k in ("garmin", "xert", "intervals", "trening", "readiness", "wellness", "sen", "sleep", "tęt", "hrv")):
        memory_keywords.append("fitness")
    if any(k in ql for k in ("rwgps", "tras", "route", "gpx", "rower", "bikepack")):
        memory_keywords.append("routes")
    if any(k in ql for k in ("knowhow", "bible", "dokument", "docs", "kanoniczn", "instrukcja", "zasad", "dokumentacj")):
        memory_keywords.append("docs")
    if any(k in ql for k in ("bilans", "kalorii", "kcal", "energy", "energi", "deficyt", "nadwyż")):
        memory_keywords.append("nutrition_balance")

    for kw in memory_keywords:
        mem = search_memory(kw, limit=3)
        if mem:
            ctx["memory"].extend(mem)

    # Docs context — only when user explicitly asks about docs
    if any(k in ql for k in ("knowhow", "bible", "dokument", "kanoniczn", "instrukcja", "zasad")):
        ctx["relevant_docs"] = ["qbot_bible", "qbot_knowhow"]

    # System status — only for status/readiness/diagnostic queries
    if any(k in ql for k in ("status", "readiness", "diagnost", "dlaczego", "problem", "błąd", "error", "nie działa", "co się dzieje")):
        ctx["load_system_status"] = True

    return ctx
