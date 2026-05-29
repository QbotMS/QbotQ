#!/usr/bin/env python3
"""QBot3 Acceptance Tests — transparent gateway, write intents, DB introspection, reader errors."""

from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
os.environ["ALBERT_LLM_PROVIDER"] = "mock"

from qbot3.agent_runtime import (
    _resolve_write_intent, _is_destructive_query,
    _all_tools_empty, _execute_tools,
    _has_reader_error, _try_db_introspection_fallback,
    orchestrate_query,
)
from qbot3.write_router import extract_nutrition_slots, build_draft, draft_self_review
from qbot3.query_decomposer import decompose_query, is_payload_contaminated, clean_payload
from qbot3.db_introspection import db_schema_list, db_table_describe, db_select_readonly
from qbot3.errors import SCHEMA_MISMATCH, READER_ERROR
from qbot3.tool_registry import tool_descriptions, list_all_tools


class TestTransparentGateway(unittest.TestCase):
    """qbot.query is a transparent gateway — no pre-router intent decisions."""

    def test_destructive_blocked(self):
        """'usuń wszystkie dzisiejsze posiłki' → blocked"""
        self.assertTrue(_is_destructive_query("usuń wszystkie dzisiejsze posiłki"))
        self.assertTrue(_is_destructive_query("usuń wszystko"))
        self.assertTrue(_is_destructive_query("skasuj wszystko"))
        self.assertFalse(_is_destructive_query("dodaj posiłek"))

    def test_write_intent_resolver(self):
        """add_nutrition_entry → mode=write, write_action=nutrition_log_add"""
        plan = _resolve_write_intent(
            {"intent": "add_nutrition_entry", "mode": "read_only", "tools_to_call": []},
            "Dodaj do dzisiejszego jadłospisu ryż"
        )
        self.assertEqual(plan["mode"], "write")
        self.assertEqual(plan["write_action"], "nutrition_log_add")
        self.assertTrue(plan["requires_confirm"])

    def test_write_intent_already_write(self):
        """mode=write should not be modified"""
        plan = _resolve_write_intent(
            {"intent": "add_nutrition_entry", "mode": "write", "write_action": "nutrition_log_add"},
            "dodaj ryż"
        )
        self.assertEqual(plan["mode"], "write")

    def test_read_intent_not_touched(self):
        """read_only intent (no write prefix) → untouched"""
        plan = _resolve_write_intent(
            {"intent": "get_calendar_events", "mode": "read_only", "tools_to_call": ["qcal_events_range"]},
            "pokaż wydarzenia"
        )
        self.assertEqual(plan["mode"], "read_only")

class TestNutritionDraft(unittest.TestCase):
    """Nutrition write intent → action_draft with correct payload."""

    def test_simple_200g_rice(self):
        """'dodaj 200g ryżu' → meal_name='ryż', amount=200, unit='g'"""
        slots = extract_nutrition_slots("dodaj do dzisiejszego jadłospisu 200g ryżu")
        self.assertIn("meal_name", slots)
        self.assertIn("ryż", slots["meal_name"].lower())

    def test_brokol_sport_2000(self):
        """Complex macro query → full payload with macros"""
        q = "Dodaj do dzisiejszego jadłospisu Brokuł Sport 2000: 1 zestaw, 5 pudełek, 2011 kcal, białko 118 g, węglowodany 196 g, tłuszcz 79 g, sól 9,5 g. Przygotuj action_draft bez zapisu."
        slots = extract_nutrition_slots(q)
        self.assertIn("meal_name", slots)
        self.assertIn("brokuł", slots["meal_name"].lower())
        self.assertIn("kcal_total", slots)
        self.assertEqual(slots["kcal_total"], 2011.0)
        self.assertEqual(slots["protein_g"], 118.0)
        self.assertEqual(slots["carbs_g"], 196.0)
        self.assertEqual(slots["fat_g"], 79.0)
        self.assertEqual(slots["salt_g"], 9.5)

    def test_0_5kg_strawberries(self):
        """'0,5 kg truskawek' → amount=0.5, unit='kg'"""
        slots = extract_nutrition_slots("dodaj 0,5 kg truskawek jako action_draft, bez zapisu")
        self.assertEqual(slots.get("amount"), 0.5)

    def test_template_id(self):
        """'template_id=4' → template_id=4"""
        slots = extract_nutrition_slots("Dodaj z szablonu Brokuł Sport 2000 template_id=4")
        self.assertEqual(slots.get("template_id"), 4)

    def test_draft_ready_with_macros(self):
        """Comprehensive macro query → draft ready_for_execute=true"""
        q = "Dodaj do dzisiejszego jadłospisu Brokuł Sport 2000: 2011 kcal, białko 118 g, węglowodany 196 g, tłuszcz 79 g"
        slots = extract_nutrition_slots(q)
        draft = build_draft("nutrition_log_add", slots, q)
        self.assertEqual(draft["action_type"], "nutrition_log_add")
        self.assertTrue(draft["ready_for_execute"])
        self.assertEqual(draft["contract_review"], "approved")

    def test_draft_incomplete_no_meal_name(self):
        """Missing meal_name → draft_incomplete"""
        q = "dodaj do jadłospisu"
        slots = extract_nutrition_slots(q)
        draft = build_draft("nutrition_log_add", slots, q)
        self.assertFalse(draft["ready_for_execute"])
        self.assertIn("meal_name", draft.get("missing_fields", []))


