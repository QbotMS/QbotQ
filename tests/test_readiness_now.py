"""Gotowosc TERAZ (fitmodel/readiness_now.py) — kara z dzisiejszej jazdy, malejaca w czasie."""
import os, sys, unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/qbot/app")
from fitmodel import readiness_now as rn

TZ = timezone(timedelta(hours=2))


class _Cur:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class FakeConn:
    def __init__(self, base, ctl, rides): self.base, self.ctl, self.rides = base, ctl, rides
    def execute(self, sql, params=None):
        if "fitmodel_daily" in sql:
            return _Cur([{"base": self.base, "ctl": self.ctl}])
        return _Cur(self.rides)


def ride(h, m, dur_s, xss):
    return {"started_at": datetime(2026, 10, 8, h, m, tzinfo=TZ), "dur": dur_s, "xss": xss, "name": "jazda"}


class T(unittest.TestCase):
    def test_no_rides_none(self):
        c = FakeConn(-0.37, 57.1, [])
        self.assertIsNone(rn.compute(c, "2026-10-08", now=datetime(2026, 10, 8, 18, 0, tzinfo=TZ)))

    def test_penalty_right_after_ride(self):
        c = FakeConn(-0.37, 57.1, [ride(14, 25, 3300, 52.8)])
        r = rn.compute(c, "2026-10-08", now=datetime(2026, 10, 8, 15, 20, tzinfo=TZ))
        self.assertAlmostEqual(r["penalty"], -0.6 * 52.8 / 57.1, places=2)
        self.assertLess(r["now"], r["base"])

    def test_decays_by_half(self):
        c = FakeConn(-0.37, 57.1, [ride(10, 0, 3600, 57.1)])
        r0 = rn.compute(c, "2026-10-08", now=datetime(2026, 10, 8, 11, 0, tzinfo=TZ))
        r1 = rn.compute(c, "2026-10-08", now=datetime(2026, 10, 8, 16, 30, tzinfo=TZ))
        self.assertAlmostEqual(r1["penalty"], r0["penalty"] / 2, places=2)

    def test_two_rides_sum(self):
        c = FakeConn(0.0, 50, [ride(8, 0, 3600, 50), ride(12, 0, 3600, 50)])
        r = rn.compute(c, "2026-10-08", now=datetime(2026, 10, 8, 13, 0, tzinfo=TZ))
        self.assertEqual(len(r["rides"]), 2)
        self.assertLess(r["penalty"], -0.6)

    def test_other_day_none(self):
        c = FakeConn(-0.37, 57.1, [ride(14, 25, 3300, 52.8)])
        self.assertIsNone(rn.compute(c, "2026-10-07", now=datetime(2026, 10, 8, 18, 0, tzinfo=TZ)))


if __name__ == "__main__":
    unittest.main()
