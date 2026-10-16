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


class TestBodyBatteryAkumulator(unittest.TestCase):
    """2026-10-16: Body Battery jako akumulator (dlug noc vs dzien) + limit +-2 na sygnal."""

    def test_dlug_i_zwrot(self):
        import datetime as dt
        from fitmodel import real_load as RL
        d = dt.date(2026, 10, 16)
        W = {d - dt.timedelta(days=k): (60, 80) for k in range(5)}   # kazda noc +60, kazdy dzien -80 -> dlug 20/noc
        z, debt = RL.bb_debt_z(d, W, 75)
        self.assertEqual(debt, 60)
        self.assertAlmostEqual(z, 60 / (3 * 75) * 2, places=6)
        W2 = {d - dt.timedelta(days=k): (90, 70) for k in range(5)}  # noce nadrabiaja -> wypoczety
        z2, _ = RL.bb_debt_z(d, W2, 75)
        self.assertLess(z2, 0)

    def test_brak_danych(self):
        import datetime as dt
        from fitmodel import real_load as RL
        self.assertEqual(RL.bb_debt_z(dt.date(2026, 10, 16), {}, 75), (None, None))

    def test_limit_sygnalu(self):
        from fitmodel import real_load as RL
        b, p = RL.body_score(-5.0, None, None, None, None, None, None, 0, 0)   # gotowosc -5 -> przycieta do +2
        self.assertEqual(p["gotowosc_3d"], 2.0)
        b2, p2 = RL.body_score(0, None, None, None, None, None, None, 0, 0, bb_z=0.3)
        self.assertEqual(p2["body_battery"], 0.3)


class TestKazdySygnalRaz(unittest.TestCase):
    """Audyt 16.10.2026 (docs/audit/sygnaly_ciala_2026-10-16.md): zaden sygnal ciala nie wchodzi do zmeczenia faktycznego dwa razy.
    Gotowosc w cialu = OBIEKTYWNA (readiness_score: HRV/RHR/sen) - samopoczucie i choroba sa w niej (readiness_effective /
    readiness_3d), wiec nie wolno ich uzyc razem z bezposrednim samopoczuciem/choroba; tetno jest w gotowosci (35%)."""

    def _src(self):
        import inspect
        from fitmodel import real_load as RL
        return inspect.getsource(RL.apply_real_load)

    def test_gotowosc_obiektywna(self):
        src = self._src()
        self.assertIn("readiness_score", src)
        self.assertNotIn("readiness_3d", src)          # zawiera samopoczucie i chorobe
        self.assertNotIn("readiness_effective", src)   # j.w.

    def test_bez_osobnego_tetna(self):
        from fitmodel import real_load as RL
        b, p = RL.body_score(0.2, None, None, None, None, None, None, 0, 0, bb_z=0.1)
        self.assertNotIn("tetno", p)
        self.assertNotIn("rhr", self._src().replace("rhr_", ""))

    def test_samopoczucie_i_choroba_raz(self):
        from fitmodel import real_load as RL
        b, p = RL.body_score(0.0, None, None, None, None, None, None, RL.ILL_W, -1, bb_z=0.0)
        self.assertAlmostEqual(b, RL.ILL_W + RL.FEEL_K, places=6)
        self.assertEqual(RL.ILL_W, 1.2)


if __name__ == "__main__":
    unittest.main()
