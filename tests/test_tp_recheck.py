"""fitmodel.tp_recheck: wyzwalacz, bezpieczniki, dolna granica z W'bal (bez bazy)."""
from __future__ import annotations

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import tp_recheck as tr  # noqa: E402

T0 = dt.date(2026, 10, 4)
ST = {**tr.DEFAULTS, "armed_at": "2026-10-04"}
NONE = {"rides": 0, "hours": 0.0, "km": 0.0}


class TriggerTests(unittest.TestCase):
    def test_nothing_yet(self):
        self.assertIsNone(tr.trigger_reason(ST, T0 + dt.timedelta(days=5), {"rides": 2, "hours": 4.0, "km": 90.0}))

    def test_days(self):
        self.assertIn("dni", tr.trigger_reason(ST, T0 + dt.timedelta(days=21), NONE))

    def test_rides_hours_km_first_wins(self):
        self.assertIn("jazd", tr.trigger_reason(ST, T0, {"rides": 8, "hours": 1, "km": 1}))
        self.assertIn("h", tr.trigger_reason(ST, T0, {"rides": 1, "hours": 15.5, "km": 1}))
        self.assertIn("km", tr.trigger_reason(ST, T0, {"rides": 1, "hours": 1, "km": 401}))

    def test_disabled_condition(self):
        st = {**ST, "after_days": None, "after_rides": None, "after_hours": None}
        self.assertIsNone(tr.trigger_reason(st, T0 + dt.timedelta(days=99), {"rides": 99, "hours": 99, "km": 1}))


class GateTests(unittest.TestCase):
    def test_illness_in_window_blocks(self):
        self.assertIn("infekcje", tr.gate_reason(T0, dt.date(2026, 9, 20), 14, 20, 8))

    def test_clear_after_illness(self):
        self.assertIsNone(tr.gate_reason(dt.date(2026, 11, 5), dt.date(2026, 9, 20), 14, 20, 8))

    def test_too_few_segments(self):
        self.assertIn("segmentow", tr.gate_reason(dt.date(2026, 11, 5), None, 14, 5, 8))


class LowerBoundTests(unittest.TestCase):
    def _ride(self, watts, secs):
        t = dt.datetime(2026, 10, 4, 10, 0, 0)
        return [(t + dt.timedelta(seconds=i), watts) for i in range(secs)]

    def test_steady_under_tp_no_deficit(self):
        self.assertGreaterEqual(tr.wbal_min_kj(self._ride(200.0, 1800), 240.0, 18000.0), 17.9)

    def test_deficit_when_over(self):
        # 300 s po 300 W przy TP 240: wydatek 60 W * 300 s = 18 kJ -> dno ~0
        self.assertAlmostEqual(tr.wbal_min_kj(self._ride(300.0, 300), 240.0, 18000.0), 0.0, delta=0.3)

    def test_lower_bound(self):
        # 600 s po 260 W, W' 18 kJ: dno >= -1 kJ wymaga (260-TP)*600 <= 19 kJ -> TP >= ~228.3
        lb = tr.lower_bound_tp([self._ride(260.0, 600)], 18000.0)
        self.assertAlmostEqual(lb, 228.3, delta=1.0)


class ReportTests(unittest.TestCase):
    def test_report_mentions_numbers(self):
        txt = tr.report_text({"tp_model_w": 256.1, "hie_kj": 18.86, "tp_lower_bound_w": 238.5, "lb_rides": 20,
                              "tp_ef_w": 236, "tp_ef_range_w": [227, 248], "ef28": 1.57, "ef_segments": 12},
                             "minelo 21 dni")
        self.assertIn("256", txt)
        self.assertIn("238", txt)
        self.assertIn("Nic nie zostalo zmienione", txt)


if __name__ == "__main__":
    unittest.main()
