from __future__ import annotations

from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch

import qbot_qcal_telegram


class TestQbotQcalTelegramManualRecompute(unittest.TestCase):
    """Reczna komenda 'przelicz trase <id>' (kontekstowo)."""

    def test_detects_recompute_commands(self) -> None:
        for text in (
            "przelicz trase 55918401",
            "przelicz trasę",
            "/przelicz 55864231",
            "policz trasę 55864231",
            "uruchom pełną analizę trasy 55918401",
            "zanalizuj trasę 3180619966",
            "analizuj trasę 3180619966",
        ):
            self.assertTrue(qbot_qcal_telegram._detect_route_recompute(text), text)

    def test_does_not_hijack_read_queries(self) -> None:
        for text in (
            "pokaż listę tras",
            "analiza trasy 55918401",
            "raport trasy 55918401",
            "ile zjadłem wczoraj",
            "18 TAK",
        ):
            self.assertFalse(qbot_qcal_telegram._detect_route_recompute(text), text)

    def test_explicit_route_id_runs_immediately(self) -> None:
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[]), \
                patch("qbot_qcal_telegram.upsert_pending_action", return_value={
                    "status": "pending", "created": True,
                    "pending_action_id": 31, "action_status": "pending",
                }) as mock_upsert, \
                patch("qbot_qcal_telegram._pending_execute", return_value={
                    "status": "OK", "action_type": "confirm_route_analysis", "route_id": "55918401",
                }) as mock_execute, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="358008451", text="przelicz trasę 55918401", dry_run=False)

        self.assertEqual(result["route_recompute"], "started")
        self.assertEqual(result["route_id"], "55918401")
        mock_execute.assert_called_once_with("358008451", 31, dry_run=False)
        self.assertEqual(
            mock_upsert.call_args.kwargs["action_type"], "confirm_route_analysis")
        self.assertEqual(
            mock_upsert.call_args.kwargs["payload"]["route_id"], "55918401")
        mock_query.assert_not_called()

    def test_route_id_from_context_asks_for_numbered_confirmation(self) -> None:
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value={
                    "state": "idle",
                    "context_json": '{"last_route_id": "55864231"}',
                }), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[]), \
                patch("qbot_qcal_telegram.upsert_pending_action", return_value={
                    "status": "pending", "created": True,
                    "pending_action_id": 42, "action_status": "pending",
                }), \
                patch("qbot_qcal_telegram._pending_execute") as mock_execute, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="358008451", text="przelicz trasę", dry_run=False)

        self.assertEqual(result["route_recompute"], "awaiting_confirmation")
        self.assertEqual(result["route_id"], "55864231")
        self.assertIn("42 TAK", result["response"])
        mock_execute.assert_not_called()
        mock_query.assert_not_called()

    def test_no_route_id_anywhere_asks_for_number(self) -> None:
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[]), \
                patch("qbot_qcal_telegram.upsert_pending_action") as mock_upsert, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="358008451", text="przelicz trasę", dry_run=False)

        self.assertEqual(result["route_recompute"], "needs_route_id")
        mock_upsert.assert_not_called()
        mock_query.assert_not_called()


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

    def test_confirm_route_analysis_forces_telegram_confirm_trigger(self) -> None:
        # Regresja: payload z fazy webhooka niesie trigger_source="rwgps_webhook";
        # wykonanie MUSI wymusic telegram_confirm, inaczej koncowe powiadomienie
        # jest po cichu pomijane (gate w route_precompute_trigger
        # ._send_route_confirmation_final_notification).
        with patch("builtins.open", unittest.mock.mock_open()), patch("subprocess.Popen") as mock_popen, \
                patch("qbot_qcal_telegram._turn_add", return_value=77):
            result = qbot_qcal_telegram._execute_writer(
                "confirm_route_analysis",
                {"route_id": "55930010", "trigger_source": "rwgps_webhook"},
                "confirm_route_analysis:def456",
                chat_id="358008451",
                action_id=23,
            )

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["trigger_source"], "telegram_confirm")
        args, _ = mock_popen.call_args
        self.assertIn("--trigger-source", args[0])
        self.assertIn("telegram_confirm", args[0])
        self.assertNotIn("rwgps_webhook", args[0])

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



