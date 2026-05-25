"""Bezpieczny procesor zapytań naturalnych — reguły intencji."""
from __future__ import annotations

from typing import Any

from qbot_tool_registry import TOOLS

_INTENT_MAP: list[dict[str, Any]] = [
    {
        "keywords": ["stan q", "status q", "self check", "czy działa", "sprawdź wszystko",
                      "czy wszystko ok", "status", "sprawdź stan"],
        "tool": "qbot_api_self_check",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["usługi", "services", "systemd", "czy działa q-bot",
                      "czy działa qlab", "status usług", "service status"],
        "tool": "qbot_services_status",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["ostatnie wywołania", "tool calls", "historia narzędzi",
                      "logi narzędzi", "recent calls", "ostatnie zapytania",
                      "historia", "logi"],
        "tool": "qbot_recent_tool_calls",
        "args": {"limit": 10},
        "confidence": "medium",
    },
    {
        "keywords": ["repo", "git", "czy repo czyste", "status git",
                      "git status", "repo czyste", "branch", "commit"],
        "tool": "qbot_git_status",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["narzędzia", "lista tools", "co umiesz", "available tools",
                      "lista narzędzi", "jakie narzędzia", "co potrafisz",
                      "dostępne", "tools list", "help"],
        "tool": "qbot_api_tools_list",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["baza", "postgres", "db", "tool_calls count",
                      "baza danych", "postgresql", "ile wpisów",
                      "database", "db overview"],
        "tool": "qbot_db_overview",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["system", "vps", "ram", "dysk", "load", "uptime",
                      "serwer", "pamięć", "procesor", "cpu",
                      "system overview", "zasoby"],
        "tool": "qbot_system_overview",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["projekt", "drzewo", "struktura projektu",
                      "struktura katalogów", "drzewo katalogów",
                      "project tree", "katalogi"],
        "tool": "qbot_project_tree",
        "args": {"max_depth": 2},
        "confidence": "medium",
    },
    {
        "keywords": ["pliki projektu", "lista plików", "pliki",
                      "project files", "wszystkie pliki"],
        "tool": "qbot_project_files",
        "args": {},
        "confidence": "medium",
    },
    {
        "keywords": ["commity", "ostatnie commity", "git log",
                      "historia commitów", "recent commits"],
        "tool": "qbot_project_recent_commits",
        "args": {"limit": 10},
        "confidence": "high",
    },
    {
        "keywords": ["diff", "zmiany", "co zmienione", "zmodyfikowane",
                      "niezapisane", "working changes"],
        "tool": "qbot_project_diff_summary",
        "args": {},
        "confidence": "high",
    },
    {
        "keywords": ["guard", "naruszenia", "czy bezpiecznie",
                      "sprawdź zasady", "bezpieczeństwo", "guard check",
                      "czy jest bezpiecznie", "security"],
        "tool": "qbot_project_guard_check",
        "args": {},
        "confidence": "high",
    },
]

_EXAMPLES = [
    "sprawdź stan Q",
    "czy repo jest czyste",
    "pokaż ostatnie wywołania narzędzi",
    "jakie narzędzia są dostępne",
    "sprawdź stan bazy danych",
    "jakie jest obciążenie systemu",
    "pokaż drzewo projektu",
    "ostatnie commity",
    "czy są jakieś zmiany",
    "sprawdź bezpieczeństwo",
]


def process_query(query: str) -> dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        return {
            "status": "error",
            "reason": "empty_query",
            "available_examples": _EXAMPLES,
        }

    best = None
    best_score = 0
    for entry in _INTENT_MAP:
        score = 0
        for kw in entry["keywords"]:
            if kw in q:
                score += len(kw)
        if score > best_score:
            best_score = score
            best = entry

    if best is None or best_score == 0:
        return {
            "status": "error",
            "reason": "unknown_intent",
            "available_examples": _EXAMPLES,
        }

    tool_name = best["tool"]
    if tool_name not in TOOLS:
        return {
            "status": "error",
            "reason": f"tool {tool_name} not in registry",
            "available_examples": _EXAMPLES,
        }

    try:
        tool_result = TOOLS[tool_name](best["args"])
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"tool execution failed: {exc}",
            "available_examples": _EXAMPLES,
        }

    return {
        "status": "ok",
        "original_query": query,
        "intent": best["keywords"][0],
        "selected_tool": tool_name,
        "confidence": best["confidence"],
        "tool_result": tool_result,
        "notes": f"matched by keyword score {best_score}",
    }
