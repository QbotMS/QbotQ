#!/usr/bin/env python3
"""Testy: rejestr narzedzi, capabilities statusu (15.10.2026), kody bledow.

Raport dzienny (daily_report_status) zaorany 15.10.2026 -- artefakt z poczatkow QBota.
Statusy funkcji: qbot_status_checks (jedno zrodlo dla SETUP > Polaczenia > Status i narzedzi Alberta).
"""

from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "/opt/qbot/app")

STATUS_TOOLS = ("hammerhead_sync_status", "withings_sync_status", "llm_status", "gate_status", "qbot_status_overview")


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


def test_status_capabilities_active() -> None:
    from qbot3.capabilities import find_capability
    for name in ("hammerhead_sync_status", "withings_sync_status", "llm_status", "gate_status"):
        cap = find_capability(name)
        assert cap is not None and cap.is_active(), name
    assert find_capability("daily_report_status") is None, "raport dzienny zaorany 15.10.2026"


def test_status_tools_registered_and_in_albert_prompt() -> None:
    from qbot3.tool_registry import tool_descriptions, lookup
    names = {t["name"] for t in tool_descriptions()}
    alb = open("/opt/qbot/app/qbot3/llm/albert.py", encoding="utf-8").read()
    for n in STATUS_TOOLS:
        assert n in names and lookup(n) is not None, n
        assert n in alb, f"{n} musi byc opisane w prompcie Alberta (_SYSTEM)"
        assert len(lookup(n).get("description") or "") < 500, n
    assert "daily_report_status" not in names


def test_status_checks_shape_and_no_secrets() -> None:
    from qbot_status_checks import all_checks, CHECKS
    r = all_checks()
    assert r["overall"] in ("ok", "warn", "bad")
    assert len(r["items"]) == len(CHECKS)
    for i in r["items"]:
        assert i["state"] in ("ok", "warn", "bad", "off"), i
        assert i["name"] and i["text"], i
        assert not re.search(r"\d{4}-\d{2}-\d{2}", i["text"]), f"data ISO w tekscie dla uzytkownika: {i['text']}"
    blob = json.dumps(r, ensure_ascii=False).lower()
    for bad in ("api_key", "token\": \"", "password", "secret"):
        assert bad not in blob, bad
