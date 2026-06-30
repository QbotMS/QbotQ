#!/usr/bin/env python3
"""Offline test mapowania dataclasses silnika -> wiersze DB (build_rows). Bez DB/sieci."""
from __future__ import annotations
import unittest

from qbot3.routes.route_elevation_engine import (
    build_route_elevation_profile, detect_route_climb_events,
)
from qbot3.routes.route_elevation_store import build_rows


def build_points(total_m, step=50.0):
    pts, d = [], 0.0
    while d <= total_m + 1e-6:
        pts.append((round(d, 3), 50.0 + d / 1e5, 20.0))
        d += step
    return pts


def dem(profile):
    def fn(coords):
        return [profile(round((lat - 50.0) * 1e5, 1)) for lat, _lon in coords]
    return fn


def climb_800_6(d):
    if d < 200: return 100.0
    if d <= 1000: return 100.0 + 0.06 * (d - 200)
    return 148.0


class TestBuildRows(unittest.TestCase):
    def setUp(self):
        self.samples = build_route_elevation_profile(build_points(2000), elevation_fn=dem(climb_800_6))
        self.climbs = detect_route_climb_events(self.samples)
        self.sample_rows, self.event_rows = build_rows(self.samples, self.climbs, route_base_id=999, route_version_key="vtest")

    def test_counts_match(self):
        self.assertEqual(len(self.sample_rows), len(self.samples))
        self.assertEqual(len(self.event_rows), len(self.climbs))
        self.assertGreaterEqual(len(self.event_rows), 1)

    def test_sample_row_shape(self):
        r = self.sample_rows[0]
        for k in ("route_base_id", "route_version_key", "sample_index", "distance_m",
                  "lat", "lon", "elevation_m", "source", "smoothing_version", "elevation_meta_json"):
            self.assertIn(k, r)
        self.assertEqual(r["route_base_id"], 999)
        self.assertEqual(r["route_version_key"], "vtest")

    def test_event_row_and_segments_json(self):
        r = self.event_rows[0]
        for k in ("route_base_id", "route_version_key", "event_index", "start_m", "end_m",
                  "length_m", "elevation_gain_m", "avg_gradient_pct", "max_gradient_pct",
                  "severity", "segments_json", "source", "detection_version", "climb_meta_json"):
            self.assertIn(k, r)
        # segments_json to lista dictow z gradientem i kategoria
        self.assertIsInstance(r["segments_json"], list)
        self.assertGreaterEqual(len(r["segments_json"]), 1)
        seg = r["segments_json"][0]
        for k in ("seg_index", "start_m", "end_m", "length_m", "gradient_pct", "category"):
            self.assertIn(k, seg)


if __name__ == "__main__":
    unittest.main()
