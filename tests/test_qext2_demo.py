"""Tryb NAGRANIE QExt2 (sesja demo-2110, 21.10.2026): jazdy z FIT qext2_demo=1 nie trafiaja do QBota.

Uruchom: .venv/bin/python3 -m unittest tests.test_qext2_demo -v
"""
import glob
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QBOT3_ENABLED", "1")
sys.path.insert(0, "/opt/qbot/app")

from fitmodel import qext2_demo  # noqa: E402


class Msg:
    def __init__(self, v):
        self.v = v

    def get_value(self, name):
        if name != "qext2_demo":
            return None
        if isinstance(self.v, Exception):
            raise self.v
        return self.v


class FakeCur:
    def __init__(self, log, row=(1,)):
        self.log, self.row = log, row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, row=(1,)):
        self.log, self.row, self.commits = [], row, 0

    def cursor(self):
        return FakeCur(self.log, self.row)

    def commit(self):
        self.commits += 1


class TestScan(unittest.TestCase):
    def test_znacznik_wykryty(self):
        self.assertTrue(qext2_demo.scan_messages([Msg(None), Msg(1)]))
        self.assertTrue(qext2_demo.scan_messages([Msg(1.0)]))

    def test_zwykla_jazda_bez_znacznika(self):
        self.assertFalse(qext2_demo.scan_messages([Msg(None)] * 50))
        self.assertFalse(qext2_demo.scan_messages([Msg(0)] * 5))
        self.assertFalse(qext2_demo.scan_messages([Msg(KeyError("x")), Msg("abc")]))

    def test_limit_rekordow(self):
        self.assertFalse(qext2_demo.scan_messages([Msg(None)] * 3 + [Msg(1)], limit=3))

    def test_prawdziwa_jazda_z_dysku_nie_jest_demo(self):
        fits = sorted(glob.glob("/opt/qbot/artifacts/fit/*.fit"), key=os.path.getmtime, reverse=True)
        if not fits:
            self.skipTest("brak plikow FIT")
        self.assertFalse(qext2_demo.is_demo_fit(fits[0]))
        with open(fits[0], "rb") as f:
            self.assertFalse(qext2_demo.is_demo_fit(f.read()))

    def test_zly_plik_to_nie_demo(self):
        self.assertFalse(qext2_demo.is_demo_fit(b"to nie jest FIT"))


class TestImportGarmin(unittest.TestCase):
    def setUp(self):
        import qbot_activity_ingest as ing
        self.ing = ing

    def test_jazda_demo_pominieta_bez_zapisu(self):
        conn = FakeConn()
        with mock.patch.object(self.ing, "download_fit", return_value=b"FIT"), \
                mock.patch.object(self.ing, "is_demo_fit", return_value=True), \
                mock.patch.object(self.ing, "store") as store, \
                mock.patch.object(self.ing, "parse_fit") as parse:
            r = self.ing.ingest_one(None, conn, {"activityId": 123, "activityName": "Jazda"}, with_report=True)
        self.assertEqual(r["skipped"], "qext2_demo")
        store.assert_not_called()
        parse.assert_not_called()
        sql, params = conn.log[0]
        self.assertIn("activity_fit_raw", sql)
        self.assertTrue(params[2].startswith("qext2_demo"))
        self.assertEqual(conn.commits, 1)

    def test_zwykla_jazda_bez_zmian(self):
        conn = FakeConn()
        with mock.patch.object(self.ing, "download_fit", return_value=b"FIT"), \
                mock.patch.object(self.ing, "is_demo_fit", return_value=False), \
                mock.patch.object(self.ing, "parse_fit", return_value=([], [], [], [])) as parse, \
                mock.patch.object(self.ing, "store", return_value={"records": 5}) as store:
            r = self.ing.ingest_one(None, conn, {"activityId": 7})
        parse.assert_called_once()
        store.assert_called_once()
        self.assertNotIn("skipped", r)
        self.assertEqual(conn.log, [])

    def test_already_liczy_pominieta_jazde_demo(self):
        conn = FakeConn()
        self.assertTrue(self.ing._already(conn, "123"))
        self.assertIn("qext2_demo", conn.log[0][0])
        self.assertIn("parse_error IS NULL", conn.log[0][0])


class TestFitIngest(unittest.TestCase):
    def test_plik_demo_pomijany(self):
        from fitmodel import fit_ingest
        with mock.patch.object(qext2_demo, "is_demo_fit", return_value=True), \
                mock.patch.object(fit_ingest, "parse_fit_to_seconds") as parse:
            r = fit_ingest.ingest_fit_file("/tmp/QX1.fit", None)
        parse.assert_not_called()
        self.assertEqual(r["status"], fit_ingest.STATUS_NO_RECORDS)
        self.assertTrue(r["error"].startswith("qext2_demo"))


if __name__ == "__main__":
    unittest.main()
