"""Testy Etapu 4 TRENER (bez bazy): bilans, serie, statusy celow, pogoda auto."""
import os
import sys
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_stats as S


def days(n, weight0=100.0, dw=0.0, intake=None, expend=2800):
    return [{"day": (date(2026, 9, 1) + timedelta(days=i)).isoformat(), "intake": intake, "expend": expend,
             "weight": weight0 + dw * i} for i in range(n)]


class TestBalance(unittest.TestCase):
    def test_from_weight_when_no_logs(self):
        b = S.balance(days(14, dw=0.05), 14, 1)
        self.assertEqual(b["source"], "weight")
        self.assertAlmostEqual(b["balance_kcal"], 385, delta=2)   # 0.05 kg/d * 7700
        self.assertAlmostEqual(b["weight_slope_kg_wk"], 0.35, delta=0.01)
        self.assertEqual(b["intake_from_weight"], 2800 + 385)

    def test_logs_when_enough(self):
        b = S.balance(days(14, intake=2500), 14, 1)
        self.assertEqual(b["source"], "logs")
        self.assertEqual(b["balance_kcal"], -300)

    def test_mode_weight_only(self):
        self.assertEqual(S.balance(days(14, intake=2500, dw=-0.03), 14, 2)["source"], "weight")

    def test_slope(self):
        self.assertAlmostEqual(S.lin_slope([(i, 2 * i + 1) for i in range(10)]), 2.0)
        self.assertIsNone(S.lin_slope([(0, 1), (1, 2)]))


class TestSeries(unittest.TestCase):
    def test_series_threshold_20km(self):
        d0 = date(2026, 6, 5)
        daily = {d0 + timedelta(days=i): (km, 1000) for i, km in enumerate([69, 94, 90, 58, 59, 82, 60])}
        daily[date(2026, 5, 1)] = (131, 400)
        s = S.series_stats(daily)
        self.assertEqual(s["series_days"], 7)
        self.assertEqual(s["max_km_day"], 131)
        self.assertEqual(s["series_km"], 512)
        self.assertEqual(s["best_km_day"], 73)
        self.assertEqual(s["best_up_day"], 1000)


class TestStatus(unittest.TestCase):
    def test_trip(self):
        hist = {"max_km_day": 131, "max_up_day": 1621, "series_days": 7, "series_start": "2026-06-05", "series_km": 511, "series_up": 7259,
                "best_km_day": 73, "best_km_series": "2026-06-05, 7 dni", "best_up_day": 1037, "best_up_series": "2026-06-05, 7 dni"}
        g = {"target": {"km": 790, "up_m": 15300, "days": 9}, "date_from": "2027-05-14", "date_to": "2027-05-22"}
        s = S.status_trip(g, hist, 55, 91)
        self.assertEqual(s["level"], "y")
        self.assertIn("przewyższenie", s["text"])

    def test_weight_wrong_direction(self):
        g = {"target": {"weight_kg": 90}, "date_to": "2027-10-31"}
        self.assertEqual(S.status_weight(g, 103.5, 103.5, 0.3, date(2026, 9, 23))["level"], "r")
        self.assertEqual(S.status_weight(g, 103.5, 104, -0.3, date(2026, 9, 23))["level"], "g")
        self.assertEqual(S.status_weight(g, 103.5, 104, -0.1, date(2026, 9, 23))["level"], "y")

    def test_linear(self):
        self.assertEqual(S.status_linear(5000, 10000, 0.5, "km", "km")["level"], "g")
        self.assertEqual(S.status_linear(3000, 10000, 0.5, "km", "km")["level"], "r")


class TestWeatherAuto(unittest.TestCase):
    def test_values(self):
        rides = [{"h": 3 if i % 3 == 0 else 1, "month": (i % 12) + 1, "feel": 10 - (i % 20), "feel_max": 20 + (i % 10),
                  "wind": 2 + (i % 5), "gust": 6 + (i % 8), "rain": 0, "snow_depth": 0.1 if i < 15 else 0} for i in range(100)]
        a = S.weather_auto(rides)
        self.assertIn("wx.wind_ms", a)
        self.assertEqual(a["wx.rain_mmh"]["value"], 0.5)
        self.assertEqual(a["wx.snow_cm"]["value"], 10)
        self.assertEqual(S.weather_auto(rides[:10]), {})


if __name__ == "__main__":
    unittest.main()
