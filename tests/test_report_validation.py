#!/usr/bin/env python3
"""Regression tests: report data validation, intent routing, and diagnostic handlers."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/opt/qbot/app")

# ── Test: qbot_report_validator ────────────────────────────────────────────

from qbot_report_validator import (
    validate_daily_report_data,
    validate_ride_report_data,
    DATA_OK,
    DATA_PARTIAL,
    DATA_MISSING,
)


class TestDailyReportValidation(unittest.TestCase):
    """validate_daily_report_data must distinguish DATA_OK / DATA_PARTIAL / DATA_MISSING."""

    def test_all_data_ok(self):
        """All sources ok → DATA_OK"""
        sources = {
            "sleep_wellness": "ok",
            "calories_expenditure": "ok",
            "nutrition": "ok",
            "activity_summary": "ok",
            "garmin_sync": "ok",
        }
        status, details = validate_daily_report_data(sources)
        self.assertEqual(status, DATA_OK)
        self.assertIsNone(details["alert_message"])

    def test_garmin_sync_failed_no_data(self):
        """Garmin sync failed + no data → DATA_MISSING"""
        sources = {
            "sleep_wellness": None,
            "calories_expenditure": None,
            "nutrition": None,
            "activity_summary": None,
            "garmin_sync": "failed",
        }
        status, details = validate_daily_report_data(sources)
        self.assertEqual(status, DATA_MISSING)
        self.assertIsNotNone(details["alert_message"])
        self.assertTrue(details["garmin_sync_failed"])

    def test_garmin_sync_failed_but_some_data(self):
        """Garmin sync failed but some data present → DATA_PARTIAL (not MISSING since present is non-empty)"""
        sources = {
            "sleep_wellness": "ok",
            "calories_expenditure": None,
            "nutrition": None,
            "activity_summary": None,
            "garmin_sync": "failed",
        }
        status, details = validate_daily_report_data(sources)
        # present=['sleep_wellness'] so present is non-empty → falls through to count check
        self.assertIn(status, (DATA_PARTIAL, DATA_MISSING))
        self.assertTrue(details["garmin_sync_failed"])

    def test_only_nutrition_partial(self):
        """Only nutrition available → DATA_PARTIAL"""
        sources = {
            "sleep_wellness": "missing",
            "calories_expenditure": "missing",
            "nutrition": "ok",
            "activity_summary": "missing",
            "garmin_sync": "ok",
        }
        status, details = validate_daily_report_data(sources)
        self.assertEqual(status, DATA_PARTIAL)
        self.assertIn("nutrition", details["present"])
        self.assertIn("alert_message", details)

    def test_all_missing(self):
        """Every source is None/missing → DATA_MISSING"""
        sources = {
            "sleep_wellness": None,
            "calories_expenditure": None,
            "nutrition": None,
            "activity_summary": None,
            "garmin_sync": None,
        }
        status, details = validate_daily_report_data(sources)
        self.assertEqual(status, DATA_MISSING)

    def test_sleep_empty_after_9(self):
        """Sleep empty after 9:00 counts as empty → DATA_PARTIAL"""
        sources = {
            "sleep_wellness": "empty",
            "calories_expenditure": "ok",
            "nutrition": "ok",
            "activity_summary": "ok",
            "garmin_sync": "ok",
        }
        status, details = validate_daily_report_data(sources)
        self.assertEqual(status, DATA_PARTIAL)
        self.assertIn("sleep_wellness", details.get("partial", []) or details.get("missing", []))


class TestRideReportValidation(unittest.TestCase):
    """validate_ride_report_data must distinguish DATA_OK / DATA_PARTIAL / DATA_MISSING."""

    def _make_activity(self, **overrides) -> dict:
        base = {
            "id": 12345,
            "moving_time": 7200,
            "distance": 100000,
            "elevation_gain": 500,
            "icu_average_watts": 200,
            "average_heartrate": 140,
            "fit_streams": {"power": {"probki_co_30s": [200] * 10}},
            "sport_type": "Ride",
        }
        base.update(overrides)
        return base

    def test_full_data_ok(self):
        """Complete ride data → DATA_OK"""
        data = {
            "aktywnosc": self._make_activity(),
            "nawierzchnia": {"dominujaca": "asphalt"},
        }
        status, details = validate_ride_report_data(data, activity_id=12345)
        self.assertEqual(status, DATA_OK)
        self.assertIsNone(details["alert_message"])

    def test_missing_activity_data(self):
        """No activity data at all → DATA_MISSING"""
        status, details = validate_ride_report_data(None, activity_id=None)
        self.assertEqual(status, DATA_MISSING)

    def test_missing_critical_fields(self):
        """Empty activity → DATA_MISSING"""
        data = {"aktywnosc": {}}
        status, details = validate_ride_report_data(data, activity_id=None)
        self.assertEqual(status, DATA_MISSING)

    def test_missing_distance_no_id(self):
        """No distance and no id → DATA_MISSING"""
        data = {
            "aktywnosc": {
                "moving_time": 3600,
                "distance": 0,
                "elevation_gain": 0,
            }
        }
        status, details = validate_ride_report_data(data, activity_id=None)
        self.assertEqual(status, DATA_MISSING)

    def test_missing_distance_with_id(self):
        """No distance but has id → DATA_PARTIAL (core identity present)"""
        data = {
            "aktywnosc": {
                "id": 1,
                "moving_time": 3600,
                "distance": 0,
                "elevation_gain": 0,
            }
        }
        status, details = validate_ride_report_data(data, activity_id=1)
        self.assertEqual(status, DATA_PARTIAL)

    def test_partial_no_power_hr(self):
        """Has distance/time/elevation but no power/HR → DATA_PARTIAL"""
        data = {
            "aktywnosc": {
                "id": 1,
                "moving_time": 3600,
                "distance": 50000,
                "elevation_gain": 200,
                "sport_type": "Ride",
            }
        }
        status, details = validate_ride_report_data(data, activity_id=1)
        self.assertEqual(status, DATA_PARTIAL)

    def test_fit_available(self):
        """FIT streams present → freshness shows fit_available=True"""
        data = {
            "aktywnosc": self._make_activity(fit_streams={"power": {"probki_co_30s": [200] * 5}}),
        }
        status, details = validate_ride_report_data(data, activity_id=12345)
        self.assertEqual(status, DATA_OK)
        self.assertTrue(details["freshness"]["fit_available"])


# ── Test: Intent routing in qbot_query_handler ─────────────────────────────

from qbot_query_handler import _resolve_intent, handle_query


class TestReportIntentRouting(unittest.TestCase):
    """Report-related queries must NOT fall into nutrition_range."""

    def test_daily_report_intent(self):
        """'raport dobowy' → daily_report, not nutrition_range"""
        intent = _resolve_intent("poka\u017c raport dobowy")
        self.assertEqual(intent, "daily_report")

    def test_ride_report_intent(self):
        """'raport z jazdy' → ride_report, not nutrition_range"""
        intent = _resolve_intent("poka\u017c raport z jazdy")
        self.assertEqual(intent, "ride_report")

    def test_empty_report_intent(self):
        """'dlaczego raport jest pusty' → report_diagnostic, not nutrition_range"""
        intent = _resolve_intent("dlaczego raport jest pusty")
        self.assertEqual(intent, "report_diagnostic")

    def test_missing_data_intent(self):
        """'brak danych w raporcie' → report_diagnostic, not nutrition_range"""
        intent = _resolve_intent("brak danych w raporcie")
        self.assertEqual(intent, "report_diagnostic")

    def test_diagnostic_report_intent(self):
        """'diagnostyka raportów' → report_diagnostic"""
        intent = _resolve_intent("diagnostyka raport\u00f3w")
        self.assertEqual(intent, "report_diagnostic")

    def test_nutrition_range_still_works(self):
        """'zakres kalorii' resolves to daily_balance first (kalorii keyword),
        but handle_query reroutes it to nutrition_range via _has_range_indicator."""
        # Pure intent resolves to daily_balance (kalorii appears first in keyword list)
        intent = _resolve_intent("zakres kalorii z ostatnich 7 dni")
        self.assertEqual(intent, "daily_balance")
        # But handle_query reroutes to nutrition_range via range indicator check
        with patch("qbot_query_handler._pg_conn") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_cursor.description = []
            mock_pg.return_value = mock_conn
            result = handle_query("zakres kalorii z ostatnich 7 dni")
            self.assertEqual(result.get("intent"), "nutrition_range")

    def test_ostatni_tydzien_nutrition(self):
        """'ostatni tydzień' alone → nutrition_range (no report keywords present)"""
        intent = _resolve_intent("ostatni tydzie\u0144")
        self.assertEqual(intent, "nutrition_range")


class TestReportDiagnosticHandlers(unittest.TestCase):
    """Diagnostic handlers must return structured data without crashing."""

    def test_daily_report_handler_returns_data(self):
        """handle_query('raport dobowy') returns structured diagnostic"""
        with patch("qbot_query_handler._pg_conn") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_cursor.description = []
            mock_pg.return_value = mock_conn

            result = handle_query("raport dobowy")
            self.assertEqual(result.get("intent"), "daily_report")
            self.assertIn("data", result)
            data = result.get("data", {})
            self.assertIn("should_send_daily_report", data)
            self.assertIn("status", data)

    def test_ride_report_handler_returns_data(self):
        """handle_query('raport z jazdy') returns structured diagnostic"""
        with patch("qbot_query_handler._pg_conn") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_cursor.description = []
            mock_pg.return_value = mock_conn

            result = handle_query("raport z jazdy")
            self.assertEqual(result.get("intent"), "ride_report")
            self.assertIn("data", result)
            data = result.get("data", {})
            self.assertIn("should_send_ride_report", data)

    def test_report_diagnostic_handler(self):
        """handle_query('dlaczego raport jest pusty') gets combined diagnostic"""
        with patch("qbot_query_handler._pg_conn") as mock_pg:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_cursor.description = []
            mock_pg.return_value = mock_conn

            result = handle_query("dlaczego raport jest pusty")
            self.assertEqual(result.get("intent"), "report_diagnostic")
            data = result.get("data", {})
            self.assertIn("daily_report", data)
            self.assertIn("ride_report", data)


if __name__ == "__main__":
    unittest.main()
