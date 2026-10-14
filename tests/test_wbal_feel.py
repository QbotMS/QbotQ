"""ModelQ: odczucie przy niskim W'bal (fitmodel/wbal_feel.py)."""
import sys
import unittest
from datetime import date

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.wbal_feel import ANSWERS, question_text, series_signal  # noqa: E402


class TestWbalFeel(unittest.TestCase):
    def test_question(self):
        t = question_text(date(2026, 10, 18), 2.4, 20.0, 238.8)
        self.assertIn("18.10", t)
        self.assertIn("2%", t)
        self.assertIn("20,0 kJ", t)

    def test_series_too_low(self):
        self.assertEqual(series_signal(["ok", "ok", "ok", "close"]), "za_nisko")

    def test_series_mixed_or_short(self):
        self.assertIsNone(series_signal(["ok", "close", "ok"]))
        self.assertIsNone(series_signal(["ok", "ok"]))
        self.assertIsNone(series_signal(["cut", "cut", "cut"]))

    def test_answers(self):
        self.assertEqual(set(ANSWERS), {"cut", "close", "ok"})


if __name__ == "__main__":
    unittest.main()
