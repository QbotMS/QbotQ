#!/usr/bin/env python3
"""TASK 14 / P3 — testy map-match PUNKT PO PUNKCIE (Overpass per punkt)."""
import unittest
from unittest import mock

from tools.rwgps import surface_landcover as sl


def _payload(*tag_dicts):
    return {"elements": [{"type": "way", "tags": dict(t)} for t in tag_dicts]}


class TestHighwayPointInference(unittest.TestCase):
    def setUp(self):
        sl._HIGHWAY_POINT_CACHE.clear()

    def test_point_query_surface_tag(self):
        with mock.patch.object(sl, "_overpass", return_value=_payload({"surface": "asphalt", "highway": "residential"})) as ov, \
             mock.patch.object(sl.time, "sleep"):
            self.assertEqual(sl._fetch_highway_for_point(50.1, 19.1), "asfalt")
            ov.assert_called_once()

    def test_point_query_highway_fallback(self):
        with mock.patch.object(sl, "_overpass", return_value=_payload({"highway": "track"})), \
             mock.patch.object(sl.time, "sleep"):
            self.assertEqual(sl._fetch_highway_for_point(50.2, 19.2), "gruntowa/szuter")

    def test_point_query_empty(self):
        with mock.patch.object(sl, "_overpass", return_value={"elements": []}), \
             mock.patch.object(sl.time, "sleep"):
            self.assertIsNone(sl._fetch_highway_for_point(50.3, 19.3))

    def test_cache_dedup(self):
        # dwa punkty ~11 m (round(.,4) -> ten sam klucz) => 1 realny request do Overpass
        with mock.patch.object(sl, "_overpass", return_value=_payload({"surface": "gravel"})) as ov, \
             mock.patch.object(sl.time, "sleep"):
            a = sl._fetch_highway_for_point(50.00001, 19.00001)
            b = sl._fetch_highway_for_point(50.00002, 19.00002)
            self.assertEqual(a, b)
            ov.assert_called_once()

    def test_throttle(self):
        with mock.patch.object(sl, "_overpass", return_value=_payload({"highway": "track"})), \
             mock.patch.object(sl.time, "sleep") as slp:
            for i in range(3):
                sl._fetch_highway_for_point(50.0 + i * 0.01, 19.0 + i * 0.01)
            self.assertEqual(slp.call_count, 3)


class TestInferSurfaceTask20(unittest.TestCase):
    """TASK 20 — testy _infer_surface: tabela + scalanie confidence."""

    def setUp(self):
        from tools.rwgps.surface_landcover import _infer_surface, _CONF_RANK
        self._infer = _infer_surface
        self._rank = _CONF_RANK

    def test_real_surface_tag_wins(self):
        label, conf = self._infer({"surface": "asphalt", "highway": "track"})
        self.assertEqual(label, "asfalt")
        self.assertEqual(conf, "wysoka")

    def test_residential_no_surface(self):
        label, conf = self._infer({"highway": "residential"})
        self.assertEqual(label, "asfalt")
        self.assertEqual(conf, "srednia")

    def test_track_grade3(self):
        label, conf = self._infer({"highway": "track", "tracktype": "grade3"})
        self.assertEqual(label, "zwir/luzna")
        self.assertEqual(conf, "niska")

    def test_track_no_tracktype(self):
        label, conf = self._infer({"highway": "track"})
        self.assertEqual(label, "nieutwardzona nieokreslona")
        self.assertEqual(conf, "niska")

    def test_path(self):
        label, conf = self._infer({"highway": "path"})
        self.assertEqual(label, "sciezka/nieutwardzona")
        self.assertEqual(conf, "niska")

    def test_no_highway(self):
        label, conf = self._infer({})
        self.assertEqual(label, "nieznana")
        self.assertEqual(conf, "nieznana")

    def test_confidence_merge_min(self):
        """Scalanie serii: realny asfalt (wysoka) + wywnioskowany asfalt (srednia) -> srednia."""
        sample_conf = ["wysoka", "srednia"]
        _seg_conf = min(sample_conf, key=lambda c: self._rank.get(c, 0))
        self.assertEqual(_seg_conf, "srednia")

    def test_confidence_rank_order(self):
        """Kolejność: wysoka > srednia > niska > nieznana."""
        r = self._rank
        self.assertGreater(r["wysoka"], r["srednia"])
        self.assertGreater(r["srednia"], r["niska"])
        self.assertGreater(r["niska"], r["nieznana"])


if __name__ == "__main__":
    unittest.main()
