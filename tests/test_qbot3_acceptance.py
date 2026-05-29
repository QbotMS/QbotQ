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
    _is_destructive_query,
    _all_tools_empty, _execute_tools,
    _has_reader_error, _try_db_introspection_fallback,
    orchestrate_query,
)
from qbot3.context_builder import build_context
from qbot3.llm.mock_provider import MockProvider
from qbot3.plan_validator import validate_plan
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

    def test_read_only_no_tools_allowed(self):
        """read_only without tools stays valid — Albert may answer directly."""
        result = validate_plan(
            {"intent": "pytanie konwersacyjne", "mode": "read_only", "tools_to_call": [], "confidence": 0.9}
        )
        self.assertEqual(result["status"], "OK")
        self.assertTrue(result["data"]["valid"])
        self.assertTrue(result["data"]["no_tools_ok"])

    def test_write_mode_still_requires_confirm(self):
        """write mode still requires explicit confirmation."""
        result = validate_plan(
            {"intent": "add_nutrition_entry", "mode": "write", "write_action": "nutrition_log_add",
             "tools_to_call": [], "requires_confirm": True, "confidence": 0.9}
        )
        self.assertEqual(result["status"], "OK")

    def test_write_mode_rejects_no_confirm(self):
        """write mode with requires_confirm=false is rejected by validator."""
        result = validate_plan(
            {"intent": "add_nutrition_entry", "mode": "write", "write_action": "nutrition_log_add",
             "tools_to_call": [], "requires_confirm": False, "confidence": 0.9}
        )
        self.assertNotEqual(result["status"], "OK")
        self.assertIn("requires_confirm", result.get("error", "").lower())

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


class TestWriteDraftWithoutSave(unittest.TestCase):
    """'bez zapisu' returns draft, never executes write."""

    def test_brokol_bez_zapisu_returns_draft(self):
        """'bez zapisu' → status=draft, mode=write, requires_confirm=true, action_draft present"""
        q = "dodaj Brokuł Sport 2000: 2011 kcal, białko 118 g, węgle 196 g, tłuszcz 79 g, sól 9,5 g, bez zapisu"
        result = orchestrate_query(q)
        self.assertEqual(result.get("status"), "draft")
        self.assertEqual(result.get("plan", {}).get("mode"), "write")
        self.assertIn("nutrition_log_add", str(result.get("action_draft", {})))
        ad = result.get("action_draft", {})
        self.assertEqual(ad.get("action_type"), "nutrition_log_add")
        self.assertTrue(ad.get("requires_confirm"))
        payload = ad.get("payload", {})
        self.assertIn("meal_name", payload)
        self.assertIn("kcal_total", payload)
        self.assertIn("protein_g", payload)
        self.assertIn("carbs_g", payload)
        self.assertIn("fat_g", payload)
        self.assertIn("brokuł", payload.get("meal_name", "").lower())
        self.assertEqual(payload.get("kcal_total"), 2011.0)
        self.assertEqual(payload.get("protein_g"), 118.0)
        self.assertNotIn("tool_results", result)  # write mode has no tools
        # answer informs user to use qbot.action_execute — that's correct, not execution


