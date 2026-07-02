from __future__ import annotations

import os
import unittest

import psycopg
from psycopg.rows import dict_row

from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute


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
class TestRoutePrecomputeOrchestrator(unittest.TestCase):
    def test_route_55798129_precompute_idempotent(self) -> None:
        first = ensure_route_precompute(route_id="55798129")
        second = ensure_route_precompute(route_id="55798129")

        self.assertEqual(first["status"], "OK")
        self.assertEqual(second["status"], "OK")
        self.assertEqual(first["route_base_id"], 1)
        self.assertEqual(first["route_artifact_id"], 306)
        self.assertEqual(first["route_version_key"], second["route_version_key"])
        self.assertEqual(first["job_count"], 3)
        self.assertEqual(second["job_count"], 3)

        for job_type in ("route_base", "route_surface", "route_poi"):
            self.assertIn(job_type, first["jobs"])
            self.assertIn(job_type, second["jobs"])
            self.assertEqual(first["jobs"][job_type]["status"], "completed")
            self.assertEqual(second["jobs"][job_type]["status"], "completed")
            self.assertEqual(first["jobs"][job_type]["schema_status"], "complete")
            self.assertEqual(second["jobs"][job_type]["schema_status"], "complete")

        self.assertEqual(first["jobs"]["route_base"]["job_result"]["route_axis_segments_count"], second["jobs"]["route_base"]["job_result"]["route_axis_segments_count"])
        self.assertEqual(first["jobs"]["route_surface"]["job_result"]["surface_layer_count"], second["jobs"]["route_surface"]["job_result"]["surface_layer_count"])
        self.assertEqual(first["jobs"]["route_poi"]["job_result"]["poi_layer_count"], second["jobs"]["route_poi"]["job_result"]["poi_layer_count"])

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

            surface_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_surface_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(surface_count), 76)

            poi_count = conn.execute(
                "SELECT count(*) AS c FROM qbot_v2.route_poi_layer WHERE route_base_id = %s",
                (1,),
            ).fetchone()["c"]
            self.assertEqual(int(poi_count), first["jobs"]["route_poi"]["layer_count"])

            job_rows = conn.execute(
                """
                SELECT job_type, status, layer_status_json->>'status' AS display_status
                FROM qbot_v2.route_precompute_jobs
                WHERE route_version_key = %s
                ORDER BY job_type
                """,
                (first["route_version_key"],),
            ).fetchall()
            self.assertEqual({row["job_type"] for row in job_rows}, {"route_base", "route_surface", "route_poi"})
            self.assertTrue(all(row["status"] == "complete" for row in job_rows))
            self.assertTrue(all(row["display_status"] == "completed" for row in job_rows))

            dup_count = conn.execute(
                """
                SELECT count(*) AS c
                FROM (
                    SELECT idempotency_key, count(*) AS n
                    FROM qbot_v2.route_precompute_jobs
                    WHERE route_version_key = %s
                    GROUP BY idempotency_key
                    HAVING count(*) > 1
                ) d
                """,
                (first["route_version_key"],),
            ).fetchone()["c"]
            self.assertEqual(int(dup_count), 0)



class TestRoutePrecomputeScopeRouting(unittest.TestCase):
    """Routing parametru scope (bez zywej bazy) — 2026-07-02."""

    def test_invalid_scope_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ensure_route_precompute(route_id="55798129", scope="bogus")

    def test_scope_poi_skips_base_rebuild(self) -> None:
        import qbot3.routes.route_precompute_orchestrator as orch
        calls = {"base": 0, "poi_only": 0}
        orig_base = orch.ensure_route_base
        orig_poi = orch._ensure_route_precompute_poi_only

        def fake_base(*a, **k):
            calls["base"] += 1
            raise AssertionError("ensure_route_base nie moze byc wolane dla scope='poi'")

        def fake_poi(route_id_text, *, trigger_source):
            calls["poi_only"] += 1
            return {"status": "OK", "scope": "poi", "route_id": route_id_text, "trigger_source": trigger_source}

        orch.ensure_route_base = fake_base
        orch._ensure_route_precompute_poi_only = fake_poi
        try:
            out = ensure_route_precompute(route_id="55798129", scope="poi", trigger_source="test")
        finally:
            orch.ensure_route_base = orig_base
            orch._ensure_route_precompute_poi_only = orig_poi

        self.assertEqual(out["scope"], "poi")
        self.assertEqual(calls["poi_only"], 1)
        self.assertEqual(calls["base"], 0)

    def test_scope_all_default_reaches_base(self) -> None:
        import qbot3.routes.route_precompute_orchestrator as orch
        calls = {"base": 0}
        orig_base = orch.ensure_route_base

        def fake_base(route_id_text):
            calls["base"] += 1
            raise RuntimeError("stop-after-base")

        orch.ensure_route_base = fake_base
        try:
            with self.assertRaises(RuntimeError):
                ensure_route_precompute(route_id="55798129")
        finally:
            orch.ensure_route_base = orig_base

        self.assertEqual(calls["base"], 1)
