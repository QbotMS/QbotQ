from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from qbot3.artifacts import route_analyzer as ra


ROUTE_GPX = "/opt/qbot/artifacts/exports/rwgps/rwgps_55798129.gpx"


class TestRoutePoiGooglePrimary(unittest.TestCase):
    def setUp(self):
        self.overpass_queries: list[str] = []

    def test_attractions_only_query_cannot_fetch_logistics(self):
        self.assertEqual(ra._route_poi_v2_requested_categories("attractions_only"), ["attraction"])
        query = ra._route_poi_v2_build_query(
            {"min_lat": 50.0, "min_lon": 17.0, "max_lat": 50.1, "max_lon": 17.1},
            "attractions_only", include_supply=False, include_water=False,
        )
        self.assertIn('["historic"]', query)
        self.assertIn('["tourism"', query)
        self.assertNotIn('["shop"', query)
        self.assertNotIn('["amenity"', query)
        self.assertNotIn('["drinking_water"', query)

    def _run(self):
        return ra.analyze_route_poi_artifact(
            ROUTE_GPX,
            route_id="55798129",
            artifact_id="306",
            km_from=0.0,
            km_to=71.137,
            buffers={
                "analysis_timeout_sec": 80.0,
                "overpass_timeout_sec": 0.1,
                "chunk_km": 12.0,
                "chunk_overlap_km": 1.0,
                "min_chunk_km": 5.0,
                "avg_speed_kmh": 18.0,
                "open_window": False,
                "google_hours": False,
            },
            focus="logistics",
            timeout_sec=80.0,
            output_format="json",
        )

    def test_google_primary_covers_late_route_supply(self):
        google_candidates = [
            {
                "osm_type": "google_places",
                "osm_id": "g-1",
                "google_place_id": "g-1",
                "google_name": "Biedronka",
                "name": "Biedronka",
                "category": "hard_resupply",
                "lat": 52.7001,
                "lon": 21.7001,
                "route_km": 45.0,
                "distance_to_track_m": 85.0,
                "source_tags": "name=Biedronka; shop=supermarket; provider=google_places; google_type=supermarket",
                "opening_hours_osm": "Mo-Su 06:00-23:00",
                "open_at_arrival": True,
                "open_source": "google",
                "eta_iso": "2026-06-29T12:30:00+02:00",
                "note": "google_primary",
            },
            {
                "osm_type": "google_places",
                "osm_id": "g-2",
                "google_place_id": "g-2",
                "google_name": "Żabka",
                "name": "Żabka",
                "category": "hard_resupply",
                "lat": 52.6401,
                "lon": 21.6401,
                "route_km": 12.0,
                "distance_to_track_m": 70.0,
                "source_tags": "name=Żabka; shop=convenience; provider=google_places; google_type=convenience_store",
                "opening_hours_osm": "Mo-Su 06:00-23:00",
                "open_at_arrival": True,
                "open_source": "google",
                "eta_iso": "2026-06-29T10:45:00+02:00",
                "note": "google_primary",
            },
        ]

        def fake_google_candidates(*args, **kwargs):
            return list(google_candidates)

        def fake_overpass(query, timeout_sec, bbox=None):
            self.overpass_queries.append(query)
            return []

        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False), \
             patch.object(ra, "_route_poi_v2_google_supply_candidates", side_effect=fake_google_candidates), \
             patch.object(ra, "_route_poi_v2_overpass_candidates", side_effect=fake_overpass):
            result = self._run()

        hard = result.get("hard_resupply") or []
        kms = [float(item.get("route_km") or 0.0) for item in hard]
        self.assertEqual(result.get("poi_source_mode"), "google_places_primary")
        self.assertEqual(result.get("google_supply_count"), 2)
        self.assertGreaterEqual(max(kms), 45.0)
        self.assertTrue(any(float(item.get("route_km") or 0.0) >= 40.0 for item in hard))
        self.assertTrue(all("nwr[\"shop\"" not in q and "\"fuel\"" not in q for q in self.overpass_queries))
        self.assertEqual(result.get("missing_chunks_count"), 0)

    def test_overpass_fallback_used_when_google_empty(self):
        overpass_calls = []

        def fake_google_candidates(*args, **kwargs):
            return []

        def fake_overpass(query, timeout_sec, bbox=None):
            overpass_calls.append(query)
            return [
                {
                    "type": "node",
                    "id": 123,
                    "lat": 52.6325,
                    "lon": 21.6787,
                    "tags": {
                        "name": "OSM Shop",
                        "shop": "convenience",
                        "opening_hours": "Mo-Su 06:00-23:00",
                    },
                }
            ]

        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False), \
             patch.object(ra, "_route_poi_v2_google_supply_candidates", side_effect=fake_google_candidates), \
             patch.object(ra, "_route_poi_v2_overpass_candidates", side_effect=fake_overpass):
            result = self._run()

        hard = result.get("hard_resupply") or []
        self.assertEqual(result.get("poi_source_mode"), "overpass_primary")
        self.assertTrue(any(item.get("name") == "OSM Shop" for item in hard))
        self.assertTrue(any("nwr[\"shop\"" in q for q in overpass_calls))

    def test_partial_chunk_reports_reason(self):
        calls = {"count": 0}

        def fake_google_candidates(*args, **kwargs):
            return []

        def fake_overpass(query, timeout_sec, bbox=None):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise TimeoutError("simulated read timeout")
            return []

        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False), \
             patch.object(ra, "_route_poi_v2_google_supply_candidates", side_effect=fake_google_candidates), \
             patch.object(ra, "_route_poi_v2_overpass_candidates", side_effect=fake_overpass):
            result = self._run()

        self.assertEqual(result.get("status"), "PARTIAL")
        self.assertGreater(result.get("missing_chunks_count", 0), 0)
        reasons = {str(chunk.get("reason")) for chunk in result.get("missing_chunks") or []}
        self.assertTrue({"overpass_timeout", "analysis_timeout"} & reasons)

    def test_google_supply_status_is_separate_from_overpass_completeness(self):
        calls = {"count": 0}

        google_candidates = [
            {
                "osm_type": "google_places",
                "osm_id": "g-1",
                "google_place_id": "g-1",
                "google_name": "Sklep 5 km",
                "name": "Sklep 5 km",
                "category": "hard_resupply",
                "lat": 52.6201,
                "lon": 21.6201,
                "route_km": 5.0,
                "distance_to_track_m": 60.0,
                "source_tags": "name=Sklep 5 km; provider=google_places",
                "opening_hours_osm": "Mo-Su 06:00-23:00",
                "open_at_arrival": True,
                "open_source": "google",
                "eta_iso": "2026-06-29T17:15:00+02:00",
                "note": "google_primary",
            },
            {
                "osm_type": "google_places",
                "osm_id": "g-2",
                "google_place_id": "g-2",
                "google_name": "Sklep 15 km",
                "name": "Sklep 15 km",
                "category": "hard_resupply",
                "lat": 52.6301,
                "lon": 21.6301,
                "route_km": 15.0,
                "distance_to_track_m": 70.0,
                "source_tags": "name=Sklep 15 km; provider=google_places",
                "opening_hours_osm": "Mo-Su 06:00-23:00",
                "open_at_arrival": True,
                "open_source": "google",
                "eta_iso": "2026-06-29T17:45:00+02:00",
                "note": "google_primary",
            },
            {
                "osm_type": "google_places",
                "osm_id": "g-3",
                "google_place_id": "g-3",
                "google_name": "Sklep 25 km",
                "name": "Sklep 25 km",
                "category": "hard_resupply",
                "lat": 52.6401,
                "lon": 21.6401,
                "route_km": 25.0,
                "distance_to_track_m": 75.0,
                "source_tags": "name=Sklep 25 km; provider=google_places",
                "opening_hours_osm": "Mo-Su 06:00-23:00",
                "open_at_arrival": True,
                "open_source": "google",
                "eta_iso": "2026-06-29T18:15:00+02:00",
                "note": "google_primary",
            },
            {
                "osm_type": "google_places",
                "osm_id": "g-4",
                "google_place_id": "g-4",
                "google_name": "Sklep 35 km",
                "name": "Sklep 35 km",
                "category": "hard_resupply",
                "lat": 52.6501,
                "lon": 21.6501,
                "route_km": 35.0,
                "distance_to_track_m": 80.0,
                "source_tags": "name=Sklep 35 km; provider=google_places",
                "opening_hours_osm": "Mo-Su 06:00-23:00",
                "open_at_arrival": True,
                "open_source": "google",
                "eta_iso": "2026-06-29T18:45:00+02:00",
                "note": "google_primary",
            },
        ]

        def fake_google_candidates(*args, **kwargs):
            return list(google_candidates)

        def fake_overpass(query, timeout_sec, bbox=None):
            calls["count"] += 1
            if calls["count"] >= 2:
                raise TimeoutError("simulated read timeout")
            return []

        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "test-key"}, clear=False), \
             patch.object(ra, "_route_poi_v2_google_supply_candidates", side_effect=fake_google_candidates), \
             patch.object(ra, "_route_poi_v2_overpass_candidates", side_effect=fake_overpass):
            result = self._run()

        self.assertEqual(result.get("poi_source_mode"), "google_places_primary")
        self.assertNotEqual(result.get("supply_status"), "PARTIAL")
        self.assertEqual(result.get("technical_completeness"), "PARTIAL")
        self.assertEqual(result.get("analysis_status"), "PARTIAL")
        self.assertGreater(result.get("missing_chunks_count", 0), 0)
        self.assertGreaterEqual(len(result.get("hard_resupply") or []), 4)


if __name__ == "__main__":
    unittest.main()