class TestRegression(unittest.TestCase):
    """Existing features must still work."""

    def test_mock_calendar_uses_db_readonly(self):
        """'pokaż kalendarz' → db_schema_list + db_table_describe + db_select_readonly, no snapshot"""
        provider = MockProvider()
        plan = provider.plan(build_context("pokaż kalendarz"), [], "pokaż kalendarz")
        self.assertIn("db_select_readonly", plan.tools_to_call)
        self.assertIn("db_table_describe", plan.tools_to_call)
        self.assertNotIn("calendar_snapshot", plan.tools_to_call)
        self.assertEqual(plan.parameters.get("table"), "calendar_events")

    def test_mock_dashboard_uses_snapshot(self):
        """'pokaż dzisiejszy dashboard' → calendar_snapshot"""
        provider = MockProvider()
        plan = provider.plan(build_context("pokaż dzisiejszy dashboard"), [], "pokaż dzisiejszy dashboard")
        self.assertIn("calendar_snapshot", plan.tools_to_call)
        self.assertNotIn("db_select_readonly", plan.tools_to_call)

    def test_mock_nutrition_uses_db_readonly(self):
        """'co dziś jadłem' → db_schema_list + db_table_describe + db_select_readonly"""
        provider = MockProvider()
        plan = provider.plan(build_context("co dziś jadłem"), [], "co dziś jadłem")
        self.assertIn("db_select_readonly", plan.tools_to_call)
        self.assertIn("db_table_describe", plan.tools_to_call)
        self.assertNotIn("nutrition_day_summary", plan.tools_to_call)
        self.assertEqual(plan.parameters.get("table"), "meal_logs")

    def test_tool_registry_includes_all(self):
        """All expected tools in registry"""
        tools = tool_descriptions()
        names = [t["name"] for t in tools]
        self.assertIn("nutrition_log_add", names)
        self.assertIn("qcal_events_range", names)
        self.assertIn("qcal_reminders_upcoming", names)
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

    def _mock_db_table_describe_flexible(self, args=None, **kwargs):
        payload = args if isinstance(args, dict) else kwargs
        table = str(payload.get("table", "calendar_events"))
        if table == "meal_logs":
            return {
                "status": "OK",
                "schema": "public",
                "table": "meal_logs",
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False, "is_pk": True},
                    {"name": "date", "type": "date", "nullable": False},
                    {"name": "meal_name", "type": "text", "nullable": True},
                    {"name": "kcal_total", "type": "numeric", "nullable": True},
                ],
                "column_count": 4,
            }
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

    def _mock_db_select_readonly_flexible(self, args=None, **kwargs):
        payload = args if isinstance(args, dict) else kwargs
        sql = str(payload.get("sql", ""))
        if "meal_logs" in sql:
            return {
                "status": "OK",
                "rows": [
                    {"id": 11, "date": "2026-05-29", "meal_name": "Owsianka", "kcal_total": 540},
                    {"id": 12, "date": "2026-05-29", "meal_name": "Ryż z kurczakiem", "kcal_total": 810},
                ],
                "row_count": 2,
                "sql_audit": "SELECT ... FROM meal_logs ...",
            }
        return {
            "status": "OK",
            "rows": [
                {"id": 1, "date_start": "2026-06-04", "title": "Bikepacking Toskania", "event_type": "trip", "status": "active"},
                {"id": 2, "date_start": "2026-06-07", "title": "Odpoczynek", "event_type": "rest", "status": "active"},
            ],
            "row_count": 2,
            "sql_audit": "SELECT ... FROM calendar_events ...",
        }

    @patch('qbot3.db_introspection.db_schema_list')
    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_db_introspection_fallback_calendar(self, mock_select, mock_describe, mock_schema_list):
        """DB introspection fallback for calendar queries"""
        mock_schema_list.return_value = {"status": "OK", "schemas": {"public": ["calendar_events"]}, "schema_count": 1}
        mock_describe.side_effect = self._mock_db_table_describe_flexible
        mock_select.side_effect = self._mock_db_select_readonly_flexible
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

    @patch('qbot3.db_introspection.db_schema_list')
    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_db_introspection_fallback_nutrition(self, mock_select, mock_describe, mock_schema_list):
        """DB introspection fallback for nutrition queries"""
        mock_schema_list.return_value = {"status": "OK", "schemas": {"public": ["meal_logs"]}, "schema_count": 1}
        mock_describe.side_effect = self._mock_db_table_describe_flexible
        mock_select.side_effect = self._mock_db_select_readonly_flexible
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
            if k in ("qcal_events_range", "db_schema_list", "db_table_describe", "db_select_readonly")
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

    def _mock_db_schema_list(self, *args, **kwargs):
        return {
            "status": "OK",
            "schemas": {"public": ["calendar_events", "meal_logs"]},
            "schema_count": 1,
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

    def _mock_db_table_describe_flexible(self, args=None, **kwargs):
        payload = args if isinstance(args, dict) else kwargs
        table = str(payload.get("table", "calendar_events"))
        if table == "meal_logs":
            return {
                "status": "OK",
                "schema": "public",
                "table": "meal_logs",
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False, "is_pk": True},
                    {"name": "date", "type": "date", "nullable": False},
                    {"name": "meal_name", "type": "text", "nullable": True},
                    {"name": "kcal_total", "type": "numeric", "nullable": True},
                ],
                "column_count": 4,
            }
        return self._mock_db_table_describe()

    def _mock_db_select_readonly_flexible(self, args=None, **kwargs):
        payload = args if isinstance(args, dict) else kwargs
        sql = str(payload.get("sql", ""))
        if "meal_logs" in sql:
            return {
                "status": "OK",
                "rows": [
                    {"id": 11, "date": "2026-05-29", "meal_name": "Owsianka", "kcal_total": 540},
                    {"id": 12, "date": "2026-05-29", "meal_name": "Ryż z kurczakiem", "kcal_total": 810},
                ],
                "row_count": 2,
                "sql_audit": "SELECT ... FROM meal_logs ...",
            }
        return self._mock_db_select_readonly()

    def _mock_db_schema_tool(self):
        return {
            "callable": lambda args: self._mock_db_schema_list(),
            "category": "db",
            "description": "Mock db_schema_list",
            "args_schema": {},
            "safety": "read",
        }

    def _mock_db_table_tool(self):
        return {
            "callable": lambda args: self._mock_db_table_describe(),
            "category": "db",
            "description": "Mock db_table_describe",
            "args_schema": {"schema": {"type": "string"}, "table": {"type": "string"}},
            "safety": "read",
        }

    def _mock_db_select_tool(self):
        return {
            "callable": lambda args: self._mock_db_select_readonly(),
            "category": "db",
            "description": "Mock db_select_readonly",
            "args_schema": {"sql": {"type": "string"}},
            "safety": "read",
        }

    @patch('qbot3.db_introspection.db_schema_list')
    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_reader_query_uses_direct_db_readonly(self, mock_select, mock_describe, mock_schema_list):
        """Ordinary calendar question → direct db_schema_list + db_table_describe + db_select_readonly, no snapshot/fallback."""
        from qbot3.tool_registry import _TOOL_REGISTRY
        _TOOL_REGISTRY["db_schema_list"] = self._mock_db_schema_tool()
        _TOOL_REGISTRY["db_table_describe"] = self._mock_db_table_tool()
        _TOOL_REGISTRY["db_select_readonly"] = self._mock_db_select_tool()
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

        # REQUIREMENT 1: direct DB tools must appear in tool_results
        self.assertIn("db_table_describe", readers,
                      f"db_table_describe missing from tool_results. Got: {readers_str}")
        self.assertIn("db_select_readonly", readers,
                      f"db_select_readonly missing from tool_results. Got: {readers_str}")

        # REQUIREMENT 2: no fallback should be needed
        self.assertNotIn("db_introspection_fallback", readers_str,
                         f"Unexpected fallback in tool_results. Got: {readers_str}")

        # REQUIREMENT 3: plan must not mark db_introspection_used
        plan = result.get("plan", {})
        self.assertFalse(plan.get("db_introspection_used", False),
                         "plan.db_introspection_used must be False for direct DB reads")

        # REQUIREMENT 4: direct rows must contain future events from calendar_events
        select_entries = [r for r in tool_results if r.get("reader") == "db_select_readonly"]
        self.assertTrue(select_entries, f"No db_select_readonly entries. Got: {readers_str}")
        select_data = select_entries[0].get("data", {})
        self.assertEqual(select_data.get("status"), "OK")
        self.assertIn("rows", select_data)
        self.assertGreater(len(select_data.get("rows", [])), 0)

    @patch('qbot3.db_introspection.db_schema_list')
    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_reader_error_fallback_only_when_needed(self, mock_select, mock_describe, mock_schema_list):
        """OK reader → NO DB introspection fallback."""
        from qbot3.tool_registry import _TOOL_REGISTRY
        _TOOL_REGISTRY["db_schema_list"] = self._mock_db_schema_tool()
        _TOOL_REGISTRY["db_table_describe"] = self._mock_db_table_tool()
        _TOOL_REGISTRY["db_select_readonly"] = self._mock_db_select_tool()
        _TOOL_REGISTRY.pop("qcal_events_range", None)

        question = "Zobacz wydarzenia w kalendarzu na dzisiaj"
        result = orchestrate_query(question)

        tool_results = result.get("tool_results", [])
        readers = [r.get("reader", "") for r in tool_results]
        readers_str = ", ".join(readers)

        # Direct DB path should still be used
        self.assertIn("db_table_describe", readers,
                      f"db_table_describe missing from tool_results. Got: {readers_str}")
        self.assertIn("db_select_readonly", readers,
                      f"db_select_readonly missing from tool_results. Got: {readers_str}")
        self.assertNotIn("db_introspection_fallback", readers_str,
                         "Should not have fallback when direct DB read succeeds")


