"""Straznik korekty ciala (fitmodel/real_load_guard.py): tylko odczyt + deduplikacja, bez wysylki."""
import os
import sys
import unittest
import datetime as dt

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import real_load_guard as G  # noqa: E402


class Guard(unittest.TestCase):
    def test_check_readonly_and_codes(self):
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect()
        try:
            for k in range(0, 60, 7):
                for code, msg in G.check(c, dt.date.today() - dt.timedelta(days=k)):
                    self.assertIn(code, ("SILA", "DANE", "DOMINACJA", "ROZBIEZNOSC"))
                    self.assertTrue(msg)
        finally:
            c.close()

    def test_season_not_spammy(self):
        """Test wsteczny 2026: najwyzej kilka powiadomien w sezonie (z blokada powtorek)."""
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect()
        try:
            d, end, last, n = dt.date(2026, 3, 1), dt.date(2026, 9, 29), {}, 0
            while d <= end:
                for code, _ in G.check(c, d):
                    if code not in last or (d - last[code]).days >= G.REPEAT_DAYS:
                        last[code] = d; n += 1
                d += dt.timedelta(days=1)
        finally:
            c.close()
        self.assertLessEqual(n, 6)

    def test_run_without_send(self):
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect()
        try:
            sent = []
            r = G.run(c, dt.date(2026, 9, 29), send=lambda t: sent.append(t))
            self.assertIn("alerts", r)
            self.assertEqual(len(sent), 1 if r["sent"] else 0)
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
