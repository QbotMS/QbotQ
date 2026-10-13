"""Serce (2026-10-12): czyste funkcje qbot_heart + obecnosc narzedzia heart_health w rejestrze."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_heart as h  # noqa: E402


def m(day, hour, s, d, p=60):
    return {"local": datetime(2026, 10, day, hour, 0), "sys": s, "dia": d, "pulse": p}


class BpCategory(unittest.TestCase):
    def test_progi(self):
        self.assertEqual(h.bp_category(120, 75)[0], "good")
        self.assertEqual(h.bp_category(132, 78)[0], "warn")
        self.assertEqual(h.bp_category(128, 86)[0], "bad")
        self.assertIn("bez zwłoki", h.bp_category(182, 90)[1])


class BpSeries(unittest.TestCase):
    def test_pomija_pierwszy_dzien_i_dzieli_rano_wieczor(self):
        rows = [m(1, 7, 160, 100), m(1, 21, 160, 100)]
        for day in range(2, 8):
            rows += [m(day, 7, 120, 80), m(day, 7, 122, 80), m(day, 21, 130, 82), m(day, 21, 128, 82)]
        out = h.bp_series_summary(rows)
        self.assertEqual(out["dropped_first_day"], "2026-10-01")
        self.assertEqual(out["days"], 7)
        self.assertEqual(out["morning"]["sys"], 121)
        self.assertEqual(out["evening"]["sys"], 129)
        self.assertEqual(out["sys"], 125)
        self.assertTrue(out["protocol_ok"])

    def test_krotka_seria_bez_odrzucania(self):
        out = h.bp_series_summary([m(5, 8, 140, 90), m(5, 20, 136, 86)])
        self.assertIsNone(out["dropped_first_day"])
        self.assertEqual(out["status"], "bad")
        self.assertFalse(out["protocol_ok"])

    def test_pusto(self):
        self.assertIsNone(h.bp_series_summary([]))


class Trend(unittest.TestCase):
    def test_status(self):
        norm = [46.0] * 30
        self.assertEqual(h.trend_vs_norm([47, 48], norm, 3, 5)["status"], "good")
        self.assertEqual(h.trend_vs_norm([49, 50], norm, 3, 5)["status"], "warn")
        self.assertEqual(h.trend_vs_norm([52, 51], norm, 3, 5)["status"], "bad")
        self.assertEqual(h.trend_vs_norm([52], norm, 3, 5)["status"], "info")


class Ecg(unittest.TestCase):
    def test_etykiety(self):
        self.assertIn("zatokowy", h.ecg_label("SINUS_NORMAL"))
        self.assertIn("NOWY_KOD", h.ecg_label("NOWY_KOD"))


class Regeneracja(unittest.TestCase):
    BP = {"from": "2026-10-12", "to": "2026-10-18", "sys": 140, "dia": 90,
          "morning": {"n": 6, "sys": 126, "dia": 84}, "evening": {"n": 6, "sys": 156, "dia": 95}}

    def test_wysokie_przy_dobrej_regeneracji(self):
        out = h.nexus(self.BP, [], {"delta": 1.0}, 78, 78, 410, 415, {})
        self.assertIn("stała cecha", out[0]["text"])
        self.assertTrue(any("Wieczorem średnio o 30/11" in p["text"] for p in out))

    def test_wysokie_przy_zmeczeniu(self):
        out = h.nexus(self.BP, [], {"delta": 4.0}, 60, 78, 330, 415, {})
        self.assertIn("słabszej regeneracji", out[0]["text"])
        self.assertIn("tętno spoczynkowe +4", out[0]["text"])

    def test_dzien_po_dniu(self):
        from datetime import date
        daily = {date(2026, 10, 10 + k): {"bp_sys_rano": 120 + 3 * k, "sleep_min": 480 - 20 * k, "hrv": 80, "tss_dzien_przed": 50}
                 for k in range(6)}
        out = h.nexus(self.BP, [], {"delta": 0}, 78, 78, 410, 415, daily)
        self.assertTrue(any("długość snu" in p["text"] for p in out))

    def test_cialo_i_spo2(self):
        b = h.body_status(109, 0.62, 33.9)
        self.assertEqual(b[0]["status"], "bad")
        self.assertIn("talia/wzrost 0,62", b[0]["text"])
        sp = h.spo2_status([88] * 20 + [93] * 10)
        self.assertEqual(sp["status"], "warn")
        self.assertEqual(sp["below90"], 20)
        self.assertIsNone(h.spo2_status([95] * 3))


class Registry(unittest.TestCase):
    def test_narzedzie_i_prompt(self):
        src = open("/opt/qbot/app/qbot3/tool_registry.py", encoding="utf-8").read()
        self.assertIn('("heart_health", _load_heart_health_tool)', src)
        prompt = open("/opt/qbot/app/qbot3/llm/albert.py", encoding="utf-8").read()
        self.assertIn("heart_health", prompt)
        from qbot3 import tool_registry as tr
        tool = tr._load_heart_health_tool()
        self.assertLess(len(tool["description"]), 500)


if __name__ == "__main__":
    unittest.main()