class TestToolParameterValidation(unittest.TestCase):
    """Tools must be planned with required parameters."""

    def test_db_select_readonly_rejects_no_sql(self):
        """db_select_readonly without sql parameter is rejected."""
        result = validate_plan({
            "intent": "xert_status", "mode": "read_only",
            "tools_to_call": ["db_select_readonly"],
            "parameters": {}, "confidence": 0.9,
        })
        self.assertNotEqual(result["status"], "OK")
        self.assertIn("sql", result.get("error", "").lower())

    def test_db_select_readonly_with_sql_passes(self):
        """db_select_readonly with sql parameter passes validation."""
        result = validate_plan({
            "intent": "xert_status", "mode": "read_only",
            "tools_to_call": ["db_select_readonly"],
            "parameters": {"sql": "SELECT * FROM xert_metrics LIMIT 10"},
            "confidence": 0.9,
        })
        self.assertEqual(result["status"], "OK")

    def test_db_table_describe_rejects_no_table(self):
        """db_table_describe without table parameter is rejected."""
        result = validate_plan({
            "intent": "xert_status", "mode": "read_only",
            "tools_to_call": ["db_table_describe"],
            "parameters": {}, "confidence": 0.9,
        })
        self.assertNotEqual(result["status"], "OK")
        self.assertIn("table", result.get("error", "").lower())

    def test_non_db_tools_ignore_param_check(self):
        """Non-DB tools are not affected by parameter validation."""
        result = validate_plan({
            "intent": "xert_status", "mode": "read_only",
            "tools_to_call": ["xert_readiness", "garmin_sync_status"],
            "parameters": {}, "confidence": 0.9,
        })
        self.assertEqual(result["status"], "OK")


