#!/usr/bin/env python3
"""Test: export_route_to_artifact registers in both route_artifacts AND qbot_v2.artifacts.

Run from /opt/qbot/app:
    python3 scripts/test_rwgps_export_artifact_store_registration.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

EXIT_FAIL = 1

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── helpers ──────────────────────────────────────────────────────────

_ok = 0
_fail = 0


def _check(cond: bool, msg: str):
    global _ok, _fail
    if cond:
        print(f"  ✅ {msg}")
        _ok += 1
    else:
        print(f"  ❌ {msg}")
        _fail += 1


def _db_conn():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )


# ── tests ─────────────────────────────────────────────────────────────

ROUTE_ID = "55395119"


def _cleanup_qbot_v2_artifacts(conn, idem_key: str):
    """Remove previous test artifact record by idempotency_key."""
    conn.execute("DELETE FROM qbot_v2.artifacts WHERE idempotency_key = %s", (idem_key,))
    conn.commit()


def test_export_and_registration():
    print(f"\n{'='*60}")
    print(f"Test: export_route_to_artifact({ROUTE_ID}) + registration")
    print(f"{'='*60}")

    from tools.rwgps.client import export_route_to_artifact

    gpx_path = Path(f"/opt/qbot/artifacts/exports/rwgps/rwgps_{ROUTE_ID}.gpx")
    idem_key = f"rwgps_export:{ROUTE_ID}:gpx"

    # 1. Pre-clean so we start fresh
    conn = _db_conn()
    try:
        _cleanup_qbot_v2_artifacts(conn, idem_key)
    finally:
        conn.close()

    # 2. Run export
    result = export_route_to_artifact(ROUTE_ID, fmt="gpx", return_mode="metadata")

    print(f"  Result status: {result.get('status')}")
    _check(result.get("ok") is True, "export_route_to_artifact returned ok=True")
    _check(result.get("artifact_store_status") == "registered", f"artifact_store_status={result.get('artifact_store_status')}")
    _check("artifact_store_id" in result, "artifact_store_id in payload")
    artifact_store_id = result.get("artifact_store_id")

    # 3. Physical file
    _check(gpx_path.exists(), f"Physical GPX exists: {gpx_path}")
    file_size = gpx_path.stat().st_size
    _check(file_size > 1000, f"GPX file size > 1KB ({file_size} bytes)")

    # 4. qbot_v2.route_artifacts
    conn = _db_conn()
    try:
        ra = conn.execute(
            "SELECT * FROM qbot_v2.route_artifacts WHERE route_id = %s ORDER BY id DESC LIMIT 1",
            (ROUTE_ID,),
        ).fetchone()
        _check(ra is not None, "Route artifact record exists in qbot_v2.route_artifacts")
        if ra:
            _check(ROUTE_ID in str(ra.get("artifact_path", "")), f"artifact_path contains route_id: {ra.get('artifact_path')}")

        # 5. qbot_v2.artifacts
        aa = conn.execute(
            "SELECT * FROM qbot_v2.artifacts WHERE idempotency_key = %s",
            (idem_key,),
        ).fetchone()
        _check(aa is not None, f"Artifact record exists in qbot_v2.artifacts (idem_key={idem_key})")
        if aa:
            _check(aa["artifact_type"] == "route", f"artifact_type = route (got {aa['artifact_type']})")
            _check(aa["source"] == "rwgps", f"source = rwgps (got {aa['source']})")
            _check(aa["mutation_type"] == "export", f"mutation_type = export (got {aa['mutation_type']})")
            _check(ROUTE_ID in (aa.get("file_path") or ""), f"file_path contains route_id: {aa.get('file_path')}")
            md = aa.get("metadata_json") or {}
            if isinstance(md, str):
                md = json.loads(md)
            _check(md.get("rwgps_route_id") == int(ROUTE_ID), f"metadata.rwgps_route_id = {int(ROUTE_ID)} (got {md.get('rwgps_route_id')})")
            _check(md.get("point_count", 0) > 0, f"metadata.point_count > 0 (got {md.get('point_count')})")
            _check(md.get("distance_km", 0) > 50, f"metadata.distance_km plausible (got {md.get('distance_km')})")
            project_id = aa.get("project_id")
            print(f"  project_id = {project_id}")
            _check(project_id is not None, f"project_id is set (got {project_id})")
            print(f"  artifact_id = {aa['artifact_id']}")

        # 6. Match artifact_store_id
        if artifact_store_id and aa:
            _check(str(aa["artifact_id"]) == str(artifact_store_id),
                   f"artifact_store_id in payload matches DB: {artifact_store_id}")

    finally:
        conn.close()


def test_idempotency():
    print(f"\n{'='*60}")
    print("Test: re-export does not create duplicate artifact")
    print(f"{'='*60}")

    from tools.rwgps.client import export_route_to_artifact

    idem_key = f"rwgps_export:{ROUTE_ID}:gpx"

    result1 = export_route_to_artifact(ROUTE_ID, fmt="gpx", return_mode="metadata")
    result2 = export_route_to_artifact(ROUTE_ID, fmt="gpx", return_mode="metadata")

    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM qbot_v2.artifacts WHERE idempotency_key = %s ORDER BY created_at",
            (idem_key,),
        ).fetchall()
        _check(len(rows) == 1, f"Only 1 artifact record after double export (got {len(rows)})")
    finally:
        conn.close()

    _check(result1.get("artifact_store_id") == result2.get("artifact_store_id"),
           "Same artifact_store_id on re-export")


def test_gpx_parser():
    print(f"\n{'='*60}")
    print(f"Test: parse GPX for route_id={ROUTE_ID}")
    print(f"{'='*60}")

    from tools.rwgps.client import summarize_rwgps_artifact

    result = summarize_rwgps_artifact(f"rwgps_{ROUTE_ID}.gpx")

    _check(result.get("ok") is True, "summarize_rwgps_artifact returned ok=True")
    points = result.get("point_count", 0)
    dist = result.get("distance_km", 0)
    elev = result.get("elevation_gain_m", 0)
    bounds = result.get("bounds")

    _check(points == 1739, f"point_count = 1739 (got {points})")
    _check(abs(dist - 84.8) < 1.0, f"distance ≈ 84.8 km (got {dist})")
    _check(elev is not None and elev > 500, f"elevation_gain_m > 500 (got {elev})")
    _check(bounds is not None, "bounds is not None")
    if bounds:
        _check(bounds.get("sw_lat") is not None, "bounds.sw_lat not None")


def test_artifacts_list():
    print(f"\n{'='*60}")
    print("Test: artifacts_list can find the route (by project_id + route type)")
    print(f"{'='*60}")

    try:
        from qbot3.artifacts.store import list_artifacts

        artifacts = list_artifacts(project_id="tuscany_2026", artifact_type="route")
        _check(len(artifacts) > 0, f"artifacts_list returned {len(artifacts)} route artifacts")

        found = [a for a in artifacts if ROUTE_ID in (a.get("file_path") or "")]
        if not found:
            # also check metadata
            for a in artifacts:
                md = a.get("metadata_json") or {}
                if isinstance(md, str):
                    try:
                        md = json.loads(md)
                    except Exception:
                        pass
                if isinstance(md, dict) and md.get("rwgps_route_id") == int(ROUTE_ID):
                    found.append(a)
        _check(len(found) >= 1, f"Found artifact for route_id={ROUTE_ID} via list_artifacts (count={len(found)})")
        if found:
            print(f"  Found artifact_id = {found[0].get('artifact_id')}")
            print(f"  file_path = {found[0].get('file_path')}")

    except ImportError as exc:
        print(f"  ⚠️  Cannot test list_artifacts: {exc}")


# ── main ──────────────────────────────────────────────────────────────

def main():
    print(f"Route ID: {ROUTE_ID}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    test_export_and_registration()
    test_idempotency()
    test_gpx_parser()
    test_artifacts_list()

    print(f"\n{'='*60}")
    print(f"Results: {_ok} passed, {_fail} failed")
    print(f"{'='*60}")

    if _fail:
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
