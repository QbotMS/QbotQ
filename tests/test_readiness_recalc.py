"""Straznik: wpis choroba/feel dodany WSTECZ (poza oknem 8 dni daily_job) musi
zmienic gotowosc tamtego dnia (readiness_effective). Test sprzata po sobie."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel.readiness import _expand_ranges, recalc_subjective_days  # noqa: E402


class ExpandRanges(unittest.TestCase):
    def test_single_and_range(self):
        t = date(2026, 9, 28)
        self.assertEqual(_expand_ranges([(date(2026, 5, 9), None)], t), [date(2026, 5, 9)])
        self.assertEqual(len(_expand_ranges([("2026-05-09", "2026-05-15")], t)), 7)

    def test_no_future_and_dedup(self):
        t = date(2026, 9, 28)
        r = _expand_ranges([(date(2026, 9, 27), date(2026, 10, 5)), (date(2026, 9, 27), None)], t)
        self.assertEqual(r, [date(2026, 9, 27), date(2026, 9, 28)])


class RetroEntryRecalc(unittest.TestCase):
    def test_retro_feel_changes_readiness(self):
        from fitmodel.api import _db_connect
        conn = _db_connect()
        day = date.today() - timedelta(days=30)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM qbot_v2.calendar_entry WHERE kind IN ('feel','illness') "
                    "AND day<=%s AND COALESCE(end_day, day)>=%s", (day, day))
        if cur.fetchone()[0]:
            self.skipTest("dzien testowy ma juz wpis subiektywny")
        recalc_subjective_days(conn, [(day, None)])  # swieza baza przed pomiarem
        cur.execute("SELECT readiness_effective FROM qbot_v2.fitmodel_daily WHERE day=%s", (day,))
        r = cur.fetchone()
        if not r or r[0] is None:
            self.skipTest("brak readiness dla dnia testowego")
        before = float(r[0])
        cur.execute("INSERT INTO qbot_v2.calendar_entry (day, kind, feel, title, note) "
                    "VALUES (%s,'feel',-2,'TEST','[test_readiness_recalc]') RETURNING id", (day,))
        eid = cur.fetchone()[0]
        conn.commit()
        try:
            recalc_subjective_days(conn, [(day, None)])
            cur.execute("SELECT readiness_effective FROM qbot_v2.fitmodel_daily WHERE day=%s", (day,))
            after = float(cur.fetchone()[0])
            self.assertAlmostEqual(after, before - 0.30, places=2)
        finally:
            cur.execute("DELETE FROM qbot_v2.calendar_entry WHERE id=%s", (eid,))
            conn.commit()
            recalc_subjective_days(conn, [(day, None)])
            cur.execute("SELECT readiness_effective FROM qbot_v2.fitmodel_daily WHERE day=%s", (day,))
            self.assertAlmostEqual(float(cur.fetchone()[0]), before, places=2)
            conn.close()


if __name__ == "__main__":
    unittest.main()
