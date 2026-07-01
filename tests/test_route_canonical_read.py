from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_canonical_read import _poi_summary, _surface_summary, read_canonical_route


def _live_db_enabled() -> bool:
    return os.getenv("QBOT_LIVE_DB_TESTS") == "1"


def _db_conn():
    conn = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )
    conn.autocommit = True
    return conn


@unittest.skipUnless(_live_db_enabled(), "QBOT_LIVE_DB_TESTS=1 required for live DB helper smoke")
class TestRouteCanonicalRead(unittest.TestCase):
    def test_surface_summary_helper_aggregates_distance_and_problems(self) -> None:
        rows = [
            {
                "segment_index": 0,
                "surface": "asphalt",
                "source": "osm_surface",
                "confidence": "high",
                "coverage_status": "GOOD_INFERRED",
                "surface_meta_json": {"distance_m": 100.0, "classification_source": "tagged_surface"},
            },
            {
                "segment_index": 1,
                "surface": "grass",
                "source": "osm_contextual",
                "confidence": "high",
                "coverage_status": "GOOD_INFERRED",
                "surface_meta_json": {"distance_m": 50.0, "classification_source": "inferred_highway"},
            },
            {
                "segment_index": 2,
                "surface": "sand",
                "source": "mystery",
                "confidence": "low",
                "coverage_status": "PARTIAL",
                "surface_meta_json": {"classification_source": "unknown_provenance"},
            },
        ]
        summary = _surface_summary(
            rows,
            {"distance_m": 200.0},
            {"overpass_metrics": {
                "chunks_total": 7,
                "chunks_ok": 7,
                "chunks_failed": 0,
                "timeout_count": 3,
                "http_error_count": 1,
            }},
        )

        self.assertEqual(summary["segment_count"], 3)
        self.assertEqual(summary["total_distance_m"], 150.0)
        self.assertEqual(summary["coverage_pct"], 75.0)
        self.assertEqual(summary["missing_distance_count"], 1)
        self.assertEqual(summary["tagged_surface_distance_m"], 100.0)
        self.assertEqual(summary["tagged_surface_pct"], 66.7)
        self.assertEqual(summary["tagged_surface_segment_count"], 1)
        self.assertEqual(summary["inferred_surface_distance_m"], 50.0)
        self.assertEqual(summary["inferred_surface_pct"], 33.3)
        self.assertEqual(summary["inferred_surface_segment_count"], 1)
        self.assertEqual(summary["unknown_provenance_count"], 1)
        self.assertEqual(summary["overpass_chunks_total"], 7)
        self.assertEqual(summary["overpass_chunks_ok"], 7)
        self.assertEqual(summary["overpass_chunks_failed"], 0)
        self.assertEqual(summary["overpass_timeout_count"], 3)
        self.assertEqual(summary["overpass_http_error_count"], 1)
        self.assertEqual(summary["by_surface"]["asphalt"]["segment_count"], 1)
        self.assertEqual(summary["by_surface"]["asphalt"]["distance_m"], 100.0)
        self.assertEqual(summary["by_surface"]["asphalt"]["pct"], 66.7)
        self.assertEqual(summary["by_surface"]["grass"]["segment_count"], 1)
        self.assertEqual(summary["by_source"]["osm_contextual"]["segment_count"], 1)
        self.assertEqual(summary["by_confidence"]["high"]["segment_count"], 2)
        self.assertEqual(summary["by_confidence"]["low"]["segment_count"], 1)
        self.assertEqual(len(summary["problem_segments"]), 2)
        self.assertEqual(summary["problem_segments"][0]["segment_index"], 1)
        self.assertTrue(summary["problem_segments"][1]["missing_distance"])

    def test_poi_summary_ranks_zero_values_before_missing_values(self) -> None:
        poi_rows = [
            {
                "category": "town",
                "name": "Town A",
                "km_on_route": 0.0,
                "distance_from_route_m": 100.0,
                "opening_hours": None,
            },
            {
                "category": "town",
                "name": "Town B",
                "km_on_route": 10.0,
                "distance_from_route_m": 100.0,
                "opening_hours": None,
            },
            {
                "category": "hard_resupply",
                "name": "Zero km",
                "km_on_route": 0.0,
                "distance_from_route_m": 0.0,
                "opening_hours": "Mo-Su 06:00-22:00",
            },
            {
                "category": "hard_resupply",
                "name": "Missing distance",
                "km_on_route": 0.5,
                "distance_from_route_m": None,
                "opening_hours": "Mo-Su 06:00-22:00",
            },
            {
                "category": "hard_resupply",
                "name": "Farther",
                "km_on_route": 1.0,
                "distance_from_route_m": 50.0,
                "opening_hours": "Mo-Su 06:00-22:00",
            },
        ]
        summary = _poi_summary(poi_rows)

        self.assertEqual(summary["poi_count"], 5)
        self.assertEqual(summary["field_counts"]["km_on_route"], 5)
        self.assertEqual(summary["field_counts"]["distance_from_route_m"], 4)
        self.assertEqual(summary["field_counts"]["opening_hours"], 3)
        self.assertEqual(summary["field_counts"]["town_rows"], 2)
        self.assertEqual(summary["by_category"]["hard_resupply"]["count"], 3)
        self.assertEqual(summary["by_category"]["town"]["count"], 2)
        self.assertTrue(summary["clusters"])
        cluster = next(item for item in summary["clusters"] if item["locality"] == "Town A")
        self.assertEqual(cluster["best_items"][0]["name"], "Zero km")
        self.assertEqual(cluster["best_items"][0]["distance_from_route_m"], 0.0)
        self.assertEqual(cluster["best_items"][1]["name"], "Farther")
        self.assertNotIn("Missing distance", [item["name"] for item in cluster["best_items"]])

    def test_route_55798129_canonical_read_is_complete(self) -> None:
        with _db_conn() as conn:
            before_jobs = conn.execute(
                """
                SELECT count(*) AS c
                FROM qbot_v2.route_precompute_jobs
                WHERE route_version_key = (
                    SELECT route_version_key
                    FROM qbot_v2.route_base
                    WHERE route_id = %s
                    ORDER BY updated_at DESC, route_base_id DESC
                    LIMIT 1
                )
                """,
                ("55798129",),
            ).fetchone()["c"]

        first = read_canonical_route(route_id="55798129")
        second = read_canonical_route(route_id="55798129", route_base_id=1)

        self.assertEqual(first["read_path"], "canonical")
        self.assertEqual(second["read_path"], "canonical")
        self.assertIsNone(first["fallback_reason"])
        self.assertIsNone(second["fallback_reason"])
        self.assertEqual(first["route_id"], "55798129")
        self.assertEqual(first["route_base_id"], 1)
        self.assertEqual(first["route_version_key"], second["route_version_key"])
        self.assertEqual(first["route_artifact_id"], 306)

        self.assertEqual(first["layer_counts"]["route_base"], 1)
        self.assertEqual(first["layer_counts"]["route_axis_segments"], 1423)
        self.assertEqual(first["layer_counts"]["route_surface_layer"], 76)
        self.assertEqual(first["layer_counts"]["route_landcover_layer"], 890)
        self.assertEqual(first["layer_counts"]["route_poi_layer"], 38)
        self.assertEqual(first["layer_counts"]["route_elevation_samples"], 1424)
        self.assertEqual(first["layer_counts"]["route_climb_events"], 1)
        self.assertIn("canonical_surface_summary", first)
        self.assertIn("canonical_poi_summary", first)
        self.assertEqual(first["canonical_surface_summary"]["segment_count"], 76)
        self.assertGreater(first["canonical_surface_summary"]["total_distance_m"], 0.0)
        self.assertTrue(first["canonical_surface_summary"]["by_surface"])
        self.assertEqual(first["canonical_surface_summary"]["coverage_pct"], 100.0)
        self.assertEqual(first["canonical_surface_summary"]["tagged_surface_pct"], 70.8)
        self.assertEqual(first["canonical_surface_summary"]["inferred_surface_pct"], 29.2)
        self.assertEqual(first["canonical_surface_summary"]["overpass_chunks_total"], 7)
        self.assertEqual(first["canonical_surface_summary"]["overpass_chunks_ok"], 7)
        self.assertEqual(first["canonical_surface_summary"]["overpass_chunks_failed"], 0)
        self.assertEqual(first["canonical_surface_summary"]["overpass_timeout_count"], 7)
        self.assertEqual(first["canonical_surface_summary"]["overpass_http_error_count"], 5)
        self.assertEqual(first["canonical_poi_summary"]["poi_count"], 38)
        self.assertEqual(first["canonical_poi_summary"]["field_counts"]["km_on_route"], 38)
        self.assertEqual(first["canonical_poi_summary"]["field_counts"]["distance_from_route_m"], 38)
        self.assertEqual(first["canonical_poi_summary"]["field_counts"]["opening_hours"], 15)
        self.assertEqual(first["canonical_poi_summary"]["field_counts"]["town_rows"], 20)
        self.assertEqual(first["canonical_poi_summary"]["by_category"]["hard_resupply"]["count"], 15)
        self.assertEqual(first["canonical_poi_summary"]["by_category"]["soft_food_stop"]["count"], 3)
        self.assertEqual(first["canonical_poi_summary"]["by_category"]["town"]["count"], 20)
        self.assertTrue(first["canonical_poi_summary"]["clusters"])

        self.assertEqual(len(first["layers"]["route_axis_segments"]), 1423)
        self.assertEqual(len(first["layers"]["route_surface_layer"]), 76)
        self.assertEqual(len(first["layers"]["route_landcover_layer"]), 890)
        self.assertEqual(len(first["layers"]["route_poi_layer"]), 38)
        self.assertEqual(len(first["layers"]["route_elevation_samples"]), 1424)
        self.assertEqual(len(first["layers"]["route_climb_events"]), 1)

        with _db_conn() as conn:
            after_jobs = conn.execute(
                """
                SELECT count(*) AS c
                FROM qbot_v2.route_precompute_jobs
                WHERE route_version_key = (
                    SELECT route_version_key
                    FROM qbot_v2.route_base
                    WHERE route_id = %s
                    ORDER BY updated_at DESC, route_base_id DESC
                    LIMIT 1
                )
                """,
                ("55798129",),
            ).fetchone()["c"]

        self.assertEqual(int(before_jobs), int(after_jobs))
