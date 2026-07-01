"""Testy offline silnika METEO — sama logika modelu (bez bazy/sieci)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_meteo_engine import (metabolic_limit_c, window_severity,
                                             rain_severity, rain_trend,
                                             storm_segment_level, _storm_worse,
                                             _terrain_label)


class TestMeteoUpal(unittest.TestCase):
    def test_limit_by_grade(self):
        self.assertEqual(metabolic_limit_c(6.0), 23.0)
        self.assertEqual(metabolic_limit_c(0.0), 25.0)
        self.assertEqual(metabolic_limit_c(-6.0), 28.0)
        self.assertEqual(metabolic_limit_c(3.0), 25.0)
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
        self.assertEqual(rain_severity(8.0, 1), "ALARM")

    def test_rain_moderate(self):
        self.assertEqual(rain_severity(3.0, 10), "FLAGA")
        self.assertEqual(rain_severity(3.0, 90), "ALARM")

    def test_rain_light(self):
        self.assertIsNone(rain_severity(1.0, 30))
        self.assertEqual(rain_severity(1.0, 60), "FLAGA")

    def test_rain_none(self):
        self.assertIsNone(rain_severity(0.0, 999))

    def test_rain_trend(self):
        self.assertEqual(rain_trend(0.2, 3.0), "narasta (wjeżdżasz w deszcz)")
        self.assertEqual(rain_trend(3.0, 0.2), "słabnie (wychodzisz z deszczu)")
        self.assertEqual(rain_trend(2.0, 2.1), "równomierny")


class TestMeteoBurza(unittest.TestCase):
    def test_storm_code_is_nogo(self):
        self.assertEqual(storm_segment_level(95, 100), "NO-GO")   # kod burzy > wszystko
        self.assertEqual(storm_segment_level(96, None), "NO-GO")
        self.assertEqual(storm_segment_level(99, 0), "NO-GO")

    def test_storm_cape_bands(self):
        self.assertEqual(storm_segment_level(3, 3000), "ALARM")   # silna niestabilnosc
        self.assertEqual(storm_segment_level(3, 1500), "FLAGA")   # umiarkowana
        self.assertIsNone(storm_segment_level(3, 500))            # slabo -> nic
        self.assertIsNone(storm_segment_level(0, None))           # brak danych CAPE

    def test_storm_worse(self):
        self.assertEqual(_storm_worse("FLAGA", "ALARM"), "ALARM")
        self.assertEqual(_storm_worse("ALARM", "NO-GO"), "NO-GO")
        self.assertEqual(_storm_worse(None, "FLAGA"), "FLAGA")
        self.assertIsNone(_storm_worse(None, None))


if __name__ == "__main__":
    unittest.main()
