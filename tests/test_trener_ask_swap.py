"""Walidacja op 'swap' w prosbie do AI (2026-10-09) - bez LLM."""
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")
import qbot_trener_ask as A

T = date.today()
WS = T - timedelta(days=T.weekday())


def ses(**kw):
    s = {"id": 1, "day": T.isoformat(), "sport": "sila", "name": "Siła obwodowa", "start_time": "18:00", "dur_min": 40,
         "status": "plan", "_ex": [{"key": "pullover_db", "name": "Pullover z jednym hantlem", "group": "plecy"},
                                    {"key": "mountain_climbers", "name": "Mountain climbers", "group": "brzuch"}]}
    s.update(kw)
    return s


class Swap(unittest.TestCase):
    def test_swap_known_key(self):
        v = A.validate({"changes": [{"op": "swap", "id": 1, "zamien": ["pullover_db", "nieznany"]}]}, WS, T, [ses()])
        self.assertEqual(len(v["changes"]), 1)
        self.assertEqual(v["changes"][0]["keys"], ["pullover_db"])
        self.assertIn("Pullover", v["changes"][0]["line"])

    def test_swap_unknown_rejected(self):
        v = A.validate({"changes": [{"op": "swap", "id": 1, "zamien": ["x"]}]}, WS, T, [ses()])
        self.assertEqual(v["changes"], [])
        self.assertTrue(v["rejected"])

    def test_reroll(self):
        v = A.validate({"changes": [{"op": "swap", "id": 1, "nowy_zestaw": True}]}, WS, T, [ses()])
        self.assertTrue(v["changes"][0]["reroll"])

    def test_not_strength_or_done(self):
        v = A.validate({"changes": [{"op": "swap", "id": 1, "nowy_zestaw": True}]}, WS, T, [ses(sport="rower")])
        self.assertEqual(v["changes"], [])
        v = A.validate({"changes": [{"op": "swap", "id": 1, "nowy_zestaw": True}]}, WS, T, [ses(status="done")])
        self.assertEqual(v["changes"], [])

    def test_no_saved_set(self):
        v = A.validate({"changes": [{"op": "swap", "id": 1, "nowy_zestaw": True}]}, WS, T, [ses(_ex=None)])
        self.assertEqual(v["changes"], [])


if __name__ == "__main__":
    unittest.main()
