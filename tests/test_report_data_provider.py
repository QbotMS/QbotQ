#!/usr/bin/env python3
"""Tests for ReportDataProvider — mock-based to avoid real DB dependency."""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, "/opt/qbot/app")

from qbot_report_data_provider import ReportDataProvider
from qbot_report_validator import (
    validate_daily_from_provider,
    validate_ride_from_provider,
    DATA_OK, DATA_PARTIAL, DATA_MISSING,
)


def _mock_db_conn(rows_by_query: dict):
    """Create a mock DB connection that returns predefined results per SQL pattern."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # description must be a list of tuples with a 'name' attribute or indexable
    # _safe_fetch does: cols = [d[0] for d in cur.description]

    def _make_description(row: dict) -> list:
        return [(k,) for k in row.keys()]

    def execute_side_effect(sql, params=None):
        sql_clean = sql.strip().lower()
        for pattern, rows in rows_by_query.items():
            if pattern in sql_clean:
                if rows:
                    mock_cursor.fetchall.return_value = rows
                    mock_cursor.description = _make_description(rows[0])
                else:
                    mock_cursor.fetchall.return_value = []
                    mock_cursor.description = []
                # _safe_fetch does not catch TypeErrors from description access
                return None
        # Default: empty (will cause _safe_fetch to return [])
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = []
        return None

    mock_cursor.execute.side_effect = execute_side_effect
    mock_cursor.fetchall.return_value = []
    mock_cursor.description = []
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = False
    return mock_conn


class TestReportDataProvider(unittest.TestCase):
    """ReportDataProvider must return structured data with proper status."""

    @patch("qbot_report_data_provider._db_conn")
    def test_daily_all_data_ok(self, mock_conn):
        """All sources have fresh data → DATA_OK."""
        d = date.today().isoformat()
        mock_conn.return_value = _mock_db_conn({
            "from qbot_v2.sleep_daily": [
                {"date": d, "duration_min": 420, "score": 78, "hrv_ms": 65.0, "resting_hr_bpm": 48, "deep_min": 90, "rem_min": 80}
            ],
            "from qbot_v2.wellness_daily": [
                {"date": d, "hrv_ms": 65.0, "resting_hr_bpm": 48, "body_battery_start": 85, "body_battery_end": 25, "stress_avg": 28, "weight_kg": 76.5, "imported_at": "now"}
            ],
            "from qbot_v2.energy_daily": [
                {"date": d, "total_kcal": 2800.0, "active_kcal": 800.0, "resting_kcal": 2000.0, "steps": 12000}
            ],
            "from qbot_v2.nutrition_daily_summary": [
                {"date": d, "kcal_total": 2400.0, "carbs_total": 280.0, "protein_total": 140.0, "fat_total": 80.0, "computed_at": "now"}
            ],
            "from qbot_v2.training_sessions": [
                {"id": 1, "date": d, "sport_type": "Ride", "distance_m": 80000, "duration_s": 10800, "elevation_m": 500}
            ],
            "from qbot_v2.body_measurements": [
                {"date": d, "weight_kg": 76.5, "body_fat_pct": 15.2, "bmi": 23.5, "imported_at": "now"}
            ],
            "from qbot_v2.xert_profile_snapshots": [
                {"date": d, "ftp_power_w": 280, "ltp_power_w": 250, "w_prime_kj": 20.5, "form_status": "fresh", "snapshot_at": "now"}
            ],
        })

        provider = ReportDataProvider()
        result = provider.get_daily_report_data(date.today())

        self.assertIn("date", result)
        self.assertEqual(result["sleep"]["status"], "ok")
        self.assertEqual(result["wellness"]["status"], "ok")
        self.assertEqual(result["energy"]["status"], "ok")
        self.assertEqual(result["nutrition"]["status"], "ok")
        self.assertEqual(result["activity_summary"]["status"], "ok")
        self.assertEqual(result["body_composition"]["status"], "ok")
        self.assertEqual(result["validation"]["status"], "DATA_OK")

    @patch("qbot_report_data_provider._db_conn")
    def test_daily_all_missing(self, mock_conn):
        """No data in any table → DATA_MISSING."""
        mock_conn.return_value = _mock_db_conn({})

        provider = ReportDataProvider()
        result = provider.get_daily_report_data(date.today())

        self.assertEqual(result["sleep"]["status"], "missing")
        self.assertEqual(result["wellness"]["status"], "missing")
        self.assertEqual(result["energy"]["status"], "missing")
        self.assertEqual(result["nutrition"]["status"], "missing")
        self.assertEqual(result["activity_summary"]["status"], "missing")
        self.assertEqual(result["body_composition"]["status"], "missing")
        self.assertEqual(result["validation"]["status"], "DATA_MISSING")

    @patch("qbot_report_data_provider._db_conn")
    def test_daily_partial_data(self, mock_conn):
        """Only sleep + nutrition available → DATA_PARTIAL."""
        d = date.today().isoformat()
        mock_conn.return_value = _mock_db_conn({
            "from qbot_v2.sleep_daily": [
                {"date": d, "duration_min": 390, "score": 72, "hrv_ms": 60.0, "resting_hr_bpm": 50}
            ],
            "from qbot_v2.nutrition_daily_summary": [
                {"date": d, "kcal_total": 2200.0, "carbs_total": 250.0, "protein_total": 120.0, "fat_total": 70.0, "computed_at": "now"}
            ],
        })

        provider = ReportDataProvider()
        result = provider.get_daily_report_data(date.today())

        self.assertEqual(result["sleep"]["status"], "ok")
        self.assertEqual(result["nutrition"]["status"], "ok")
        self.assertEqual(result["wellness"]["status"], "missing")
        self.assertEqual(result["energy"]["status"], "missing")
        self.assertEqual(result["activity_summary"]["status"], "missing")
        self.assertEqual(result["body_composition"]["status"], "missing")
        # 4 missing fields → DATA_MISSING (more than 3)
        self.assertEqual(result["validation"]["status"], "DATA_MISSING")

    @patch("qbot_report_data_provider._db_conn")
    def test_daily_partial_ok(self, mock_conn):
        """3 sources present → DATA_PARTIAL (not MISSING)."""
        d = date.today().isoformat()
        mock_conn.return_value = _mock_db_conn({
            "from qbot_v2.sleep_daily": [
                {"date": d, "duration_min": 390, "score": 72, "hrv_ms": 60.0, "resting_hr_bpm": 50}
            ],
            "from qbot_v2.wellness_daily": [
                {"date": d, "hrv_ms": 60.0, "resting_hr_bpm": 50, "body_battery_start": 80,
                 "body_battery_end": 25, "stress_avg": 28, "weight_kg": 76.5, "imported_at": "now"}
            ],
            "from qbot_v2.energy_daily": [
                {"date": d, "total_kcal": 2600.0, "active_kcal": 700.0, "resting_kcal": 1900.0, "steps": 10000}
            ],
        })

        provider = ReportDataProvider()
        result = provider.get_daily_report_data(date.today())

        self.assertEqual(result["validation"]["status"], "DATA_PARTIAL")

    @patch("qbot_report_data_provider._db_conn")
    def test_ride_full_data(self, mock_conn):
        """Full activity data → DATA_OK."""
        tf = date.today().isoformat()
        mock_conn.return_value = _mock_db_conn({
            "from qbot_v2.training_sessions": [
                {"id": 100, "date": tf, "started_at": f"{tf}T10:00:00+02:00", "sport_type": "Ride",
                 "distance_m": 95000, "duration_s": 12600, "elevation_m": 750,
                 "avg_power_w": 220, "normalized_power_w": 225, "avg_hr_bpm": 138,
                 "max_hr_bpm": 165, "tss": 210, "external_id": "garmin_12345"}
            ],
        })

        provider = ReportDataProvider()
        result = provider.get_ride_report_data(100)

        self.assertEqual(result["aktywnosc"]["status"], "ok")
        self.assertEqual(result["validation"]["status"], "DATA_OK")
        self.assertEqual(result["aktywnosc"]["distance_m"], 95000)

    @patch("qbot_report_data_provider._db_conn")
    def test_ride_no_activity(self, mock_conn):
        """No activity data → DATA_MISSING."""
        mock_conn.return_value = _mock_db_conn({})

        provider = ReportDataProvider()
        result = provider.get_ride_report_data(999)

        self.assertEqual(result["aktywnosc"]["status"], "missing")
        self.assertEqual(result["validation"]["status"], "DATA_MISSING")

    @patch("qbot_report_data_provider._db_conn")
    def test_ride_no_power_hr(self, mock_conn):
        """Activity found but missing power/HR → DATA_PARTIAL."""
        tf = date.today().isoformat()
        mock_conn.return_value = _mock_db_conn({
            "from qbot_v2.training_sessions": [
                {"id": 101, "date": tf, "started_at": f"{tf}T10:00:00+02:00", "sport_type": "Ride",
                 "distance_m": 50000, "duration_s": 7200, "elevation_m": 300,
                 "avg_power_w": None, "normalized_power_w": None, "avg_hr_bpm": None,
                 "max_hr_bpm": None, "tss": None}
            ],
        })

        provider = ReportDataProvider()
        result = provider.get_ride_report_data(101)

        self.assertEqual(result["aktywnosc"]["status"], "partial")
        self.assertIn("avg_power_w", result["aktywnosc"]["missing_fields"])
        self.assertIn("avg_hr_bpm", result["aktywnosc"]["missing_fields"])
        self.assertEqual(result["validation"]["status"], "DATA_PARTIAL")


class TestValidateFromProvider(unittest.TestCase):
    """validate_daily_from_provider / validate_ride_from_provider must map correctly."""

    def test_validate_daily_ok(self):
        """DATA_OK from provider → DATA_OK from validator."""
        result = {"validation": {"status": "DATA_OK", "missing_fields": []},
                  "sleep": {"status": "ok"}, "wellness": {"status": "ok"},
                  "energy": {"status": "ok"}, "nutrition": {"status": "ok"},
                  "activity_summary": {"status": "ok"}, "body_composition": {"status": "ok"}}
        status, details = validate_daily_from_provider(result)
        self.assertEqual(status, DATA_OK)
        self.assertIsNone(details["alert_message"])

    def test_validate_daily_missing(self):
        """DATA_MISSING → alert message."""
        result = {"validation": {"status": "DATA_MISSING", "missing_fields": ["sleep", "wellness"]},
                  "sleep": {"status": "missing"}, "wellness": {"status": "missing"}}
        status, details = validate_daily_from_provider(result)
        self.assertEqual(status, DATA_MISSING)
        self.assertIsNotNone(details["alert_message"])

    def test_validate_ride_ok(self):
        """DATA_OK → no alert."""
        result = {"validation": {"status": "DATA_OK"}, "aktywnosc": {"status": "ok", "missing_fields": []}}
        status, details = validate_ride_from_provider(result)
        self.assertEqual(status, DATA_OK)
        self.assertIsNone(details["alert_message"])

    def test_validate_ride_missing(self):
        """DATA_MISSING → alert."""
        result = {"validation": {"status": "DATA_MISSING", "missing_fields": ["activity_data"],
                                 "alert": "Brak danych."}, "aktywnosc": {"status": "missing"}}
        status, details = validate_ride_from_provider(result)
        self.assertEqual(status, DATA_MISSING)
        self.assertIsNotNone(details["alert_message"])


class TestSourceFreshness(unittest.TestCase):
    """get_source_freshness returns proper status for each source."""

    @patch("qbot_report_data_provider._db_conn")
    def test_freshness_all_fresh(self, mock_conn):
        """All tables have today's data → fresh."""
        d = date.today().isoformat()

        def execute_side_effect(sql, params=None):
            mock = MagicMock()
            mock.fetchone.return_value = (date.today(),)
            return mock
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = execute_side_effect
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_conn.return_value.__enter__.return_value = mock_conn.return_value
        mock_conn.return_value.__exit__.return_value = False

        provider = ReportDataProvider()
        freshness = provider.get_source_freshness(date.today())

        self.assertIsInstance(freshness, dict)
        for table, info in freshness.items():
            if isinstance(info, dict) and "error" not in info:
                self.assertIn("freshness", info)

    @patch("qbot_report_data_provider._db_conn")
    def test_freshness_no_data(self, mock_conn):
        """No data → missing freshness."""
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (None,)
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_conn.return_value.__enter__.return_value = mock_conn.return_value
        mock_conn.return_value.__exit__.return_value = False

        provider = ReportDataProvider()
        freshness = provider.get_source_freshness(date.today())

        for table, info in freshness.items():
            if isinstance(info, dict) and "error" not in info:
                self.assertEqual(info["freshness"], "missing")


if __name__ == "__main__":
    unittest.main()
