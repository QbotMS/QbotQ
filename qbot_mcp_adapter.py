#!/usr/bin/env python3
"""Minimal QBot MCP adapter for the ChatGPT connector."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from qbot_artifact_tools import (
    _tool_qbot_artifact_create,
    _tool_qbot_artifact_get,
    _tool_qbot_artifact_list,
)
from qbot_external_llm_tools import _tool_qbot_external_context_bundle
from qbot_llm_planner import _tool_qbot_llm_run_query, _tool_qbot_tool_policy_list
from qbot_ops_tools import _tool_qbot_operator_final_smoke_test
from qbot_roadmap_runner import (
    _tool_qbot_roadmap_runner_list_tasks,
    _tool_qbot_roadmap_runner_next_task,
    _tool_qbot_roadmap_runner_status,
)
from qbot_telegram_tools import _tool_qbot_telegram_status
from qbot_assistant_inbox import (
    _tool_qbot_assistant_inbox_list,
    _tool_qbot_assistant_inbox_status,
)
from qbot_tools import _tool_qbot_status

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "QBot MCP Adapter v1"
MCP_SERVER_VERSION = "1.0.0"
MCP_SESSION_HEADER = "mcp-session-id"

_SESSION_STATE: dict[str, dict[str, Any]] = {}

_MCP_TOOL_MAP: dict[str, dict[str, Any]] = {
    "qbot.status": {
        "qbot_tool": "qbot_operator_final_smoke_test",
        "description": "Final operational smoke test for QBot.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.readiness": {
        "qbot_tool": "qbot_readiness_report",
        "description": "Readiness report for the local QBot stack.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.ask": {
        "qbot_tool": "qbot_llm_run_query",
        "description": "Safe question routing through QBot policy/planner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "execute": {"type": "boolean", "default": False},
                "style": {"type": "string", "enum": ["concise", "operator", "detailed"], "default": "concise"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.runbook": {
        "qbot_tool": "qbot_operator_runbook",
        "description": "Execute or preview a curated QBot operator runbook.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "execute": {"type": "boolean", "default": False},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.context_bundle": {
        "qbot_tool": "qbot_external_context_bundle",
        "description": "Build a sanitized context bundle for external ChatGPT usage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 20000, "default": 12000},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifact_create": {
        "qbot_tool": "qbot_artifact_create",
        "description": "Create a safe PostgreSQL artifact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_type": {"type": "string", "default": "report"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source_plan_id": {"type": "integer"},
            },
            "required": ["title", "content"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_SAFE",
        "auth_required": True,
    },
    "qbot.artifact_list": {
        "qbot_tool": "qbot_artifact_list",
        "description": "List recent artifacts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifact_get": {
        "qbot_tool": "qbot_artifact_get",
        "description": "Get one artifact by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.task_queue_add": {
        "qbot_tool": "qbot_task_queue_add",
        "description": "Add a task to QBot queue for CLI execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "What to do"},
                "style": {"type": "string", "default": "short"},
                "tools_to_use": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_SAFE",
        "auth_required": True,
    },
    "qbot.task_queue_list": {
        "qbot_tool": "qbot_task_queue_list",
        "description": "List tasks in the QBot queue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "default": "pending"},
                "limit": {"type": "integer", "default": 50},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.task_queue_next": {
        "qbot_tool": "qbot_task_queue_next",
        "description": "Get the next pending task for CLI execution.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.task_queue_status": {
        "qbot_tool": "qbot_task_queue_status",
        "description": "Update task status after execution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string", "enum": ["pass", "blocked", "fail", "in_progress"]},
                "result_summary": {"type": "string"},
                "error": {"type": "string"},
            },
            "required": ["task_id", "status"],
            "additionalProperties": False,
        },
        "safety_class": "WRITE_SAFE",
        "auth_required": True,
    },
    "qbot.tool_policy": {
        "qbot_tool": "qbot_tool_policy_list",
        "description": "List QBot tool policy metadata.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.telegram_status": {
        "qbot_tool": "qbot_telegram_status",
        "description": "Summarize Telegram bot status and webhook health.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.roadmap_runner_status": {
        "qbot_tool": "qbot_roadmap_runner_status",
        "description": "Read-only roadmap runner status including task/block progress.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.roadmap_runner_list_tasks": {
        "qbot_tool": "qbot_roadmap_runner_list_tasks",
        "description": "Read-only roadmap task list and safety metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "block": {"type": "string", "default": ""},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.roadmap_runner_next_task": {
        "qbot_tool": "qbot_roadmap_runner_next_task",
        "description": "Read-only next roadmap task preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "block": {"type": "string", "default": ""},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.qlab_status": {
        "qbot_tool": "qbot_qlab_status",
        "description": "Compatibility alias for legacy QLab status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.assistant_inbox_status": {
        "qbot_tool": "qbot_assistant_inbox_status",
        "description": "Read-only local assistant inbox status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.assistant_inbox_list": {
        "qbot_tool": "qbot_assistant_inbox_list",
        "description": "Read-only assistant inbox list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "unread_only": {"type": "boolean", "default": False},
                "source": {"type": "string", "default": ""},
                "block": {"type": "string", "default": ""},
                "status": {"type": "string", "default": ""},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.weather_legacy_status": {
        "qbot_tool": "qbot_weather_legacy_status",
        "description": "Read-only weather/OpenWeatherMap legacy status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.weather_status": {
        "qbot_tool": "qbot_weather_status",
        "description": "Read-only current weather status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "default": "Marki"},
                "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 1},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.weather_current": {
        "qbot_tool": "qbot_weather_current",
        "description": "Read-only current weather snapshot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "default": "Marki"},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.weather_forecast": {
        "qbot_tool": "qbot_weather_forecast",
        "description": "Read-only weather forecast summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "default": "Marki"},
                "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 7},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garage_legacy_status": {
        "qbot_tool": "qbot_garage_legacy_status",
        "description": "Read-only garage / gate / home automation legacy status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifacts_legacy_status": {
        "qbot_tool": "qbot_artifacts_legacy_status",
        "description": "Read-only filesystem artifacts and PostgreSQL artifact bridge status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifacts_filesystem_inventory": {
        "qbot_tool": "qbot_artifacts_filesystem_inventory",
        "description": "Read-only inventory of /opt/qbot/artifacts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prefix": {"type": "string", "default": ""},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifact_import_preview": {
        "qbot_tool": "qbot_artifact_import_from_file_preview",
        "description": "Preview-only artifact import mapping from a filesystem file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "relative_path": {"type": "string"},
            },
            "required": ["relative_path"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.artifact_export_preview": {
        "qbot_tool": "qbot_artifact_export_preview",
        "description": "Preview-only artifact export plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "integer"},
            },
            "required": ["artifact_id"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.external_integrations_report": {
        "qbot_tool": "qbot_external_integrations_report",
        "description": "Read-only combined report for external integrations.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garmin_proxy_status": {
        "qbot_tool": "qbot_garmin_proxy_status",
        "description": "Read-only legacy Garmin proxy status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garmin_upload_status": {
        "qbot_tool": "qbot_garmin_upload_status",
        "description": "Read-only legacy Garmin upload status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.hammerhead_import_status": {
        "qbot_tool": "qbot_hammerhead_import_status",
        "description": "Read-only legacy Hammerhead import status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.hammerhead_import_inventory": {
        "qbot_tool": "qbot_hammerhead_import_inventory",
        "description": "List Hammerhead original FIT files in outgoing.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.hammerhead_restore_plan": {
        "qbot_tool": "qbot_hammerhead_restore_plan",
        "description": "Restore plan for Hammerhead FIT import capability.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_status": {
        "qbot_tool": "qbot_rwgps_legacy_status",
        "description": "Read-only RWGPS legacy parity status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_config_status": {
        "qbot_tool": "qbot_rwgps_config_status",
        "description": "Check RWGPS configuration without exposing secrets.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_route_search": {
        "qbot_tool": "qbot_rwgps_route_search",
        "description": "Search RWGPS routes by free-text query and show best match.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "offset": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 0},
                "include_details": {"type": "boolean", "default": True},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_route_list": {
        "qbot_tool": "qbot_rwgps_route_list",
        "description": "List RWGPS routes as records instead of a summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "offset": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 0},
                "sort": {"type": "string", "default": "updated_at"},
                "order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                "search": {"type": "string", "default": ""},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_route_get": {
        "qbot_tool": "qbot_rwgps_route_get",
        "description": "Get a single RWGPS route by route_id.",
        "input_schema": {
            "type": "object",
            "properties": {"route_id": {"type": "string"}},
            "required": ["route_id"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_route_export_links": {
        "qbot_tool": "qbot_rwgps_route_export_links",
        "description": "Get RWGPS export availability and links for GPX/TCX/FIT by route_id.",
        "input_schema": {
            "type": "object",
            "properties": {"route_id": {"type": "string"}},
            "required": ["route_id"],
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.rwgps_restore_plan": {
        "qbot_tool": "qbot_rwgps_restore_plan",
        "description": "Restore plan for RWGPS capability.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.csv_export_status": {
        "qbot_tool": "qbot_csv_export_status",
        "description": "Comprehensive CSV export status — inventory, latest, preview readiness.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.csv_export_inventory": {
        "qbot_tool": "qbot_csv_export_inventory",
        "description": "List CSV files in outgoing directory.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.csv_export_latest_get": {
        "qbot_tool": "qbot_csv_export_latest_get",
        "description": "Read latest CSV file — preview rows only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["garmin_proxy_latest", "latest_any"], "default": "garmin_proxy_latest"},
                "limit_rows": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.xert_status": {
        "qbot_tool": "qbot_xert_readiness_status",
        "description": "Read-only Xert training status — FTP, form, W'.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.xert_config_status": {
        "qbot_tool": "qbot_xert_config_status",
        "description": "Read-only Xert configuration status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.intervals_status": {
        "qbot_tool": "qbot_intervals_wellness_status",
        "description": "Read-only Intervals.icu wellness status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.intervals_config_status": {
        "qbot_tool": "qbot_intervals_config_status",
        "description": "Read-only Intervals.icu configuration status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garmin_status": {
        "qbot_tool": "qbot_garmin_config_status",
        "description": "Read-only Garmin configuration status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garmin_upload_dry_run": {
        "qbot_tool": "qbot_garmin_upload_dry_run",
        "description": "Read-only Garmin upload dry run.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.hammerhead_status": {
        "qbot_tool": "qbot_hammerhead_import_status",
        "description": "Read-only Hammerhead import status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.hammerhead_inventory": {
        "qbot_tool": "qbot_hammerhead_import_inventory",
        "description": "Read-only Hammerhead FIT file inventory.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.hammerhead_dry_run": {
        "qbot_tool": "qbot_hammerhead_import_dry_run",
        "description": "Read-only Hammerhead import dry run.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.cronometer_status": {
        "qbot_tool": "qbot_cronometer_legacy_status",
        "description": "Read-only Cronometer legacy status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.openweathermap_status": {
        "qbot_tool": "qbot_weather_config_status",
        "description": "Read-only weather configuration status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.openmaps_status": {
        "qbot_tool": "qbot_openmaps_legacy_status",
        "description": "Read-only OpenMaps legacy status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.overpass_status": {
        "qbot_tool": "qbot_openmaps_legacy_status",
        "description": "Read-only Overpass/OpenMaps legacy status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garage_list": {
        "qbot_tool": "qbot_garage_raw_list",
        "description": "Read-only Garage raw listing.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}},
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garage_search": {
        "qbot_tool": "qbot_garage_raw_search",
        "description": "Read-only Garage raw search.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "default": ""}, "limit": {"type": "integer", "default": 20}},
            "additionalProperties": False,
        },
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.garage_status": {
        "qbot_tool": "qbot_garage_raw_status",
        "description": "Read-only Garage raw status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.daily_report_status": {
        "qbot_tool": "qbot_daily_report_status",
        "description": "Read-only daily report status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.daily_report_preview": {
        "qbot_tool": "qbot_daily_report_preview",
        "description": "Read-only daily report preview.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.ride_report_status": {
        "qbot_tool": "qbot_ride_report_status",
        "description": "Read-only ride report status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.ride_report_latest": {
        "qbot_tool": "qbot_ride_report_latest",
        "description": "Read-only latest ride report.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
    "qbot.ride_report_preview": {
        "qbot_tool": "qbot_ride_report_preview",
        "description": "Read-only ride report preview.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "safety_class": "READ_ONLY",
        "auth_required": False,
    },
}


def _token_configured() -> bool:
    return bool(os.getenv("MCP_SHARED_SECRET") or os.getenv("QBOT_MCP_TOKEN"))


def _configured_token() -> str:
    return os.getenv("MCP_SHARED_SECRET") or os.getenv("QBOT_MCP_TOKEN") or ""


def _auth_header_ok(headers: dict[str, str]) -> bool:
    token = _configured_token()
    if not token:
        return True
    bearer = headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer.split(" ", 1)[1].strip() == token
    return headers.get("x-qbot-mcp-token", "") == token


def _public_mcp_url() -> str:
    base = os.getenv("QBOT_PUBLIC_BASE_URL", "").strip()
    if base:
        return base.rstrip("/") + "/mcp/"
    return "https://qbot.cytr.us/mcp/"


def _local_health_url() -> str:
    return "http://127.0.0.1:8001/mcp/health"


def _public_health_url() -> str:
    return _public_mcp_url().rstrip("/") + "/health"


def _local_api_ok() -> bool:
    try:
        import subprocess
        proc = subprocess.run(
            ["systemctl", "is-active", "qbot-api.service"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode != 0 or proc.stdout.strip() != "active":
            return False
        import api_db
        return api_db.ping()
    except Exception:
        return False


def _public_mcp_reachable() -> bool:
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            resp = client.get(_public_health_url())
            return resp.status_code == 200
    except Exception:
        return False


def _exposed_tool_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, meta in _MCP_TOOL_MAP.items():
        enabled = True
        if meta.get("auth_required") and not _token_configured():
            enabled = False
        items.append({
            "name": name,
            "qbot_tool": meta["qbot_tool"],
            "description": meta["description"],
            "inputSchema": meta["input_schema"],
            "safety_class": meta["safety_class"],
            "auth_required": meta["auth_required"],
            "enabled": enabled,
        })
    return items


def _allowed_exposed_tools() -> list[str]:
    return [item["name"] for item in _exposed_tool_items() if item["enabled"]]


def _tool_mapping_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "mcp_tool": item["name"],
            "qbot_tool": item["qbot_tool"],
            "safety_class": item["safety_class"],
            "auth_required": item["auth_required"],
            "enabled": item["enabled"],
        }
        for item in _exposed_tool_items()
    ]


def _tool_qbot_mcp_status(_args: dict | None = None) -> dict[str, Any]:
    token_configured = _token_configured()
    exposed = _allowed_exposed_tools()
    disabled = [item["name"] for item in _exposed_tool_items() if not item["enabled"]]
    local_ok = _local_api_ok()
    public_ok = _public_mcp_reachable()
    status = "WARN" if not token_configured else "OK"
    if not local_ok:
        status = "ERROR"
    return {
        "tool": "qbot_mcp_status",
        "mcp_routes_enabled": True,
        "public_url": _public_mcp_url(),
        "auth_configured": token_configured,
        "auth_mode": "token" if token_configured else "read_only",
        "exposed_tools": exposed,
        "disabled_tools": disabled,
        "qbot_api_local_ok": local_ok,
        "public_mcp_reachable": public_ok,
        "local_health_url": _local_health_url(),
        "public_health_url": _public_health_url(),
        "status": status,
    }


def _tool_qbot_readiness_report(_args: dict | None = None) -> dict[str, Any]:
    from qbot_operator_tools import _tool_qbot_readiness_report as _impl

    return _impl(_args)


def _tool_qbot_mcp_tools_list(_args: dict | None = None) -> dict[str, Any]:
    items = _tool_mapping_snapshot()
    return {
        "tool": "qbot_mcp_tools_list",
        "count": len(items),
        "tools": items,
        "status": "OK" if items else "ERROR",
    }


def _tool_qbot_mcp_call_preview(args: dict | None = None) -> dict[str, Any]:
    args = args or {}
    mcp_tool = str(args.get("mcp_tool", "")).strip()
    tool_args = args.get("args", {})
    if not isinstance(tool_args, dict):
        return {
            "tool": "qbot_mcp_call_preview",
            "status": "error",
            "error": "args must be an object",
        }
    if not mcp_tool:
        return {
            "tool": "qbot_mcp_call_preview",
            "status": "error",
            "error": "mcp_tool required",
        }
    meta = _MCP_TOOL_MAP.get(mcp_tool)
    if not meta:
        return {
            "tool": "qbot_mcp_call_preview",
            "status": "error",
            "error": f"unknown MCP tool: {mcp_tool}",
            "allowed_tools": sorted(_MCP_TOOL_MAP.keys()),
        }
    execute_requested = bool(tool_args.get("execute", False))
    would_execute = bool(meta["enabled"]) and (execute_requested or meta["safety_class"] == "READ_ONLY")
    policy_notes: list[str] = []
    if not meta["enabled"]:
        policy_notes.append("blocked by local auth mode")
    if mcp_tool == "qbot.artifact_create" and not _token_configured():
        policy_notes.append("artifact creation requires MCP token")
    if mcp_tool == "qbot.ask" and execute_requested:
        policy_notes.append("execution goes through the QBot policy engine")
    if mcp_tool == "qbot.runbook" and execute_requested:
        policy_notes.append("runbook execution is controlled by the QBot runbook allowlist")
    return {
        "tool": "qbot_mcp_call_preview",
        "mcp_tool": mcp_tool,
        "mapped_qbot_tool": meta["qbot_tool"],
        "policy_notes": policy_notes,
        "would_execute": would_execute,
        "status": "OK" if meta["enabled"] else "BLOCKED",
    }


def _tool_by_name(name: str):
    mapping = {
        "qbot_status": _tool_qbot_status,
        "qbot_operator_final_smoke_test": _tool_qbot_operator_final_smoke_test,
        "qbot_readiness_report": _tool_qbot_readiness_report,
        "qbot_llm_run_query": _tool_qbot_llm_run_query,
        "qbot_external_context_bundle": _tool_qbot_external_context_bundle,
        "qbot_artifact_create": _tool_qbot_artifact_create,
        "qbot_artifact_list": _tool_qbot_artifact_list,
        "qbot_artifact_get": _tool_qbot_artifact_get,
        "qbot_tool_policy_list": _tool_qbot_tool_policy_list,
        "qbot_telegram_status": _tool_qbot_telegram_status,
        "qbot_mcp_status": _tool_qbot_mcp_status,
        "qbot_mcp_tools_list": _tool_qbot_mcp_tools_list,
        "qbot_mcp_call_preview": _tool_qbot_mcp_call_preview,
    }
    return mapping.get(name)


def _dispatch_local_qbot_tool(
    tool_name: str,
    args: dict | None = None,
    *,
    source: str = "qbot-api",
    mcp_tool: str | None = None,
    session_id: str | None = None,
    log_call: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    clean_args = args if isinstance(args, dict) else {}
    func = _tool_by_name(tool_name)
    if func is None:
        try:
            from qbot_tool_registry import TOOLS
            func = TOOLS.get(tool_name)
        except Exception:
            func = None
    if func is None:
        try:
            from qbot_tool_registry import TOOLS
            available = sorted(TOOLS.keys())
        except Exception:
            available = [
                "qbot_status",
                "qbot_operator_final_smoke_test",
                "qbot_readiness_report",
                "qbot_llm_run_query",
                "qbot_external_context_bundle",
                "qbot_artifact_create",
                "qbot_artifact_list",
                "qbot_artifact_get",
                "qbot_tool_policy_list",
                "qbot_telegram_status",
                "qbot_mcp_status",
                "qbot_mcp_tools_list",
                "qbot_mcp_call_preview",
            ]
        allowed = [
            "qbot_status",
            "qbot_operator_final_smoke_test",
            "qbot_readiness_report",
            "qbot_llm_run_query",
            "qbot_external_context_bundle",
            "qbot_artifact_create",
            "qbot_artifact_list",
            "qbot_artifact_get",
            "qbot_tool_policy_list",
            "qbot_telegram_status",
            "qbot_mcp_status",
            "qbot_mcp_tools_list",
            "qbot_mcp_call_preview",
        ]
        result: dict[str, Any] = {
            "error": f"unknown tool: {tool_name}",
            "available": available or allowed,
        }
    else:
        result = func(clean_args)

    if log_call:
        audit_args = dict(clean_args)
        audit_args["_source"] = source
        if mcp_tool:
            audit_args["_mcp_tool"] = mcp_tool
        if session_id:
            audit_args["_mcp_session_id"] = session_id
        try:
            import api_db
            api_db.save_tool_call(tool_name, audit_args, result)
        except Exception as exc:
            warnings.append(f"db save failed: {exc}")
    return result, warnings


def _normalize_tool_name(mcp_tool: str) -> str:
    meta = _MCP_TOOL_MAP.get(mcp_tool)
    if not meta:
        return ""
    return meta["qbot_tool"]


def _mcp_result_content(result: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}


def _mcp_error(message: str, *, code: int = -32601, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _new_session() -> str:
    session_id = str(uuid.uuid4())
    _SESSION_STATE[session_id] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "initialized": True,
    }
    return session_id


def _validate_mcp_access(method: str, headers: dict[str, str], *, tool_name: str | None = None) -> tuple[bool, str | None]:
    # initialize + tools/list are always accessible (MCP spec)
    if method in ("initialize", "notifications/initialized", "tools/list"):
        return True, None
    if method != "tools/call":
        return True, None
    if not tool_name:
        return False, "tool name missing"
    meta = _MCP_TOOL_MAP.get(tool_name)
    if not meta:
        return False, "tool not allowed"
    if meta.get("auth_required", False) and _token_configured() and not _auth_header_ok(headers):
        return False, "missing or invalid MCP token"
    return True, None


def handle_mcp_request(
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, int, dict[str, str]]:
    headers = {k.lower(): v for k, v in (headers or {}).items()}

    if "tool" in payload and "method" not in payload:
        payload = {
            "jsonrpc": "2.0",
            "id": payload.get("id", 1),
            "method": "tools/call",
            "params": {
                "name": payload.get("tool"),
                "arguments": payload.get("args", {}),
            },
        }

    method = payload.get("method", "")
    request_id = payload.get("id")
    params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}

    if method == "initialize":
        session_id = _new_session()
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": "Use tools/call with the allowlisted qbot.* adapter tools.",
        }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }, 200, {MCP_SESSION_HEADER: session_id}

    if method == "notifications/initialized":
        return None, 202, {}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": _exposed_tool_items()},
        }, 200, {}

    if method == "tools/call":
        name = str(params.get("name", "")).strip()
        arguments = params.get("arguments", {})
        ok, auth_error = _validate_mcp_access(method, headers, tool_name=name or None)
        if not ok:
            return _mcp_error(auth_error or "unauthorized", code=401), 401, {"WWW-Authenticate": "Bearer"}
        if not name:
            return _mcp_error("tool name missing", code=-32602, request_id=request_id), 200, {}
        meta = _MCP_TOOL_MAP.get(name)
        if not meta:
            return _mcp_error(f"tool not allowed: {name}", code=-32601, request_id=request_id), 200, {}
        if not isinstance(arguments, dict):
            return _mcp_error("arguments must be an object", code=-32602, request_id=request_id), 200, {}

        qbot_tool = _normalize_tool_name(name)
        if not qbot_tool:
            return _mcp_error(f"tool not mapped: {name}", code=-32601, request_id=request_id), 200, {}

        session_id = headers.get(MCP_SESSION_HEADER, "")
        clean_args = dict(arguments)

        if name == "qbot.ask":
            query = str(clean_args.get("query", "")).strip()
            execute = bool(clean_args.get("execute", False))
            style = str(clean_args.get("style", "concise"))
            if not query:
                result = {"tool": name, "status": "error", "error": "query required"}
            else:
                if execute:
                    result = _tool_qbot_llm_run_query({"query": query, "execute": True})
                else:
                    from qbot_query_processor import process_query
                    result = process_query(query, execute=False)
                result["tool"] = "qbot.ask"
                result["style"] = style
        elif name == "qbot.runbook":
            runbook_name = str(clean_args.get("name", "")).strip()
            execute = bool(clean_args.get("execute", False))
            from qbot_operator_tools import _tool_qbot_operator_runbook
            result = _tool_qbot_operator_runbook({"name": runbook_name, "execute": execute})
            result["tool"] = "qbot.runbook"
        elif name == "qbot.context_bundle":
            topic = str(clean_args.get("topic", "")).strip()
            max_chars = clean_args.get("max_chars", 12000)
            if not topic:
                result = {"tool": "qbot.context_bundle", "status": "error", "error": "topic required"}
            else:
                result = _tool_qbot_external_context_bundle({"topic": topic, "max_chars": max_chars})
                result["tool"] = "qbot.context_bundle"
        elif name == "qbot.artifact_create" and not _token_configured():
            result = {
                "tool": name,
                "status": "BLOCKED",
                "execute": False,
                "policy_status": "BLOCKED",
                "reason": "MCP token not configured",
            }
        else:
            tool_args = dict(clean_args)
            if name == "qbot.artifact_create":
                if "tags" in tool_args and isinstance(tool_args["tags"], str):
                    tool_args["tags"] = [tool_args["tags"]]
            tool_result, warnings = _dispatch_local_qbot_tool(
                qbot_tool,
                tool_args,
                source="mcp",
                mcp_tool=name,
                session_id=session_id or None,
                log_call=False,
            )
            result = tool_result
            if warnings:
                result = dict(result)
                result.setdefault("warnings", [])
                if isinstance(result["warnings"], list):
                    result["warnings"].extend(warnings)
                else:
                    result["warnings"] = warnings

        audit_args = dict(clean_args)
        audit_args["_source"] = "mcp"
        audit_args["_mcp_tool"] = name
        if session_id:
            audit_args["_mcp_session_id"] = session_id
        try:
            import api_db
            api_db.save_tool_call(qbot_tool, audit_args, result)
        except Exception:
            pass

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _mcp_result_content(result),
        }, 200, {}

    return _mcp_error(f"unsupported method: {method}", code=-32601, request_id=request_id), 200, {}
