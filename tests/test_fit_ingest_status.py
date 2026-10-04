"""fit_ingest: jawny status parsowania, pomijanie przetworzonych jazd, blokada.

Bez bazy: ingest_fit_file dla uszkodzonego pliku konczy przed DB;
logika pomijania i blokada testowane jako czyste funkcje.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import fit_ingest as fi  # noqa: E402

REAL_FIT = "/opt/qbot/artifacts/fit/24603122930.fit"
T = datetime(2026, 10, 1, tzinfo=timezone.utc)


class ParseTests(unittest.TestCase):
    def setUp(self):
        fd, self.bad = tempfile.mkstemp(suffix=".fit")
        os.write(fd, b"to nie jest plik FIT " * 10)
        os.close(fd)

    def tearDown(self):
        os.unlink(self.bad)

    def test_strict_raises(self):
        with self.assertRaises(Exception):
            fi.parse_fit_to_seconds(self.bad, strict=True)

    def test_non_strict_logs_and_returns_empty(self):
        with self.assertLogs("fitmodel.fit_ingest", level="ERROR"):
            self.assertEqual(fi.parse_fit_to_seconds(self.bad), [])

    def test_ingest_reports_parse_error_without_db(self):
        with self.assertLogs("fitmodel.fit_ingest", level="ERROR"):
            r = fi.ingest_fit_file(self.bad, db_conn=None)
        self.assertEqual(r["status"], fi.STATUS_PARSE_ERROR)
        self.assertTrue(r["error"])
        self.assertEqual(r["segments_found"], 0)

    @unittest.skipUnless(os.path.exists(REAL_FIT), "brak pliku FIT")
    def test_real_fit_regression(self):
        rows = fi.parse_fit_to_seconds(REAL_FIT, strict=True)
        self.assertGreater(len(rows), 1000)
        self.assertIsInstance(rows[0]["timestamp"], datetime)
        self.assertIn("power", rows[0])

    def test_ride_buckets_uses_shared_parser(self):
        from fitmodel import ride_buckets
        self.assertIs(ride_buckets.parse_fit_to_seconds, fi.parse_fit_to_seconds)


class SkipTests(unittest.TestCase):
    def test_ride_with_segments_skipped(self):
        self.assertTrue(fi.should_skip_ride(True, None, T))

    def test_new_ride_processed(self):
        self.assertFalse(fi.should_skip_ride(False, None, T))

    def test_ok_zero_segments_skipped(self):
        self.assertTrue(fi.should_skip_ride(False, ("ok", 1, T), T))

    def test_no_records_skipped(self):
        self.assertTrue(fi.should_skip_ride(False, ("no_records", 1, T), T))

    def test_changed_file_reprocessed(self):
        self.assertFalse(fi.should_skip_ride(False, ("ok", 1, T), T + timedelta(hours=1)))

    def test_parse_error_retried_until_limit(self):
        self.assertFalse(fi.should_skip_ride(False, ("parse_error", 2, T), T))
        self.assertTrue(fi.should_skip_ride(False, ("parse_error", fi.MAX_PARSE_ATTEMPTS, T), T))


class LockTests(unittest.TestCase):
    def setUp(self):
        self._orig = fi.LOCK_PATH
        fd, fi.LOCK_PATH = tempfile.mkstemp(suffix=".lock")
        os.close(fd)

    def tearDown(self):
        os.unlink(fi.LOCK_PATH)
        fi.LOCK_PATH = self._orig

    def test_second_run_blocked_then_free(self):
        first = fi._acquire_lock(0)
        self.assertIsNotNone(first)
        self.assertGreaterEqual(first, 0)
        self.assertIsNone(fi._acquire_lock(0))
        fi._release_lock(first)
        again = fi._acquire_lock(0)
        self.assertIsNotNone(again)
        fi._release_lock(again)


class HrBandTests(unittest.TestCase):
    """Okno stabilne: rowna moc 180 W, HR staly; dolny prog 0.60 HRmax (184 -> 110.4 bpm)."""

    def _win(self, hr):
        return [{"power": 180.0, "heart_rate": hr} for _ in range(60)]

    def test_hr_113_now_in_band(self):
        self.assertTrue(fi._stable_window_ok(self._win(113.0), 184.0))

    def test_hr_108_below_band(self):
        self.assertFalse(fi._stable_window_ok(self._win(108.0), 184.0))

    def test_hr_upper_band_unchanged(self):
        self.assertTrue(fi._stable_window_ok(self._win(156.0), 184.0))
        self.assertFalse(fi._stable_window_ok(self._win(158.0), 184.0))


if __name__ == "__main__":
    unittest.main()
