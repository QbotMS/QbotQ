from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

from scripts.route_precompute_trigger import ensure_route_precompute_trigger
from scripts.route_precompute_trigger import _ensure_rwgps_route_artifact
from scripts.route_precompute_trigger import _ensure_rwgps_surface_profile
from scripts.route_precompute_trigger import _ensure_rwgps_route_frames
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
        with patch("scripts.route_precompute_trigger._ensure_rwgps_route_artifact", return_value={
            "status": "OK",
            "import_status": "imported",
            "route_id": "55798129",
            "route_artifact_id": 306,
            "route_parse_result_id": 17,
        }) as mock_import, patch("scripts.route_precompute_trigger._ensure_rwgps_surface_profile", return_value={
            "status": "OK",
            "surface_status": "imported",
            "route_id": "55798129",
            "route_artifact_id": 306,
            "surface_profile_id": 19,
        }) as mock_surface, patch("scripts.route_precompute_trigger.ensure_route_base", return_value={
            "route_base": {"route_base_id": 1},
            "route_artifact_id": 306,
            "route_version_key": "rk-1",
        }), patch("scripts.route_precompute_trigger._route_precompute_rows", return_value=[]), patch(
            "scripts.route_precompute_trigger._ensure_rwgps_route_frames",
            return_value={
                "status": "OK",
                "frames_status": "built",
                "route_id": "55798129",
                "route_artifact_id": 306,
                "frame_count": 271,
            },
        ) as mock_frames, patch(
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
        self.assertEqual(result["route_import"]["import_status"], "imported")
        self.assertEqual(result["route_surface"]["surface_status"], "imported")
        self.assertEqual(result["route_frames"]["frames_status"], "built")
        self.assertEqual(result["route_version_key"], "rk-1")
        mock_import.assert_called_once_with("55798129")
        mock_surface.assert_called_once_with("55798129", route_artifact_id=306)
        mock_frames.assert_called_once_with("55798129", route_artifact_id=306)
        mock_precompute.assert_called_once_with(route_id="55798129", trigger_source="rwgps_webhook")

    def test_ensure_rwgps_surface_profile_runs_when_missing(self) -> None:
        with patch("scripts.route_precompute_trigger._route_import_state", return_value={
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 402,
            "route_parse_result_id": 28,
        }), patch("scripts.route_precompute_trigger._route_surface_profile_state", side_effect=[
            {"has_profile": False, "surface_profile_id": None},
            {"has_profile": False, "surface_profile_id": None},
            {"has_profile": True, "surface_profile_id": 19},
        ]), patch("scripts.route_precompute_trigger._route_artifact_path", return_value="/opt/qbot/artifacts/exports/rwgps/rwgps_55911618.gpx"), patch(
            "qbot_route_tools._tool_qbot_route_artifact_enrich",
            return_value={"ok": True, "status": "OK", "surface_profile": {"id": 19}},
        ) as mock_enrich, patch("scripts.route_precompute_trigger._persist_surface_profile_from_enrich_result", return_value={"id": 19}), patch(
            "tools.rwgps.route_frames.build",
            return_value=0,
        ) as mock_build:
            result = _ensure_rwgps_surface_profile("55911618", route_artifact_id=402)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["surface_status"], "imported")
        self.assertEqual(result["surface_profile_id"], 19)
        mock_enrich.assert_called_once()
        mock_build.assert_called_once_with(route_id="55911618", frame_size=80.0, dry_run=False, show=0)

    def test_ensure_rwgps_surface_profile_skips_when_ready(self) -> None:
        with patch("scripts.route_precompute_trigger._route_import_state", return_value={
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 402,
            "route_parse_result_id": 28,
        }), patch("scripts.route_precompute_trigger._route_surface_profile_state", return_value={
            "has_profile": True,
            "surface_profile_id": 19,
        }), patch("scripts.route_precompute_trigger._route_artifact_path") as mock_path, patch(
            "qbot_route_tools._tool_qbot_route_artifact_enrich",
        ) as mock_enrich:
            result = _ensure_rwgps_surface_profile("55911618", route_artifact_id=402)

        self.assertEqual(result["surface_status"], "skipped")
        mock_path.assert_not_called()
        mock_enrich.assert_not_called()

    def test_ensure_rwgps_route_frames_runs_when_missing(self) -> None:
        with patch("scripts.route_precompute_trigger._route_import_state", return_value={
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 402,
            "route_parse_result_id": 28,
        }), patch("scripts.route_precompute_trigger._route_frames_state", side_effect=[
            {"has_frames": False, "frame_count": 0},
            {"has_frames": True, "frame_count": 271},
        ]), patch("tools.rwgps.route_frames.build", return_value=0) as mock_build:
            result = _ensure_rwgps_route_frames("55911618", route_artifact_id=402)

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["frames_status"], "built")
        self.assertEqual(result["frame_count"], 271)
        mock_build.assert_called_once_with(route_id="55911618", frame_size=80.0, dry_run=False, show=0)

    def test_ensure_rwgps_route_frames_skips_when_ready(self) -> None:
        with patch("scripts.route_precompute_trigger._route_import_state", return_value={
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 402,
            "route_parse_result_id": 28,
        }), patch("scripts.route_precompute_trigger._route_frames_state", return_value={
            "has_frames": True,
            "frame_count": 271,
        }), patch("tools.rwgps.route_frames.build") as mock_build:
            result = _ensure_rwgps_route_frames("55911618", route_artifact_id=402)

        self.assertEqual(result["frames_status"], "skipped")
        mock_build.assert_not_called()

    def test_ensure_rwgps_surface_profile_reports_failure(self) -> None:
        with patch("scripts.route_precompute_trigger._route_import_state", return_value={
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 402,
            "route_parse_result_id": 28,
        }), patch("scripts.route_precompute_trigger._route_surface_profile_state", return_value={
            "has_profile": False,
            "surface_profile_id": None,
        }), patch("scripts.route_precompute_trigger._route_artifact_path", return_value="/opt/qbot/artifacts/exports/rwgps/rwgps_55911618.gpx"), patch(
            "qbot_route_tools._tool_qbot_route_artifact_enrich",
            return_value={"ok": False, "status": "ERROR", "reason": "surface failed"},
        ):
            result = _ensure_rwgps_surface_profile("55911618", route_artifact_id=402)

        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["surface_status"], "failed")
        self.assertIn("surface failed", result["error"])

    def test_ensure_rwgps_route_artifact_exports_when_missing(self) -> None:
        missing_state = {
            "has_artifact": False,
            "has_parse_result": False,
            "route_artifact_id": None,
            "route_parse_result_id": None,
        }
        ready_state = {
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 777,
            "route_parse_result_id": 778,
        }

        with patch("scripts.route_precompute_trigger._route_import_state", side_effect=[missing_state, ready_state]), patch(
            "tools.rwgps.client.export_route_to_artifact",
            return_value={"ok": True, "status": "OK", "artifact_store_id": "abc"},
        ) as mock_export:
            result = _ensure_rwgps_route_artifact("55911618")

        self.assertEqual(result["import_status"], "imported")
        self.assertEqual(result["route_artifact_id"], 777)
        self.assertEqual(result["route_parse_result_id"], 778)
        mock_export.assert_called_once_with("55911618", fmt="gpx", return_mode="metadata")

    def test_ensure_rwgps_route_artifact_skips_when_ready(self) -> None:
        ready_state = {
            "has_artifact": True,
            "has_parse_result": True,
            "route_artifact_id": 777,
            "route_parse_result_id": 778,
        }
        with patch("scripts.route_precompute_trigger._route_import_state", return_value=ready_state), patch(
            "tools.rwgps.client.export_route_to_artifact",
        ) as mock_export:
            result = _ensure_rwgps_route_artifact("55911618")

        self.assertEqual(result["import_status"], "skipped")
        mock_export.assert_not_called()

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
