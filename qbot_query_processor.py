"""Bezpieczny procesor zapytań z planami wykonania (Tool Execution Plan v1)."""
from __future__ import annotations

from typing import Any

from qbot_tool_registry import TOOLS

_SAFE_MULTI_EXECUTE_TOOLS: set[str] = {
    "qbot_api_self_check",
    "qbot_git_status",
    "qbot_project_guard_check",
    "qbot_services_status",
    "qbot_db_overview",
    "qbot_system_overview",
    "qbot_project_diff_summary",
    "qbot_project_recent_commits",
    "qbot_recent_tool_calls",
    "qbot_api_tools_list",
}

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
    "sprawdź stan Q, repo i guard",
    "pełny przegląd",
]

_MULTI_TOOL_SETS: dict[str, list[str]] = {
    "wszystko": ["qbot_api_self_check", "qbot_system_overview", "qbot_db_overview",
                  "qbot_git_status", "qbot_project_guard_check"],
    "pełny przegląd": ["qbot_api_self_check", "qbot_system_overview", "qbot_db_overview",
                        "qbot_git_status", "qbot_project_guard_check"],
    "kompletny status": ["qbot_api_self_check", "qbot_system_overview", "qbot_db_overview",
                          "qbot_git_status", "qbot_project_guard_check"],
}

_MULTI_TOOL_LIMIT = 5


def _get_tool_args(tool_name: str) -> dict[str, Any]:
    for entry in _INTENT_MAP:
        if entry["tool"] == tool_name:
            return entry["args"]
    return {}


def _unknown_plan(query: str, reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "original_query": query,
        "intent": "unknown_intent",
        "selected_tool": None,
        "confidence": "low",
        "execution_mode": "preview_only",
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
        "planned_tools": [],
        "preview_only": True,
        "tool_result": None,
        "executed_tools": [],
        "tool_results": None,
        "required_data": [],
        "limitations": ["No intent matched — try a different query or use a direct tool"],
        "reason": reason,
        "available_examples": _EXAMPLES,
    }


def _single_tool_result(query: str, entry: dict[str, Any],
                        matched_kws: list[str], best_score: int) -> dict[str, Any]:
    tool_name = entry["tool"]
    if tool_name not in TOOLS:
        return _unknown_plan(query, f"tool {tool_name} not in registry")

    classify_ok = {"step": 1, "action": "classify_intent", "status": "ok",
                   "reason": f"matched_keywords: {matched_kws}"}
    select_ok = {"step": 2, "action": "select_tool", "status": "ok",
                 "tool": tool_name, "reason": "intent maps to allowlisted tool"}

    try:
        tool_result = TOOLS[tool_name](entry["args"])
        execute_step = {"step": 3, "action": "execute_tool", "status": "ok",
                        "tool": tool_name}
    except Exception as exc:
        execute_step = {"step": 3, "action": "execute_tool", "status": "error",
                        "tool": tool_name, "reason": str(exc)}

    exec_status = "ok" if execute_step["status"] == "ok" else "error"

    return {
        "status": exec_status,
        "original_query": query,
        "intent": entry["keywords"][0],
        "selected_tool": tool_name if exec_status == "ok" else None,
        "confidence": entry["confidence"],
        "execution_mode": "single_tool",
        "execution_plan": {
            "mode": "single_tool",
            "steps": [classify_ok, select_ok, execute_step],
        },
        "planned_tools": [tool_name],
        "preview_only": False,
        "tool_result": tool_result if exec_status == "ok" else None,
        "executed_tools": [tool_name] if exec_status == "ok" else [],
        "tool_results": {tool_name: tool_result} if exec_status == "ok" else None,
        "required_data": entry.get("required_data", []),
        "limitations": entry.get("limitations", []),
        "notes": f"matched by keyword score {best_score}",
    }


def process_query(query: str, execute: bool = False) -> dict[str, Any]:
    q = (query or "").strip().lower()
    if not q:
        return _unknown_plan(query, "empty_query")

    for mt_key, mt_tools in _MULTI_TOOL_SETS.items():
        if mt_key in q:
            tool_args_list: list[tuple[str, dict[str, Any]]] = [
                (t, _get_tool_args(t)) for t in mt_tools if t in TOOLS
            ]
            return _build_multi_preview(query, tool_args_list, f"full_overview:{mt_key}", execute)

    matches: list[tuple[int, dict[str, Any], list[str]]] = []
    for entry in _INTENT_MAP:
        score = 0
        kws: list[str] = []
        for kw in entry["keywords"]:
            if kw in q:
                kws.append(kw)
                score += len(kw)
        if score > 0:
            matches.append((score, entry, kws))

    if not matches:
        return _unknown_plan(query, "unknown_intent")

    conjunctions = {"i", ",", "oraz", "też", "także", "plus"}
    has_conjunction = any(c in q for c in conjunctions)

    if has_conjunction and len(matches) >= 2:
        tool_args_list: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        for _score, entry, _kws in matches:
            t = entry["tool"]
            if t not in seen:
                tool_args_list.append((t, entry["args"]))
                seen.add(t)
        if len(tool_args_list) >= 2:
            if len(tool_args_list) > _MULTI_TOOL_LIMIT:
                tool_args_list = tool_args_list[:_MULTI_TOOL_LIMIT]
            return _build_multi_preview(query, tool_args_list,
                                        f"matched {len(matches)} intents with conjunction", execute)

    best_score, best, matched_kws = max(matches, key=lambda x: x[0])
    return _single_tool_result(query, best, matched_kws, best_score)


