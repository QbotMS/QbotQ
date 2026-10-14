"""[GARMIN-DANE] Etap 4: sygnal 'Organizm pod obciazeniem' (temp. skory + HRV/tetno)."""
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.body_signal import evaluate  # noqa: E402

D0 = date(2026, 1, 1)


def rows(last, n=60, h=80.0, r=48.0, t=0.0):
    out = [(D0 + timedelta(days=i), t, h, r) for i in range(n)]
    out.append((D0 + timedelta(days=n),) + last)
    return out


class TestBodySignal(unittest.TestCase):
    def test_signal_temp_and_hrv(self):
        e = evaluate(rows((0.5, 70.0, 48.0)))
        self.assertTrue(e["signal"])
        self.assertIn("HRV 70 ms (norma 80)", e["text"])
        self.assertIn("+0,5 °C", e["text"])

    def test_signal_temp_and_rhr(self):
        self.assertTrue(evaluate(rows((0.4, 80.0, 52.0)))["signal"])

    def test_warm_room_no_signal(self):
        e = evaluate(rows((0.5, 82.0, 47.0)))
        self.assertFalse(e["signal"])
        self.assertIsNone(e["text"])

    def test_low_temp_ignored(self):
        self.assertFalse(evaluate(rows((-0.8, 60.0, 55.0)))["signal"])

    def test_below_threshold(self):
        self.assertFalse(evaluate(rows((0.3, 60.0, 55.0)))["signal"])

    def test_too_little_history_no_signal(self):
        self.assertFalse(evaluate(rows((0.6, 60.0, 55.0), n=10))["signal"])

    def test_no_temp(self):
        self.assertIsNone(evaluate([(D0, None, 80, 48)]))

    def test_last_night_with_temp_used(self):
        rs = rows((0.5, 70.0, 48.0)) + [(D0 + timedelta(days=99), None, 80.0, 48.0)]
        self.assertEqual(evaluate(rs)["date"], (D0 + timedelta(days=60)).isoformat())


if __name__ == "__main__":
    unittest.main()
