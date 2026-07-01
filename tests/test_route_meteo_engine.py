"""Testy offline silnika METEO — sama logika modelu (bez bazy/sieci)."""
import datetime as _dt
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_meteo_engine import (metabolic_limit_c, window_severity,
                                             rain_severity, rain_trend,
                                             storm_segment_level, _storm_worse,
                                             _nearest_town_before, _build_storm_alerts,
                                             cold_severity, effective_wind_ms,
                                             _terrain_label)

UTC = _dt.timezone.utc


class TestMeteoUpal(unittest.TestCase):
    def test_limit_by_grade(self):
        self.assertEqual(metabolic_limit_c(6.0), 23.0)
        self.assertEqual(metabolic_limit_c(0.0), 25.0)
        self.assertEqual(metabolic_limit_c(-6.0), 28.0)
        self.assertEqual(metabolic_limit_c(3.0), 25.0)

    def test_terrain_label(self):
        self.assertEqual(_terrain_label(5.0), "podjazd")
        self.assertEqual(_terrain_label(0.0), "płasko")
        self.assertEqual(_terrain_label(-5.0), "zjazd")

    def test_severity(self):
        self.assertEqual(window_severity(0.0, 1, 4), "ALARM")
        self.assertIsNone(window_severity(-1.0, 999, 1))
        self.assertEqual(window_severity(1.0, 45, 1), "FLAGA")
        self.assertEqual(window_severity(1.0, 120, 1), "ALARM")
        self.assertEqual(window_severity(3.0, 30, 2), "FLAGA")
        self.assertEqual(window_severity(5.0, 15, 2), "ALARM")
        self.assertEqual(window_severity(7.0, 1, 2), "ALARM")


class TestMeteoDeszcz(unittest.TestCase):
    def test_rain(self):
        self.assertEqual(rain_severity(8.0, 1), "ALARM")
        self.assertEqual(rain_severity(3.0, 10), "FLAGA")
        self.assertEqual(rain_severity(3.0, 90), "ALARM")
        self.assertIsNone(rain_severity(1.0, 30))
        self.assertEqual(rain_severity(1.0, 60), "FLAGA")
        self.assertIsNone(rain_severity(0.0, 999))

    def test_trend(self):
        self.assertEqual(rain_trend(0.2, 3.0), "narasta (wjeżdżasz w deszcz)")
        self.assertEqual(rain_trend(3.0, 0.2), "słabnie (wychodzisz z deszczu)")


class TestMeteoBurza(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(storm_segment_level(95, 100), "NO-GO")
        self.assertEqual(storm_segment_level(3, 3000), "ALARM")
        self.assertEqual(storm_segment_level(3, 1500), "FLAGA")
        self.assertIsNone(storm_segment_level(3, 500))
        self.assertEqual(_storm_worse("ALARM", "NO-GO"), "NO-GO")

    def test_nearest_town(self):
        towns = [{"name": "A", "km": 10}, {"name": "B", "km": 38}, {"name": "C", "km": 50}]
        self.assertEqual(_nearest_town_before(towns, 40)["name"], "B")
        self.assertIsNone(_nearest_town_before(towns, 5))

    def _seg(self, km, eta, eta_utc, clear):
        return {"km": km, "eta": eta, "_dur_min": 30.0, "burza": "NO-GO", "burza_kod": 95,
                "cape": 800, "gust_ms": 12.0, "_eta_utc": eta_utc, "_storm_clear_utc": clear}

    def test_wait_and_town(self):
        t0 = _dt.datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        clear = _dt.datetime(2026, 7, 1, 13, 0, tzinfo=UTC)
        run = [self._seg(40, "14:00", t0, clear),
               self._seg(42, "14:30", t0 + _dt.timedelta(minutes=30), clear)]
        a = _build_storm_alerts(run, [{"name": "Brańszczyk", "km": 38}])[0]
        self.assertEqual(a["severity"], "NO-GO")
        self.assertEqual(a["czekanie_min"], 60)
        self.assertEqual(a["przeczekaj_w"]["miejscowosc"], "Brańszczyk")


class TestMeteoZimno(unittest.TestCase):
    def test_cold_severity(self):
        self.assertEqual(cold_severity(-30, 1), "ALARM")        # ekstremalny -> od razu
        self.assertEqual(cold_severity(-15, 15), "ALARM")       # silny, dlugo
        self.assertEqual(cold_severity(-15, 5), "FLAGA")        # silny, krotko
        self.assertEqual(cold_severity(-5, 60), "ALARM")        # umiarkowany, dlugo
        self.assertEqual(cold_severity(-5, 30), "FLAGA")
        self.assertIsNone(cold_severity(-5, 10))
        self.assertEqual(cold_severity(5, 60), "FLAGA")         # lagodny, bardzo dlugo
        self.assertIsNone(cold_severity(5, 30))
        self.assertIsNone(cold_severity(15, 999))               # komfort -> nic

    def test_effective_wind(self):
        # brak heading -> pelne czolo: ped 25 km/h (~6.94) + wiatr 3
        self.assertAlmostEqual(effective_wind_ms(25.0, 3.0, None, None), 6.944 + 3.0, delta=0.01)
        # wiatr z tylu (tail=+4) na plasko przy 25 km/h -> 6.94-4 czolowo
        self.assertAlmostEqual(effective_wind_ms(25.0, 4.0, 4.0, 0.0), 6.944 - 4.0, delta=0.01)
        # wiatr z boku (cross=5), ped 0 -> 5
        self.assertAlmostEqual(effective_wind_ms(0.0, 5.0, 0.0, 5.0), 5.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