def _build_multi_preview(query: str, tool_args_list: list[tuple[str, dict[str, Any]]],
                          reason: str, execute: bool = False) -> dict[str, Any]:
    valid = [(t, a) for t, a in tool_args_list if t in TOOLS]
    if len(valid) > _MULTI_TOOL_LIMIT:
        valid = valid[:_MULTI_TOOL_LIMIT]

    tool_names = [t for t, _ in valid]

    if not execute:
        steps: list[dict[str, Any]] = [
            {"step": 1, "action": "classify_intent", "status": "ok",
             "reason": reason},
            {"step": 2, "action": "build_multi_tool_plan", "status": "ok",
             "tools": tool_names, "reason": f"{len(valid)} allowlisted tools selected"},
            {"step": 3, "action": "preview_tools", "status": "skipped",
             "reason": "preview only — tools were not executed"},
        ]

        limitations: list[str] = [
            "Preview only; tools were not executed",
            "No arbitrary command execution",
            "Only allowlisted tools can appear in plan",
        ]
        if len(tool_args_list) > _MULTI_TOOL_LIMIT:
            limitations.append(f"Plan truncated to {_MULTI_TOOL_LIMIT} tools")

        return {
            "status": "ok",
            "original_query": query,
            "intent": "multi_tool_preview",
            "selected_tool": None,
            "confidence": "medium",
            "execution_mode": "preview_only",
            "execution_plan": {
                "mode": "preview_only",
                "steps": steps,
            },
            "planned_tools": tool_names,
            "preview_only": True,
            "tool_result": None,
            "executed_tools": [],
            "tool_results": None,
            "required_data": [],
            "limitations": limitations,
            "notes": "multi-tool preview — no tools executed",
        }

    safe_valid = [(t, a) for t, a in valid if t in _SAFE_MULTI_EXECUTE_TOOLS]

    execute_steps: list[dict[str, Any]] = [
        {"step": 1, "action": "classify_intent", "status": "ok",
         "reason": reason},
        {"step": 2, "action": "build_multi_tool_plan", "status": "ok",
         "tools": [t for t, _ in safe_valid],
         "reason": f"{len(safe_valid)} allowlisted tools selected for execution"},
    ]

    executed_tools: list[str] = []
    tool_results: dict[str, Any] = {}
    has_error = False
    has_ok = False

    step_num = 3
    for tool_name, tool_args in safe_valid:
        try:
            result = TOOLS[tool_name](tool_args)
            if isinstance(result, dict) and result.get("status") == "error":
                has_error = True
                execute_steps.append({
                    "step": step_num, "action": "execute_tool",
                    "tool": tool_name, "status": "error",
                    "reason": result.get("error", "tool returned error"),
                })
            else:
                has_ok = True
                execute_steps.append({
                    "step": step_num, "action": "execute_tool",
                    "tool": tool_name, "status": "ok",
                })
            tool_results[tool_name] = result
        except Exception as exc:
            has_error = True
            execute_steps.append({
                "step": step_num, "action": "execute_tool",
                "tool": tool_name, "status": "error",
                "reason": str(exc),
            })
            tool_results[tool_name] = {"error": str(exc), "tool": tool_name}
        executed_tools.append(tool_name)
        step_num += 1

    skipped = [t for t, _ in valid if t not in _SAFE_MULTI_EXECUTE_TOOLS]
    if skipped:
        execute_steps.append({
            "step": step_num, "action": "skip_tool",
            "tools": skipped, "status": "skipped",
            "reason": "not in SAFE_MULTI_EXECUTE_TOOLS",
        })

    if has_error and has_ok:
        status = "partial"
    elif has_error:
        status = "error"
    else:
        status = "ok"

    limitations = [
        "Controlled multi-tool execution",
        "Only allowlisted tools were executed",
        "No arbitrary command execution",
    ]

    return {
        "status": status,
        "original_query": query,
        "intent": "multi_tool_execution",
        "selected_tool": None,
        "confidence": "medium",
        "execution_mode": "multi_tool_execute",
        "execution_plan": {
            "mode": "multi_tool_execute",
            "steps": execute_steps,
        },
        "planned_tools": tool_names,
        "preview_only": False,
        "tool_result": None,
        "executed_tools": executed_tools,
        "tool_results": tool_results,
        "required_data": [],
        "limitations": limitations,
        "notes": "multi-tool execution — tools were executed from allowlist",
    }
