"""Testy Etapu 5 TRENER (bez bazy i bez wysylki): teksty Telegram, DTO Garmina."""
import os
import sys
import unittest
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_garmin as G
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


class TestGarmin(unittest.TestCase):
    def test_bike_power(self):
        d = G.build_dto(S(), 253)
        st = d["workoutSegments"][0]["workoutSteps"]
        self.assertEqual([x["stepType"]["stepTypeKey"] for x in st], ["warmup", "interval", "cooldown"])
        self.assertEqual(sum(x["endConditionValue"] for x in st), 7200)
        self.assertEqual((st[1]["targetValueOne"], st[1]["targetValueTwo"]), (142.0, 190.0))
        self.assertEqual(d["sportType"]["sportTypeKey"], "cycling")

    def test_bike_no_ftp(self):
        st = G.build_dto(S(), None)["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(st[1]["targetType"]["workoutTargetTypeKey"], "no.target")

    def test_other_sports(self):
        self.assertEqual(G.build_dto(S(sport="sila", name="Siła A", dur_min=40), 253)["sportType"]["sportTypeKey"], "strength_training")
        self.assertEqual(G.build_dto(S(sport="joga", name="Joga", dur_min=15), 253)["estimatedDurationInSecs"], 900)

    def test_idem_changes_with_content(self):
        self.assertNotEqual(G.idem_key(S()), G.idem_key(S(dur_min=90)))
        self.assertEqual(G.idem_key(S()), G.idem_key(S()))

    def test_dry_run(self):
        self.assertEqual(G.push(S(), 253, dry_run=True)["status"], "DRY_RUN_OK")


if __name__ == "__main__":
    unittest.main()
