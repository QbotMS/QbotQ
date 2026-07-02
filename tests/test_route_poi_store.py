from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_poi_store import ensure_route_poi


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


@unittest.skipUnless(_live_db_enabled(), "QBOT_LIVE_DB_TESTS=1 required for live DB writer smoke")
class TestRoutePoiStore(unittest.TestCase):
    def test_route_55798129_poi_layer_idempotent(self) -> None:
        conn = _db_conn()
        try:
            base_row = conn.execute(
                """
                SELECT route_base_id, route_artifact_id, route_version_key
                FROM qbot_v2.route_base
                WHERE route_id = %s
                ORDER BY updated_at DESC, route_base_id DESC
                LIMIT 1
                """,
                ("55798129",),
            ).fetchone()
            self.assertIsNotNone(base_row)
            route_base_id = int(base_row["route_base_id"])
            conn.commit()
        finally:
            conn.close()

        first = ensure_route_poi(route_base_id=route_base_id)
        second = ensure_route_poi(route_base_id=route_base_id)

        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "OK")
        self.assertEqual(first["route_base_id"], 1)
        self.assertEqual(first["route_artifact_id"], 306)
        self.assertGreater(first["poi_layer_count"], 0)
        self.assertEqual(first["poi_layer_count"], second["poi_layer_count"])

        conn = _db_conn()
        try:
            poi_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_poi_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(poi_count), first["poi_layer_count"])

            dup_count = conn.execute(
                """
                SELECT count(*) AS c
                FROM (
                    SELECT route_base_id, poi_key, count(*) AS n
                    FROM qbot_v2.route_poi_layer
                    WHERE route_base_id = %s
                    GROUP BY route_base_id, poi_key
                    HAVING count(*) > 1
                ) d
                """,
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(dup_count), 0)

            route_base_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_base WHERE route_id = %s",
                ("55798129",),
            ).fetchone()["c"]
            self.assertEqual(int(route_base_count), 1)

            axis_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_axis_segments WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(axis_count), 1423)

            surface_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_surface_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(surface_count), 76)

            conn.commit()
        finally:
            conn.close()
