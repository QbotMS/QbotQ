from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

from scripts.route_precompute_trigger import ensure_route_precompute_trigger
import scripts.route_precompute_trigger as route_precompute_trigger_module
from qbot_api import rwgps_webhook


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


class _DummyRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def body(self) -> bytes:
        import json

        return json.dumps(self._payload).encode("utf-8")


class TestRoutePrecomputeTrigger(unittest.TestCase):
    def test_precompute_complete_tracks_active_job_types(self) -> None:
        rows_4 = [
            {"job_type": "route_base", "status": "complete"},
            {"job_type": "route_surface", "status": "complete"},
            {"job_type": "route_landcover", "status": "complete"},
            {"job_type": "route_poi", "status": "complete"},
        ]
        rows_5 = rows_4 + [{"job_type": "route_shade", "status": "complete"}]
        rows_6 = rows_5 + [{"job_type": "route_elevation", "status": "complete"}]

        env_4 = {"QBOT_ROUTE_SHADE_ENABLED": "0", "QBOT_ROUTE_ELEVATION_ENABLED": "0"}
        env_5 = {"QBOT_ROUTE_SHADE_ENABLED": "1", "QBOT_ROUTE_ELEVATION_ENABLED": "0"}
        env_6 = {"QBOT_ROUTE_SHADE_ENABLED": "1", "QBOT_ROUTE_ELEVATION_ENABLED": "1"}

        self.assertTrue(route_precompute_trigger_module._precompute_complete(rows_4, env=env_4))
        self.assertFalse(route_precompute_trigger_module._precompute_complete(rows_5, env=env_4))
        self.assertFalse(route_precompute_trigger_module._precompute_complete(rows_6, env=env_4))

        self.assertFalse(route_precompute_trigger_module._precompute_complete(rows_4, env=env_5))
        self.assertTrue(route_precompute_trigger_module._precompute_complete(rows_5, env=env_5))
        self.assertFalse(route_precompute_trigger_module._precompute_complete(rows_6, env=env_5))

        self.assertFalse(route_precompute_trigger_module._precompute_complete(rows_4, env=env_6))
        self.assertFalse(route_precompute_trigger_module._precompute_complete(rows_5, env=env_6))
        self.assertTrue(route_precompute_trigger_module._precompute_complete(rows_6, env=env_6))

    def test_helper_runs_when_jobs_incomplete(self) -> None:
        with patch("scripts.route_precompute_trigger.ensure_route_base", return_value={
            "route_base": {"route_base_id": 1},
            "route_artifact_id": 306,
            "route_version_key": "rk-1",
        }), patch("scripts.route_precompute_trigger._route_precompute_rows", return_value=[]), patch(
            "scripts.route_precompute_trigger.ensure_route_precompute",
            return_value={
                "status": "OK",
                "route_id": "55798129",
                "route_base_id": 1,
                "route_artifact_id": 306,
                "route_version_key": "rk-1",
                "job_rows": [
                    {"job_type": "route_base"},
                    {"job_type": "route_surface"},
                    {"job_type": "route_landcover"},
                    {"job_type": "route_poi"},
                ],
            },
        ) as mock_precompute:
            result = ensure_route_precompute_trigger(route_id="55798129")

        self.assertEqual(result["trigger_status"], "ran")
        self.assertEqual(result["route_version_key"], "rk-1")
        mock_precompute.assert_called_once_with(route_id="55798129", trigger_source="rwgps_webhook")

    @unittest.skipUnless(_live_db_enabled(), "QBOT_LIVE_DB_TESTS=1 required for live DB trigger smoke")
    def test_route_55798129_trigger_idempotent(self) -> None:
        conn = _db_conn()
        try:
            before = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_precompute_jobs WHERE route_id = %s",
                ("55798129",),
            ).fetchone()["c"]
        finally:
            conn.close()

        first = ensure_route_precompute_trigger(route_id="55798129")
        second = ensure_route_precompute_trigger(route_id="55798129")

        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "OK")
        self.assertEqual(first["trigger_status"], "skipped")
        self.assertEqual(second["trigger_status"], "skipped")

        conn = _db_conn()
        try:
            after = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_precompute_jobs WHERE route_id = %s",
                ("55798129",),
            ).fetchone()["c"]
            self.assertEqual(int(before), int(after))

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

            landcover_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_landcover_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(landcover_count), 890)

            poi_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_poi_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(poi_count), 38)

            dup_count = conn.execute(
                """
                SELECT count(*) AS c
                FROM (
                    SELECT idempotency_key, count(*) AS n
                    FROM qbot_v2.route_precompute_jobs
                    WHERE route_id = %s
                    GROUP BY idempotency_key
                    HAVING count(*) > 1
                ) d
                """,
                ("55798129",),
            ).fetchone()["c"]
            self.assertEqual(int(dup_count), 0)

            job_rows = conn.execute(
                """
                SELECT job_type, status, layer_status_json->>'status' AS display_status
                FROM qbot_v2.route_precompute_jobs
                WHERE route_id = %s
                ORDER BY job_type
                """,
                ("55798129",),
            ).fetchall()
            self.assertEqual({row["job_type"] for row in job_rows}, {"route_base", "route_surface", "route_landcover", "route_poi"})
            self.assertTrue(all(row["status"] == "complete" for row in job_rows))
            self.assertTrue(all(row["display_status"] == "completed" for row in job_rows))
        finally:
            conn.close()

    def test_webhook_spawns_precompute_worker(self) -> None:
        payload = {
            "notifications": [
                {"item_type": "route", "action": "created", "item_id": "55798129"},
                {"item_type": "route", "action": "updated", "item_id": "55798129"},
            ]
        }
        with patch("subprocess.Popen") as mock_popen, patch("builtins.open", unittest.mock.mock_open()):
            import asyncio

            response = asyncio.run(rwgps_webhook("secret", _DummyRequest(payload), None))

        self.assertEqual(response.status_code, 403)

        with patch.dict(os.environ, {"QBOT_RWGPS_WEBHOOK_SECRET": "secret"}, clear=False):
            with patch("subprocess.Popen") as mock_popen, patch("builtins.open", unittest.mock.mock_open()):
                import asyncio

                response = asyncio.run(rwgps_webhook("secret", _DummyRequest(payload), None))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_popen.call_count, 1)
        args, kwargs = mock_popen.call_args
        self.assertIn("/opt/qbot/app/scripts/route_precompute_trigger.py", args[0])
        self.assertEqual(args[0][-1], "55798129")
        self.assertEqual(kwargs["cwd"], "/opt/qbot/app")
        self.assertTrue(kwargs["start_new_session"])
