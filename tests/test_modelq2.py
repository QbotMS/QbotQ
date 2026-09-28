# -*- coding: utf-8 -*-
"""Testy ModelQ v2 (2026-09-28). Czesc A-C: czyste obliczenia na sztucznych danych (bez bazy).
Czesc D: spojnosc na zywej bazie (TYLKO ODCZYT; pomijane gdy baza niedostepna).
Czesc E: straznik kanonu XSS (raport z jazdy / lista jazd / fakty analizy = XSS ModelQ).
Uruchom: .venv/bin/python3 -m unittest tests.test_modelq2
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2.xss import compute_xss
from fitmodel.modelq2.mpa import replay_mpa
from fitmodel.modelq2.training_load import build_load_series, TAU_TL, TAU_RL
from fitmodel.modelq2 import progression, publish

SIG = Signature.from_kj(tp_w=250.0, hie_kj=20.0, pp_w=900.0)
T0 = dt.datetime(2026, 1, 1, 10, 0, 0, tzinfo=dt.timezone.utc)


def rows_of(powers):
    return [(T0 + dt.timedelta(seconds=i), float(p)) for i, p in enumerate(powers)]


# ---------------------------------------------------------------- A) XSS jazdy
class TestXss(unittest.TestCase):
    def test_hour_at_threshold_is_about_100_low(self):
        x = compute_xss(rows_of([250] * 3600), SIG)
        self.assertAlmostEqual(x.low, 100.0, delta=5.0)
        self.assertLess(x.high + x.peak, 2.0)

    def test_hour_at_half_threshold_is_about_50(self):
        x = compute_xss(rows_of([125] * 3600), SIG)
        self.assertAlmostEqual(x.total, 50.0, delta=3.0)
        self.assertLess(x.high, 0.5)

    def test_longer_ride_gives_more_xss(self):
        a = compute_xss(rows_of([150] * 3600), SIG).total
        b = compute_xss(rows_of([150] * 7200), SIG).total
        self.assertAlmostEqual(b, 2 * a, delta=0.05 * a)

    def test_surges_add_high_and_drain_wprime(self):
        p = []
        for _ in range(12):
            p += [200] * 240 + [450] * 60
        steady = compute_xss(rows_of([200] * len(p)), SIG)
        surgy = compute_xss(rows_of(p), SIG)
        self.assertGreater(surgy.high, 5.0)
        self.assertGreater(surgy.total, steady.total)
        res = replay_mpa(rows_of(p), SIG, smooth=True, keep_series=True)
        self.assertLess(res.min_wbal_pct, 90.0)


# ---------------------------------------------------------------- B) forma / zmeczenie
class TestLoad(unittest.TestCase):
    D = dt.date(2026, 1, 1)

    def _tot(self, dl):
        ctl = dl.low.tl + dl.high.tl + dl.peak.tl
        atl = dl.low.rl + dl.high.rl + dl.peak.rl
        return ctl, atl

    def test_single_day_step(self):
        s = build_load_series({self.D: (70.0, 0.0, 0.0)})
        ctl, atl = self._tot(s[0])
        self.assertAlmostEqual(ctl, 70.0 / TAU_TL, places=6)
        self.assertAlmostEqual(atl, 70.0 / TAU_RL, places=6)

    def test_rest_decays_and_gaps_are_zero(self):
        s = build_load_series({self.D: (100.0, 0.0, 0.0), self.D + dt.timedelta(days=3): (0.0, 0.0, 0.0)})
        self.assertEqual(len(s), 4)  # dni luk wypelnione
        c0, a0 = self._tot(s[0]); c1, a1 = self._tot(s[1])
        self.assertAlmostEqual(c1, c0 * (1 - 1 / TAU_TL), places=6)
        self.assertAlmostEqual(a1, a0 * (1 - 1 / TAU_RL), places=6)

    def test_tsb_is_ctl_minus_atl(self):
        s = build_load_series({self.D: (80.0, 5.0, 1.0)})
        self.assertAlmostEqual(s[0].low.form + s[0].high.form + s[0].peak.form,
                               (s[0].low.tl + s[0].high.tl + s[0].peak.tl) - (s[0].low.rl + s[0].high.rl + s[0].peak.rl), places=9)


# ---------------------------------------------------------------- C) wiele jazd dziennie
class _Cur:
    def __init__(self, rows=None, starts=None, inserted=None):
        self.rows, self.starts, self.inserted, self._last = rows or [], starts or {}, inserted, None

    def execute(self, sql, params=None):
        self._sql, self._params = sql, params
        if "INSERT INTO qbot_v2.modelq2_ride" in sql and self.inserted is not None:
            self.inserted.append(params[0])

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if "started_at FROM qbot_v2.training_sessions" in self._sql:
            st = self.starts.get(self._params[0])
            return (st,) if st else None
        return None  # brak w modelq2_ride / brak kwarantanny


class _Conn:
    def __init__(self, cur):
        self.c = cur

    def cursor(self):
        return self.c

    def commit(self):
        pass


class TestMultiRide(unittest.TestCase):
    def test_two_rides_same_day_are_summed(self):
        d = dt.date(2026, 4, 1)
        conn = _Conn(_Cur(rows=[(d, 40.0, 1.0, 0.0), (d, 30.0, 2.0, 0.5), (d + dt.timedelta(days=1), 10.0, 0.0, 0.0)]))
        out = progression._load_xss_by_day(conn)
        self.assertEqual(out[d], (70.0, 3.0, 0.5))
        self.assertEqual(out[d + dt.timedelta(days=1)], (10.0, 0.0, 0.0))

    def _ingest(self, rides, starts):
        inserted = []
        orig = (publish.io.list_rides, publish._mq2_sig_before, publish.io.fetch_ride_rows, publish.replay_mpa, publish.compute_xss)

        class R:
            n_ticks, duration_s, min_wbal_pct, series = 3000, 3000, 80.0, []

        class X:
            low, high, peak, total = 50.0, 1.0, 0.0, 51.0
        try:
            publish.io.list_rides = lambda a, b: rides
            publish._mq2_sig_before = lambda cur, d: SIG
            publish.io.fetch_ride_rows = lambda eid: []
            publish.replay_mpa = lambda *a, **k: R()
            publish.compute_xss = lambda *a, **k: X()
            n = publish.ingest_new_rides_xss(_Conn(_Cur(starts=starts, inserted=inserted)), lookback_days=30)
        finally:
            publish.io.list_rides, publish._mq2_sig_before, publish.io.fetch_ride_rows, publish.replay_mpa, publish.compute_xss = orig
        return n, inserted

    def test_ingest_takes_every_ride_of_the_day(self):
        d = dt.date(2026, 4, 1)
        n, ins = self._ingest([("A", d, 3000), ("B", d, 2500)],
                              {"A": dt.datetime(2026, 4, 1, 8, 0), "B": dt.datetime(2026, 4, 1, 16, 0)})
        self.assertEqual(n, 2)
        self.assertEqual(sorted(ins), ["A", "B"])

    def test_duplicate_with_same_start_counted_once(self):
        d = dt.date(2026, 4, 1)
        n, ins = self._ingest([("A", d, 3000), ("A2", d, 2900)],
                              {"A": dt.datetime(2026, 4, 1, 8, 0), "A2": dt.datetime(2026, 4, 1, 8, 0)})
        self.assertEqual(ins, ["A"])  # strumien z wieksza liczba probek


# ---------------------------------------------------------------- D) spojnosc na zywej bazie (odczyt)
def _db():
    try:
        from fitmodel.api import _db_connect
        return _db_connect()
    except Exception:
        return None


class TestModelQ2Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = _db()
        if cls.conn is None:
            raise unittest.SkipTest("baza niedostepna")
        from fitmodel.modelq2 import integrity
        cls.I = integrity

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "conn", None):
            cls.conn.close()

    def test_every_ride_with_1hz_has_xss(self):
        self.assertEqual(self.I.missing_xss(self.conn.cursor()), [])

    def test_daily_load_equals_sum_of_rides(self):
        self.assertEqual(self.I.daily_load_mismatch(self.conn.cursor()), [])

    def test_no_duplicate_rides(self):
        self.assertEqual(self.I.duplicate_rides(self.conn.cursor()), [])


# ---------------------------------------------------------------- E) straznik kanonu XSS
class TestCanonicalXss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = _db()
        if cls.conn is None:
            raise unittest.SkipTest("baza niedostepna")
        cur = cls.conn.cursor()
        cur.execute("""SELECT m.external_id, m.xss_total FROM qbot_v2.modelq2_ride m
                       JOIN qbot_v2.ride_report_data d ON d.ride_key = m.external_id
                       ORDER BY m.ride_date DESC LIMIT 1""")
        cls.ride = cur.fetchone()
        if not cls.ride:
            raise unittest.SkipTest("brak jazdy z raportem")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "conn", None):
            cls.conn.close()

    def test_ride_report_load_is_modelq(self):
        from qbot3.rides import ride_report_builder as B
        w1 = B.apply_canonical_load({"ride_key": self.ride[0], "load": {"xss": {"value": 999.0, "source": "wbal_replay"}}})
        self.assertEqual(w1["load"]["xss"]["source"], "modelq2")
        self.assertAlmostEqual(w1["load"]["xss"]["value"], float(self.ride[1]), delta=0.05)

    def test_analysis_facts_use_modelq(self):
        from qbot3.rides import ride_report_facts as F
        ses = F._session(self.conn.cursor(), self.ride[0])
        self.assertAlmostEqual(float(ses[5]), float(self.ride[1]), delta=0.05)

    def test_ride_list_uses_modelq(self):
        from fastapi import Response
        import qbot_web
        rides = qbot_web.rides_ready(Response())["rides"]
        cur = self.conn.cursor()
        checked = 0
        for r in rides[:15]:
            cur.execute("SELECT xss_total FROM qbot_v2.modelq2_ride WHERE external_id=%s", (r["ride_key"],))
            m = cur.fetchone()
            if m and m[0] is not None:
                self.assertEqual(r["xss"], round(float(m[0])), "lista jazd %s" % r["ride_key"])
                checked += 1
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
