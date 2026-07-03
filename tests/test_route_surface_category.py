"""Testy logiki kategoryzacji nawierzchni (5 kat.) — compute_category, czysta funkcja."""
import unittest

from qbot3.routes.route_surface_category_store import compute_category


def cat(**kw):
    kw.setdefault("surface", None); kw.setdefault("tracktype", None)
    kw.setdefault("highway", None); kw.setdefault("classification_source", None)
    kw.setdefault("smoothness", None); kw.setdefault("ctx", None)
    return compute_category(**kw)[0]


class TestSurfaceCategory(unittest.TestCase):
    def test_hard_surfaces_cat1(self):
        for s in ("asphalt", "concrete", "paving_stones"):
            self.assertEqual(cat(surface=s, classification_source="tagged_surface"), 1)

    def test_good_gravel_cat2(self):
        self.assertEqual(cat(surface="compacted", classification_source="tagged_surface"), 2)
        self.assertEqual(cat(surface="fine_gravel", classification_source="tagged_surface"), 2)

    def test_normal_gravel_cat3(self):
        for s in ("gravel", "dirt", "ground", "cobblestone"):
            self.assertEqual(cat(surface=s, classification_source="tagged_surface"), 3)

    def test_hard_slow_cat4(self):
        self.assertEqual(cat(surface="grass", classification_source="tagged_surface"), 4)
        self.assertEqual(cat(surface="mixed", classification_source="tagged_surface"), 4)

    def test_risk_cat5(self):
        for s in ("sand", "mud", "rocky", "stony"):
            self.assertEqual(cat(surface=s, classification_source="tagged_surface"), 5)

    def test_tracktype_wins_over_derived_label(self):
        # grade4 -> engine label 'dirt' (kat3), ale tracktype ma wygrac -> kat4
        self.assertEqual(cat(surface="dirt", tracktype="grade4",
                             classification_source="inferred_tracktype"), 4)
        self.assertEqual(cat(surface="grass", tracktype="grade5",
                             classification_source="inferred_tracktype"), 5)
        self.assertEqual(cat(surface="compacted", tracktype="grade1",
                             classification_source="inferred_tracktype"), 2)

    def test_bare_segment_is_cat5(self):
        self.assertEqual(cat(surface="ground", highway="track",
                             classification_source="inferred_highway"), 5)

    def test_bare_softened_by_context_land(self):
        ctx = {"sand_risk": "SREDNIE", "surface_estimate": "grunt", "dominant_pl": "uprawy"}
        self.assertEqual(cat(surface="ground", highway="track",
                             classification_source="inferred_highway", ctx=ctx), 4)

    def test_bare_stays_5_on_strong_sand(self):
        ctx = {"sand_risk": "WYSOKIE", "surface_estimate": "grunt", "dominant_pl": "uprawy"}
        self.assertEqual(cat(surface="ground", highway="track",
                             classification_source="inferred_highway", ctx=ctx), 5)

    def test_inferred_sand_risk_does_not_force_5(self):
        # wnioskowany SREDNIE/WNIOSK. nie moze robic falszywej pewnosci -> zostaje 4
        ctx = {"sand_risk": "WNIOSK.", "surface_estimate": "droga polna / grunt", "dominant_pl": "trawy"}
        self.assertEqual(cat(surface="ground", highway="track",
                             classification_source="inferred_highway", ctx=ctx), 4)

    def test_smoothness_degrader_hard_to_4(self):
        self.assertEqual(cat(surface="asphalt", classification_source="tagged_surface",
                             smoothness="very_bad"), 4)

    def test_smoothness_degrader_grund_minus_one_capped_4(self):
        self.assertEqual(cat(surface="gravel", classification_source="tagged_surface",
                             smoothness="bad"), 4)   # 3 -> 4
        self.assertEqual(cat(surface="compacted", classification_source="tagged_surface",
                             smoothness="bad"), 3)   # 2 -> 3
        self.assertEqual(cat(surface="grass", classification_source="tagged_surface",
                             smoothness="bad"), 4)   # 4 -> min(4,5)=4, bad nie robi 5

    def test_smoothness_terrible_forces_5(self):
        self.assertEqual(cat(surface="asphalt", classification_source="tagged_surface",
                             smoothness="impassable"), 5)

    def test_smoothness_degrades_tagged_surface(self):
        # Ad.4: degrader dziala tez gdy jest jawny tag surface
        self.assertEqual(cat(surface="compacted", tracktype="grade1",
                             classification_source="tagged_surface", smoothness="bad"), 3)

    def test_inferred_paved_is_not_bare(self):
        # inferred_highway z asfaltem = wnioskowana utwardzona -> kat.1, NIE goly/kat.4
        self.assertEqual(cat(surface="asphalt", highway="service",
                             classification_source="inferred_highway"), 1)
        # ...nawet z kontekstem (kontekst nie lagodzi utwardzonej)
        ctx = {"sand_risk": "NISKIE", "surface_estimate": "pewnie utwardzona", "dominant_pl": "las"}
        self.assertEqual(cat(surface="asphalt", highway="service",
                             classification_source="inferred_highway", ctx=ctx), 1)

    def test_inferred_highway_bare_track_is_5_or_softened(self):
        # ground z inferred_highway = goly track -> kat.5 bez kontekstu
        self.assertEqual(cat(surface="ground", highway="track",
                             classification_source="inferred_highway"), 5)

    def test_good_smoothness_no_change(self):
        self.assertEqual(cat(surface="gravel", classification_source="tagged_surface",
                             smoothness="good"), 3)


if __name__ == "__main__":
    unittest.main()