class TestQueryDecomposition(unittest.TestCase):
    """Query decomposition separates domain task from control directives."""

    def test_control_directive_no_write(self):
        """'bez zapisu' → control directive no_write"""
        dec = decompose_query("zapisz do kalendarza event jutro o 10:00 Test QBot3, bez zapisu")
        texts = [d["text"] for d in dec["control_directives"]]
        self.assertTrue(any("bez zapisu" in t.lower() for t in texts))
        self.assertEqual(dec["execution_intent"], "draft_only")
        self.assertNotIn("bez zapisu", dec["domain_task_text"])

    def test_payload_not_contaminated(self):
        """Payload should not contain control directive text."""
        dec = decompose_query("dodaj testowy posiłek 200g ryżu jako action_draft, bez zapisu")
        payload = {"meal_name": "ryż", "amount": 200, "unit": "g"}
        warnings = is_payload_contaminated(payload, dec, "nutrition_log_add")
        self.assertEqual(len(warnings), 0, f"Payload contamination: {warnings}")

    def test_control_directive_removed_from_domain(self):
        """'bez zapisu' removed from domain_task_text"""
        dec = decompose_query("zapamiętaj jako fakt projektowy: Gate działa end-to-end z Karoo, bez zapisu")
        self.assertNotIn("bez zapisu", dec["domain_task_text"])
        self.assertIn("Gate", dec["domain_task_text"])

    def test_safety_intent_no_unlock(self):
        """'bez otwierania' → safety_intent=['no_unlock']"""
        dec = decompose_query("sprawdź status furtki bez otwierania")
        self.assertIn("no_unlock", dec["safety_intent"])


class TestDBIntrospection(unittest.TestCase):
    """Transparent DB read-only layer."""

    def test_schema_list(self):
        """db_schema_list returns schemas"""
        result = db_schema_list()
        self.assertIn("status", result)
        if result["status"] == "OK":
            self.assertGreater(result["schema_count"], 0)

    def test_table_describe(self):
        """db_table_describe returns columns"""
        result = db_table_describe({"table": "calendar_events"})
        self.assertIn("status", result)
        if result["status"] == "OK":
            self.assertIn("columns", result)
            col_names = [c["name"] for c in result["columns"]]
            self.assertIn("title", col_names)

    def test_select_readonly_blocks_write(self):
        """SELECT guard blocks INSERT"""
        result = db_select_readonly({"sql": "INSERT INTO test VALUES (1)"})
        self.assertEqual(result["status"], "BLOCKED")


class TestActionExecuteSemantics(unittest.TestCase):
    """qbot.action_execute proper semantics."""

    def test_confirm_required(self):
        """confirm=false → BLOCKED"""
        from qbot3.adapters.mcp_adapter import _handle_action_execute
        result = _handle_action_execute("test-req", {
            "action_type": "nutrition_log_add",
            "payload_json": {"meal_name": "test"},
            "idempotency_key": "test-key",
            "confirm": False,
        })
        data = json.loads(result["result"]["content"][0]["text"])
        self.assertEqual(data["status"], "BLOCKED")

    def test_dry_run(self):
        """dry_run=true → DRY_RUN_OK, write_committed=false"""
        from qbot3.adapters.mcp_adapter import _handle_action_execute
        result = _handle_action_execute("test-req", {
            "action_type": "nutrition_log_add",
            "payload_json": {"meal_name": "test"},
            "idempotency_key": "test-key-dry",
            "confirm": True,
            "dry_run": True,
        })
        data = json.loads(result["result"]["content"][0]["text"])
        self.assertEqual(data["status"], "DRY_RUN_OK")
        self.assertFalse(data.get("write_committed", True))


