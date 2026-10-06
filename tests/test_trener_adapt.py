"""TRENER: wykonanie vs plan (qbot_trener_ops.deviation) i tekst Telegrama (qbot_trener_notify.adapt_text). Bez bazy."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_trener_ops as OPS  # noqa: E402
import qbot_trener_notify as N  # noqa: E402


class DeviationTest(unittest.TestCase):
    def test_today_case_much_more(self):
        # 2026-10-06: plan 30' spokojnie (obc. 22), realnie 141' (obc. 130)
        d = OPS.deviation(30, 22, 141, 130, "rower", 15, 120)
        self.assertEqual(d["flag"], "wiecej")
        self.assertTrue(d["adapt"])
        self.assertTrue(d["heavy"])
        self.assertEqual(d["d_xss"], 108)

    def test_short_ride_small_diff_no_adapt(self):
        # +10% czasu krotkiej jazdy = szum: oznaczenie tak, przeliczenie nie
        d = OPS.deviation(30, 22, 33, 24, "rower", 15, 120)
        self.assertEqual(d["flag"], "wiecej")
        self.assertFalse(d["adapt"])

    def test_within_plan(self):
        d = OPS.deviation(60, 45, 62, 47, "rower", 15, 120)
        self.assertIsNone(d["flag"])
        self.assertFalse(d["adapt"])

    def test_long_ride_10pct_adapts(self):
        # +10% dlugiej jazdy = realne zmeczenie (+25 obc.)
        d = OPS.deviation(300, 220, 330, 245, "rower", 15, 120)
        self.assertTrue(d["adapt"])
        self.assertEqual(d["flag"], "wiecej")

    def test_less_than_plan(self):
        d = OPS.deviation(90, 70, 45, 30, "rower", 15, 120)
        self.assertEqual(d["flag"], "mniej")
        self.assertTrue(d["adapt"])
        self.assertFalse(d["heavy"])

    def test_threshold_from_calibration(self):
        self.assertFalse(OPS.deviation(60, 45, 80, 65, "rower", 30, 120)["adapt"])
        self.assertTrue(OPS.deviation(60, 45, 80, 65, "rower", 15, 120)["adapt"])

    def test_strength_without_load(self):
        d = OPS.deviation(40, 12, 60, None, "sila", 15, 120)
        self.assertEqual(d["flag"], "wiecej")
        self.assertFalse(d["adapt"])


class AdaptTextTest(unittest.TestCase):
    def test_text(self):
        res = {"change_id": 1, "lines": ["− 10-08 🚲 Rower luźno (przed wyprawą) 09:00 45′", "+ 10-08 🧘 Joga 09:00 30′"],
               "notes": ["2026-10-07: przerwa po ciężkiej jeździe 2026-10-06 (Marki, ~130 XSS) — bez roweru"],
               "devs": [dict(OPS.deviation(30, 22, 141, 130), day="2026-10-06", sport="rower", name="Rower spokojnie",
                             plan_min=30, plan_xss=22.0, real_min=141, real_xss=130.0)]}
        t = N.adapt_text(res)
        self.assertIn("plan 30′ / obc. 22 → realnie 2:21 / obc. 130", t)
        self.assertIn("📈", t)
        self.assertIn("Rower luźno", t)
        self.assertIn("przerwa po ciężkiej", t)
        self.assertTrue(t.rstrip().endswith(N.URL))


if __name__ == "__main__":
    unittest.main()
