"""Ponawianie nieudanych kawalkow Overpass (incydent 2026-10-05, komoot-3331694546)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import tools.rwgps.route_surface_engine as eng  # noqa: E402
from qbot3.routes import route_surface_store as store  # noqa: E402


def _samples(n: int):
    return [eng.Sample(index=i, lat=50.0 + i * 0.0004, lon=19.5, ele=None, dist_m=i * 50.0) for i in range(n)]


def _way(wid: int):
    return {"type": "way", "id": wid, "tags": {"highway": "track"},
            "geometry": [{"lat": 50.0, "lon": 19.5}, {"lat": 50.01, "lon": 19.5}]}


class OverpassChunkRetryTest(unittest.TestCase):
    def setUp(self):
        self.p1 = mock.patch.object(eng, "OVERPASS_CHUNK_RETRY_PAUSE_SEC", 0)
        self.p1.start()

    def tearDown(self):
        self.p1.stop()

    def test_failed_chunk_recovered_on_retry(self):
        calls = {"n": 0}

        def fake(query, metrics, timeout=None):
            calls["n"] += 1
            if calls["n"] == 2:  # drugi kawalek pada w pierwszym przebiegu
                raise RuntimeError("Overpass unavailable: timeout")
            return {"elements": [_way(calls["n"])]}, "x"

        warnings, metrics = [], eng._new_overpass_metrics()
        with mock.patch.object(eng, "_overpass", side_effect=fake):
            ways = eng._fetch_highways_along_track(_samples(440), 80, warnings, metrics)
        self.assertEqual(metrics["chunks_failed"], 0)
        self.assertEqual(metrics["chunks_recovered"], 1)
        self.assertNotIn(eng.OVERPASS_INCOMPLETE_WARNING, warnings)
        self.assertGreaterEqual(len(ways), 3)  # 1 kawalek ok + 2 polowki z ponowienia

    def test_permanent_failure_marked_incomplete(self):
        def fake(query, metrics, timeout=None):
            raise RuntimeError("Overpass unavailable: timeout")

        warnings, metrics = [], eng._new_overpass_metrics()
        with mock.patch.object(eng, "_overpass", side_effect=fake):
            eng._fetch_highways_along_track(_samples(220), 80, warnings, metrics)
        self.assertEqual(metrics["chunks_failed"], 1)
        self.assertIn(eng.OVERPASS_INCOMPLETE_WARNING, warnings)
        self.assertTrue(any("km 0.0-" in w for w in warnings))

    def test_reason_message_overpass(self):
        conn = mock.Mock()
        conn.execute.return_value.fetchone.return_value = {
            "coverage_pct": 67.4, "warnings": ["Overpass highway chunk 12 failed-open: timeout"]}
        msg = store._low_quality_reason(conn, {"route_id": "komoot-1", "route_artifact_id": 1})
        self.assertIn("Overpass", msg)
        self.assertIn("67%", msg)

    def test_reason_message_low_coverage(self):
        conn = mock.Mock()
        conn.execute.return_value.fetchone.return_value = {"coverage_pct": 70.0, "warnings": []}
        msg = store._low_quality_reason(conn, {"route_id": "komoot-1", "route_artifact_id": 1})
        self.assertIn("tylko w 70%", msg)


if __name__ == "__main__":
    unittest.main()