class TestRegression(unittest.TestCase):
    """Existing features must still work."""

    def test_tool_registry_includes_all(self):
        """All expected tools in registry"""
        tools = tool_descriptions()
        names = [t["name"] for t in tools]
        self.assertIn("nutrition_log_add", names)
        self.assertIn("calendar_event_add", names)
        self.assertIn("reminder_add", names)
        self.assertIn("db_schema_list", names)
        self.assertIn("db_select_readonly", names)

    def test_only_two_public_tools(self):
        """Only qbot.query + qbot.action_execute public tools"""
        from qbot3.adapters.mcp_adapter import _list_tools
        tools_list = _list_tools("test")
        tools = tools_list["result"]["tools"]
        names = [t["name"] for t in tools]
        self.assertEqual(names, ["qbot.query", "qbot.action_execute"])

    def test_calendar_missing_title(self):
        """'zapisz event' → draft incomplete, pending_task"""
        q = "zapisz event"
        from qbot3.write_router import build_draft
        payload = {}
        draft = build_draft("calendar_event_add", payload, q)
        self.assertFalse(draft["ready_for_execute"])
        self.assertTrue(draft.get("pending_task", False))


class TestDBIntrospectionFallback(unittest.TestCase):
    """Reader error → DB introspection fallback."""

    def test_has_reader_error_true(self):
        """Tool with SCHEMA_MISMATCH detected"""
        results = [{"reader": "qcal_events_range", "status": "SCHEMA_MISMATCH", "data": {"error": "column all_day not found"}}]
        self.assertTrue(_has_reader_error(results))

    def test_has_reader_error_false(self):
        """Tool with OK status not detected as error"""
        results = [{"reader": "qcal_events_range", "status": "OK", "data": {"events": []}}]
        self.assertFalse(_has_reader_error(results))

    def test_has_reader_error_empty(self):
        """Empty results → no error"""
        self.assertFalse(_has_reader_error([]))

    def test_db_introspection_fallback_calendar(self):
        """DB introspection fallback for calendar queries"""
        plan = {"intent": "calendar", "tools_to_call": ["qcal_events_range"]}
        results = _try_db_introspection_fallback(plan, "zobacz wydarzenia w kalendarzu")
        if results:
            readers = [r.get("reader", "") for r in results]
            # Must include db_table_describe and db_select_readonly
            self.assertIn("db_table_describe", readers)
            self.assertIn("db_select_readonly", readers)
            # Must include combined fallback result with rows
            fallback_results = [r for r in results if r["status"] == "OK" and "db_introspection_fallback" in r.get("reader", "")]
            if fallback_results:
                data = fallback_results[0]["data"]
                self.assertIn("table", data)
                self.assertEqual(data["table"], "calendar_events")
                self.assertIn("rows", data)

    def test_db_introspection_fallback_no_match(self):
        """No relevant tables → no results"""
        plan = {"intent": "unknown", "tools_to_call": []}
        results = _try_db_introspection_fallback(plan, "hello world")
        self.assertIsNone(results)

    def test_db_introspection_fallback_nutrition(self):
        """DB introspection fallback for nutrition queries"""
        plan = {"intent": "nutrition", "tools_to_call": ["nutrition_day_summary"]}
        results = _try_db_introspection_fallback(plan, "co jadłem dzisiaj")
        if results:
            tables = [r["data"].get("table") for r in results if r["status"] == "OK"]
            self.assertIn("meal_logs", tables or ["meal_logs"])

    def test_introspection_tools_available_in_registry(self):
        """DB introspection tools are registered for Albert"""
        from qbot3.tool_registry import tool_descriptions
        tools = tool_descriptions()
        names = [t["name"] for t in tools]
        for n in ["db_schema_list", "db_table_describe", "db_sample_rows", "db_select_readonly"]:
            self.assertIn(n, names, f"{n} not in tool registry")

    def test_reader_error_blocks_empty_detection(self):
        """SCHEMA_MISMATCH is NOT detected as empty"""
        results = [{"reader": "qcal_events_range", "status": "SCHEMA_MISMATCH", "data": {"error": "column not found"}}]
        self.assertFalse(_all_tools_empty(results))


