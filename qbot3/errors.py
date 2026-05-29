#!/usr/bin/env python3
"""QBot3 Error Taxonomy — shared status codes for all capabilities.

Usage:
  from qbot3.errors import OK, DATA_MISSING, error_result
  return error_result(DATA_MISSING, "No Garmin data for today")
"""

from __future__ import annotations

from typing import Any

# Status codes
OK = "OK"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
ERROR = "ERROR"
DATA_MISSING = "DATA_MISSING"
CONNECTOR_MISSING = "CONNECTOR_MISSING"
AUTH_MISSING = "AUTH_MISSING"
DOC_MISSING = "DOC_MISSING"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
PLAN_INVALID = "PLAN_INVALID"
SAFETY_BLOCKED = "SAFETY_BLOCKED"
LEGACY_FALLBACK_BLOCKED = "LEGACY_FALLBACK_BLOCKED"
TOOL_ERROR = "TOOL_ERROR"
PROVIDER_ERROR = "PROVIDER_ERROR"
CAPABILITY_MISSING = "CAPABILITY_MISSING"
CONFIG_MISMATCH = "CONFIG_MISMATCH"
NEEDS_LOCATION = "NEEDS_LOCATION"
DUPLICATE = "DUPLICATE"


def error_result(status: str, message: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "error": message}
    result.update(extra)
    return result


def success_result(data: Any = None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status": OK}
    if data is not None:
        result["data"] = data
    result.update(extra)
    return result
