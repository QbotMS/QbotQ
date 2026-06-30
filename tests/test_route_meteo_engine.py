"""Testy offline silnika METEO — sama logika modelu (bez bazy/sieci)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_meteo_engine import (metabolic_limit_c, window_severity,
                                             _terrain_label)


class TestMeteoModel(unittest.TestCase):
    def test_limit_by_grade(self):
        self.assertEqual(metabolic_limit_c(6.0), 23.0)    # podjazd -> bardzo ciezka
        self.assertEqual(metabolic_limit_c(0.0), 25.0)    # plasko -> ciezka
        self.assertEqual(metabolic_limit_c(-6.0), 28.0)   # zjazd -> umiarkowana
        self.assertEqual(metabolic_limit_c(3.0), 25.0)    # granica: 3% to jeszcze plasko
        self.assertEqual(metabolic_limit_c(-3.0), 25.0)   # granica: -3% to jeszcze plasko

    def test_terrain_label(self):
        self.assertEqual(_terrain_label(5.0), "podjazd")
        self.assertEqual(_terrain_label(0.0), "płasko")
        self.assertEqual(_terrain_label(-5.0), "zjazd")

    def test_severity_extreme_always_alarm(self):
        self.assertEqual(window_severity(0.0, 1, 4), "ALARM")   # strefa ekstremalna bez wzgledu na czas

    def test_severity_under_limit_none(self):
        self.assertIsNone(window_severity(-1.0, 999, 1))
        self.assertIsNone(window_severity(0.0, 999, 1))

    def test_severity_band_0_2(self):
        self.assertIsNone(window_severity(1.0, 30, 1))
        self.assertEqual(window_severity(1.0, 45, 1), "FLAGA")
        self.assertEqual(window_severity(1.0, 120, 1), "ALARM")

    def test_severity_band_2_4(self):
        self.assertIsNone(window_severity(3.0, 29, 2))
        self.assertEqual(window_severity(3.0, 30, 2), "FLAGA")
        self.assertEqual(window_severity(3.0, 60, 2), "ALARM")

    def test_severity_band_4_6(self):
        self.assertIsNone(window_severity(5.0, 6, 2))
        self.assertEqual(window_severity(5.0, 7, 2), "FLAGA")
        self.assertEqual(window_severity(5.0, 15, 2), "ALARM")

    def test_severity_band_over_6(self):
        self.assertEqual(window_severity(7.0, 1, 2), "ALARM")


if __name__ == "__main__":
    unittest.main()
