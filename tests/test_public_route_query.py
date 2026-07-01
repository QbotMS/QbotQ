"""Regression tests for the public qbot.query wrapper."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import qbot_tools


class TestPublicRouteQueryRouteReport(unittest.TestCase):
    def test_full_route_analysis_uses_route_report(self) -> None:
        route_report_out = {
            "status": "OK",
            "variant": "pelny",
            "route_id": "55798129",
            "analysis": (
                "## WERDYKT TRASY / DECYZJA\n"
                "- decyzja: JEDŹ OSTROŻNIE\n\n"
                "## A0C - PROFIL WYSOKOŚCI / PODJAZDY\n"
                "- ascent_smoothed=426.7 m\n\n"
                "## A4 - METEO / WBGT / alerty upału\n"
                "- WBGT=31.0\n"
            ),
            "context_for_section_c": "C1 ...",
            "notes": "",
        }

        with patch("qbot_query_router.query", side_effect=AssertionError("legacy router should not run")), \
                patch("qbot_route_report_tool._tool_route_report", return_value=route_report_out) as mock_report:
            result = qbot_tools._tool_qbot_query(
                {
                    "query": "pełna analiza trasy 55798129 start 2026-06-30 15:00",
                    "mode": "read_only",
                    "scope": "all",
                }
            )

        self.assertEqual(result["status"], "ok")
        self.assertIn("WERDYKT TRASY / DECYZJA", result["answer"])
        self.assertIn("A0C - PROFIL WYSOKOŚCI / PODJAZDY", result["answer"])
        self.assertIn("A4 - METEO / WBGT / alerty upału", result["answer"])
        self.assertEqual(result["route_report"]["variant"], "pelny")
        self.assertEqual(result["route_report"]["route_id"], "55798129")
        self.assertEqual(mock_report.call_args.args[0]["variant"], "pelny")
        self.assertEqual(mock_report.call_args.args[0]["route_id"], "55798129")
        self.assertEqual(mock_report.call_args.args[0]["start"], "2026-06-30 15:00")

    def test_route_report_failure_falls_back_to_legacy_router(self) -> None:
        with patch("qbot_route_report_tool._tool_route_report", return_value={"status": "ERROR", "error": "boom"}) as mock_report, \
                patch("qbot_query_router.query", return_value={"status": "ok", "answer": "router answer"}) as mock_router:
            result = qbot_tools._tool_qbot_query(
                {
                    "query": "pełna analiza trasy 55798129 start 2026-06-30 15:00",
                    "mode": "read_only",
                    "scope": "all",
                }
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer"], "router answer")
        mock_report.assert_called_once()
        mock_router.assert_called_once()

    def test_route_report_exception_falls_back_to_legacy_router(self) -> None:
        with patch("qbot_route_report_tool._tool_route_report", side_effect=RuntimeError("boom")) as mock_report, \
                patch("qbot_query_router.query", return_value={"status": "ok", "answer": "router answer"}) as mock_router:
            result = qbot_tools._tool_qbot_query(
                {
                    "query": "pełna analiza trasy 55798129 start 2026-06-30 15:00",
                    "mode": "read_only",
                    "scope": "all",
                }
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer"], "router answer")
        mock_report.assert_called_once()
        mock_router.assert_called_once()

    def test_near_miss_route_query_does_not_use_route_report(self) -> None:
        with patch("qbot_route_report_tool._tool_route_report", side_effect=AssertionError("route_report bypass should not run")), \
                patch("qbot_query_router.query", return_value={"status": "ok", "answer": "router answer"}) as mock_router:
            result = qbot_tools._tool_qbot_query(
                {
                    "query": "analiza trasy 55798129 start 2026-06-30 15:00",
                    "mode": "read_only",
                    "scope": "all",
                }
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer"], "router answer")
        mock_router.assert_called_once()

    def test_regular_question_does_not_use_route_report(self) -> None:
        with patch("qbot_route_report_tool._tool_route_report", side_effect=AssertionError("route_report bypass should not run")), \
                patch("qbot_query_router.query", return_value={"status": "ok", "answer": "router answer"}) as mock_router:
            result = qbot_tools._tool_qbot_query(
                {
                    "query": "ile kalorii dziś",
                    "mode": "read_only",
                    "scope": "all",
                }
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer"], "router answer")
        mock_router.assert_called_once()

    def test_route_write_intent_does_not_use_route_report(self) -> None:
        with patch("qbot_route_report_tool._tool_route_report", side_effect=AssertionError("route_report bypass should not run")), \
                patch("qbot_query_router.query", return_value={"status": "ok", "answer": "router answer"}) as mock_router:
            result = qbot_tools._tool_qbot_query(
                {
                    "query": "dodaj trasę 123",
                    "mode": "read_only",
                    "scope": "all",
                }
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer"], "router answer")
        mock_router.assert_called_once()

    def test_non_route_query_still_uses_router(self) -> None:
        with patch("qbot_query_router.query", return_value={"status": "ok", "answer": "router answer"}) as mock_router:
            result = qbot_tools._tool_qbot_query({"query": "status qbot", "mode": "read_only", "scope": "all"})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answer"], "router answer")
        mock_router.assert_called_once()


if __name__ == "__main__":
    unittest.main()
