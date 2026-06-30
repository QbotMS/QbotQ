#!/usr/bin/env python3
"""Testy offline silnika przewyzszen/podjazdow (2C). Bez sieci — syntetyczny DEM."""
from __future__ import annotations
import unittest
from dataclasses import asdict

from qbot3.routes.route_elevation_engine import (
    build_route_elevation_profile, detect_route_climb_events, summarize,
)


def build_points(total_m, step=50.0):
    pts, d = [], 0.0
    while d <= total_m + 1e-6:
        pts.append((round(d, 3), 50.0 + d / 1e5, 20.0))
        d += step
    if pts[-1][0] < total_m:
        pts.append((total_m, 50.0 + total_m / 1e5, 20.0))
    return pts


def dem(profile):
    def fn(coords):
        out = []
        for lat, _lon in coords:
            dd = round((lat - 50.0) * 1e5, 1)
            out.append(profile(dd))
        return out
    return fn


# --- profile syntetyczne ---
def flat(d):
    return 100.0

def climb_800_6(d):
    if d < 200: return 100.0
    if d <= 1000: return 100.0 + 0.06 * (d - 200)
    return 148.0

def short_200_8(d):
    # 200 m @8% — wyraznie ponizej progu 400 m -> odrzucony
    if d < 200: return 100.0
    if d <= 400: return 100.0 + 0.08 * (d - 200)
    return 116.0

def shallow_600_2(d):
    if d < 200: return 100.0
    if d <= 800: return 100.0 + 0.02 * (d - 200)
    return 112.0

def wall_climb(d):
    # 200..600 @3%, 600..800 @12% (sciana), 800..1200 @3%
    if d < 200: return 100.0
    if d <= 600: return 100.0 + 0.03 * (d - 200)
    if d <= 800: return 112.0 + 0.12 * (d - 600)
    if d <= 1200: return 136.0 + 0.03 * (d - 800)
    return 148.0

def saw(base, amp=2.0):
    def p(d):
        return base(d) + (amp if int(round(d / 50.0)) % 2 == 0 else -amp)
    return p

def real_climb_600_5(d):
    # 600 m @5% — wyraznie powyzej progu -> przezywa szum
    if d < 200: return 100.0
    if d <= 800: return 100.0 + 0.05 * (d - 200)
    return 130.0


class TestElevationEngine(unittest.TestCase):

    def _profile(self, profile, total):
        return build_route_elevation_profile(build_points(total), elevation_fn=dem(profile))

    def test_flat_no_climb(self):
        s = self._profile(flat, 2000)
        self.assertEqual(detect_route_climb_events(s), [])
        summ = summarize(s)
        self.assertLess(summ["ascent_smoothed_m"], 2.0)
        self.assertLess(summ["max_grade_pct"], 1.0)

    def test_single_climb(self):
        s = self._profile(climb_800_6, 2000)
        ev = detect_route_climb_events(s)
        self.assertEqual(len(ev), 1)
        c = ev[0]
        self.assertTrue(700 <= c.length_m <= 900, c.length_m)
        self.assertTrue(5.0 <= c.avg_gradient_pct <= 7.0, c.avg_gradient_pct)
        self.assertTrue(c.segments, "brak segmentow 100 m")
        self.assertIn(c.severity, ("sciana", "dlugi", "umiarkowany"))

    def test_too_short_not_detected(self):
        s = self._profile(short_200_8, 1000)
        self.assertEqual(detect_route_climb_events(s), [])

    def test_too_shallow_not_detected(self):
        s = self._profile(shallow_600_2, 1200)
        self.assertEqual(detect_route_climb_events(s), [])

    def test_wall_visible_in_segments(self):
        s = self._profile(wall_climb, 1400)
        ev = detect_route_climb_events(s)
        self.assertEqual(len(ev), 1)
        c = ev[0]
        self.assertTrue(4.0 <= c.avg_gradient_pct <= 6.0, c.avg_gradient_pct)
        # sciana musi byc widoczna w max i w ktoryms segmencie
        self.assertGreaterEqual(c.max_gradient_pct, 9.0)
        self.assertTrue(any(seg.category in ("stromy", "bardzo_stromy") for seg in c.segments))

    def test_noise_killed_but_wall_kept(self):
        # plaski + szum -> brak fantomowych podjazdow
        s_flat = self._profile(saw(flat), 1000)
        self.assertEqual(detect_route_climb_events(s_flat), [])
        # realny 600 m @5% + ten sam szum -> wykryty
        s_real = self._profile(saw(real_climb_600_5), 1200)
        ev = detect_route_climb_events(s_real)
        self.assertEqual(len(ev), 1, [(e.start_m, e.end_m, e.avg_gradient_pct) for e in ev])

    def test_deterministic(self):
        s1 = self._profile(climb_800_6, 2000)
        s2 = self._profile(climb_800_6, 2000)
        self.assertEqual([asdict(e) for e in detect_route_climb_events(s1)],
                         [asdict(e) for e in detect_route_climb_events(s2)])

    def test_contract_fields(self):
        s = self._profile(climb_800_6, 2000)
        smp = asdict(s[0])
        for k in ("sample_index", "distance_m", "lat", "lon", "elevation_m", "source", "smoothing_version"):
            self.assertIn(k, smp)
        ev = detect_route_climb_events(s)[0]
        dd = asdict(ev)
        for k in ("event_index", "start_m", "end_m", "length_m", "elevation_gain_m",
                  "avg_gradient_pct", "max_gradient_pct", "severity", "source",
                  "detection_version", "segments"):
            self.assertIn(k, dd)
        for k in ("seg_index", "start_m", "end_m", "length_m", "gradient_pct", "category"):
            self.assertIn(k, dd["segments"][0])


if __name__ == "__main__":
    unittest.main()
