"""Ponawianie nieudanych kawalkow Overpass (incydent 2026-10-05, komoot-3331694546)
+ lokalne zrodlo drog OSM (tools/rwgps/osm_local.py)."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import tools.rwgps.route_surface_engine as eng  # noqa: E402
from tools.rwgps import osm_local  # noqa: E402
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
        self.p2 = mock.patch.dict(os.environ, {"QBOT_SURFACE_LOCAL_OSM": "0"})
        self.p2.start()

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()

    def test_failed_chunk_recovered_on_retry(self):
        calls = {"n": 0}

        def fake(query, metrics, timeout=None):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("Overpass unavailable: timeout")
            return {"elements": [_way(calls["n"])]}, "x"

        warnings, metrics = [], eng._new_overpass_metrics()
        with mock.patch.object(eng, "_overpass", side_effect=fake):
            ways = eng._fetch_highways_along_track(_samples(440), 80, warnings, metrics)
        self.assertEqual(metrics["chunks_failed"], 0)
        self.assertEqual(metrics["chunks_recovered"], 1)
        self.assertNotIn(eng.OVERPASS_INCOMPLETE_WARNING, warnings)
        self.assertGreaterEqual(len(ways), 3)

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


class LocalOsmTest(unittest.TestCase):
    """Sztuczna baza + kwadratowy obszar 49-51 N / 19-21 E."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "poland.poly").write_text(
            "test\n1\n 19.0 49.0\n 21.0 49.0\n 21.0 51.0\n 19.0 51.0\nEND\nEND\n", encoding="utf-8")
        con = sqlite3.connect(d / "roads.sqlite")
        con.executescript("""
            CREATE TABLE ways(id INTEGER PRIMARY KEY, tags_json TEXT, geom_json TEXT);
            CREATE VIRTUAL TABLE ways_rtree USING rtree(id, min_lat, max_lat, min_lon, max_lon);
            CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        """)
        con.execute("INSERT INTO ways VALUES (7, '{\"highway\":\"track\",\"tracktype\":\"grade2\"}', '[[50.0,20.0],[50.01,20.0]]')")
        con.execute("INSERT INTO ways_rtree VALUES (7, 50.0, 50.01, 20.0, 20.0)")
        con.commit()
        con.close()
        self.patches = [
            mock.patch.object(osm_local, "DB", d / "roads.sqlite"),
            mock.patch.object(osm_local, "POLY", d / "poland.poly"),
            mock.patch.object(osm_local, "_rings", None),
            mock.patch.dict(os.environ, {"QBOT_SURFACE_LOCAL_OSM": "1"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_coverage(self):
        self.assertTrue(osm_local.covers_bbox(49.9, 19.9, 50.1, 20.1))
        self.assertFalse(osm_local.covers_bbox(50.9, 20.9, 51.1, 21.1))  # wystaje poza obszar

    def test_query_overpass_shape(self):
        p = osm_local.query_ways(49.99, 19.99, 50.02, 20.01)
        self.assertEqual(len(p["elements"]), 1)
        el = p["elements"][0]
        self.assertEqual(el["tags"]["tracktype"], "grade2")
        self.assertEqual(el["geometry"][0], {"lat": 50.0, "lon": 20.0})

    def test_engine_uses_local_not_overpass(self):
        samples = [eng.Sample(index=i, lat=50.0 + i * 0.00005, lon=20.0, ele=None, dist_m=i * 5.0) for i in range(50)]
        warnings, metrics = [], eng._new_overpass_metrics()
        with mock.patch.object(eng, "_overpass", side_effect=AssertionError("Overpass nie powinien byc wolany")):
            ways = eng._fetch_highways_along_track(samples, 80, warnings, metrics)
        self.assertEqual(metrics.get("local_osm_chunks"), 1)
        self.assertEqual(len(ways), 1)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
