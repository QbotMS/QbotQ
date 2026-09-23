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


def real_like():
    daily = {}
    # Mazury 2025: 8 dni lekkich petli (403 km, 2955 m)
    for i, (km, up) in enumerate([(46, 278), (50, 425), (25, 136), (55, 298), (34, 290), (72, 607), (65, 548), (56, 373)]):
        daily[date(2025, 8, 8) + timedelta(days=i)] = (km, up)
    # Toskania 2026: 7 dni (511 km, 7259 m)
    for i, (km, up) in enumerate([(69, 766), (94, 1238), (90, 1237), (58, 613), (59, 1150), (82, 1290), (59, 965)]):
        daily[date(2026, 6, 5) + timedelta(days=i)] = (km, up)
    # Opole 2026: 3 dni (341 km, 2372 m); rekord dnia 131 km
    for i, (km, up) in enumerate([(131, 825), (109, 824), (101, 723)]):
        daily[date(2026, 8, 1) + timedelta(days=i)] = (km, up)
    return daily


def geo_like():
    """Mazury: 8 dni petli z jednej bazy; Sycylia: petle z bazy; Toskania: 7 dni z punktu do punktu (~0,4 st. dziennie)."""
    d = {}
    base_m, base_s = (54.0, 22.0), (36.9, 15.1)
    for i, (km, up) in enumerate([(46, 278), (50, 425), (25, 136), (55, 298), (34, 290), (72, 607), (65, 548), (56, 373)]):
        d[date(2025, 8, 8) + timedelta(days=i)] = (km, up, base_m, base_m)
    for i, dd in enumerate([8, 9, 11, 13, 14, 17, 18, 20]):
        d[date(2026, 8, dd)] = (50, 600, base_s, base_s)
    pt = (43.7, 11.2)
    for i, (km, up) in enumerate([(69, 766), (94, 1238), (90, 1237), (58, 613), (59, 1150), (82, 1290), (59, 965)]):
        nxt = (pt[0] - 0.4, pt[1] + 0.1)
        d[date(2026, 6, 5) + timedelta(days=i)] = (km, up, pt, nxt)
        pt = nxt
    return d


class TestExpeditions(unittest.TestCase):
    def test_only_point_to_point_counts(self):
        ch = S.expedition_chains(geo_like())
        self.assertEqual(len(ch), 1)
        self.assertEqual((ch[0]["start"], ch[0]["days"], ch[0]["km"]), ("2026-06-05", 7, 511))

    def test_stats_ignore_base_loops(self):
        s = S.series_stats(geo_like())
        self.assertEqual(s["ref"]["start"], "2026-06-05")
        self.assertEqual(s["longest"]["days"], 7)      # Mazury (8 dni petli) juz nie sa "najdluzsza wyprawa"

    def test_rest_day_inside_trip(self):
        d = {}
        pt = (50.0, 17.0)
        for dd in (1, 2, 4):  # 3 = dzien przerwy
            nxt = (pt[0] + 0.3, pt[1]); d[date(2026, 8, dd)] = (100, 800, pt, nxt); pt = nxt
        self.assertEqual(S.expedition_chains(d)[0]["days"], 3)


def geo_with_opole():
    d = geo_like()
    pt = (50.7, 17.9)
    for i, (km, up) in enumerate([(131, 825), (109, 824), (101, 723)]):
        nxt = (pt[0] - 0.3, pt[1] - 0.3); d[date(2026, 8, 1) + timedelta(days=i)] = (km, up, pt, nxt); pt = nxt
    return d


class TestTripWindow(unittest.TestCase):
    def test_short_trip_compared_with_best_3_days(self):
        hist = S.series_stats(geo_with_opole())
        g = {"kind": "trip", "target": {"km": 300, "up_m": 2500, "days": 3}, "date_from": "2027-04-16", "date_to": "2027-04-18"}
        st = S.status_trip(g, hist, 56, 91)
        rows = {r["k"]: r for r in st["rows"]}
        self.assertEqual(st["level"], "g")                                  # Opole 114 km/d i Toskania >833 m/d
        self.assertGreaterEqual(rows["km na dzień"]["have"], 100)
        self.assertGreaterEqual(rows["przewyższenie na dzień"]["have"], 0.9 * 833)   # Opole: 114 km i 791 m/dzien w jednym bloku
        self.assertEqual(rows["dni pod rząd"]["have"], 7)

    def test_long_trip_uses_whole_longest(self):
        hist = S.series_stats(geo_with_opole())
        g = {"kind": "trip", "target": {"km": 792, "up_m": 15004, "days": 11}, "date_from": "2027-05-14", "date_to": "2027-05-24"}
        rows = {r["k"]: r for r in S.status_trip(g, hist, 56, 91)["rows"]}
        self.assertEqual(rows["km na dzień"]["have"], 73)                  # cale 7 dni Toskanii (dluzszego okna nie ma)


class TestSeries(unittest.TestCase):
    def test_reference_is_heaviest_not_longest(self):
        s = S.series_stats(real_like())
        self.assertEqual(s["ref"]["start"], "2026-06-05")        # Toskania, nie Mazury
        self.assertEqual(s["ref"]["days"], 7)
        self.assertEqual(s["ref"]["km"], 511)
        self.assertEqual(s["longest"]["days"], 8)                # tylko informacyjnie
        self.assertEqual(s["max_km_day"], 131)


class TestStatus(unittest.TestCase):
    def test_trip_uses_reference_trip(self):
        hist = S.series_stats(real_like())
        g = {"kind": "trip", "target": {"km": 790, "up_m": 15000, "days": 11}, "date_from": "2027-05-14", "date_to": "2027-05-24"}
        st = S.status_trip(g, hist, 56, 91)
        rows = {r["k"]: r for r in st["rows"]}
        self.assertEqual(rows["dni pod rząd"]["have"], 7)
        self.assertIn("05.06.2026–11.06.2026", rows["km na dzień"]["note"])
        self.assertEqual(rows["km na dzień"]["have"], 73)
        self.assertEqual(rows["przewyższenie na dzień"]["have"], 1037)
        self.assertIn("dni pod rząd", st["text"])   # 7/11 = 0.64 < przewyzszenie 1037/1364 = 0.76

    def test_long_ride_uses_day_record(self):
        hist = S.series_stats(real_like())
        st = S.status_trip({"kind": "long_ride", "target": {"km": 200, "up_m": 1500}, "date_from": "2027-06-12"}, hist, 56, 91)
        rows = {r["k"]: r for r in st["rows"]}
        self.assertEqual(rows["dystans"]["have"], 131)
        self.assertNotIn("dni pod rząd", rows)

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
