from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from qbot_query_handler import _resolve_intent, handle_query


class TestGarminActivityRouting(unittest.TestCase):
    def test_generic_activity_with_id_goes_to_detail(self) -> None:
        intent = _resolve_intent("pokaż aktywność Garmin 23155690938")
        self.assertEqual(intent, "garmin_activity_detail")

    def test_stream_request_with_id_goes_to_streams(self) -> None:
        intent = _resolve_intent("pokaż dostępne pola dla Garmin 23155690938")
        self.assertEqual(intent, "garmin_activity_streams")

    def test_export_request_with_id_goes_to_export(self) -> None:
        intent = _resolve_intent("eksport aktywności do artefaktu Garmin 23155690938")
        self.assertEqual(intent, "garmin_activity_export")

    def test_training_word_with_activity_id_does_not_fall_back_to_training_recent(self) -> None:
        intent = _resolve_intent("pokaż trening Garmin 23155690938")
        self.assertEqual(intent, "garmin_activity_streams")

    def test_detail_request_with_10_digit_id_goes_to_detail(self) -> None:
        intent = _resolve_intent("szczegóły aktywności 23155690938")
        self.assertEqual(intent, "garmin_activity_detail")

    def test_detail_handler_returns_full_json(self) -> None:
        fake_details = {
            "activityId": "23155690938",
            "name": "Evening ride",
            "metrics": {"power": 260, "hr": 142},
        }

        class _FakeClient:
            def get_activity_details(self, activity_id: str):
                self.activity_id = activity_id
                return fake_details

        with patch("qbot_query_handler.garmin_client", return_value=_FakeClient()):
            result = handle_query("szczegóły aktywności 23155690938")

        self.assertEqual(result.get("intent"), "garmin_activity_detail")
        self.assertEqual(result.get("status"), "OK")
        self.assertEqual(result.get("data", {}).get("activity_id"), "23155690938")
        self.assertEqual(result.get("data", {}).get("details"), fake_details)
        self.assertEqual(json.loads(result.get("answer")), fake_details)


if __name__ == "__main__":
    unittest.main()
