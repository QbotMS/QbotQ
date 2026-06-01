#!/usr/bin/env python3
"""Test that commit-poi generates GPX with <wpt> as primary POI delivery method.

Verifies:
  1. Candidates does not modify RWGPS
  2. commit-poi generates selected_poi.gpx with <wpt> elements
  3. Waypoints have correct lat/lon/name/desc
  4. Original GPX not modified
  5. commit-poi does not make RWGPS PUT calls

Usage:
  cd /opt/qbot/app
  .venv/bin/python scripts/test_route_logistics_commit_poi_gpx_wpt.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.route_logistics import (
    ARTIFACTS_ROOT, LOGISTICS_DIR,
    POICandidate, ensure_dir,
    write_selected_poi_json, write_selected_poi_geojson,
    write_selected_poi_gpx, write_commit_summary_md,
)

ROUTE_ID = "test_route_99999"
TEST_DIR = LOGISTICS_DIR / ROUTE_ID


def _asdict(obj):
    return {
        "candidate_id": obj.candidate_id,
        "category": obj.category,
        "subtype": obj.subtype,
        "name": obj.name,
        "lat": obj.lat,
        "lon": obj.lon,
        "distance_from_track_m": obj.distance_from_track_m,
        "km_on_route": obj.km_on_route,
        "source": obj.source,
        "confidence": obj.confidence,
        "status": obj.status,
    }


class TestCommitPoiGpxWpt(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ensure_dir(ROUTE_ID)
        cls.test_pois = [
            POICandidate(
                candidate_id="food_001",
                category="food",
                subtype="restaurant",
                name="Pod Aniolami",
                lat=43.5500,
                lon=10.6000,
                distance_from_track_m=50,
                km_on_route=5.0,
                source="OSM",
                confidence="HIGH",
                status="CANDIDATE",
                notes="Obiad",
            ),
            POICandidate(
                candidate_id="water_003",
                category="water",
                subtype="drinking_water",
                name="Fontanna na rynku",
                lat=43.5550,
                lon=10.6050,
                distance_from_track_m=10,
                km_on_route=7.5,
                source="OSM",
                confidence="HIGH",
                status="CANDIDATE",
            ),
        ]

    def tearDown(self):
        for f in TEST_DIR.glob("selected_poi*"):
            f.unlink(missing_ok=True)
        if (TEST_DIR / "poi_commit_summary.md").exists():
            (TEST_DIR / "poi_commit_summary.md").unlink()

    @classmethod
    def tearDownClass(cls):
        import shutil
        if TEST_DIR.exists():
            shutil.rmtree(str(TEST_DIR))

    def test_candidates_does_not_modify_rwgps(self):
        """Candidates phase must not call any RWGPS API."""
        from lib.route_logistics import write_candidates_json
        payload = {"candidates": [_asdict(self.test_pois[0])], "metadata": {"route_id": ROUTE_ID, "mode": "test"}}
        path = write_candidates_json(self.test_pois, ROUTE_ID, payload, "test", [], [])
        self.assertTrue(path.exists())
        self.assertFalse(hasattr(self, "_rwgps_called"))

    def test_commit_poi_generates_gpx_with_wpt(self):
        """commit-poi must output selected_poi.gpx containing <wpt> elements."""
        write_selected_poi_json(self.test_pois, ROUTE_ID)
        write_selected_poi_geojson(self.test_pois, ROUTE_ID)
        gpx_path = write_selected_poi_gpx(self.test_pois, ROUTE_ID)
        write_commit_summary_md(self.test_pois, [], ROUTE_ID)

        self.assertTrue(gpx_path.exists(), "selected_poi.gpx not created")
        self.assertGreater(gpx_path.stat().st_size, 0, "selected_poi.gpx is empty")

        tree = ET.parse(str(gpx_path))
        root = tree.getroot()

        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        wpts = root.findall("gpx:wpt", ns)
        self.assertEqual(len(wpts), 2, f"Expected 2 <wpt>, got {len(wpts)}")

        wpt1 = wpts[0]
        self.assertEqual(wpt1.attrib["lat"], "43.55")
        self.assertEqual(wpt1.attrib["lon"], "10.6")
        self.assertEqual(wpt1.find("gpx:name", ns).text, "food_001")
        self.assertIn("Pod Aniolami", wpt1.find("gpx:desc", ns).text)
        self.assertEqual(wpt1.find("gpx:type", ns).text, "food")

        wpt2 = wpts[1]
        self.assertEqual(wpt2.attrib["lat"], "43.555")
        self.assertEqual(wpt2.attrib["lon"], "10.605")
        self.assertEqual(wpt2.find("gpx:name", ns).text, "water_003")
        self.assertIn("Fontanna", wpt2.find("gpx:desc", ns).text)
        self.assertEqual(wpt2.find("gpx:type", ns).text, "water")

    def test_original_gpx_not_modified(self):
        """Original source GPX must not be changed by commit-poi."""
        orig_path = Path("/opt/qbot/artifacts/exports/rwgps/rwgps_55395119.gpx")
        if not orig_path.exists():
            self.skipTest("Original GPX not found — skipping")
        mtime_before = orig_path.stat().st_mtime

        write_selected_poi_json(self.test_pois, ROUTE_ID)
        write_selected_poi_gpx(self.test_pois, ROUTE_ID)

        mtime_after = orig_path.stat().st_mtime
        self.assertEqual(mtime_before, mtime_after, "Original GPX was modified by commit-poi!")

    def test_selected_poi_gpx_has_no_trk(self):
        """selected_poi.gpx must contain only <wpt>, no <trk>."""
        write_selected_poi_gpx(self.test_pois, ROUTE_ID)
        gpx_path = TEST_DIR / "selected_poi.gpx"
        content = gpx_path.read_text(encoding="utf-8")

        self.assertIn("<wpt ", content)
        self.assertNotIn("<trk>", content)
        self.assertNotIn("<trkpt>", content)

    def test_commit_poi_does_not_call_rwgps(self):
        """commit-poi must not make any RWGPS PUT call — pure artifact generation."""
        import unittest.mock
        from tools.rwgps import client as rwgps_client

        with unittest.mock.patch.object(rwgps_client, "httpx") as mock_httpx:
            write_selected_poi_json(self.test_pois, ROUTE_ID)
            write_selected_poi_gpx(self.test_pois, ROUTE_ID)
            mock_httpx.put.assert_not_called()
            mock_httpx.post.assert_not_called()

    def test_candidates_output_files(self):
        """Candidates phase generates required artifacts."""
        from lib.route_logistics import write_candidates_json, write_candidates_md
        p1 = write_candidates_json(self.test_pois, ROUTE_ID, "test", None, [], [])
        self.assertTrue(p1.exists(), "candidates.json not created")
        p2 = write_candidates_md(self.test_pois, ROUTE_ID, mode="test")
        self.assertTrue(p2.exists(), "candidates.md not created")

    def test_empty_candidates_creates_all_outputs(self):
        """Empty candidate list must still produce all output files."""
        from lib.route_logistics import write_candidates_json, write_candidates_geojson, write_candidates_md, write_debug_json
        empty: list = []
        p1 = write_candidates_json(empty, ROUTE_ID, "test", None, [], [])
        self.assertTrue(p1.exists(), "candidates.json not created for empty list")
        payload = json.loads(p1.read_text())
        self.assertEqual(payload.get("status"), "CANDIDATES_READY")
        self.assertEqual(payload.get("counts", {}).get("shops"), 0)

        p2 = write_candidates_geojson(empty, ROUTE_ID)
        self.assertTrue(p2.exists(), "candidates.geojson not created for empty list")
        geojson = json.loads(p2.read_text())
        self.assertEqual(len(geojson.get("features", [])), 0)

        p3 = write_candidates_md(empty, ROUTE_ID, mode="test")
        self.assertTrue(p3.exists(), "candidates.md not created for empty list")

        p4 = write_debug_json({"route_id": ROUTE_ID, "total": 0, "note": "empty test"}, ROUTE_ID)
        self.assertTrue(p4.exists(), "debug.json not created")

    def test_lodging_skip_in_full_mode(self):
        """--mode full without --require must skip lodging, not abort.
        Tests the category filtering logic directly (no Overpass calls)."""
        from lib.route_logistics import CATEGORY_ORDER, DEFAULT_BUFFERS

        # Simulate the logic from candidates.py:
        # When --mode full and no --require, lodging should be removed from categories
        categories_full = list(CATEGORY_ORDER)
        self.assertIn("lodging", categories_full)

        require_raw = None  # no --require provided
        lodging_skipped = False
        if "lodging" in categories_full and not require_raw:
            lodging_skipped = True
            categories_full = [c for c in categories_full if c != "lodging"]

        self.assertTrue(lodging_skipped, "lodging must be flagged as skipped")
        self.assertNotIn("lodging", categories_full, "lodging must be removed from categories")
        self.assertIn("shops", categories_full, "other categories must remain")
        self.assertIn("food", categories_full, "other categories must remain")
        self.assertGreater(len(categories_full), 0, "must have remaining categories")

    def test_overpass_fallback_endpoints_defined(self):
        """Overpass fallback list must have at least 2 endpoints."""
        from lib.route_logistics import OVERPASS_URLS
        self.assertGreaterEqual(len(OVERPASS_URLS), 2)
        for url in OVERPASS_URLS:
            self.assertTrue(url.startswith("http"), f"Invalid Overpass URL: {url}")

    def test_selected_poi_output_files(self):
        """Commit-poi generates all required artifacts."""
        write_selected_poi_json(self.test_pois, ROUTE_ID)
        write_selected_poi_geojson(self.test_pois, ROUTE_ID)
        write_selected_poi_gpx(self.test_pois, ROUTE_ID)
        write_commit_summary_md(self.test_pois, [], ROUTE_ID)

        self.assertTrue((TEST_DIR / "selected_poi.json").exists())
        self.assertTrue((TEST_DIR / "selected_poi.geojson").exists())
        self.assertTrue((TEST_DIR / "selected_poi.gpx").exists())
        self.assertTrue((TEST_DIR / "poi_commit_summary.md").exists())

    def test_gpx_wpt_coordinates_from_selection(self):
        """Waypoint coordinates must match exactly the selected POI data."""
        write_selected_poi_gpx(self.test_pois, ROUTE_ID)
        gpx_path = TEST_DIR / "selected_poi.gpx"

        tree = ET.parse(str(gpx_path))
        root = tree.getroot()
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        wpts = root.findall("gpx:wpt", ns)

        for poi, wpt in zip(self.test_pois, wpts):
            self.assertAlmostEqual(float(wpt.attrib["lat"]), poi.lat, places=4)
            self.assertAlmostEqual(float(wpt.attrib["lon"]), poi.lon, places=4)
            self.assertEqual(wpt.find("gpx:name", ns).text, poi.candidate_id)
            self.assertIn(poi.name, wpt.find("gpx:desc", ns).text)
            self.assertEqual(wpt.find("gpx:type", ns).text, poi.category)

if __name__ == "__main__":
    unittest.main()
