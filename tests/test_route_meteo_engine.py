"""Testy offline silnika METEO — sama logika modelu (bez bazy/sieci)."""
import datetime as _dt
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes.route_meteo_engine import (metabolic_limit_c, window_severity,
                                             rain_severity, rain_trend,
                                             storm_segment_level, _storm_worse,
                                             _nearest_town_before, _build_storm_alerts,
                                             _terrain_label)

UTC = _dt.timezone.utc


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

    def test_severity_bands(self):
        self.assertIsNone(window_severity(-1.0, 999, 1))
        self.assertIsNone(window_severity(1.0, 30, 1))
        self.assertEqual(window_severity(1.0, 45, 1), "FLAGA")
        self.assertEqual(window_severity(1.0, 120, 1), "ALARM")
        self.assertEqual(window_severity(3.0, 30, 2), "FLAGA")
        self.assertEqual(window_severity(3.0, 60, 2), "ALARM")
        self.assertEqual(window_severity(5.0, 7, 2), "FLAGA")
        self.assertEqual(window_severity(5.0, 15, 2), "ALARM")
        self.assertEqual(window_severity(7.0, 1, 2), "ALARM")


class TestMeteoDeszcz(unittest.TestCase):
    def test_rain_bands(self):
        self.assertEqual(rain_severity(8.0, 1), "ALARM")
        self.assertEqual(rain_severity(3.0, 10), "FLAGA")
        self.assertEqual(rain_severity(3.0, 90), "ALARM")
        self.assertIsNone(rain_severity(1.0, 30))
        self.assertEqual(rain_severity(1.0, 60), "FLAGA")
        self.assertIsNone(rain_severity(0.0, 999))

    def test_rain_trend(self):
        self.assertEqual(rain_trend(0.2, 3.0), "narasta (wjeżdżasz w deszcz)")
        self.assertEqual(rain_trend(3.0, 0.2), "słabnie (wychodzisz z deszczu)")
        self.assertEqual(rain_trend(2.0, 2.1), "równomierny")


class TestMeteoBurza(unittest.TestCase):
    def test_storm_code_is_nogo(self):
        self.assertEqual(storm_segment_level(95, 100), "NO-GO")
        self.assertEqual(storm_segment_level(96, None), "NO-GO")

    def test_storm_cape_bands(self):
        self.assertEqual(storm_segment_level(3, 3000), "ALARM")
        self.assertEqual(storm_segment_level(3, 1500), "FLAGA")
        self.assertIsNone(storm_segment_level(3, 500))
        self.assertIsNone(storm_segment_level(0, None))

    def test_storm_worse(self):
        self.assertEqual(_storm_worse("FLAGA", "ALARM"), "ALARM")
        self.assertEqual(_storm_worse("ALARM", "NO-GO"), "NO-GO")
        self.assertIsNone(_storm_worse(None, None))

    def test_nearest_town_before(self):
        towns = [{"name": "A", "km": 10}, {"name": "B", "km": 38}, {"name": "C", "km": 50}]
        self.assertEqual(_nearest_town_before(towns, 40)["name"], "B")
        self.assertEqual(_nearest_town_before(towns, 55)["name"], "C")
        self.assertIsNone(_nearest_town_before(towns, 5))

    def _storm_seg(self, km, eta, eta_utc, clear_utc):
        return {"km": km, "eta": eta, "_dur_min": 30.0, "burza": "NO-GO", "burza_kod": 95,
                "cape": 800, "gust_ms": 12.0, "_eta_utc": eta_utc, "_storm_clear_utc": clear_utc}

    def test_storm_alert_wait_and_town(self):
        t0 = _dt.datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        clear = _dt.datetime(2026, 7, 1, 13, 0, tzinfo=UTC)
        run = [self._storm_seg(40, "14:00", t0, clear),
               self._storm_seg(42, "14:30", t0 + _dt.timedelta(minutes=30), clear)]
        towns = [{"name": "Brańszczyk", "km": 38}, {"name": "Daleko", "km": 60}]
        alerts = _build_storm_alerts(run, towns)
        self.assertEqual(len(alerts), 1)
        a = alerts[0]
        self.assertEqual(a["severity"], "NO-GO")
        self.assertEqual(a["czekanie_min"], 60)                      # 12:00 -> 13:00
        self.assertEqual(a["przeczekaj_w"]["miejscowosc"], "Brańszczyk")

    def test_storm_alert_persists_wait_none(self):
        t0 = _dt.datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
        run = [self._storm_seg(40, "14:00", t0, None)]  # burza nie mija do konca prognozy
        alerts = _build_storm_alerts(run, [{"name": "X", "km": 30}])
        self.assertIsNone(alerts[0]["czekanie_min"])


if __name__ == "__main__":
    unittest.main()
