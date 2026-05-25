"""Rejestr narzędzi Q API — metadata i słownik TOOLS."""
from __future__ import annotations

from typing import Any

from qbot_tools import (
    _tool_qbot_api_self_check,
    _tool_qbot_api_tools_list,
    _tool_qbot_db_overview,
    _tool_qbot_git_status,
    _tool_qbot_recent_tool_calls,
    _tool_qbot_services_status,
    _tool_qbot_status,
    _tool_qbot_system_overview,
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
}
