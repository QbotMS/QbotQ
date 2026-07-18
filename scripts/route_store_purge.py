#!/usr/bin/env python3
"""Kompletne czyszczenie trasy z route store po numerze (route_id).

Domyslnie DRY-RUN (tylko raport). Realne kasowanie wymaga --confirm.

Kasuje (dzieki ON DELETE CASCADE wystarcza skasowac korzenie):
  - route_base   (WHERE route_id) -> kaskada: axis_segments, climb_events,
                 elevation_samples, landcover_layer, poi_layer, attraction_run,
                 attraction_layer, shade_layer,
                 surface_layer, analysis_run, precompute_jobs
  - route_artifacts (WHERE route_id) -> kaskada: route_frames, route_frame_weather,
                 route_parse_results, route_surface_profiles -> route_surface_segments
  - artifacts    (surowka: idempotency_key LIKE 'rwgps_export:<id>:%')
  - pliki na dysku wskazane przez rekordy (tylko wewnatrz ARTIFACTS_ROOT)

NIE kasuje przejazdow: ride_frames.route_artifact_id ma ON DELETE SET NULL,
wiec jazdy zostaja, tylko odpiete od trasy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")

# tabele kaskadowane po route_base_id
BASE_CHILDREN = [
    "route_axis_segments", "route_climb_events", "route_elevation_samples",
    "route_landcover_layer", "route_poi_layer", "route_attraction_run",
    "route_attraction_layer", "route_shade_layer",
    "route_surface_layer", "route_analysis_run", "route_precompute_jobs",
]
# tabele kaskadowane po route_artifact_id
ARTIFACT_CHILDREN = [
    "route_frames", "route_frame_weather", "route_parse_results",
    "route_surface_profiles",
]


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )


def _scalar(conn, sql, params):
    row = conn.execute(sql, params).fetchone()
    return list(row.values())[0] if row else 0


def _collect(conn, route_id: str) -> dict:
    rid = str(route_id).strip()
    artifacts = [r["id"] for r in conn.execute(
        "SELECT id FROM qbot_v2.route_artifacts WHERE route_id::text=%s", (rid,)).fetchall()]
    bases = [r["route_base_id"] for r in conn.execute(
        "SELECT route_base_id FROM qbot_v2.route_base WHERE route_id::text=%s", (rid,)).fetchall()]

    counts: dict[str, int] = {}
    counts["route_artifacts"] = len(artifacts)
    counts["route_base"] = len(bases)
    for t in BASE_CHILDREN:
        counts[t] = _scalar(conn,
            f"SELECT count(*) FROM qbot_v2.{t} WHERE route_base_id = ANY(%s)", (bases,)) if bases else 0
    for t in ARTIFACT_CHILDREN:
        counts[t] = _scalar(conn,
            f"SELECT count(*) FROM qbot_v2.{t} WHERE route_artifact_id = ANY(%s)", (artifacts,)) if artifacts else 0
    counts["route_surface_segments"] = _scalar(conn,
        "SELECT count(*) FROM qbot_v2.route_surface_segments s "
        "JOIN qbot_v2.route_surface_profiles p ON p.id=s.route_surface_profile_id "
        "WHERE p.route_artifact_id = ANY(%s)", (artifacts,)) if artifacts else 0
    counts["artifacts_raw"] = _scalar(conn,
        "SELECT count(*) FROM qbot_v2.artifacts WHERE idempotency_key LIKE %s",
        (f"rwgps_export:{rid}:%",))
    detached = _scalar(conn,
        "SELECT count(*) FROM qbot_v2.ride_frames WHERE route_artifact_id = ANY(%s)",
        (artifacts,)) if artifacts else 0

    # pliki na dysku
    files: list[str] = []
    for r in conn.execute(
        "SELECT artifact_path FROM qbot_v2.route_artifacts WHERE route_id::text=%s AND artifact_path IS NOT NULL",
        (rid,)).fetchall():
        files.append(r["artifact_path"])
    for r in conn.execute(
        "SELECT file_path FROM qbot_v2.artifacts WHERE idempotency_key LIKE %s AND file_path IS NOT NULL",
        (f"rwgps_export:{rid}:%",)).fetchall():
        files.append(r["file_path"])

    # tylko istniejace pliki wewnatrz ARTIFACTS_ROOT (sciezki wzgledne -> od ARTIFACTS_ROOT)
    safe_files, skipped, seen = [], [], set()
    for f in files:
        if not f:
            continue
        p = Path(f)
        if not p.is_absolute():
            p = ARTIFACTS_ROOT / p
        try:
            rp = p.resolve()
            inside = ARTIFACTS_ROOT in rp.parents or rp == ARTIFACTS_ROOT
        except Exception:
            inside = False
        key = str(rp) if inside else f
        if key in seen:
            continue
        seen.add(key)
        if inside and rp.exists():
            safe_files.append(str(rp))
        else:
            skipped.append(f)

    return {"route_id": rid, "artifact_ids": artifacts, "base_ids": bases,
            "counts": counts, "rides_detached": detached,
            "files_to_delete": safe_files, "files_skipped": skipped}


def purge_route(route_id: str, confirm: bool = False) -> dict:
    rid = str(route_id).strip()
    if not rid:
        return {"status": "ERROR", "error": "route_id required"}
    with _conn() as conn:
        info = _collect(conn, rid)
        total = sum(info["counts"].values())
        if total == 0 and not info["files_to_delete"]:
            return {"status": "NOOP", "mode": "dry_run" if not confirm else "delete",
                    **info, "note": f"Brak danych dla trasy {rid} - nic do usuniecia."}
        if not confirm:
            return {"status": "DRY_RUN", "mode": "dry_run",
                    "note": "Podglad. Aby usunac, uruchom z --confirm.", **info}
        # realne kasowanie w jednej transakcji
        deleted = {}
        deleted["route_base"] = conn.execute(
            "DELETE FROM qbot_v2.route_base WHERE route_id::text=%s", (rid,)).rowcount
        deleted["route_artifacts"] = conn.execute(
            "DELETE FROM qbot_v2.route_artifacts WHERE route_id::text=%s", (rid,)).rowcount
        deleted["artifacts_raw"] = conn.execute(
            "DELETE FROM qbot_v2.artifacts WHERE idempotency_key LIKE %s",
            (f"rwgps_export:{rid}:%",)).rowcount
        conn.commit()
        # pliki na dysku po udanym commicie
        removed_files, file_errors = [], []
        for f in info["files_to_delete"]:
            try:
                Path(f).unlink()
                removed_files.append(f)
            except Exception as exc:
                file_errors.append(f"{f}: {exc}")
        return {"status": "DELETED", "mode": "delete", "route_id": rid,
                "db_deleted_roots": deleted, "cascaded_children_estimate": info["counts"],
                "rides_detached": info["rides_detached"],
                "files_removed": removed_files, "file_errors": file_errors}


def main() -> None:
    ap = argparse.ArgumentParser(description="Kompletne czyszczenie trasy z route store po numerze.")
    ap.add_argument("route_id")
    ap.add_argument("--confirm", action="store_true", help="Wykonaj realne usuniecie (domyslnie tylko podglad).")
    args = ap.parse_args()
    print(json.dumps(purge_route(args.route_id, confirm=args.confirm), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
