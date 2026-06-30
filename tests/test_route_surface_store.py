from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_base_store import ensure_route_base
from qbot3.routes.route_surface_store import ensure_route_surface


def _live_db_enabled() -> bool:
    return os.getenv("QBOT_LIVE_DB_TESTS") == "1"


def _db_conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


@unittest.skipUnless(_live_db_enabled(), "QBOT_LIVE_DB_TESTS=1 required for live DB writer smoke")
class TestRouteSurfaceStore(unittest.TestCase):
    def test_route_55798129_surface_layer_idempotent(self) -> None:
        base = ensure_route_base("55798129")
        first = ensure_route_surface(route_base_id=int(base["route_base"]["route_base_id"]))
        second = ensure_route_surface(route_base_id=int(base["route_base"]["route_base_id"]))

        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "OK")
        self.assertEqual(first["route_base_id"], 1)
        self.assertEqual(first["surface_profile_route_artifact_id"], 306)
        self.assertGreater(first["surface_layer_count"], 0)
        self.assertEqual(first["surface_layer_count"], second["surface_layer_count"])

        with _db_conn() as conn:
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

            layer_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_surface_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(layer_count), first["surface_layer_count"])

            dup_count = conn.execute(
                """
                SELECT count(*) AS c
                FROM (
                    SELECT route_base_id, segment_index, count(*) AS n
                    FROM qbot_v2.route_surface_layer
                    WHERE route_base_id = %s
                    GROUP BY route_base_id, segment_index
                    HAVING count(*) > 1
                ) d
                """,
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(dup_count), 0)

