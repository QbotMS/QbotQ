"""Faktyczne zmeczenie/swiezosc (fitmodel/real_load.py)."""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import real_load as RL  # noqa: E402


class Body(unittest.TestCase):
    def test_signs(self):
        b, p = RL.body_score(-1.0, 50, 47, 1.5, 40, 70, 15, 0, 0)
        self.assertGreater(b, 0)                       # zmeczone cialo
        b2, _ = RL.body_score(0.8, 45, 47, 1.5, 90, 70, 15, 0, 0)
        self.assertLess(b2, 0)                         # wypoczete cialo -> mniej zmeczenia
    def test_feel_only_when_nonzero(self):
        b0, p0 = RL.body_score(0, None, None, None, None, None, None, 0, 0)
        self.assertEqual(b0, 0.0); self.assertNotIn("samopoczucie", p0)
        bw, pw = RL.body_score(0, None, None, None, None, None, None, 0, -2)
        self.assertAlmostEqual(bw, 0.6); self.assertIn("samopoczucie", pw)
        bg, _ = RL.body_score(0, None, None, None, None, None, None, 0, 2)
        self.assertAlmostEqual(bg, -0.6)
    def test_illness_adds(self):
        b, p = RL.body_score(0, None, None, None, None, None, None, 1.0, 0)
        self.assertAlmostEqual(b, 1.0); self.assertIn("infekcja", p)


class Live(unittest.TestCase):
    def test_columns_consistent(self):
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect(); cur = c.cursor()
        cur.execute("SELECT atl_raw, ctl_xss, body_load, atl_real, tsb_real FROM qbot_v2.fitmodel_daily "
                    "WHERE atl_real IS NOT NULL ORDER BY day DESC LIMIT 30")
        rows = cur.fetchall(); c.close()
        self.assertTrue(rows)
        for atl, ctl, b, af, tf in rows:
            self.assertAlmostEqual(float(af), float(atl) + RL.BETA * float(b) * float(ctl), delta=0.2)
            self.assertAlmostEqual(float(tf), float(ctl) - float(af), delta=0.2)


if __name__ == "__main__":
    unittest.main()
