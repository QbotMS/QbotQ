"""Testy regul wnioskowania kontekstu nawierzchni (route_surface_context.infer_context).

Walidacja logiki zatwierdzonej z uzytkownikiem (audyt 2026-07-02, potwierdzone w terenie:
Poligon km20 = realny piach). Reguly dotycza WYLACZNIE odcinkow bez tagu OSM.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qbot3.routes.route_surface_context_store import infer_context


class TestInferContext(unittest.TestCase):
    def test_track_open_sand_is_high_sand_alarm(self):
        out = infer_context("track", None, 30, 100, True)
        self.assertEqual(out["sand_risk"], "WNIOSK.")
        self.assertIn("polna", out["surface_estimate"])

    def test_track_open_no_sand_is_medium(self):
        out = infer_context("track", None, 40, 90, False)
        self.assertEqual(out["sand_risk"], "SREDNIE")

    def test_alarm_requires_open_at_least_70pct(self):
        # otwarte tylko 60% -> BEZ alarmu (niepewne otoczenie nie krzyczy)
        out = infer_context("track", None, 30, 60, True)
        self.assertNotEqual(out["sand_risk"], "WYSOKIE")

    def test_track_forest_is_moderate(self):
        self.assertEqual(infer_context("track", None, 10, 100, True)["sand_risk"], "UMIARK.")

    def test_forest_effect_from_50pct(self):
        self.assertEqual(infer_context("track", None, 10, 55, True)["sand_risk"], "UMIARK.")

    def test_track_no_signals_is_medium(self):
        self.assertEqual(infer_context("track", None, None, 0, False)["sand_risk"], "SREDNIE")

    def test_tracktype_wins_over_context(self):
        out = infer_context("track", "grade3", 30, 100, True)  # nawet otwarte+piach
        self.assertEqual(out["surface_estimate"], "szuter")
        self.assertEqual(out["sand_risk"], "NISKO-SR")

    def test_tracktype_grade4_with_sand_is_medium(self):
        self.assertEqual(infer_context("track", "grade4", 10, 100, True)["sand_risk"], "SREDNIE")

    def test_forest_path_is_low_singletrack(self):
        out = infer_context("path", None, 10, 100, True)
        self.assertEqual(out["sand_risk"], "NISKIE")
        self.assertIn("singletrack", out["surface_estimate"])

    def test_open_path_with_sand_is_medium(self):
        self.assertEqual(infer_context("path", None, 30, 90, True)["sand_risk"], "SREDNIE")

    def test_paved_highway_without_tag_is_low(self):
        for hw in ("residential", "unclassified", "tertiary", "secondary"):
            out = infer_context(hw, None, 10, 100, True)
            self.assertEqual(out["sand_risk"], "NISKIE", hw)
            self.assertEqual(out["surface_estimate"], "prawdopodobnie utwardzona", hw)

    def test_service_builtup_is_paved(self):
        self.assertEqual(infer_context("service", None, 50, 100, False)["surface_estimate"], "utwardzona")

    def test_unknown_highway_has_no_signal(self):
        out = infer_context(None, None, None, 0, False)
        self.assertEqual(out["surface_estimate"], "nieznana")
        self.assertEqual(out["sand_risk"], "?")


if __name__ == "__main__":
    unittest.main()
