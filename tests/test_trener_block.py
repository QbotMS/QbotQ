"""Testy modelu bloku (bez bazy)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_block as B


class TestModel(unittest.TestCase):
    def test_step_matches_modelq(self):
        # z danych ModelQ 22->23.09.2026: CTL 56.9 -> 55.5, ATL 31.7 -> 27.2 przy ~0 XSS
        ctl, atl = B.step(56.9, 31.7, 0)
        self.assertAlmostEqual(ctl, 55.5, delta=0.2)
        self.assertAlmostEqual(atl, 27.2, delta=0.2)

    def test_trip_drops_tsb_then_recovers(self):
        d0 = date(2026, 10, 3)
        days = [d0 + timedelta(days=i) for i in range(6)]
        sim = B.simulate(55, 28, days, {days[0]: 227, days[1]: 227, days[2]: 227})
        self.assertLess(sim[3]["tsb_am"], B.TSB_FLOOR)      # rano po 3 dniach wyprawy
        self.assertGreater(sim[5]["tsb_am"], sim[3]["tsb_am"])

    def test_daily_target_formula(self):
        # staly X = CTL + 6*ramp przez 7 dni daje przyrost ~ramp
        ctl, atl = 50.0, 50.0
        x = ctl + 6 * 4
        for _ in range(7):
            ctl, atl = B.step(ctl, atl, x)
        self.assertAlmostEqual(ctl - 50, 4, delta=0.6)


if __name__ == "__main__":
    unittest.main()
