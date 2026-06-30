from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_base_store import ensure_route_base


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
class TestRouteBaseStore(unittest.TestCase):
    def test_route_55798129_is_idempotent(self) -> None:
        first = ensure_route_base("55798129")
        second = ensure_route_base("55798129")

        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "OK")
        self.assertEqual(first["route_artifact_id"], 306)
        self.assertEqual(first["route_parse_result_id"], 17)
        self.assertEqual(first["route_base"]["route_base_id"], second["route_base"]["route_base_id"])
        self.assertEqual(first["route_version_key"], second["route_version_key"])
        self.assertEqual(first["route_axis_segments_count"], second["route_axis_segments_count"])
        self.assertGreater(first["route_axis_segments_count"], 0)

        with _db_conn() as conn:
            base_rows = conn.execute(
                """
                SELECT route_base_id, route_version_key
                FROM qbot_v2.route_base
                WHERE route_id = %s
                ORDER BY updated_at DESC, route_base_id DESC
                """,
                ("55798129",),
            ).fetchall()
            self.assertGreaterEqual(len(base_rows), 1)
            route_base_id = int(base_rows[0]["route_base_id"])
            seg_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_axis_segments WHERE route_base_id = %s",
                (route_base_id,),
            ).fetchone()["c"]
            self.assertEqual(int(seg_count), first["route_axis_segments_count"])

            seg_count_2 = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_axis_segments WHERE route_base_id = %s",
                (route_base_id,),
            ).fetchone()["c"]
            self.assertEqual(int(seg_count_2), int(seg_count))
