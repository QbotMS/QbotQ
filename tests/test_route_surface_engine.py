"""Testy POPRAWNOSCI klasyfikacji nawierzchni (route_surface_engine).

Powod (audyt 2026-07-02, docs/AUDYT_NAWIERZCHNIA.md, ustalenie 6): rdzen silnika
NIE mial ani jednego testu poprawnosci etykiet — tylko testy wykonania/ksztaltu.
Te testy pilnuja regul: tag wygrywa, tracktype grade1-5, wnioskowanie z highway,
kanonizacja surowego tagu. Sluza tez jako dowod regresji przy usuwaniu martwego
kodu landcoveru (decyzje 1-2).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.rwgps.route_surface_engine import _canonical_surface, _infer_from_tags


class TestCanonicalSurface(unittest.TestCase):
    def test_direct_and_aliases(self):
        self.assertEqual(_canonical_surface("gravel"), "gravel")
        self.assertEqual(_canonical_surface("asphalt"), "asphalt")
        self.assertEqual(_canonical_surface("paved"), "asphalt")
        self.assertEqual(_canonical_surface("chipseal"), "asphalt")
        self.assertEqual(_canonical_surface("fine_gravel"), "fine_gravel")
        self.assertEqual(_canonical_surface("compacted"), "compacted")
        self.assertEqual(_canonical_surface("sett"), "cobblestone")
        self.assertEqual(_canonical_surface("cobblestone"), "cobblestone")
        self.assertEqual(_canonical_surface("earth"), "dirt")
        self.assertEqual(_canonical_surface("ground"), "ground")
        self.assertEqual(_canonical_surface("grass"), "grass")

    def test_unpaved_is_mixed_not_truth(self):
        # 'unpaved' to gruby kubelek — swiadomie mapowany na 'mixed', nie na twarda etykiete
        self.assertEqual(_canonical_surface("unpaved"), "mixed")

    def test_empty_and_none(self):
        self.assertIsNone(_canonical_surface(""))
        self.assertIsNone(_canonical_surface(None))

    def test_fuzzy_substrings(self):
        self.assertEqual(_canonical_surface("asphalt;paved"), "asphalt")
        self.assertEqual(_canonical_surface("fine_gravel;dirt"), "fine_gravel")
        # 'sand' sprawdzane przed 'dirt' w kolejnosci substringow
        self.assertEqual(_canonical_surface("dirt/sand"), "sand")


class TestInferFromTags(unittest.TestCase):
    def _s(self, tags):
        return _infer_from_tags(tags)

    def test_tag_wins_over_everything(self):
        surface, conf, _expl, csrc = self._s({"surface": "gravel", "highway": "primary", "tracktype": "grade5"})
        self.assertEqual(surface, "gravel")
        self.assertEqual(conf, "high")
        self.assertEqual(csrc, "tagged_surface")

    def test_explicit_tag(self):
        surface, conf, _e, csrc = self._s({"surface": "asphalt"})
        self.assertEqual((surface, conf, csrc), ("asphalt", "high", "tagged_surface"))

    def test_tracktype_grades(self):
        self.assertEqual(self._s({"tracktype": "grade1"})[0], "compacted")
        self.assertEqual(self._s({"tracktype": "grade1"})[3], "inferred_tracktype")
        self.assertEqual(self._s({"tracktype": "grade2"})[0], "fine_gravel")
        self.assertEqual(self._s({"tracktype": "grade3"})[0], "gravel")
        self.assertEqual(self._s({"tracktype": "grade4"})[0], "dirt")
        self.assertEqual(self._s({"tracktype": "grade5"})[0], "grass")

    def test_highway_track_without_tags(self):
        surface, conf, _e, csrc = self._s({"highway": "track"})
        self.assertEqual((surface, conf, csrc), ("ground", "low", "inferred_highway"))

    def test_paved_highway(self):
        surface, conf, _e, csrc = self._s({"highway": "primary"})
        self.assertEqual((surface, conf, csrc), ("asphalt", "medium", "inferred_highway"))

    def test_paved_highway_bad_smoothness_downgraded(self):
        surface, conf, _e, csrc = self._s({"highway": "primary", "smoothness": "very_bad"})
        self.assertEqual((surface, conf, csrc), ("mixed", "medium", "inferred_highway"))

    def test_cycleway_paved(self):
        self.assertEqual(self._s({"highway": "cycleway"})[0], "asphalt")

    def test_path_is_dirt_low(self):
        surface, conf, _e, csrc = self._s({"highway": "path"})
        self.assertEqual((surface, conf, csrc), ("dirt", "low", "inferred_highway"))

    def test_no_tags_is_unknown(self):
        surface, conf, _e, csrc = self._s({})
        self.assertEqual((surface, conf, csrc), ("unknown", "unknown", "unknown"))


if __name__ == "__main__":
    unittest.main()
