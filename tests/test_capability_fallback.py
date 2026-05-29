#!/usr/bin/env python3
"""Tests: tool registry, capability lookup, error codes."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, "/opt/qbot/app")


def test_capability_fallback_empty_tools() -> None:
    """If ALL tools return empty, capability fallback should fire."""
    from qbot3.agent_runtime import _all_tools_empty

    assert _all_tools_empty([]) is True
    assert _all_tools_empty([{"data": {"status": "DATA_MISSING"}}]) is True
    assert _all_tools_empty([{"data": {"status": "CONNECTOR_MISSING"}}]) is True
    assert _all_tools_empty([{"data": {"status": "NO_DATA"}}]) is True
    assert _all_tools_empty([{"data": {"status": "OK", "data": {"key": "val"}}}]) is False
    assert _all_tools_empty([{"data": {}}]) is True
    assert _all_tools_empty([{"data": None}]) is True
    assert _all_tools_empty([{"data": {"status": "OK"}}]) is True  # status only = empty
    print(f"  ✅ _all_tools_empty: 8/8 cases")


def test_capability_fallback_daily_report_status() -> None:
    """daily_report_status capability is active and can be found by intent."""
    from qbot3.capabilities import find_capability_by_intent, find_capability

    cap = find_capability("daily_report_status")
    assert cap is not None, "daily_report_status capability must exist"
    assert cap.is_active(), "daily_report_status must be active"
    assert cap.definition.name == "daily_report_status"
    print(f"  ✅ daily_report_status: active, name={cap.definition.name}")

    # Find by intent keywords matching description substrings
    for kw in ("report", "pipeline", "delivery", "status"):
        found = find_capability_by_intent(kw)
        assert found is not None, f"Should find capability by intent '{kw}'"
        assert found.definition.name == "daily_report_status"
    print(f"  ✅ find_capability_by_intent: 4/4 keywords match daily_report_status")


def test_tool_registry_has_daily_report_status() -> None:
    """daily_report_status must be in tool_descriptions (for LLM planner)."""
    from qbot3.tool_registry import tool_descriptions, lookup

    descs = tool_descriptions()
    names = [t["name"] for t in descs]
    assert "daily_report_status" in names, "Must be in tool_descriptions for LLM planner"
    assert lookup("daily_report_status") is not None, "Must be in tool_registry"
    print(f"  ✅ daily_report_status in tool_descriptions ({len(descs)} tools total)")


def test_system_logs_recent_not_primary_for_domain_queries() -> None:
    """system_logs_recent is NOT the default for domain issues."""
    from qbot3.tool_registry import lookup

    spec = lookup("system_logs_recent")
    assert spec is not None
    desc = spec.get("description", "")
    assert "daily" not in desc.lower() or "raport" not in desc.lower(), \
        "system_logs_recent description should not mention daily report"
    print(f"  ✅ system_logs_recent description: domain-neutral")


def test_capability_missing_error_code() -> None:
    """CAPABILITY_MISSING is a valid error code with proposal support."""
    from qbot3.errors import CAPABILITY_MISSING, error_result

    err = error_result(CAPABILITY_MISSING, "test missing", capability_proposal={"name": "test"})
    assert err["status"] == "CAPABILITY_MISSING"
    assert "capability_proposal" in err
    print(f"  ✅ CAPABILITY_MISSING error code works")


if __name__ == "__main__":
    os.environ["QBOT3_ENABLED"] = "1"
    print("=== Tool Registry & Capability Tests ===")
    test_capability_fallback_empty_tools()
    test_capability_fallback_daily_report_status()
    test_tool_registry_has_daily_report_status()
    test_system_logs_recent_not_primary_for_domain_queries()
    test_capability_missing_error_code()
    print("\n✅ All tool registry & capability tests passed")
