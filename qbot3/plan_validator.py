#!/usr/bin/env python3
"""QBot3 Plan Validator — checks LLM-generated plans before execution.

Ensures plan integrity, safety, and registry compliance.
"""

from __future__ import annotations

from typing import Any

from qbot3.errors import OK, PLAN_INVALID, SAFETY_BLOCKED, LEGACY_FALLBACK_BLOCKED, error_result, success_result
from qbot3.tool_registry import lookup


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate an LLM-generated plan. Returns OK or error_result."""
    mode = plan.get("mode", "read_only")
    tools = plan.get("tools_to_call", [])
    write_action = plan.get("write_action")
    intent = plan.get("intent", "")
    confidence = plan.get("confidence", 0.0)
    plan_json_lower = str(plan).lower()

    if not intent:
        return error_result(PLAN_INVALID, "Plan missing intent")

    if mode not in ("read_only", "write", "plan_only"):
        return error_result(PLAN_INVALID, f"Invalid mode: {mode}")

    # Validate tools exist in registry
    missing_tools = []
    for tool_name in tools:
        spec = lookup(tool_name)
        if not spec:
            missing_tools.append(tool_name)
    if missing_tools:
        return error_result(PLAN_INVALID, f"Tools not found in registry: {missing_tools}")

    # Write mode checks
    if mode == "write":
        if not write_action:
            return error_result(PLAN_INVALID, "Write mode requires write_action")
        write_spec = lookup(write_action)
        if not write_spec:
            return error_result(PLAN_INVALID, f"Write action '{write_action}' not found in registry")
        if write_spec.get("safety") != "write":
            return error_result(PLAN_INVALID, f"Action '{write_action}' is not marked as write in registry")
        if not plan.get("requires_confirm"):
            return error_result(PLAN_INVALID, "Write mode requires requires_confirm=true")
        if tools:
            return error_result(PLAN_INVALID, "Write mode should not have tools_to_call — use write_action instead")

    # Read mode checks
    if mode == "read_only" and not tools:
        return error_result(PLAN_INVALID, "Read mode requires at least one tool")
    if mode == "read_only" and write_action:
        return error_result(PLAN_INVALID, "Read mode should not have write_action")

    # Confidence check
    if confidence < 0.3 and not plan.get("needs_clarification"):
        return error_result(PLAN_INVALID, f"Low confidence ({confidence}) without clarification flag")

    # Block write execution through qbot.query
    if any(k in plan_json_lower for k in ("action_execute", "qbot.action_execute")):
        return error_result(PLAN_INVALID, "Write execution through qbot.query is blocked — use qbot.action_execute")

    # Block legacy patterns
    blocked_patterns = [
        "classify_intent", "_parse_nutrition", "_parse_event", "_match_meal",
        "process_query", "qbot_query_router", "_INTENT_PATTERNS", "_TOOL_DISPATCH",
        "slot_filling", "intent_routing",
    ]
    for pattern in blocked_patterns:
        if pattern in plan_json_lower:
            return error_result(LEGACY_FALLBACK_BLOCKED, f"Plan references legacy function: '{pattern}'")

    # Block system-level dangerous tools
    dangerous_patterns = ["shell", "subprocess", "os.system", "exec(", "eval(", "file_write", "db_raw", "__import__"]
    for pattern in dangerous_patterns:
        if pattern in plan_json_lower:
            return error_result(SAFETY_BLOCKED, f"Plan contains dangerous pattern: '{pattern}'")

    return success_result({"valid": True})
