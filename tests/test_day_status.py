"""Status dnia (fitmodel/day_status.py): klasyfikacja + zywa baza."""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import day_status as DS  # noqa: E402


class Classify(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(DS.classify(True, False, False, 1.31), "przeciazenie")
        self.assertEqual(DS.classify(False, True, False, 1.31), "przeciazenie")
        self.assertEqual(DS.classify(False, False, True, 1.31), "przeciazenie")
        self.assertEqual(DS.classify(True, False, False, 1.0), "zmeczony")
        self.assertEqual(DS.classify(False, False, False, 1.4), "uwaga")
        self.assertEqual(DS.classify(False, False, True, 0.8), "uwaga")
        self.assertEqual(DS.classify(False, False, False, 1.0), "w_normie")
        self.assertEqual(DS.classify(False, False, False, None), "w_normie")


class Live(unittest.TestCase):
    def test_statuses_present_and_valid(self):
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect(); cur = c.cursor()
        cur.execute("SELECT day_status, count(*) FROM qbot_v2.fitmodel_daily WHERE day >= current_date - 60 GROUP BY 1")
        rows = dict(cur.fetchall()); c.close()
        self.assertTrue(rows)
        self.assertTrue(set(rows) <= {"przeciazenie", "zmeczony", "uwaga", "w_normie", None})


if __name__ == "__main__":
    unittest.main()
