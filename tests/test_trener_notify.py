"""Testy Etapu 5 TRENER (bez bazy i bez wysylki): teksty Telegram, DTO Garmina."""
import os
import sys
import unittest
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_notify as N


def S(**kw):
    s = {"id": 1, "day": date(2026, 10, 3), "sport": "rower", "name": "Długa jazda", "start_time": time(8, 0), "dur_min": 120,
         "status": "plan", "cut": False, "zone": 2, "note": None, "training_session_id": None}
    s.update(kw)
    return s


class TestTexts(unittest.TestCase):
    def test_plan(self):
        t = N.text_plan(date(2026, 9, 28), [S(), S(id=2, sport="joga", name="Joga", dur_min=30, day=date(2026, 10, 4))], "Roztrenowanie", 5.0, ["x"])
        self.assertIn("Plan tygodnia 28.09–04.10", t)
        self.assertIn("sb 03.10 08:00 🚲 Długa jazda 120′", t)
        self.assertIn("2.5 h", t)

    def test_day_empty(self):
        self.assertIsNone(N.text_day(date(2026, 10, 3), [S(status="done")]))
        self.assertIn("Dziś", N.text_day(date(2026, 10, 3), [S()]))

    def test_review(self):
        ses = [S(status="done"), S(id=2, status="skip", day=date(2026, 9, 29)), S(id=3, status="done", dur_min=60, day=date(2026, 9, 30))]
        t = N.text_review(date(2026, 9, 28), ses, 0.5, 1, -0.2)
        self.assertIn("Zrobione 3.5 h z 3.0 h planu", t)
        self.assertIn("Nie wyszło", t)
        self.assertIn("Plan wykonany.", t)
        low = N.text_review(date(2026, 9, 28), [S(status="skip", day=date(2026, 9, 28)), S(id=5, day=date(2026, 9, 28), dur_min=60)], 0, 0, None)
        self.assertIn("Trudny tydzień", low)


if __name__ == "__main__":
    unittest.main()
