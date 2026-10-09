# -*- coding: utf-8 -*-
"""Testy czystych funkcji opisu Strava (qbot_strava_publish). 2026-10-09."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_strava_publish as P  # noqa: E402

PROGI = {"h75": 89.9, "x50": 110.0, "x75": 198.0}


class T(unittest.TestCase):
    def test_surface_4_10(self):
        s = P.surface_split({"trudna/wolna": 20.2, "twarda szybka": 54.7, "zwykly gravel": 20.1, "ryzyko/niepewne": 5.0})
        self.assertEqual(s, {"asfalt": 55, "szuter": 20, "ujeby": 25})
        self.assertIsNone(P.surface_split({}))

    def test_effort(self):
        self.assertEqual(P.effort_class(346, 29.0, dict(PROGI, xss_h=69.5)), "mocno")      # 04.10
        self.assertEqual(P.effort_class(250, 4.0, dict(PROGI, xss_h=110)), "wpierdol")
        self.assertEqual(P.effort_class(60, 70.0, dict(PROGI, xss_h=50)), "lekko")
        self.assertEqual(P.effort_class(150, 40.0, dict(PROGI, xss_h=80)), "rowno")

    def test_tiles_plural(self):
        self.assertEqual(P.tiles_phrase(1), "🟩 1 nowy kwadrat")
        self.assertEqual(P.tiles_phrase(3), "🟩 3 nowe kwadraty")
        self.assertEqual(P.tiles_phrase(12), "🟩 12 nowych kwadratów")
        self.assertEqual(P.tiles_phrase(63), "🟩 63 nowe kwadraty")

    def test_region_guard(self):
        f = {"towns": ["Wyszogród", "Czerwińsk nad Wisłą"], "admin": ["województwo mazowieckie"], "candidates": []}
        v = P.vocab_of(f)
        self.assertTrue(P.region_ok("Mazowsze, między Wyszogrodem a Czerwińskiem nad Wisłą", v))
        self.assertFalse(P.region_ok("Puszcza Kampinoska", v))          # nazwa spoza danych
        self.assertFalse(P.region_ok(None, v))

    def test_assemble(self):
        f = {"km": 107.2, "elev_m": 618, "moving_s": 17520, "surface": {"asfalt": 55, "szuter": 20, "ujeby": 25},
             "effort": {"cls": "mocno", "min_wbal": 29.0}, "new_tiles": 63, "stop": {"place": "Wyszogród", "min": 22}}
        d = P.assemble(f, "Mazowsze", ["Bazylika w Czerwińsku nad Wisłą"])
        lines = d.split("\n")
        self.assertEqual(len(lines), 4)
        self.assertIn("🪨 25% ujebów", lines[0])
        self.assertTrue(lines[1].startswith("💪 Mocno, ale stabilnie: 4:52 w ruchu"))
        self.assertIn("⭐ Bazylika w Czerwińsku nad Wisłą", lines[2])
        self.assertEqual(lines[3], P.SIGNATURE)


if __name__ == "__main__":
    unittest.main()
