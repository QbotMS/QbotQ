#!/usr/bin/env python3
"""TASK 13 / P3 — testy czystego mapowania kaskady highway (bez sieci)."""
import unittest

from tools.rwgps import route_brief as rb


class TestSurfaceInference(unittest.TestCase):
    def _rows(self):
        # (frame_index, d0, d1, ele0, ele1, egain, grade, surface)
        return [
            (0, 0, 1000, 0, 0, 0, 0.0, "asfalt"),    # ma wlasna nawierzchnie
            (1, 1000, 2000, 0, 0, 0, 0.0, None),      # nieznana, srodek 1500
            (2, 2000, 3000, 0, 0, 0, 0.0, None),      # nieznana, srodek 2500
        ]

    def test_fills_only_unknown_from_highway_guess(self):
        sectors = [
            {"s_m": 1000.0, "e_m": 2000.0, "surface_guess": "asfalt (szac.)"},
            {"s_m": 2000.0, "e_m": 3000.0, "surface_guess": "gruntowa/szuter (szac.)"},
        ]
        out = rb._map_guess_to_frames(self._rows(), sectors)
        self.assertEqual(out.get(1), "asfalt (szac.)")
        self.assertEqual(out.get(2), "gruntowa/szuter (szac.)")
        self.assertNotIn(0, out)

    def test_no_guess_when_sector_has_none(self):
        sectors = [{"s_m": 1000.0, "e_m": 2000.0, "surface_guess": None}]
        self.assertEqual(rb._map_guess_to_frames(self._rows(), sectors), {})

    def test_infer_skips_network_when_all_known(self):
        rows = [(0, 0, 1000, 0, 0, 0, 0.0, "asfalt")]
        self.assertEqual(rb._infer_unknown_frame_surfaces(rows, route_id="x"), {})


if __name__ == "__main__":
    unittest.main()
