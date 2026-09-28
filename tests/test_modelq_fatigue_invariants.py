"""Straznik ModelQ (2026-09-28): (1) dzien choroby BEZ jazdy nie jest odpoczynkiem ->
ATL+ nie spada; (2) load_ramp = srednia XSS 7 dni / srednia 28 dni; (3) publish
(przycisk AKTUALIZACJA) nie kasuje korekt zmeczenia. Tylko odczyt."""
import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")


class ModelQFatigueInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fitmodel.api import _db_connect
        cls.conn = _db_connect()
        cls.cur = cls.conn.cursor()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _ride_days(self):
        self.cur.execute("SELECT ride_date, SUM(xss_total) FROM qbot_v2.modelq2_ride GROUP BY ride_date")
        return {r[0]: float(r[1] or 0) for r in self.cur.fetchall()}

    def test_illness_without_ride_keeps_atl_plus_flat(self):
        rides = self._ride_days()
        self.cur.execute("SELECT day, COALESCE(end_day, day) FROM qbot_v2.calendar_entry WHERE kind='illness'")
        days = set()
        for a, b in self.cur.fetchall():
            d = a
            while d <= b:
                days.add(d); d += timedelta(days=1)
        checked = 0
        for d in sorted(days):
            if rides.get(d, 0) > 0 or rides.get(d - timedelta(days=1), None) is None and False:
                continue
            self.cur.execute("SELECT day, atl_plus FROM qbot_v2.fitmodel_daily WHERE day IN (%s,%s) ORDER BY day",
                             (d - timedelta(days=1), d))
            rows = self.cur.fetchall()
            if len(rows) != 2 or rows[0][1] is None or rows[1][1] is None:
                continue
            self.assertAlmostEqual(float(rows[1][1]), float(rows[0][1]), delta=0.3, msg=str(d))
            checked += 1
        if not checked:
            self.skipTest("brak dni choroby bez jazdy")

    def test_load_ramp_matches_xss(self):
        self.cur.execute("SELECT day, load_ramp FROM qbot_v2.fitmodel_daily WHERE load_ramp IS NOT NULL "
                         "ORDER BY day DESC LIMIT 1")
        r = self.cur.fetchone()
        if not r:
            self.skipTest("brak load_ramp")
        day, ramp = r[0], float(r[1])
        rides = self._ride_days()
        vals = [rides.get(day - timedelta(days=i), 0.0) for i in range(28)]
        exp = (sum(vals[:7]) / 7) / (sum(vals) / 28)
        self.assertAlmostEqual(ramp, exp, delta=0.011)

    def test_publish_keeps_corrections(self):
        import inspect
        from fitmodel.modelq2 import publish
        src = inspect.getsource(publish.run_daily_v2)
        self.assertIn("apply_hidden_fatigue", src)


if __name__ == "__main__":
    unittest.main()
