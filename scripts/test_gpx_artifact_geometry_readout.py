#!/usr/bin/env python3
"""Test: deterministic GPX geometry readout for route_id / artifact_id / path.

Run from /opt/qbot/app:
    python3 scripts/test_gpx_artifact_geometry_readout.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

EXIT_FAIL = 1
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


ROUTE_ID = "55395119"
ARTIFACT_ID = None  # resolved dynamically


def resolve_artifact_id() -> str | None:
    """Look up artifact_id for route_id=55395119 from qbot_v2.artifacts."""
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )
    row = conn.execute(
        "SELECT artifact_id FROM qbot_v2.artifacts "
        "WHERE metadata_json->>'rwgps_route_id' = %s "
        "AND status = 'active'::qbot_v2.artifact_status "
        "ORDER BY created_at DESC LIMIT 1",
        (ROUTE_ID,),
    ).fetchone()
    conn.close()
    return str(row["artifact_id"]) if row else None


def test_by_route_id():
    print(f"\n{'='*60}")
    print(f"Test: parse_gpx_artifact_geometry(route_id={ROUTE_ID})")
    print(f"{'='*60}")

    from tools.rwgps.client import parse_gpx_artifact_geometry

    result = parse_gpx_artifact_geometry(route_id=ROUTE_ID)
    _check(result.get("ok") is True, f"ok=True (status={result.get('status')})")
    _check(result.get("route_id") == ROUTE_ID, f"route_id={ROUTE_ID}")
    _check(result.get("artifact_id") is not None, "artifact_id is not None")
    _check(result.get("absolute_path") is not None, "absolute_path is not None")
    _check(result.get("size_bytes", 0) > 1000, f"size_bytes > 1KB ({result.get('size_bytes')})")

    # ── Metrics ──
    pc = result.get("point_count", 0)
    dk = result.get("distance_km", 0)
    eg = result.get("elevation_gain_m", 0)

    _check(pc == 1739, f"point_count = 1739 (got {pc})")
    _check(85.1 >= dk >= 84.5, f"distance_km in 84.5–85.1 (got {dk})")
    _check(eg is not None and eg > 700, f"elevation_gain_m > 700 (got {eg})")

    # ── Bbox ──
    bbox = result.get("bbox")
    _check(bbox is not None, "bbox not None")
    if bbox:
        _check(bbox.get("sw_lat") is not None, "bbox.sw_lat")
        _check(bbox.get("sw_lng") is not None, "bbox.sw_lng")
        _check(bbox.get("ne_lat") is not None, "bbox.ne_lat")
        _check(bbox.get("ne_lng") is not None, "bbox.ne_lng")

    # ── Start / end ──
    sp = result.get("start_point")
    ep = result.get("end_point")
    _check(sp is not None and sp.get("lat") is not None, "start_point exists")
    _check(ep is not None and ep.get("lat") is not None, "end_point exists")
    if sp and ep:
        _check(sp["lat"] != ep["lat"] or sp["lon"] != ep["lon"], "start != end (different points)")

    # ── Control points ──
    cp = result.get("control_points_every_5km", [])
    _check(len(cp) >= 15, f"control_points_every_5km count >= 15 (got {len(cp)})")
    if cp:
        _check(cp[0].get("lat") is not None, "first control point has lat")
        _check(cp[0].get("km") == 0.0, "first control point at km=0")
        _check(cp[-1].get("km") >= 80, f"last control point km >= 80 (got {cp[-1].get('km')})")

    # ── Geometry sample ──
    gs = result.get("geometry_sample", [])
    _check(len(gs) > 0, f"geometry_sample not empty ({len(gs)} pts)")
    _check(len(gs) <= 200, f"geometry_sample <= 200 pts (got {len(gs)})")
    if gs:
        _check("lat" in gs[0], "geometry_sample[0] has lat")
        _check("lon" in gs[0], "geometry_sample[0] has lon")

    # ── track_length_km ──
    tl = result.get("track_length_km")
    _check(tl is not None and tl > 80, f"track_length_km > 80 (got {tl})")

    global ARTIFACT_ID
    ARTIFACT_ID = result.get("artifact_id")
    return result


def test_by_artifact_id():
    print(f"\n{'='*60}")
    print(f"Test: parse_gpx_artifact_geometry(artifact_id={ARTIFACT_ID})")
    print(f"{'='*60}")

    if not ARTIFACT_ID:
        print("  ⚠️  Skipping — no artifact_id resolved")
        return

    from tools.rwgps.client import parse_gpx_artifact_geometry

    result = parse_gpx_artifact_geometry(artifact_id=ARTIFACT_ID)
    _check(result.get("ok") is True, f"ok=True (status={result.get('status')})")
    _check(result.get("artifact_id") == ARTIFACT_ID, f"artifact_id matches")
    _check(result.get("absolute_path") is not None, "absolute_path not None")
    _check(result.get("point_count", 0) == 1739, f"point_count = 1739")
    _check(result.get("distance_km", 0) > 84, f"distance_km > 84")


def test_by_path():
    print(f"\n{'='*60}")
    print("Test: parse_gpx_artifact_geometry(path=...)")
    print(f"{'='*60}")

    from tools.rwgps.client import parse_gpx_artifact_geometry

    # by relative path
    rel = f"exports/rwgps/rwgps_{ROUTE_ID}.gpx"
    result = parse_gpx_artifact_geometry(path=rel)
    _check(result.get("ok") is True, f"relative path works: {rel}")

    # by filename only
    fn = f"rwgps_{ROUTE_ID}.gpx"
    result2 = parse_gpx_artifact_geometry(path=fn)
    _check(result2.get("ok") is True, f"filename-only works: {fn}")

    # by absolute path
    abs_path = f"/opt/qbot/artifacts/exports/rwgps/rwgps_{ROUTE_ID}.gpx"
    result3 = parse_gpx_artifact_geometry(path=abs_path)
    _check(result3.get("ok") is True, f"absolute path works: {abs_path}")

    # non-existent
    result4 = parse_gpx_artifact_geometry(path="nonexistent.gpx")
    _check(result4.get("ok") is False, "nonexistent file returns ok=False")
    _check(result4.get("status") == "NOT_FOUND", "nonexistent returns NOT_FOUND")


def test_invalid_args():
    print(f"\n{'='*60}")
    print("Test: invalid args")
    print(f"{'='*60}")

    from tools.rwgps.client import parse_gpx_artifact_geometry

    # no args
    r = parse_gpx_artifact_geometry()
    _check(r.get("ok") is False, "no args → ok=False")
    _check(r.get("status") == "INVALID_ARGS", "no args → INVALID_ARGS")

    # two args
    r = parse_gpx_artifact_geometry(route_id=ROUTE_ID, artifact_id="x")
    _check(r.get("ok") is False, "two args → ok=False")


def test_no_rwgps_call():
    print(f"\n{'='*60}")
    print("Test: no RWGPS API call during geometry readout")
    print(f"{'='*60}")

    from tools.rwgps.client import (
        parse_gpx_artifact_geometry,
        _resolve_route_record as real_resolve,
    )

    original_resolve = real_resolve

    def assert_no_resolve(*args, **kwargs):
        raise AssertionError("RWGPS API was called during geometry readout!")

    import tools.rwgps.client as _client_module

    _client_module._resolve_route_record = assert_no_resolve
    try:
        result = parse_gpx_artifact_geometry(route_id=ROUTE_ID)
        _check(result.get("ok") is True, "geometry readout succeeded without RWGPS call")
    except AssertionError as exc:
        _check(False, str(exc))
    finally:
        _client_module._resolve_route_record = original_resolve


def test_not_writing_to_db():
    print(f"\n{'='*60}")
    print("Test: geometry readout does not write to database")
    print(f"{'='*60}")

    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )

    # Snapshot counts before
    before = {}
    for tbl in ("route_artifacts", "artifacts", "route_parse_results"):
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM qbot_v2.{tbl}").fetchone()
        before[tbl] = row["cnt"]

    from tools.rwgps.client import parse_gpx_artifact_geometry

    result = parse_gpx_artifact_geometry(route_id=ROUTE_ID)
    _check(result.get("ok") is True, "geometry readout ok")

    after = {}
    for tbl in ("route_artifacts", "artifacts", "route_parse_results"):
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM qbot_v2.{tbl}").fetchone()
        after[tbl] = row["cnt"]

    conn.close()

    for tbl in before:
        same = before[tbl] == after[tbl]
        _check(same, f"qbot_v2.{tbl} count unchanged ({before[tbl]} → {after[tbl]})")


def test_dump_summary(result):
    """Optionally write a diagnostic JSON artifact."""
    diag_path = Path(
        f"/opt/qbot/artifacts/projects/tuscany_2026/rwgps_{ROUTE_ID}_geometry_summary.json"
    )

    summary = {
        "route_id": ROUTE_ID,
        "artifact_id": result.get("artifact_id"),
        "project_id": result.get("project_id"),
        "path": result.get("relative_path"),
        "absolute_path": result.get("absolute_path"),
        "filename": result.get("filename"),
        "size_bytes": result.get("size_bytes"),
        "point_count": result.get("point_count"),
        "distance_km": result.get("distance_km"),
        "elevation_gain_m": result.get("elevation_gain_m"),
        "elevation_loss_m": result.get("elevation_loss_m"),
        "min_elevation_m": result.get("min_elevation_m"),
        "max_elevation_m": result.get("max_elevation_m"),
        "bbox": result.get("bbox"),
        "start_point": result.get("start_point"),
        "end_point": result.get("end_point"),
        "track_length_km": result.get("track_length_km"),
        "control_points_every_5km": result.get("control_points_every_5km"),
        "geometry_sample": result.get("geometry_sample"),
        "analytics_source": result.get("analytics_source"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    diag_path.parent.mkdir(parents=True, exist_ok=True)
    diag_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  📄 Geometry summary written: {diag_path}")
    return diag_path


def main():
    print(f"GPX Geometry Readout Test")
    print(f"Route ID: {ROUTE_ID}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()

    # Resolve artifact_id once
    global ARTIFACT_ID
    ARTIFACT_ID = resolve_artifact_id()
    print(f"Resolved artifact_id: {ARTIFACT_ID}")

    result = test_by_route_id()
    test_by_artifact_id()
    test_by_path()
    test_invalid_args()
    test_no_rwgps_call()
    test_not_writing_to_db()

    if result and result.get("ok"):
        test_dump_summary(result)

    print(f"\n{'='*60}")
    print(f"Results: {_ok} passed, {_fail} failed")
    print(f"{'='*60}")

    if _fail:
        sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