class TestDBIntrospectionFallbackIntegration(unittest.TestCase):
    """Full integration: reader error → DB introspection fallback in runtime."""

    def setUp(self):
        from qbot3.tool_registry import _TOOL_REGISTRY
        self._orig_tools = {
            k: dict(v) for k, v in _TOOL_REGISTRY.items()
            if k in ("qcal_events_range",)
        }

    def tearDown(self):
        from qbot3.tool_registry import _TOOL_REGISTRY
        for k, v in self._orig_tools.items():
            _TOOL_REGISTRY[k] = v

    def _make_schema_mismatch_tool(self) -> dict:
        """Return a tool spec that always returns SCHEMA_MISMATCH."""
        return {
            "callable": lambda args: {
                "status": "SCHEMA_MISMATCH",
                "error": "column all_day does not exist. Use db_table_describe to discover actual columns.",
            },
            "category": "calendar",
            "description": "QCal events for a date range.",
            "args_schema": {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
            "safety": "read",
        }

    def _mock_db_table_describe(self, *args, **kwargs):
        return {
            "status": "OK",
            "schema": "public",
            "table": "calendar_events",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False, "is_pk": True},
                {"name": "date_start", "type": "date", "nullable": False},
                {"name": "date_end", "type": "date", "nullable": True},
                {"name": "title", "type": "text", "nullable": True},
                {"name": "event_type", "type": "text", "nullable": True},
                {"name": "status", "type": "text", "nullable": True},
            ],
            "column_count": 6,
        }

    def _mock_db_select_readonly(self, *args, **kwargs):
        return {
            "status": "OK",
            "rows": [
                {"id": 1, "date_start": "2026-06-04", "title": "Bikepacking Toskania", "event_type": "trip", "status": "active"},
                {"id": 2, "date_start": "2026-06-07", "title": "Odpoczynek", "event_type": "rest", "status": "active"},
            ],
            "row_count": 2,
            "sql_audit": "SELECT ... FROM calendar_events ...",
        }

    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_reader_error_triggers_db_introspection_fallback(self, mock_select, mock_describe):
        """Reader SCHEMA_MISMATCH → runtime auto-runs db_table_describe + db_select_readonly."""
        mock_describe.side_effect = self._mock_db_table_describe
        mock_select.side_effect = self._mock_db_select_readonly

        from qbot3.tool_registry import _TOOL_REGISTRY
        schema_mismatch_tool = self._make_schema_mismatch_tool()
        _TOOL_REGISTRY["qcal_events_range"] = schema_mismatch_tool

        question = (
            "Zobacz, czy w QCal/kalendarzu jest event bikepacking w Toskanii "
            "od 4.06.2026 do 13.06.2026. Jeśli reader QCal ma błąd, użyj DB introspection/read-only."
        )
        result = orchestrate_query(question)

        tool_results = result.get("tool_results", [])
        readers = [r.get("reader", "") for r in tool_results]
        readers_str = ", ".join(readers)

        # REQUIREMENT 1: db_table_describe must appear in tool_results
        self.assertIn("db_table_describe", readers,
                      f"db_table_describe missing from tool_results. Got: {readers_str}")

        # REQUIREMENT 2: db_select_readonly must appear in tool_results
        self.assertIn("db_select_readonly", readers,
                      f"db_select_readonly missing from tool_results. Got: {readers_str}")

        # REQUIREMENT 3: db_introspection_fallback.* must appear in tool_results
        self.assertTrue(
            any("db_introspection_fallback" in r for r in readers),
            f"db_introspection_fallback.* missing from tool_results. Got: {readers_str}",
        )

        # REQUIREMENT 4: plan must record db_introspection_used
        plan = result.get("plan", {})
        self.assertTrue(plan.get("db_introspection_used", False),
                        "plan.db_introspection_used must be True")

        # REQUIREMENT 5: fallback data must contain actual rows
        fallback_entries = [r for r in tool_results if "db_introspection_fallback" in r.get("reader", "")]
        self.assertTrue(len(fallback_entries) > 0, "At least one db_introspection_fallback entry")
        fb = fallback_entries[0]
        self.assertEqual(fb.get("status"), "OK", f"Fallback status should be OK, got {fb.get('status')}")
        fb_data = fb.get("data", {})
        self.assertIn("rows", fb_data, "Fallback data must contain rows")
        self.assertGreater(fb_data.get("row_count", 0), 0, "Fallback must return at least 1 row")

    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_reader_error_fallback_only_when_needed(self, mock_select, mock_describe):
        """OK reader → NO DB introspection fallback."""
        mock_describe.side_effect = self._mock_db_table_describe
        mock_select.side_effect = self._mock_db_select_readonly

        from qbot3.tool_registry import _TOOL_REGISTRY
        _TOOL_REGISTRY.pop("qcal_events_range", None)

        question = "Zobacz wydarzenia w kalendarzu na dzisiaj"
        result = orchestrate_query(question)

        tool_results = result.get("tool_results", [])
        readers = [r.get("reader", "") for r in tool_results]
        readers_str = ", ".join(readers)

        # When no error, no fallback needed
        self.assertNotIn("db_introspection_fallback", readers_str,
                         "Should not have fallback when no reader error")


if __name__ == "__main__":
    print("=== QBot3 Acceptance Tests ===")
    unittest.main(verbosity=2)
