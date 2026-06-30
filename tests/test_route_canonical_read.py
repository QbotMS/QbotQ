from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_canonical_read import read_canonical_route


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

