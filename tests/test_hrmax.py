"""Testy fitmodel/hrmax.py -- wykrywanie wiarygodnego szczytu tetna i zasady publikacji."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel import hrmax as h  # noqa: E402


def ride(hr_fn, p_fn, n=1200):
    return [(s, p_fn(s), hr_fn(s)) for s in range(n)]


class TestPeak(unittest.TestCase):
    def test_real_effort_peak(self):
        # podjazd: tetno rosnie 1 ud./3 s do 172, moc 260 W przy CP 240
        hr = lambda s: min(172, 120 + s // 3) if s < 900 else 150
        r = h.ride_peak(ride(hr, lambda s: 260), 240)
        self.assertEqual(r[0], 172)
        self.assertEqual(r[3], "ok")

    def test_artifact_like_2_may_rejected(self):
        # 02.05.2026: 93 -> 181 -> 115 w 90 s przy ~70 W -- ma odpasc (skok i brak wysilku)
        def hr(s):
            if 600 <= s < 615:
                return 181
            if 595 <= s < 600 or 615 <= s < 620:
                return 140
            return 93 if s < 600 else 115
        r = h.ride_peak(ride(hr, lambda s: 70), 240)
        self.assertNotEqual(r[0], 181)

    def test_high_hr_without_effort_rejected(self):
        hr = lambda s: min(175, 100 + s // 4)
        r = h.ride_peak(ride(hr, lambda s: 120), 240)
        self.assertIsNone(r[0])
        self.assertIn("bez wysilku", r[3])

    def test_short_spike_not_sustained(self):
        hr = lambda s: 185 if 500 <= s < 505 else 150
        r = h.ride_peak(ride(hr, lambda s: 250), 240)
        self.assertEqual(r[0], 150)

    def test_no_power_rejected(self):
        r = h.ride_peak(ride(lambda s: 170, lambda s: None), 240)
        self.assertIsNone(r[0])


class TestPublish(unittest.TestCase):
    D = dt.date(2026, 10, 1)

    def test_start_from_history_or_seed(self):
        self.assertEqual(h.publish_value(None, [(171, "a", self.D), (173, "b", self.D)])[0], 173)
        self.assertEqual(h.publish_value(None, [])[0], h.SEED_BPM)

    def test_up_immediately(self):
        self.assertEqual(h.publish_value(173, [(175, "a", self.D)])[0], 175)

    def test_down_only_when_far(self):
        self.assertEqual(h.publish_value(173, [(171, "a", self.D)])[0], 173)     # w tolerancji 3 ud.
        self.assertEqual(h.publish_value(184, [(173, "a", self.D)])[0], 173)     # 184 -> 173 (nic blizej niz 3 ud.)

    def test_no_peaks_keeps(self):
        self.assertEqual(h.publish_value(173, [])[0], 173)


if __name__ == "__main__":
    unittest.main()
