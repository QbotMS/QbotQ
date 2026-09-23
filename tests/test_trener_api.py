"""Testy walidacji TRENER API (bez bazy): qbot_trener_api.clean_*."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qbot_trener_api import (BadInput, clean_goal, clean_overrides, clean_period, clean_rule,
                             clean_session, clean_window)


class TestGoal(unittest.TestCase):
    def test_ok_minimal(self):
        g = clean_goal({"kind": "trip", "name": "Badlands"})
        self.assertEqual(g["priority"], "B")
        self.assertEqual(g["status"], "active")
        self.assertEqual(g["target"], {})

    def test_bad_kind(self):
        with self.assertRaises(BadInput):
            clean_goal({"kind": "x", "name": "a"})

    def test_dates_order(self):
        with self.assertRaises(BadInput):
            clean_goal({"kind": "trip", "name": "a", "date_from": "2027-05-20", "date_to": "2027-05-10"})

    def test_partial(self):
        self.assertEqual(clean_goal({"priority": "A"}, partial=True), {"priority": "A"})


class TestRule(unittest.TestCase):
    W = {"d": [1, 0, 1, 1, 0, 0, 0], "k": "h", "a": "17:30", "b": "20:30"}

    def test_window_ok(self):
        self.assertEqual(clean_window(self.W, "busy")["ac"], [])

    def test_window_bad_time(self):
        with self.assertRaises(BadInput):
            clean_window({**self.W, "a": "25:00"}, "busy")
        with self.assertRaises(BadInput):
            clean_window({**self.W, "a": "18:00", "b": "17:00"}, "busy")

    def test_window_days(self):
        with self.assertRaises(BadInput):
            clean_window({**self.W, "d": [1, 0, 3, 0, 0, 0, 0]}, "busy")

    def test_window_activities_only_for_training(self):
        w = {**self.W, "ac": ["joga", "rower", "rower"]}
        self.assertEqual(clean_window(w, "pref")["ac"], ["rower", "joga"])
        self.assertEqual(clean_window(w, "busy")["ac"], [])
        with self.assertRaises(BadInput):
            clean_window({**self.W, "ac": ["pilka"]}, "pref")

    def test_window_all_day(self):
        w = clean_window({"d": [0, 0, 0, 0, 0, 1, 1], "k": "all"}, "pref")
        self.assertNotIn("a", w)

    def test_period(self):
        self.assertEqual(clean_period(None), {"m": "all"})
        self.assertEqual(clean_period({"m": "yearly", "f": "01.09", "t": "26.06"})["f"], "01.09")
        with self.assertRaises(BadInput):
            clean_period({"m": "yearly", "f": "1.9", "t": "26.06"})
        with self.assertRaises(BadInput):
            clean_period({"m": "once", "f": "2027-02-01", "t": "2027-01-01"})

    def test_rule_full(self):
        r = clean_rule({"kind": "busy", "name": "Trening syna", "windows": [self.W],
                        "period": {"m": "yearly", "f": "01.09", "t": "26.06"}})
        self.assertEqual(r["icon"], "📌")
        self.assertEqual(len(r["windows"]), 1)


class TestSession(unittest.TestCase):
    def test_ok(self):
        s = clean_session({"day": "2026-09-24", "sport": "rower", "name": "Las", "dur_min": 60,
                           "min_min": 30, "start_time": "12:30:00"})
        self.assertEqual(s["start_time"], "12:30")
        self.assertEqual(s["status"], "plan")

    def test_min_gt_dur(self):
        with self.assertRaises(BadInput):
            clean_session({"day": "2026-09-24", "sport": "rower", "name": "x", "dur_min": 20, "min_min": 30})

    def test_bad_sport(self):
        with self.assertRaises(BadInput):
            clean_session({"day": "2026-09-24", "sport": "bieg", "name": "x", "dur_min": 20})


class TestOverrides(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(clean_overrides({"wx.wind_ms": 7, "regen.gap_h": None}), {"wx.wind_ms": 7, "regen.gap_h": None})
        with self.assertRaises(BadInput):
            clean_overrides({"Zly Klucz": 1})


class TestAuto(unittest.TestCase):
    def test_sensitivity_low_data(self):
        from qbot_trener_api import auto_sensitivity
        self.assertEqual(auto_sensitivity([(0.1, 1.0)] * 5)["value"], 5)

    def test_sensitivity_strong(self):
        from qbot_trener_api import auto_sensitivity
        pairs = [(i / 10, 1 + i / 100) for i in range(30)]
        self.assertEqual(auto_sensitivity(pairs)["value"], 10)

    def test_threshold(self):
        from qbot_trener_api import auto_min_threshold
        r = auto_min_threshold([i / 100 for i in range(100)], 15)
        self.assertAlmostEqual(r["threshold"], 0.15)

    def test_heavy_gap(self):
        from qbot_trener_api import auto_heavy_gap
        self.assertEqual(auto_heavy_gap([1] * 4 + [2] * 6)["value"], 48)
        self.assertEqual(auto_heavy_gap([1] * 3)["value"], 48)
        self.assertEqual(auto_heavy_gap([1] * 9 + [2])["value"], 24)


if __name__ == "__main__":
    unittest.main()
