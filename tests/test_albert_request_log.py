"""Log Alberta (qbot3/observability.py) i powod bledu ride_analysis.

2026-10-04: request_id 477e9825 - Albert napisal "blad parsera FIT", a log
mial tylko nazwy narzedzi. Teraz wpis ma argumenty, status, blad i skrot wyniku.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from qbot3 import observability as obs  # noqa: E402


class LogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (obs._LOG_DIR, obs._LOG_FILE, obs._MAX_BYTES)
        obs._LOG_DIR = Path(self.tmp.name)
        obs._LOG_FILE = obs._LOG_DIR / "qbot3_agent.log"

    def tearDown(self):
        obs._LOG_DIR, obs._LOG_FILE, obs._MAX_BYTES = self._orig
        self.tmp.cleanup()

    def _tool_results(self):
        return [
            {"reader": "ride_analysis", "args": {"fit": "/x/brak.fit"}, "status": "WARN",
             "data": {"status": "WARN", "warning": "Nakladanie FIT nieudane (kod 2): BLAD: brak pliku FIT"}},
            {"reader": "db_select_readonly", "args": {"sql": "SELECT " + "x," * 400 + "1"},
             "status": "OK", "data": {"status": "OK", "rows": list(range(1000))}},
        ]

    def test_default_dir_not_tmp(self):
        self.assertEqual(str(self._orig[0]), os.getenv("QBOT3_LOG_DIR", "/opt/qbot/logs"))

    def test_entry_has_question_answer_and_tool_calls(self):
        obs.log_request("abc12345", "gpt", "gpt-6-luna", "read_only", "albert_native_step_2",
                        ["ride_analysis"], ["ride_analysis"], False, "OK", "", 123,
                        question="porownaj jazdy", answer="blad parsera FIT",
                        tool_calls=obs.summarize_tool_results(self._tool_results()))
        entry = json.loads(obs._LOG_FILE.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(entry["request_id"], "abc12345")
        self.assertEqual(entry["question"], "porownaj jazdy")
        calls = entry["tool_calls"]
        self.assertEqual(calls[0]["tool"], "ride_analysis")
        self.assertIn("brak.fit", calls[0]["args"])
        self.assertIn("brak pliku FIT", calls[0]["error"])
        self.assertLessEqual(len(calls[1]["args"]), obs._ARGS_MAX + 20)
        self.assertLessEqual(len(calls[1]["result"]), obs._RESULT_MAX + 20)

    def test_rotation(self):
        obs._MAX_BYTES = 10
        obs._LOG_FILE.write_text("x" * 100, encoding="utf-8")
        obs.log_request("r1", "gpt", "m", "read_only", "i", [], [], False, "OK", "", 1)
        self.assertTrue(obs._LOG_FILE.with_name("qbot3_agent.log.1").exists())
        self.assertEqual(len(obs._LOG_FILE.read_text(encoding="utf-8").splitlines()), 1)

    def test_summarize_tolerates_garbage(self):
        self.assertEqual(obs.summarize_tool_results(None), [])
        self.assertEqual(obs.summarize_tool_results(["x", {"reader": "t", "data": "tekst"}])[0]["tool"], "t")


class RideAnalysisReasonTests(unittest.TestCase):
    def test_missing_fit_reason_is_returned(self):
        import qbot_route_tools as rt
        out = rt._tool_qbot_ride_analysis({"fit": "/nie/ma/takiego.fit"})
        self.assertEqual(out["status"], "WARN")
        self.assertIn("brak pliku FIT", out["notes"])
        self.assertIn("kod 2", out["notes"])


if __name__ == "__main__":
    unittest.main()
