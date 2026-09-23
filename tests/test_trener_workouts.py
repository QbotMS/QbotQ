"""Testy zestawow cwiczen TRENER (bez bazy)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_workouts as W


class TestStrength(unittest.TestCase):
    def test_full_body_plus_accent(self):
        d = W.details("sila", "bz", 40, False, 0)
        groups = [e["group"] for e in d["exercises"]]
        for g in ("nogi", "klatka", "plecy", "barki", "brzuch", "tył ciała"):
            self.assertIn(g, groups)
        self.assertEqual(d["accent"], "klatka + ramiona")
        self.assertEqual(len(d["exercises"]), 8)
        self.assertEqual(d["rounds"], 3)

    def test_accent_rotation(self):
        self.assertEqual([W.details("sila", "rt", 40, False, n)["accent"] for n in range(5)],
                         ["klatka + ramiona", "plecy", "nogi", "brzuch", "klatka + ramiona"])

    def test_variants_rotate(self):
        a = W.details("sila", "bz", 40, False, 0)["exercises"][0]["name"]
        b = W.details("sila", "bz", 40, False, 4)["exercises"][0]["name"]
        self.assertNotEqual(a, b)

    def test_minimum_and_phase(self):
        self.assertEqual(W.details("sila", "bz", 15, True, 0)["rounds"], 1)
        self.assertEqual(W.details("sila", "rt", 40, False, 0)["rounds"], 2)
        self.assertIn("40 s pracy", W.details("sila", "rt", 40, False, 0)["text"])
        self.assertEqual(W.details("sila", None, 40, False, 0)["rounds"], 3)  # brak fazy -> baza

    def test_bodyweight_present(self):
        names = " ".join(e["name"] for n in range(8) for e in W.details("sila", "bz", 40, False, n)["exercises"])
        self.assertIn("Pompki", names)
        self.assertIn("Deska", names)


class TestRowing(unittest.TestCase):
    def test_phases(self):
        self.assertIn("3 × 8′", W.details("wiosl", "bz", 30)["text"])
        self.assertIn("6 × 3′", W.details("wiosl", "bd", 40)["text"])
        self.assertIn("minimum", W.details("wiosl", "bz", 15, True)["text"])
        self.assertIn("nogi → tułów → ręce", W.details("wiosl", "rt", 30)["text"])


if __name__ == "__main__":
    unittest.main()
