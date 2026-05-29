#!/usr/bin/env python3
"""QBot3 Plan Validator — checks LLM-generated plans before execution.

Ensures plan integrity, safety, and registry compliance.
"""

from __future__ import annotations

from typing import Any

from qbot3.errors import (
    OK, PLAN_INVALID, CAPABILITY_MISSING, SAFETY_BLOCKED,
    LEGACY_FALLBACK_BLOCKED, error_result, success_result,
)
from qbot3.tool_registry import lookup


_READ_ONLY_TOOL_HINTS = (
    "calendar", "calend", "nutrition", "meal", "food", "posił", "jad",
    "route", "rwgps", "training", "workout", "wellness", "sleep", "garmin",
    "xert", "gate", "weather", "dashboard", "snapshot", "summary", "report",
    "balance", "bilans", "kcal", "energy",
)


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate an LLM-generated plan. Returns OK, CAPABILITY_MISSING, or error."""
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

    # Read mode — no tools, check capability registry
    if mode == "read_only" and not tools:
        return success_result({"valid": True, "no_tools_ok": True})

    if mode == "read_only" and write_action:
        return error_result(PLAN_INVALID, "Read mode should not have write_action")

    # Confidence check
    if confidence < 0.3 and not plan.get("needs_clarification"):
        return error_result(PLAN_INVALID, f"Low confidence ({confidence}) without clarification flag")

    # Block write execution through qbot.query
    if any(k in plan_json_lower for k in ("action_execute", "qbot.action_execute")):
        return error_result(PLAN_INVALID, "Write execution through qbot.query is blocked — use qbot.action_execute")

    # Validate tool parameters against args_schema
    params = plan.get("parameters", {})
    for tool_name in tools:
        spec = lookup(tool_name)
        if not spec:
            continue
        args_schema = spec.get("args_schema", {})
        if not args_schema:
            continue
        # db_select_readonly requires sql parameter — reject if missing
        if tool_name == "db_select_readonly" and not params.get("sql"):
            return error_result(PLAN_INVALID, f"db_select_readonly requires 'sql' parameter. Provide a concrete SELECT query or use db_schema_list / db_table_describe first.")
        # db_table_describe and db_sample_rows require table parameter
        if tool_name in ("db_table_describe", "db_sample_rows") and not params.get("table"):
            return error_result(PLAN_INVALID, f"{tool_name} requires 'table' parameter. Use db_schema_list to discover available tables first.")

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


def _check_capability_for_intent(intent: str) -> dict[str, Any] | None:
    """Check if a capability exists or could be proposed for an intent."""
    try:
        from qbot3.capabilities import find_capability_by_intent, propose_capability
        cap = find_capability_by_intent(intent)
        if cap:
            d = cap.definition
            if cap.is_active():
                return {
                    "needed_capability": d.name,
                    "intent": intent,
                    "safety_class": d.safety_class,
                    "data_sources": d.data_sources,
                    "capability_found": True,
                    "active": True,
                    "auto_buildable": cap.is_auto_buildable(),
                    "message": f"Intent '{intent}' pasuje do capability '{d.name}' (state: {d.promotion_state}). "
                               f"Uruchom capability bezpośrednio.",
                }
            return {
                "needed_capability": d.name,
                "intent": intent,
                "safety_class": d.safety_class,
                "capability_found": True,
                "active": False,
                "promotion_state": d.promotion_state,
                "auto_buildable": cap.is_auto_buildable(),
                "message": f"Intent '{intent}' pasuje do capability '{d.name}', ale jest w stanie "
                           f"'{d.promotion_state}'. Promuj do 'active' przed użyciem.",
            }
        if not any(h in intent.lower() for h in _READ_ONLY_TOOL_HINTS):
            return None
        # No capability found — propose one
        proposal = propose_capability(
            intent,
            f"Brak capability dla intentu '{intent}'. "
            f"Żaden z istniejących tooli ani capability nie obsługuje tego zapytania.",
        )
        # Unwrap proposal from the response wrapper
        inner = proposal.get("proposal", proposal)
        return {
            "needed_capability": inner.get("name", f"{intent}_status"),
            "intent": intent,
            "safety_class": inner.get("safety_class", "READ_ONLY"),
            "data_sources": inner.get("data_sources", []),
            "capability_found": False,
            "active": False,
            "auto_buildable": proposal.get("auto_buildable", False),
            "message": proposal.get("message", f"Brak capability dla '{intent}'."),
            "_raw_proposal": inner,
        }
    except ImportError:
        return None