class TestTelegramRouteSourceDispatch(unittest.TestCase):
    """RWGPS (8 cyfr) vs Komoot (10 cyfr) — dwa rozne workery."""

    def test_source_detection_by_id_length(self) -> None:
        self.assertEqual(qbot_qcal_telegram._route_source_for_id("55918401"), "rwgps")
        self.assertEqual(qbot_qcal_telegram._route_source_for_id("3180619966"), "komoot")

    def test_komoot_without_attractions_offers_buttons(self) -> None:
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[]), \
                patch("qbot_qcal_telegram.upsert_pending_action") as mock_upsert, \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="358008451", text="przelicz trase 3180619966", dry_run=False)

        self.assertEqual(result["route_recompute"], "komoot_choice")
        self.assertEqual(result["komoot_choice"], "3180619966")
        mock_upsert.assert_not_called()
        mock_query.assert_not_called()

    def test_komoot_id_uses_komoot_action_type(self) -> None:
        with patch("qbot_qcal_telegram.is_authorized", return_value=True), \
                patch("qbot_qcal_telegram._conv_get", return_value=None), \
                patch("qbot_qcal_telegram._pending_active_rows", return_value=[]), \
                patch("qbot_qcal_telegram.upsert_pending_action", return_value={
                    "status": "pending", "created": True,
                    "pending_action_id": 51, "action_status": "pending",
                }) as mock_upsert, \
                patch("qbot_qcal_telegram._pending_execute", return_value={
                    "status": "OK", "action_type": "confirm_komoot_analysis",
                    "tour_id": "3180619966",
                }), \
                patch("qbot_qcal_telegram._turn_add"), \
                patch("qbot_qcal_telegram._conv_upsert"), \
                patch("qbot_tools._tool_qbot_query") as mock_query:
            result = qbot_qcal_telegram.handle_message(
                chat_id="358008451", text="przelicz trase 3180619966 z atrakcjami",
                dry_run=False)

        self.assertEqual(result["route_recompute"], "started")
        self.assertEqual(
            mock_upsert.call_args.kwargs["action_type"], "confirm_komoot_analysis")
        self.assertEqual(
            mock_upsert.call_args.kwargs["payload"]["tour_id"], "3180619966")
        self.assertTrue(mock_upsert.call_args.kwargs["payload"]["atrakcje"])
        self.assertIn("Komoot", result["response"])
        mock_query.assert_not_called()

    def test_komoot_writer_spawns_komoot_worker(self) -> None:
        with patch("subprocess.Popen") as mock_popen, \
                patch("qbot_qcal_telegram._turn_add", return_value=901), \
                patch("qbot_qcal_telegram._route_confirm_log_path",
                      return_value="/tmp/komoot_test.log"), \
                patch("builtins.open", unittest.mock.mock_open()):
            result = qbot_qcal_telegram._execute_writer(
                "confirm_komoot_analysis",
                {"tour_id": "3180619966"},
                "idem",
                chat_id="358008451",
                action_id=51,
            )

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["launch_audit_id"], 901)
        cmd = mock_popen.call_args.args[0]
        self.assertIn("scripts/komoot_analyze_worker.py", cmd[1])
        self.assertEqual(cmd[2], "3180619966")
        self.assertNotIn("--atrakcje", cmd)

    def test_komoot_writer_passes_attractions_flag(self) -> None:
        with patch("subprocess.Popen") as mock_popen, \
                patch("qbot_qcal_telegram._turn_add", return_value=902), \
                patch("qbot_qcal_telegram._route_confirm_log_path",
                      return_value="/tmp/komoot_test.log"), \
                patch("builtins.open", unittest.mock.mock_open()):
            result = qbot_qcal_telegram._execute_writer(
                "confirm_komoot_analysis",
                {"tour_id": "3180619966", "atrakcje": True},
                "idem",
                chat_id="358008451",
                action_id=52,
            )

        self.assertEqual(result["status"], "OK")
        self.assertTrue(result["atrakcje"])
        self.assertIn("--atrakcje", mock_popen.call_args.args[0])

    def test_attractions_phrases_detected(self) -> None:
        self.assertTrue(qbot_qcal_telegram._wants_attractions("przelicz trase 1 z atrakcjami"))
        self.assertTrue(qbot_qcal_telegram._wants_attractions("analizuj trase 1 + atrakcje"))
        self.assertFalse(qbot_qcal_telegram._wants_attractions("przelicz trase 1"))

    def test_komoot_writer_needs_tour_id(self) -> None:
        result = qbot_qcal_telegram._execute_writer(
            "confirm_komoot_analysis", {}, "idem", chat_id="358008451", action_id=51)
        self.assertEqual(result["status"], "error")


class TestTelegramPollerRouteGateway(unittest.TestCase):
    """Poller (telegram_reply_processor) musi oddac trasy do gatewayu."""

    def test_recompute_command_goes_to_gateway(self) -> None:
        import telegram_reply_processor as trp
        self.assertTrue(trp._is_route_gateway_message("358008451", "przelicz trase 3180619966"))

    def test_plain_wellness_message_stays_in_poller(self) -> None:
        import telegram_reply_processor as trp
        with patch("qbot_qcal_telegram._pending_active_rows", return_value=[]):
            self.assertFalse(trp._is_route_gateway_message("358008451", "spalem 7h, nogi ciezkie"))

    def test_numbered_yes_goes_to_gateway_only_with_active_pending(self) -> None:
        import telegram_reply_processor as trp
        with patch("qbot_qcal_telegram._pending_active_rows", return_value=[{"id": 51}]):
            self.assertTrue(trp._is_route_gateway_message("358008451", "51 TAK"))
        with patch("qbot_qcal_telegram._pending_active_rows", return_value=[]):
            self.assertFalse(trp._is_route_gateway_message("358008451", "51 TAK"))

if __name__ == "__main__":
    unittest.main()
