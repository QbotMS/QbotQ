from __future__ import annotations

import unittest
from unittest.mock import patch

import qbot_qcal_telegram


class TestQbotQcalTelegramRouteQuery(unittest.TestCase):
    def test_route_analysis_uses_public_qbot_query_wrapper(self) -> None:
        route_report_result = {
            "tool": "qbot_query",
            "status": "ok",
            "answer": (
                "## WERDYKT TRASY / DECYZJA\n"
                "- decyzja: JEDŹ OSTROŻNIE\n\n"
                "## A0C - PROFIL WYSOKOŚCI / PODJAZDY\n"
                "- ascent_smoothed=426.7 m\n\n"
                "## A4 - METEO / WBGT / alerty upału\n"
                "- WBGT=31.0\n"
            ),
            "intents_detected": ["route_report"],
            "route_report": {
                "variant": "pelny",
                "route_id": "55798129",
            },
        }

        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query", return_value=route_report_result) as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="123",
                text="pełna analiza trasy 55798129 start 2026-06-30 15:00",
                dry_run=False,
            )

        self.assertEqual(result["status"], "ok")
        self.assertIn("WERDYKT TRASY / DECYZJA", result["response"])
        self.assertIn("A0C - PROFIL WYSOKOŚCI / PODJAZDY", result["response"])
        self.assertIn("A4 - METEO / WBGT / alerty upału", result["response"])
        mock_query.assert_called_once()
        payload = mock_query.call_args.args[0]
        self.assertEqual(payload["query"], "pełna analiza trasy 55798129 start 2026-06-30 15:00")
        self.assertEqual(payload["mode"], "read_only")
        self.assertEqual(payload["scope"], "all")

    def test_route_analysis_wrapper_failure_degrades_safely(self) -> None:
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query", side_effect=RuntimeError("boom")):
            result = qbot_qcal_telegram.handle_message(
                chat_id="123",
                text="pełna analiza trasy 55798129 start 2026-06-30 15:00",
                dry_run=False,
            )

        self.assertEqual(result["status"], "error")
        self.assertIn("Błąd", result["response"])


if __name__ == "__main__":
    unittest.main()
