from __future__ import annotations

from datetime import datetime, timezone, timedelta
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

    def test_route_query_with_null_date_resolution_does_not_crash(self) -> None:
        query_result = {
            "status": "ok",
            "answer": "Odpowiedź testowa",
            "intents_detected": ["route_report"],
            "date_resolution": None,
            "plan": {"is_write_intent": False},
            "orchestrator": {},
        }

        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[]), \
                patch("qbot_qcal_telegram._pending_get", return_value=None), \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query", return_value=query_result) as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="358008451",
                text="pokaż trasę 55918401",
                dry_run=False,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["response"], "Odpowiedź testowa")
        mock_query.assert_called_once()

    def test_confirm_route_analysis_writer_spawns_worker(self) -> None:
        with patch("builtins.open", unittest.mock.mock_open()), patch("subprocess.Popen") as mock_popen, \
                patch("qbot_qcal_telegram._turn_add", return_value=77) as mock_turn_add:
            result = qbot_qcal_telegram._execute_writer(
                "confirm_route_analysis",
                {"route_id": "55918401", "trigger_source": "telegram_confirm"},
                "confirm_route_analysis:abc123",
                chat_id="358008451",
                action_id=18,
            )

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["route_id"], "55918401")
        self.assertEqual(result["launch_audit_id"], 77)
        mock_popen.assert_called_once()
        mock_turn_add.assert_called_once()
        self.assertTrue(str(result["worker_log_path"]).startswith("/opt/qbot/artifacts/logs/"))
        self.assertNotIn("/tmp/", str(result["worker_log_path"]))
        args, kwargs = mock_popen.call_args
        self.assertIn("/opt/qbot/app/scripts/route_precompute_trigger.py", args[0])
        self.assertIn("55918401", args[0])
        self.assertIn("--trigger-source", args[0])
        self.assertIn("telegram_confirm", args[0])
        self.assertEqual(kwargs["cwd"], "/opt/qbot/app")
        self.assertTrue(kwargs["start_new_session"])

    def test_route_confirm_log_path_uses_artifacts_logs(self) -> None:
        with patch.dict("os.environ", {"QBOT_ROUTE_CONFIRM_LOG_DIR": "/opt/qbot/artifacts/logs"}, clear=False):
            path = qbot_qcal_telegram._route_confirm_log_path("55918401")

        self.assertTrue(path.startswith("/opt/qbot/artifacts/logs/"))
        self.assertIn("rwgps_confirmations", path)
        self.assertTrue(path.endswith("rwgps_precompute_55918401_telegram_confirm.log"))
        self.assertNotIn("/tmp/", path)

    def test_pending_execute_marks_confirm_route_analysis_failed_without_launch_audit(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        fake_cur = unittest.mock.MagicMock()
        fake_cur.fetchone.return_value = {
            "id": 18,
            "chat_id": "358008451",
            "action_type": "confirm_route_analysis",
            "status": "pending",
            "payload_json": {"route_id": "55918401"},
            "preview_text": "preview",
            "idempotency_key": "confirm_route_analysis:abc123",
            "expires_at": future,
        }
        fake_conn = unittest.mock.MagicMock()
        fake_conn.cursor.return_value = fake_cur

        with patch("qbot_qcal_telegram._db", return_value=fake_conn), \
                patch("qbot_qcal_telegram._execute_writer", return_value={"status": "OK", "action_type": "confirm_route_analysis"}) as mock_writer, \
                patch("qbot_qcal_telegram._conv_upsert"):
            result = qbot_qcal_telegram._pending_execute("358008451", 18, dry_run=False)

        self.assertEqual(result["status"], "error")
        self.assertIn("missing durable launch audit", result["error"])
        mock_writer.assert_called_once()
        update_sql, update_params = fake_cur.execute.call_args_list[-1].args
        self.assertIn("UPDATE telegram_pending_actions SET status=%s", update_sql)
        self.assertEqual(update_params[0], "failed")

    def test_pending_execute_marks_confirm_route_analysis_executed_with_launch_audit(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        fake_cur = unittest.mock.MagicMock()
        fake_cur.fetchone.return_value = {
            "id": 18,
            "chat_id": "358008451",
            "action_type": "confirm_route_analysis",
            "status": "pending",
            "payload_json": {"route_id": "55918401"},
            "preview_text": "preview",
            "idempotency_key": "confirm_route_analysis:abc123",
            "expires_at": future,
        }
        fake_conn = unittest.mock.MagicMock()
        fake_conn.cursor.return_value = fake_cur

        with patch("qbot_qcal_telegram._db", return_value=fake_conn), \
                patch("qbot_qcal_telegram._execute_writer", return_value={"status": "OK", "action_type": "confirm_route_analysis", "launch_audit_id": 77}) as mock_writer, \
                patch("qbot_qcal_telegram._conv_upsert"):
            result = qbot_qcal_telegram._pending_execute("358008451", 18, dry_run=False)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["launch_audit_id"], 77)
        mock_writer.assert_called_once()
        update_sql, update_params = fake_cur.execute.call_args_list[-1].args
        self.assertIn("UPDATE telegram_pending_actions SET status=%s", update_sql)
        self.assertEqual(update_params[0], "executed")

    def test_single_pending_action_yes_executes_without_number(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[
                    {"id": 18, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                ]), \
                patch("qbot_qcal_telegram._pending_execute", return_value={"status": "OK", "action_type": "confirm_route_analysis"}) as mock_execute, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(chat_id="358008451", text="tak", dry_run=False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["executed"])
        mock_execute.assert_called_once_with("358008451", 18, dry_run=False)
        mock_query.assert_not_called()

    def test_two_pending_actions_yes_requires_number(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[
                    {"id": 18, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                    {"id": 19, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                ]), \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(chat_id="358008451", text="tak", dry_run=False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result.get("needs_number"))
        self.assertEqual(result["response"], "Masz kilka aktywnych próśb. Odpowiedz numerem, np. 18 TAK.")
        mock_query.assert_not_called()

    def test_two_pending_actions_numbered_yes_executes_target(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[
                    {"id": 18, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                    {"id": 19, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                ]), \
                patch("qbot_qcal_telegram._pending_execute", return_value={"status": "OK", "action_type": "confirm_route_analysis"}) as mock_execute, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(chat_id="358008451", text="#18 TAK", dry_run=False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["executed"])
        self.assertEqual(result["action_id"], 18)
        mock_execute.assert_called_once_with("358008451", 18, dry_run=False)
        mock_query.assert_not_called()

    def test_two_pending_actions_numbered_no_declines_target(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[
                    {"id": 18, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                    {"id": 19, "action_type": "confirm_route_analysis", "status": "pending", "expires_at": future},
                ]), \
                patch("qbot_qcal_telegram._pending_decline", return_value={"status": "declined"}) as mock_decline, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(chat_id="358008451", text="18 nie", dry_run=False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result.get("declined"))
        self.assertEqual(result["action_id"], 18)
        mock_decline.assert_called_once_with("358008451", 18)
        mock_query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
