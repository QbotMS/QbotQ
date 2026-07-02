"""Testy kanonicznego czytnika segmentow 50 m — czysta logika (bez DB)."""
import unittest

from qbot3.routes.route_segments_50m import (build_surface_ranges, project_surface,
                                             surface_class, _midpoint)


class TestSurfaceClass(unittest.TestCase):
    def test_paved(self):
        self.assertEqual(surface_class("asphalt"), "paved")
        self.assertEqual(surface_class("concrete"), "paved")

    def test_unpaved(self):
        self.assertEqual(surface_class("gravel"), "unpaved")
        self.assertEqual(surface_class("ground"), "unpaved")
        self.assertEqual(surface_class("mixed"), "unpaved")

    def test_unknown(self):
        self.assertIsNone(surface_class(None))
        self.assertIsNone(surface_class(""))
        self.assertIsNone(surface_class("cos_dziwnego"))


class TestSurfaceRanges(unittest.TestCase):
    def _rows(self):
        return [
            {"surface": "asphalt", "surface_meta_json": {"km_from": 0.0, "km_to": 0.55}},
            {"surface": "mixed", "surface_meta_json": {"km_from": 0.55, "km_to": 1.15}},
            {"surface": "ground", "surface_meta_json": {"km_from": 1.15, "km_to": 4.35}},
        ]

    def test_build_sorted(self):
        r = build_surface_ranges(self._rows())
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0], (0.0, 0.55, "asphalt"))

    def test_build_skips_missing_km(self):
        rows = [{"surface": "asphalt", "surface_meta_json": {}}]
        self.assertEqual(build_surface_ranges(rows), [])

    def test_build_parses_json_string(self):
        rows = [{"surface": "gravel", "surface_meta_json": '{"km_from": 2.0, "km_to": 3.0}'}]
        self.assertEqual(build_surface_ranges(rows), [(2.0, 3.0, "gravel")])

    def test_project_inside(self):
        r = build_surface_ranges(self._rows())
        self.assertEqual(project_surface(0.30, r), "asphalt")
        self.assertEqual(project_surface(0.90, r), "mixed")
        self.assertEqual(project_surface(2.00, r), "ground")

    def test_project_boundary_is_left_inclusive(self):
        r = build_surface_ranges(self._rows())
        self.assertEqual(project_surface(0.55, r), "mixed")

    def test_project_past_end_uses_last(self):
        r = build_surface_ranges(self._rows())
        self.assertEqual(project_surface(9.99, r), "ground")

    def test_project_empty(self):
        self.assertEqual(project_surface(1.0, []), "unknown")


class TestMidpoint(unittest.TestCase):
    def test_linestring(self):
        geo = {"type": "LineString", "coordinates": [[21.0, 52.0, 80.0],
                                                     [21.1, 52.1, 81.0],
                                                     [21.2, 52.2, 82.0]]}
        lat, lon = _midpoint(geo)
        self.assertAlmostEqual(lat, 52.1)
        self.assertAlmostEqual(lon, 21.1)

    def test_json_string(self):
        lat, lon = _midpoint('{"type":"LineString","coordinates":[[21.0,52.0],[21.5,52.5]]}')
        self.assertIsNotNone(lat)

    def test_empty(self):
        self.assertEqual(_midpoint({}), (None, None))


if __name__ == "__main__":
    unittest.main()
