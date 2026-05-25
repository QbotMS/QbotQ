"""Bezpieczny procesor zapytań z planami wykonania (Tool Execution Plan v1)."""
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
        "required_data": ["API health endpoint", "PostgreSQL connection", "systemd service status", "git repository state"],
        "limitations": ["Only checks local services", "Does not check external APIs like Intervals.icu or Garmin"],
    },
    {
        "keywords": ["usługi", "services", "systemd", "czy działa q-bot",
                      "czy działa qlab", "status usług", "service status"],
        "tool": "qbot_services_status",
        "args": {},
        "confidence": "high",
        "required_data": ["systemd service status for 4 services"],
        "limitations": ["Only checks Q-related services", "Does not report resource usage"],
    },
    {
        "keywords": ["ostatnie wywołania", "tool calls", "historia narzędzi",
                      "logi narzędzi", "recent calls", "ostatnie zapytania",
                      "historia", "logi"],
        "tool": "qbot_recent_tool_calls",
        "args": {"limit": 10},
        "confidence": "medium",
        "required_data": ["PostgreSQL tool_calls table"],
        "limitations": ["Returns at most 50 entries", "Requires database connection"],
    },
    {
        "keywords": ["repo", "git", "czy repo czyste", "status git",
                      "git status", "repo czyste", "branch", "commit"],
        "tool": "qbot_git_status",
        "args": {},
        "confidence": "high",
        "required_data": ["Git repository at /opt/qbot/app"],
        "limitations": ["Only checks local repo", "Requires git safe.directory config for qbot user"],
    },
    {
        "keywords": ["narzędzia", "lista tools", "co umiesz", "available tools",
                      "lista narzędzi", "jakie narzędzia", "co potrafisz",
                      "dostępne", "tools list", "help"],
        "tool": "qbot_api_tools_list",
        "args": {},
        "confidence": "high",
        "required_data": ["Tool registry metadata"],
        "limitations": ["Static listing only", "Does not include detailed usage examples"],
    },
    {
        "keywords": ["baza", "postgres", "db", "tool_calls count",
                      "baza danych", "postgresql", "ile wpisów",
                      "database", "db overview"],
        "tool": "qbot_db_overview",
        "args": {},
        "confidence": "high",
        "required_data": ["PostgreSQL connection", "tool_calls table"],
        "limitations": ["Only reports tool_calls stats", "Does not show raw query results"],
    },
    {
        "keywords": ["system", "vps", "ram", "dysk", "load", "uptime",
                      "serwer", "pamięć", "procesor", "cpu",
                      "system overview", "zasoby"],
        "tool": "qbot_system_overview",
        "args": {},
        "confidence": "high",
        "required_data": ["/proc/uptime", "/proc/loadavg", "/proc/meminfo", "df output", "systemd status"],
        "limitations": ["Read-only OS metrics", "No per-process detail", "No network I/O stats"],
    },
    {
        "keywords": ["projekt", "drzewo", "struktura projektu",
                      "struktura katalogów", "drzewo katalogów",
                      "project tree", "katalogi"],
        "tool": "qbot_project_tree",
        "args": {"max_depth": 2},
        "confidence": "medium",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Max depth 4", "Skips .git, .venv, __pycache__, logs, outgoing", "Does not read file contents"],
    },
    {
        "keywords": ["pliki projektu", "lista plików", "pliki",
                      "project files", "wszystkie pliki"],
        "tool": "qbot_project_files",
        "args": {},
        "confidence": "medium",
        "required_data": ["Filesystem at /opt/qbot/app"],
        "limitations": ["Max 200 files", "Skips .git, .venv, __pycache__, logs, outgoing", "Does not read file contents"],
    },
    {
        "keywords": ["commity", "ostatnie commity", "git log",
                      "historia commitów", "recent commits"],
        "tool": "qbot_project_recent_commits",
        "args": {"limit": 10},
        "confidence": "high",
        "required_data": ["Git repository at /opt/qbot/app"],
        "limitations": ["Max 30 commits", "Short format only (%h %s)"],
    },
    {
        "keywords": ["diff", "zmiany", "co zmienione", "zmodyfikowane",
                      "niezapisane", "working changes"],
        "tool": "qbot_project_diff_summary",
        "args": {},
        "confidence": "high",
        "required_data": ["Git repository at /opt/qbot/app"],
        "limitations": ["Summary only (--stat, --name-only)", "Does not return full diff content"],
    },
    {
        "keywords": ["guard", "naruszenia", "czy bezpiecznie",
                      "sprawdź zasady", "bezpieczeństwo", "guard check",
                      "czy jest bezpiecznie", "security"],
        "tool": "qbot_project_guard_check",
        "args": {},
        "confidence": "high",
        "required_data": ["Git repository state", "systemd service config", "ss listening ports"],
        "limitations": ["Only checks predefined rules", "Does not scan for CVEs or vulnerabilities"],
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


def _unknown_plan(query: str, reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "original_query": query,
        "intent": "unknown_intent",
        "selected_tool": None,
        "confidence": "low",
        "execution_plan": {
            "mode": "single_tool",
            "steps": [
                {"step": 1, "action": "classify_intent", "status": "error",
                 "reason": reason},
                {"step": 2, "action": "select_tool", "status": "skipped",
                 "reason": reason},
                {"step": 3, "action": "execute_tool", "status": "skipped",
                 "reason": reason},
            ],
        },
        "required_data": [],
        "limitations": ["No intent matched — try a different query or use a direct tool"],
        "reason": reason,
        "available_examples": _EXAMPLES,
    }


def process_query(query: str) -> dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        return _unknown_plan(query, "empty_query")

    best = None
    best_score = 0
    matched_kws: list[str] = []
    for entry in _INTENT_MAP:
        score = 0
        kws: list[str] = []
        for kw in entry["keywords"]:
            if kw in q:
                kws.append(kw)
                score += len(kw)
        if score > best_score:
            best_score = score
            best = entry
            matched_kws = kws

    if best is None or best_score == 0:
        return _unknown_plan(query, "unknown_intent")

    tool_name = best["tool"]
    if tool_name not in TOOLS:
        return _unknown_plan(query, f"tool {tool_name} not in registry")

    classify_ok = {"step": 1, "action": "classify_intent", "status": "ok",
                   "reason": f"matched_keywords: {matched_kws}"}

    select_ok = {"step": 2, "action": "select_tool", "status": "ok",
                 "tool": tool_name, "reason": "intent maps to allowlisted tool"}

    try:
        tool_result = TOOLS[tool_name](best["args"])
        execute_step = {"step": 3, "action": "execute_tool", "status": "ok",
                        "tool": tool_name}
    except Exception as exc:
        execute_step = {"step": 3, "action": "execute_tool", "status": "error",
                        "tool": tool_name, "reason": str(exc)}

    exec_status = "ok" if execute_step["status"] == "ok" else "error"

    return {
        "status": exec_status,
        "original_query": query,
        "intent": best["keywords"][0],
        "selected_tool": tool_name if exec_status == "ok" else None,
        "confidence": best["confidence"],
        "execution_plan": {
            "mode": "single_tool",
            "steps": [classify_ok, select_ok, execute_step],
        },
        "required_data": best.get("required_data", []),
        "limitations": best.get("limitations", []),
        "tool_result": tool_result if exec_status == "ok" else None,
        "notes": f"matched by keyword score {best_score}",
    }
