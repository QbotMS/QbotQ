#!/usr/bin/env python3
"""Regression tests: readiness diagnostics noise separation and schema-aware probes."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, "/opt/qbot/app")

import api_db
import qbot_operator_tools as operator_tools
import qbot_ops_tools as ops_tools
import qbot_tools
import qbot_legacy_cutover_tools


class TestReadinessDiagnosticsNoise(unittest.TestCase):
    def test_error_summary_separates_noise_from_active_errors(self):
        rows = [
            {
                "id": 34,
                "tool": "",
                "result": {"error": "unknown tool: ", "available": ["qbot_query"]},
                "created_at": datetime(2026, 6, 29, 16, 25, 46, tzinfo=timezone.utc),
            },
            {
                "id": 24,
                "tool": "qbot_action_execute",
                "result": {
                    "error": "A route with name 'rwgps_55257604' already exists (ID 55556706). Skipping.",
                    "status": "DUPLICATE_SKIPPED",
                },
                "created_at": datetime(2026, 6, 8, 17, 6, 57, tzinfo=timezone.utc),
            },
            {
                "id": 8,
                "tool": "qbot_query",
                "result": {"error": "unknown error"},
                "created_at": datetime(2026, 5, 30, 6, 49, 18, tzinfo=timezone.utc),
            },
            {
                "id": 7,
                "tool": "qbot_query",
                "result": {"error": "unknown tool: qbot_query"},
                "created_at": datetime(2026, 5, 30, 6, 48, 56, tzinfo=timezone.utc),
            },
        ]

        with patch.object(api_db, "select_tool_calls", return_value=rows):
            result = operator_tools._tool_qbot_error_summary({"limit": 50})

        self.assertEqual(result["active_errors_count"], 0)
        self.assertEqual(result["historical_errors_count"], 1)
        self.assertEqual(result["expected_test_errors_count"], 2)
        self.assertEqual(result["malformed_legacy_records_count"], 1)
        self.assertEqual(result["status"], "WARN")

    def test_readiness_uses_only_active_errors(self):
        fake_error_summary = {
            "tool": "qbot_error_summary",
            "status": "OK",
            "active_errors_count": 0,
            "active_error_rate": 0.0,
            "historical_errors_count": 2,
            "expected_test_errors_count": 1,
            "malformed_legacy_records_count": 1,
            "classified_errors": {
                "active_errors": 0,
                "expected_test_errors": 1,
                "historical_errors": 2,
                "malformed_legacy_records": 1,
                "permission_warnings": 0,
            },
        }

        with patch.object(operator_tools, "_tool_qbot_api_self_check", return_value={"status": "OK", "checks": []}), \
                patch.object(operator_tools, "_tool_qbot_project_guard_check", return_value={"status": "OK", "violations": []}), \
                patch.object(operator_tools, "_tool_qbot_git_status", return_value={"clean": True, "status_short": []}), \
                patch.object(operator_tools, "_tool_qbot_db_overview", return_value={"db_connected": True}), \
                patch.object(operator_tools, "_tool_qbot_error_summary", return_value=fake_error_summary), \
                patch.object(api_db, "ping", return_value=True), \
                patch.object(ops_tools, "_tool_qbot_backup_status", return_value={"status": "OK"}), \
                patch.object(ops_tools, "_tool_qbot_backup_timer_status", return_value={"status": "OK"}), \
                patch.object(ops_tools, "_tool_qbot_restore_drill_status", return_value={"status": "OK"}):
            readiness = operator_tools._tool_qbot_readiness_report()

        self.assertEqual(readiness["status"], "READY")
        error_check = next(c for c in readiness["checks"] if c["name"] == "error_summary")
        self.assertEqual(error_check["status"], "OK")
        self.assertEqual(error_check["detail"]["active_errors_count"], 0)
        self.assertEqual(error_check["detail"]["active_error_rate"], 0.0)

    def test_project_guard_marks_gate_dependency_as_info(self):
        real_run = qbot_tools.subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd and cmd[0] == "ss":
                return CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_run(cmd, *args, **kwargs)

        with patch.object(qbot_tools, "_tool_qbot_project_diff_summary", return_value={"status_short": [], "diff_files": []}), \
                patch.object(qbot_tools, "_tool_qbot_git_status", return_value={"clean": True}), \
                patch.object(qbot_tools.subprocess, "run", side_effect=fake_run):
            guard = qbot_tools._tool_qbot_project_guard_check()

        self.assertEqual(guard["status"], "OK")
        self.assertTrue(any(v.get("severity") == "INFO" and v.get("expected_dependency") for v in guard["violations"]))
        self.assertFalse(any(v.get("severity") == "WARN" and "gate_hikconnect.py" in v.get("what", "") for v in guard["violations"]))

    def test_rwgps_storage_overview_prefers_qbot_v2_schema(self):
        class FakeCursor:
            def __init__(self, row):
                self._row = row

            def fetchone(self):
                return self._row

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, query, params=()):
                q = str(query)
                if "to_regclass" in q:
                    name = str(params[0])
                    return FakeCursor({"exists": name.startswith("qbot_v2.")})
                if "FROM qbot_v2.route_artifacts ORDER BY id DESC LIMIT 1" in q:
                    return FakeCursor({"id": 10, "route_id": "55798129", "artifact_path": "/opt/qbot/artifacts/exports/rwgps/rwgps_55798129.gpx", "filename": "rwgps_55798129.gpx", "sha256": "abc", "created_at": datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc), "updated_at": datetime(2026, 6, 29, 10, 5, tzinfo=timezone.utc)})
                if "FROM qbot_v2.route_parse_results ORDER BY id DESC LIMIT 1" in q:
                    return FakeCursor({"id": 20, "route_artifact_id": 10, "parser_version": "gpx-summary-v1", "source_artifact_sha256": "abc", "parsed_at": datetime(2026, 6, 29, 10, 5, tzinfo=timezone.utc)})
                if "FROM qbot_v2.route_surface_profiles ORDER BY id DESC LIMIT 1" in q:
                    return FakeCursor({"id": 30, "route_artifact_id": 10, "enrichment_version": "surface-profile-v1", "source_artifact_sha256": "abc", "enriched_at": datetime(2026, 6, 29, 10, 10, tzinfo=timezone.utc), "sample_every_m": 50})
                if "FROM qbot_v2.route_surface_segments ORDER BY id DESC LIMIT 1" in q:
                    return FakeCursor({"id": 40, "route_surface_profile_id": 30, "segment_index": 0, "surface": "asphalt", "source": "osm"})
                if "FROM qbot_v2.route_artifacts" in q and "COUNT(*)" in q:
                    return FakeCursor({"cnt": 2})
                if "FROM qbot_v2.route_parse_results" in q and "COUNT(*)" in q:
                    return FakeCursor({"cnt": 1})
                if "FROM qbot_v2.route_surface_profiles" in q and "COUNT(*)" in q:
                    return FakeCursor({"cnt": 1})
                if "FROM qbot_v2.route_surface_segments" in q and "COUNT(*)" in q:
                    return FakeCursor({"cnt": 3})
                raise AssertionError(f"unexpected query: {q}")

        original_conn = api_db._conn
        api_db._conn = lambda: FakeConn()
        try:
            overview = api_db.rwgps_storage_overview()
        finally:
            api_db._conn = original_conn

        self.assertTrue(overview["schema_ready"])
        self.assertEqual(overview["seed_status"], "SEEDED")
        self.assertEqual(overview["missing_tables"], [])
        self.assertEqual(overview["tables"]["route_surface_profiles"]["schema"], "qbot_v2")
        self.assertEqual(overview["tables"]["route_surface_segments"]["schema"], "qbot_v2")

    def test_cutover_status_exposes_legacy_note(self):
        status = qbot_legacy_cutover_tools._tool_qbot_legacy_cutover_status()
        self.assertIn("legacy still enabled", status["readiness_note"])
        self.assertEqual(status["takeover_readiness_percent"], 95)


if __name__ == "__main__":
    unittest.main()