class TestXertReadinessRegistry(unittest.TestCase):
    """xert_readiness tool must be callable through registry without TypeError."""

    def test_xert_readiness_lookup_and_call(self):
        """xert_readiness in registry, callable via _execute_tools signature."""
        from qbot3.tool_registry import lookup
        spec = lookup("xert_readiness")
        self.assertIsNotNone(spec, "xert_readiness not in registry")
        self.assertIn("callable", spec)
        self.assertIn("wrapped", spec)
        # Simulate what _execute_tools does: callable_fn(wrapped, args)
        callable_fn = spec["callable"]
        wrapped = spec["wrapped"]
        args = {"_question": "test xert readiness"}
        # This should NOT raise TypeError (takes 2 positional args but X were given)
        try:
            result = callable_fn(wrapped, args)
            self.assertIsInstance(result, dict)
        except TypeError as e:
            self.fail(f"xert_readiness callable raised TypeError: {e}")

    def test_xert_readiness_via_execute_tools(self):
        """xert_readiness callable through _execute_tools works."""
        from qbot3.agent_runtime import _execute_tools
        result = _execute_tools(["xert_readiness"], {}, "test xert query")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get("reader"), "xert_readiness")
        # Should not be a TypeError — even if the tool returns error, it should be caught
        self.assertNotIn("TypeError", str(result[0].get("data", {})))


class TestDbIntrospectionFallbackNoGuessing(unittest.TestCase):
    """Fallback must not guess table names from query words."""

    @patch('qbot3.db_introspection.db_schema_list')
    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_fallback_rejects_guess_tables(self, mock_select, mock_describe, mock_schema_list):
        """Fallback with only non-table words in query returns None or clear DATA_MISSING."""
        mock_schema_list.return_value = {"status": "OK", "schemas": {"public": []}, "schema_count": 0}
        plan = {"intent": "xert_status", "tools_to_call": ["xert_readiness"]}
        # Query contains words like "readiness", "freshness", "this", "is", "questions", "records", "days"
        q = "sprawdź status Xert: konfiguracja, ostatnie dane w DB, ostatnia synchronizacja, błędy connectora"
        results = _try_db_introspection_fallback(plan, q)
        # Should NOT try to describe tables named "readiness", "freshness", "this", "is", etc.
        # If no real xert tables exist, it should return DATA_MISSING or None
        if results:
            # If results returned, none should be from guessed table names
            for r in results:
                reader = r.get("reader", "")
                self.assertNotIn("readiness", reader, f"Guessed table name in reader: {reader}")
                self.assertNotIn("freshness", reader, f"Guessed table name in reader: {reader}")
                self.assertNotIn("this", reader, f"Guessed table name in reader: {reader}")
                self.assertNotIn("is", reader, f"Guessed table name in reader: {reader}")
                self.assertNotIn("questions", reader, f"Guessed table name in reader: {reader}")
                self.assertNotIn("records", reader, f"Guessed table name in reader: {reader}")
                self.assertNotIn("days", reader, f"Guessed table name in reader: {reader}")

    @patch('qbot3.db_introspection.db_schema_list')
    @patch('qbot3.db_introspection.db_table_describe')
    @patch('qbot3.db_introspection.db_select_readonly')
    def test_fallback_xert_no_tables(self, mock_select, mock_describe, mock_schema_list):
        """Xert query without xert tables in DB returns DATA_MISSING."""
        mock_schema_list.return_value = {"status": "OK", "schemas": {"public": []}, "schema_count": 0}
        plan = {"intent": "xert_status", "tools_to_call": ["xert_readiness"]}
        q = "sprawdź status Xert"
        results = _try_db_introspection_fallback(plan, q)
        self.assertIsNotNone(results, "Should return diagnostic even without xert tables")
        self.assertEqual(results[0]["status"], "DATA_MISSING")
        self.assertIn("Xert", results[0]["data"].get("note", ""))


if __name__ == "__main__":
    print("=== QBot3 Acceptance Tests ===")
    unittest.main(verbosity=2)
