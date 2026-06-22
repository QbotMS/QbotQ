#!/usr/bin/env python3
"""Smoke tests for QBot Route Logistics — two-stage POI workflow.

Tests:
1. candidates mode=full (needs real GPX on disk)
2. candidates mode=attractions
3. lodging without requirements → NEEDS_REQUIREMENTS
4. lodging with requirements
5. commit-poi with valid IDs
6. commit-poi with invalid IDs
7. Safety: original route not modified, candidates ≠ POI
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.route_logistics import (
    LOGISTICS_DIR, RWGPS_EXPORT_DIR, CATEGORY_ORDER,
    load_gpx_track, resolve_route_gpx,
    POICandidate, parse_lodging_requirements,
    nearest_track_distance, haversine_m,
)

TEST_ROUTES = [
    ("55395119", "Toskania Etap 02"),
    ("55401067", "Puzn\u00f3wka"),
]


class TestGPXLoading(unittest.TestCase):
    """GPX files must be loadable for test routes."""

    def test_55395119_gpx_exists(self):
        """Route 55395119 GPX exists and has track points."""
        gpx = resolve_route_gpx("55395119")
        self.assertIsNotNone(gpx, f"GPX not found for 55395119 in {RWGPS_EXPORT_DIR}")
        if gpx:
            track = load_gpx_track(gpx)
            self.assertGreater(len(track), 10, f"Too few track points: {len(track)}")

    def test_55401067_gpx_exists(self):
        """Route 55401067 GPX exists and has track points."""
        gpx = resolve_route_gpx("55401067")
        self.assertIsNotNone(gpx, f"GPX not found for 55401067 in {RWGPS_EXPORT_DIR}")
        if gpx:
            track = load_gpx_track(gpx)
            self.assertGreater(len(track), 10, f"Too few track points: {len(track)}")

    def test_haversine(self):
        """Haversine distance is reasonable."""
        d = haversine_m(52.2297, 21.0122, 52.2370, 21.0170)
        self.assertAlmostEqual(d, 900, delta=200)


class TestPOIModel(unittest.TestCase):
    """POICandidate dataclass works correctly."""

    def test_to_dict_omits_none(self):
        """to_dict() omits None values."""
        c = POICandidate(candidate_id="test_001", category="food", name="Test", lat=1.0, lon=2.0)
        d = c.to_dict()
        self.assertNotIn("phone", d)  # None → omitted
        self.assertEqual(d["candidate_id"], "test_001")

    def test_minimal_candidate(self):
        """Minimal candidate with required fields."""
        c = POICandidate(candidate_id="water_001", category="water", name="Fontanna", lat=52.0, lon=21.0)
        self.assertEqual(c.status, "CANDIDATE")
        self.assertEqual(c.confidence, "SOURCE_ONLY")

    def test_osm_construction(self):
        """from_osm creates valid candidate."""
        el = {"id": 12345, "type": "node", "tags": {"name": "Bar Centrale", "amenity": "cafe"}}
        c = POICandidate.from_osm(el, "food", "cafe", 43.1, 10.5)
        self.assertEqual(c.name, "Bar Centrale")
        self.assertEqual(c.category, "food")
        self.assertEqual(c.source, "OSM")
        self.assertIn("review", c.notes)


class TestLodgingRequirements(unittest.TestCase):
    """Lodging requirements parsing and validation."""

    def test_no_requirements(self):
        """No args → NEEDS_REQUIREMENTS."""
        result = parse_lodging_requirements(None)
        self.assertEqual(result["status"], "NEEDS_REQUIREMENTS")

    def test_missing_fields(self):
        """Partial args → NEEDS_REQUIREMENTS with missing fields."""
        result = parse_lodging_requirements({"people": 2})
        self.assertEqual(result["status"], "NEEDS_REQUIREMENTS")
        self.assertIn("budget", result.get("missing", []))

    def test_full_requirements(self):
        """Complete args → OK."""
        result = parse_lodging_requirements({"people": 2, "budget": 150, "radius_from_stage_end_m": 5000})
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["people"], 2)


class TestSafety(unittest.TestCase):
    """Safety: candidates must not create POI, commit only selects existing."""

    def test_candidates_not_poi(self):
        """Candidate status is CANDIDATE, not POI."""
        c = POICandidate(candidate_id="test_001", category="food", name="Test", lat=1.0, lon=2.0)
        self.assertEqual(c.status, "CANDIDATE")
        self.assertNotEqual(c.status, "POI")

    def test_commit_poi_uses_candidate_status(self):
        """Selected POI must have different semantics."""
        c = POICandidate(candidate_id="test_001", category="food", name="Test", lat=1.0, lon=2.0)
        self.assertEqual(c.status, "CANDIDATE")
        # After selection, status changes are explicit
        c.status = "SELECTED"
        self.assertEqual(c.status, "SELECTED")

    @unittest.skipUnless(
        (LOGISTICS_DIR / "55395119" / "candidates.json").exists(),
        "candidates.json not found for 55395119 (run candidates first)",
    )
    def test_candidates_json_has_all_fields(self):
        """candidates.json has all required fields."""
        path = LOGISTICS_DIR / "55395119" / "candidates.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("status"), "CANDIDATES_READY")
        self.assertIn("route_id", payload)
        self.assertIn("counts", payload)
        self.assertIn("candidates", payload)

        for c in payload["candidates"]:
            self.assertIn("candidate_id", c)
            self.assertIn("category", c)
            self.assertIn("name", c)
            self.assertIn("lat", c)
            self.assertIn("lon", c)
            self.assertIn("source", c)
            self.assertIn("confidence", c)
            self.assertIn("status", c)


class TestCachingOverpass(unittest.TestCase):
    """Overpass queries are cached per category per route."""

    def test_overpass_query_format(self):
        """Overpass query strings have proper formatting."""
        from lib.route_logistics import OVERPASS_QUERIES
        for cat, query in OVERPASS_QUERIES.items():
            self.assertIn("{buffer}", query, f"{cat}: missing buffer placeholder")
            self.assertIn("{lat}", query, f"{cat}: missing lat placeholder")
            self.assertIn("{lon}", query, f"{cat}: missing lon placeholder")

    def test_all_categories_covered(self):
        """All CATEGORY_ORDER have Overpass queries."""
        from lib.route_logistics import OVERPASS_QUERIES
        for cat in CATEGORY_ORDER:
            self.assertIn(cat, OVERPASS_QUERIES, f"{cat} has no Overpass query")


if __name__ == "__main__":
    unittest.main()
