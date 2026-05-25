"""Rejestr narzędzi Q API — metadata i słownik TOOLS."""
from __future__ import annotations

from typing import Any

from qbot_tools import (
    _tool_qbot_api_self_check,
    _tool_qbot_api_tools_list,
    _tool_qbot_db_overview,
    _tool_qbot_git_status,
    _tool_qbot_project_diff_summary,
    _tool_qbot_project_files,
    _tool_qbot_project_guard_check,
    _tool_qbot_project_recent_commits,
    _tool_qbot_project_tree,
    _tool_qbot_query,
    _tool_qbot_recent_tool_calls,
    _tool_qbot_services_status,
    _tool_qbot_status,
    _tool_qbot_system_overview,
)

from qbot_operator_tools import (
    _tool_qbot_error_summary,
    _tool_qbot_operator_runbook,
    _tool_qbot_operator_snapshot,
    _tool_qbot_readiness_report,
    _tool_qbot_tool_usage_summary,
)

TOOLS_META: dict[str, dict[str, Any]] = {
    "qbot_status": {
        "description": "Podstawowe informacje o serwerze API (hostname, python, pid)",
        "category": "diagnostic",
        "safe": True,
        "args_schema": {},
    },
    "qbot_services_status": {
        "description": "Status usług systemd: q-bot, qbot-qlab, qbot-api, postgresql",
        "category": "diagnostic",
        "safe": True,
        "args_schema": {},
    },
    "qbot_recent_tool_calls": {
        "description": "Ostatnie N wywołań tooli z historii (limit 1–50)",
        "category": "database",
        "safe": True,
        "args_schema": {"limit": 10},
    },
    "qbot_git_status": {
        "description": "Stan repozytorium Git (/opt/qbot/app): branch, commit, clean",
        "category": "diagnostic",
        "safe": True,
        "args_schema": {},
    },
    "qbot_api_tools_list": {
        "description": "Lista wszystkich dostępnych narzędzi API z metadanymi",
        "category": "meta",
        "safe": True,
        "args_schema": {},
    },
    "qbot_db_overview": {
        "description": "Przegląd bazy danych: wersja PG, licznik tool_calls, statusy",
        "category": "database",
        "safe": True,
        "args_schema": {},
    },
    "qbot_system_overview": {
        "description": "Przegląd systemu: uptime, load, dysk, RAM, statusy usług",
        "category": "diagnostic",
        "safe": True,
        "args_schema": {},
    },
    "qbot_api_self_check": {
        "description": "Zbiorczy autotest API: DB, usługi, git, liczniki",
        "category": "meta",
        "safe": True,
        "args_schema": {},
    },
    "qbot_project_tree": {
        "description": "Drzewo katalogów projektu (max_depth 1–4)",
        "category": "project",
        "safe": True,
        "args_schema": {"max_depth": 2},
    },
    "qbot_project_files": {
        "description": "Lista plików projektu z rozmiarem i datą modyfikacji",
        "category": "project",
        "safe": True,
        "args_schema": {},
    },
    "qbot_project_recent_commits": {
        "description": "Ostatnie commity Git (limit 1–30)",
        "category": "project",
        "safe": True,
        "args_schema": {"limit": 10},
    },
    "qbot_project_diff_summary": {
        "description": "Podsumowanie zmian roboczych: status, diff --stat, lista plików",
        "category": "project",
        "safe": True,
        "args_schema": {},
    },
    "qbot_project_guard_check": {
        "description": "Sprawdzenie naruszeń zasad: qbot_qlab, Gate, env, port",
        "category": "project",
        "safe": True,
        "args_schema": {},
    },
    "qbot_query": {
        "description": "Procesor zapytań naturalnych — rozpoznaje intencje i deleguje do narzędzi",
        "category": "meta",
        "safe": True,
        "args_schema": {"query": "sprawdź stan Q"},
    },
    "qbot_error_summary": {
        "description": "Podsumowanie ostatnich błędów z historii tool_calls",
        "category": "operator",
        "safe": True,
        "args_schema": {"limit": 50},
    },
    "qbot_tool_usage_summary": {
        "description": "Statystyka użycia narzędzi: liczba wywołań, statusy, najczęściej używane",
        "category": "operator",
        "safe": True,
        "args_schema": {"limit": 200},
    },
    "qbot_readiness_report": {
        "description": "Ocena gotowości Qbot do pracy: READY, READY_WITH_WARNINGS, NOT_READY",
        "category": "operator",
        "safe": True,
        "args_schema": {},
    },
    "qbot_operator_snapshot": {
        "description": "Zbiorczy snapshot diagnostyczny — API, system, DB, git, guard, błędy",
        "category": "operator",
        "safe": True,
        "args_schema": {"include_recent_calls": True, "recent_limit": 20},
    },
    "qbot_operator_runbook": {
        "description": "Gotowe operacyjne scenariusze (safe_to_work, full_diagnostic, error_review, project_review, api_review)",
        "category": "operator",
        "safe": True,
        "args_schema": {"name": "safe_to_work", "execute": False},
    },
}

TOOLS: dict[str, Any] = {
    "qbot_status": _tool_qbot_status,
    "qbot_services_status": _tool_qbot_services_status,
    "qbot_recent_tool_calls": _tool_qbot_recent_tool_calls,
    "qbot_git_status": _tool_qbot_git_status,
    "qbot_api_tools_list": _tool_qbot_api_tools_list,
    "qbot_db_overview": _tool_qbot_db_overview,
    "qbot_system_overview": _tool_qbot_system_overview,
    "qbot_api_self_check": _tool_qbot_api_self_check,
    "qbot_project_tree": _tool_qbot_project_tree,
    "qbot_project_files": _tool_qbot_project_files,
    "qbot_project_recent_commits": _tool_qbot_project_recent_commits,
    "qbot_project_diff_summary": _tool_qbot_project_diff_summary,
    "qbot_project_guard_check": _tool_qbot_project_guard_check,
    "qbot_query": _tool_qbot_query,
    "qbot_error_summary": _tool_qbot_error_summary,
    "qbot_tool_usage_summary": _tool_qbot_tool_usage_summary,
    "qbot_readiness_report": _tool_qbot_readiness_report,
    "qbot_operator_snapshot": _tool_qbot_operator_snapshot,
    "qbot_operator_runbook": _tool_qbot_operator_runbook,
}
