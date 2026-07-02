"""Testy renderowania warstwy route_surface_context w raporcie trasy.

Sprawdza sekcje A3D (_route_surface_context_lines) oraz wpiecie alarmu piachu
do werdyktu (_route_verdict_section_lines). Dane wejsciowe syntetyczne (bez bazy).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_route_report_tool as R


def _ctx(elevated, high_km=0.0, med_km=0.0, seg=10, counts=None):
    return {
        "source": "route_surface_context_v1",
        "segment_count": seg,
        "risk_counts": counts or {"WYSOKIE": 1, "NISKIE": 9},
        "sand_km_high": high_km,
        "sand_km_medium": med_km,
        "elevated": elevated,
    }


HIGH_SEG = {"km_from": 20.35, "km_to": 20.85, "sand_risk": "WYSOKIE",
            "surface_estimate": "MOZLIWY GLEBOKI PIACH", "dominant_pl": "trawy",
            "agreement_pct": 80, "reason": "polna droga nietagowana na piaszczystym podlozu -> rozwaz objazd"}
MED_SEG = {"km_from": 60.9, "km_to": 61.15, "sand_risk": "SREDNIE",
           "surface_estimate": "grunt", "dominant_pl": "las", "agreement_pct": 100,
           "reason": "track grade4 (ocena jakosci z OSM)"}


class TestSurfaceContextRender(unittest.TestCase):
    def test_empty_context_renders_nothing(self):
        self.assertEqual(R._route_surface_context_lines({"canonical_surface_context": _ctx([], seg=0)}), [])
        self.assertEqual(R._route_surface_context_lines({}), [])

    def test_high_segment_produces_alarm(self):
        lines = R._route_surface_context_lines({"canonical_surface_context": _ctx([HIGH_SEG], high_km=0.5)})
        text = "\n".join(lines)
        self.assertIn("MOŻLIWY GŁĘBOKI PIACH", text)
        self.assertIn("20.35", text)
        self.assertIn("rozważ objazd", text)

    def test_per_segment_lines_listed(self):
        lines = R._route_surface_context_lines({"canonical_surface_context": _ctx([HIGH_SEG, MED_SEG], high_km=0.5, med_km=0.25)})
        text = "\n".join(lines)
        self.assertIn("[WYSOKIE]", text)
        self.assertIn("[SREDNIE]", text)
        self.assertIn("trawy 80%", text)

    def test_verdict_puts_sand_first(self):
        route_source = {
            "canonical_surface_summary": {"inferred_surface_pct": 10.0, "coverage_pct": 100.0,
                                          "tagged_surface_pct": 90.0, "by_surface": {}},
            "canonical_surface_context": _ctx([HIGH_SEG], high_km=0.5),
            "canonical_poi_summary": {"poi_count": 10},
            "canonical_elevation_summary": {"ascent_smoothed_m": 200},
        }
        meteo_ok = {"status": "OK", "result": {"hazards": []}}
        lines = R._route_verdict_section_lines(route_source, meteo_ok, {})
        text = "\n".join(lines)
        self.assertIn("piach", text.lower())


if __name__ == "__main__":
    unittest.main()
