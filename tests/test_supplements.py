"""qbot_supplements: wersje dawek, dni tygodnia, regularnosc (czyste funkcje, bez bazy)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_supplements as S  # noqa: E402


class Dawki(unittest.TestCase):
    def test_wersja_na_dzien(self):
        v = [{"from": "2026-10-01", "dose": 4000, "unit": "j.m."}, {"from": "2026-10-20", "dose": 2000, "unit": "j.m."}]
        self.assertEqual(S.dose_on(v, date(2026, 10, 19))["dose"], 4000)
        self.assertEqual(S.dose_on(v, date(2026, 10, 20))["dose"], 2000)
        self.assertIsNone(S.dose_on(v, date(2026, 9, 30)))

    def test_format(self):
        self.assertEqual(S.fmt_dose(1.5, "mg"), "1,5 mg")
        self.assertEqual(S.fmt_dose(4000, "j.m."), "4000 j.m.")
        self.assertEqual(S.fmt_dose(None, "mg"), "")

    def test_dni(self):
        self.assertTrue(S.is_scheduled(None, date(2026, 10, 13)))
        self.assertTrue(S.is_scheduled([1], date(2026, 10, 13)))     # wtorek
        self.assertFalse(S.is_scheduled([0, 2], date(2026, 10, 13)))


class Regularnosc(unittest.TestCase):
    def test_procent_i_niepotwierdzone(self):
        d1, d2, d3 = date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)
        sched = {d1: [1, 2], d2: [1, 2], d3: [1]}
        log = {(d1, 1): "taken", (d1, 2): "taken", (d2, 1): "skipped", (d2, 2): "taken"}
        r = S.regularity(sched, log)
        self.assertEqual(r["items"][1]["pct"], 33)
        self.assertEqual(r["items"][2]["pct"], 100)
        self.assertEqual(r["pct"], 60)
        self.assertEqual(r["unconfirmed_days"], ["2026-10-12"])


if __name__ == "__main__":
    unittest.main()
