"""Testy offline silnika METEO — sama logika modelu (bez bazy/sieci)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_meteo_engine import (metabolic_limit_c, window_severity,
                                             rain_severity, rain_trend, _terrain_label)


class TestMeteoUpal(unittest.TestCase):
    def test_limit_by_grade(self):
        self.assertEqual(metabolic_limit_c(6.0), 23.0)    # podjazd -> bardzo ciezka
        self.assertEqual(metabolic_limit_c(0.0), 25.0)    # plasko -> ciezka
        self.assertEqual(metabolic_limit_c(-6.0), 28.0)   # zjazd -> umiarkowana
        self.assertEqual(metabolic_limit_c(3.0), 25.0)    # granica: 3% to jeszcze plasko
        self.assertEqual(metabolic_limit_c(-3.0), 25.0)

    def test_terrain_label(self):
        self.assertEqual(_terrain_label(5.0), "podjazd")
        self.assertEqual(_terrain_label(0.0), "płasko")
        self.assertEqual(_terrain_label(-5.0), "zjazd")

    def test_severity_extreme_always_alarm(self):
        self.assertEqual(window_severity(0.0, 1, 4), "ALARM")

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


class TestMeteoDeszcz(unittest.TestCase):
    def test_rain_heavy_always_alarm(self):
        self.assertEqual(rain_severity(8.0, 1), "ALARM")   # silny opad -> alarm od razu

    def test_rain_moderate(self):
        self.assertEqual(rain_severity(3.0, 10), "FLAGA")
        self.assertEqual(rain_severity(3.0, 90), "ALARM")  # umiarkowany, ale dlugo -> alarm

    def test_rain_light(self):
        self.assertIsNone(rain_severity(1.0, 30))          # lekki, krotko -> nic
        self.assertEqual(rain_severity(1.0, 60), "FLAGA")  # lekki, ale dlugie moknięcie

    def test_rain_none(self):
        self.assertIsNone(rain_severity(0.0, 999))

    def test_rain_trend(self):
        self.assertEqual(rain_trend(0.2, 3.0), "narasta (wjeżdżasz w deszcz)")
        self.assertEqual(rain_trend(3.0, 0.2), "słabnie (wychodzisz z deszczu)")
        self.assertEqual(rain_trend(2.0, 2.1), "równomierny")


if __name__ == "__main__":
    unittest.main()
