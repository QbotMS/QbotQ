#!/usr/bin/env python3
"""QBot3 Plan Validator — checks LLM-generated plans before execution.

Ensures plan integrity, safety, and registry compliance.
Detects domain-tool mismatches and returns CAPABILITY_MISSING/MISMATCH
with concrete proposals instead of PLAN_INVALID or silent wrong-tool usage.
"""

from __future__ import annotations

from typing import Any

from qbot3.errors import (
    OK, PLAN_INVALID, CAPABILITY_MISSING, SAFETY_BLOCKED,
    LEGACY_FALLBACK_BLOCKED, error_result, success_result,
)
from qbot3.tool_registry import lookup


# Known domain ↔ dedicated tool/capability mappings.
# When LLM plans tools outside these for a domain, it's a MISMATCH.
_DOMAIN_TOOL_MAP: dict[str, list[str]] = {
    # domain keywords -> expected tools/capabilities
    "daily report": ["daily_report_status"],
    "raport dzienny": ["daily_report_status"],
    "email pipeline": ["daily_report_status"],
    "report pipeline": ["daily_report_status"],
    "gate": ["gate_status"],
    "furtka": ["gate_status"],
    "hikconnect": ["gate_status"],
    "hammerhead": ["hammerhead_sync_status"],
    "garmin sync": ["hammerhead_sync_status", "garmin_sync_status"],
    "transfer": ["hammerhead_sync_status"],
    "llm": ["system_env_status"],
    "model": ["system_env_status"],
    "jaki model": ["system_env_status"],
    "provider": ["system_env_status"],
    "llm_status": ["system_env_status"],
    "daily_report_status": ["daily_report_status"],
    "gate_status": ["gate_status"],
    "hammerhead_sync_status": ["hammerhead_sync_status", "garmin_sync_status"],
}

# Generic tools that should NOT be the primary answer for specific domains.
# They are fallbacks, not domain solutions.
_GENERIC_TOOLS = frozenset({
    "system_logs_recent", "system_env_status",
})


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

    # Read mode domain-tool mismatch detection
    if mode == "read_only" and tools:
        mismatch_result = _detect_domain_tool_mismatch(intent, tools, plan_json_lower)
        if mismatch_result:
            return mismatch_result
        # Also check intent-based mismatch: if intent clearly maps to a domain but tools are generic
        if intent:
            intent_mismatch = _detect_intent_tool_mismatch(intent, tools)
            if intent_mismatch:
                return intent_mismatch

    # Read mode — no tools, check capability registry
    if mode == "read_only" and not tools:
        if intent:
            proposal = _check_capability_for_intent(intent)
            if proposal:
                return error_result(
                    CAPABILITY_MISSING,
                    proposal["message"],
                    capability_proposal=proposal,
                    intent=intent,
                )
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


def _detect_domain_tool_mismatch(intent: str, tools: list[str], plan_lower: str) -> dict[str, Any] | None:
    """Detect when LLM picks generic tools for a specific domain.

    Returns a CAPABILITY_MISSING proposal if tools don't match the domain.
    """
    # Check each domain mapping
    for domain_keywords, expected_tools in _DOMAIN_TOOL_MAP.items():
        if domain_keywords not in plan_lower:
            continue
        # Domain matched — check if tools include expected ones
        has_expected = any(et in tools for et in expected_tools)
        if has_expected:
            return None  # OK, correct tools used
        # Domain matched but expected tools NOT used — this is a MISMATCH
        # Check if generic tools were used instead
        generic_used = [t for t in tools if t in _GENERIC_TOOLS]
        if generic_used:
            proposal = _propose_for_domain(intent, domain_keywords, expected_tools)
            return error_result(
                CAPABILITY_MISSING,
                proposal["message"],
                capability_proposal=proposal,
                mismatch_detected=True,
                generic_tools_used=generic_used,
                expected_tools=expected_tools,
                intent=intent,
            )
    return None


def _detect_intent_tool_mismatch(intent: str, tools: list[str]) -> dict[str, Any] | None:
    """Detect when intent name suggests a domain but LLM picked generic tools.

    Example: intent='llm_status' with tools=['system_env_status'] → mismatch.
    """
    # Check if any domain keyword is in the intent name
    il = intent.lower()
    for domain_keywords, expected_tools in _DOMAIN_TOOL_MAP.items():
        if domain_keywords not in il:
            continue
        has_expected = any(et in tools for et in expected_tools)
        if has_expected:
            return None
        generic_used = [t for t in tools if t in _GENERIC_TOOLS]
        if generic_used:
            proposal = _propose_for_domain(intent, domain_keywords, expected_tools)
            return error_result(
                CAPABILITY_MISSING,
                proposal["message"],
                capability_proposal=proposal,
                mismatch_detected=True,
                generic_tools_used=generic_used,
                expected_tools=expected_tools,
                intent=intent,
            )
    return None


def _propose_for_domain(intent: str, domain: str, expected_tools: list[str]) -> dict[str, Any]:
    """Generate a concrete capability proposal for a known domain."""
    from qbot3.capabilities import propose_capability
    return propose_capability(
        intent,
        f"Wykryto mismatch domeny '{domain}': zamiast {expected_tools} użyto ogólnych narzędzi. "
        f"Potrzebna capability dla '{domain}'.",
        domain_hint=domain,
    )


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
