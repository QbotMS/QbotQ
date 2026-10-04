"""fitmodel.threshold_sync: histereza, zapis z odczytem kontrolnym, bledy nie sa polykane (bez sieci i bazy)."""
from __future__ import annotations

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import threshold_sync as ts  # noqa: E402

DAY = dt.date(2026, 10, 4)


class _Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, ftp, store=True, put_code=200):
        self.ftp, self.store, self.put_code, self.puts = ftp, store, put_code, []

    def get(self, url):
        return _Resp([{"id": 1, "types": ["Run"], "ftp": None},
                      {"id": 32928, "types": ["Ride", "GravelRide"], "ftp": self.ftp}])

    def put(self, url, json):
        self.puts.append((url, json))
        if self.store and self.put_code < 400:
            self.ftp = json["ftp"]
        return _Resp({}, self.put_code)


class HysteresisTests(unittest.TestCase):
    def test_small_change_skipped(self):
        self.assertFalse(ts.needs_update(247, 251))   # 1.6%

    def test_big_change(self):
        self.assertTrue(ts.needs_update(247, 256))    # 3.6%
        self.assertTrue(ts.needs_update(256, 247))

    def test_missing_old(self):
        self.assertTrue(ts.needs_update(None, 250))


class RunTests(unittest.TestCase):
    def test_writes_ftp_only_without_apply(self):
        c, sent = FakeClient(236), []
        r = ts.run(None, send=sent.append, client=c, tp_day=DAY, tp_w=256.1)
        self.assertEqual(r["threshold_sync"], "zapisano")
        self.assertEqual(c.puts, [(f"{ts.API}/sport-settings/32928", {"ftp": 256})])
        self.assertNotIn("apply", c.puts[0][0])
        self.assertIn("236 -> 256", sent[0])

    def test_no_change_within_hysteresis(self):
        c = FakeClient(252)
        r = ts.run(None, client=c, tp_day=DAY, tp_w=256.1)
        self.assertEqual(r["threshold_sync"], "bez zmian")
        self.assertEqual(c.puts, [])

    def test_dry_run_does_not_write(self):
        c = FakeClient(236)
        r = ts.run(None, client=c, dry_run=True, tp_day=DAY, tp_w=256.1)
        self.assertIn("dry-run", r["threshold_sync"])
        self.assertEqual(c.puts, [])

    def test_verification_mismatch_raises_and_alerts(self):
        c, sent = FakeClient(236, store=False), []
        with self.assertRaises(RuntimeError):
            ts.run(None, send=sent.append, client=c, tp_day=DAY, tp_w=256.1)
        self.assertIn("NIEUDANA", sent[0])

    def test_http_error_raises(self):
        c, sent = FakeClient(236, put_code=403), []
        with self.assertRaises(RuntimeError):
            ts.run(None, send=sent.append, client=c, tp_day=DAY, tp_w=256.1)
        self.assertIn("HTTP 403", sent[0])


if __name__ == "__main__":
    unittest.main()
