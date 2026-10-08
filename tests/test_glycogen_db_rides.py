"""Glikogen: jazdy z bazy (activity_record) zamiast czytania wszystkich plikow FIT (2026-10-08)."""
import sys, unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "/opt/qbot/app")
from fitmodel import glycogen as g

T0 = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class _Cur:
    def __init__(self, conn): self.c, self.res = conn, []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None):
        if "training_sessions" in sql:
            self.res = self.c.sessions
        else:
            self.res = self.c.records.get(params[0], [])
    def fetchall(self): return self.res


class FakeConn:
    def __init__(self, sessions, records): self.sessions, self.records = sessions, records
    def cursor(self): return _Cur(self)


def rec(n, p=200):
    return [(T0 + timedelta(seconds=i), p) for i in range(n)]


class T(unittest.TestCase):
    def test_grouped_by_local_day(self):
        c = FakeConn([("a", date(2026, 10, 8), T0, 10), ("b", date(2026, 10, 6), T0 - timedelta(days=2), 5)],
                     {"a": rec(10), "b": rec(5)})
        out = g._ride_rows_by_day_db(c, date(2026, 10, 1), date(2026, 10, 8))
        self.assertEqual(sorted(out), [date(2026, 10, 6), date(2026, 10, 8)])
        self.assertEqual(len(out[date(2026, 10, 8)][0]), 10)

    def test_same_start_counted_once_longest_wins(self):
        c = FakeConn([("short", date(2026, 10, 8), T0, 5), ("long", date(2026, 10, 8), T0, 9)],
                     {"short": rec(5), "long": rec(9)})
        out = g._ride_rows_by_day_db(c, date(2026, 10, 8), date(2026, 10, 8))
        self.assertEqual(len(out[date(2026, 10, 8)]), 1)
        self.assertEqual(len(out[date(2026, 10, 8)][0]), 9)

    def test_two_rides_same_day(self):
        c = FakeConn([("x", date(2026, 10, 8), T0, 3), ("y", date(2026, 10, 8), T0 + timedelta(hours=5), 4)],
                     {"x": rec(3), "y": rec(4)})
        out = g._ride_rows_by_day_db(c, date(2026, 10, 8), date(2026, 10, 8))
        self.assertEqual(len(out[date(2026, 10, 8)]), 2)

    def test_no_samples_skipped(self):
        c = FakeConn([("yoga", date(2026, 10, 7), T0, 0)], {})
        self.assertEqual(g._ride_rows_by_day_db(c, date(2026, 10, 7), date(2026, 10, 7)), {})


if __name__ == "__main__":
    unittest.main()
