# -*- coding: utf-8 -*-
"""Testy tytulu [Qbot] (2026-10-09 e)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_strava_publish as P  # noqa: E402

W_0410 = {"cloud_pct": {"value": 99.7}, "precip_mm": {"value": {"sum": 0.0, "wet_h": 0}},
          "temp_c": {"value": {"avg": 12.3, "max": 24, "min": 10}}, "wind_ms": {"value": {"avg": 1.6, "max": 2.0}}}


class T(unittest.TestCase):
    def test_default_names(self):
        for n in ("Afternoon Ride", "☁️ Afternoon Ride", "Evening Gravel Ride", "Zakroczym Kolarstwo", "Jazda popołudniowa".replace("Jazda popołudniowa", "Popołudniowa jazda"), "Ride"):
            self.assertTrue(P.is_default_name(n), n)
        for n in ("Zakroczym w ogniu 🔥", "MyBIOM", "Do mamy", "Magnetyzer", "Oppelner Gravelzug - D2 Ziębice-Prudnik", None, ""):
            self.assertFalse(P.is_default_name(n), n)

    def test_weather(self):
        self.assertEqual(P.weather_icons(W_0410), ["☁️"])
        hot = {"cloud_pct": {"value": 10}, "temp_c": {"value": {"avg": 27, "max": 33, "min": 22}}, "wind_ms": {"value": {"max": 3}}}
        self.assertEqual(P.weather_icons(hot), ["☀️", "🔥"])
        rain = {"cloud_pct": {"value": 100}, "precip_mm": {"value": {"sum": 4.0, "wet_h": 2}}, "wind_ms": {"value": {"max": 9}},
                "temp_c": {"value": {"avg": 9}}}
        self.assertEqual(P.weather_icons(rain), ["🌧️", "💨"])
        self.assertEqual(P.weather_icons(None), [])

    def test_label(self):
        s = {"asfalt": 55, "szuter": 20, "ujeby": 25}
        self.assertEqual(P.ride_label(107, s, None), "wyprawa")
        self.assertEqual(P.ride_label(80, s, None), "wyprawa")
        self.assertEqual(P.ride_label(52, s, None), "gravel")
        self.assertEqual(P.ride_label(40, {"asfalt": 90, "szuter": 8, "ujeby": 2}, None), "szosa")
        self.assertEqual(P.ride_label(40, {"asfalt": 75, "szuter": 15, "ujeby": 10}, None), "mix")
        self.assertEqual(P.ride_label(109, s, 2), "bikepacking D2")

    def test_title(self):
        t = P.build_title(None, P.title_places(["Kamion", "Wyszogród", "Śladów", "Czerwińsk nad Wisłą"],
                                               {"Wyszogród": 1, "Czerwińsk nad Wisłą": 1}),
                          "wyprawa", "mocno", ["☁️"])
        self.assertEqual(t, "[Qbot] Wyszogród – Czerwińsk nad Wisłą · wyprawa 💪 ☁️")
        self.assertNotIn("km", t)
        self.assertEqual(P.build_title("mybiom", [], "gravel", "mocno", ["☁️"]), "MyBIOM")
        self.assertEqual(P.build_title("domamy", [], None, None, []), "do Mamy")


if __name__ == "__main__":
    unittest.main()
