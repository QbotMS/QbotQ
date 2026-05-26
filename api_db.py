import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


_DB_CONNECT_TIMEOUT_SEC = int(os.getenv("PG_CONNECT_TIMEOUT", "5"))
_SQL_FILES = (
    "init_qbot.sql",
    "llm_planner_v1.sql",
    "rwgps_route_store_v1.sql",
)

def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=_DB_CONNECT_TIMEOUT_SEC,
    )


def _sql_path(name: str) -> Path:
    return Path(__file__).parent / "sql" / name


def _run_sql_file(conn, path: Path) -> None:
    if not path.exists():
        return
    ddl = path.read_text(encoding="utf-8")
    if ddl.strip():
        conn.execute(ddl)


def _jsonb(value):
    if value is None:
        return Jsonb({})
    return Jsonb(value)


def init_db():
    with _conn() as conn:
        for sql_name in _SQL_FILES:
            _run_sql_file(conn, _sql_path(sql_name))
        conn.commit()


def _fetch_one_dict(conn, query: str, params: tuple | None = None) -> dict | None:
    row = conn.execute(query, params or ()).fetchone()
    return dict(row) if row else None


def _infer_route_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    if stem.startswith("rwgps_"):
        candidate = stem.split("rwgps_", 1)[1].strip()
        if candidate:
            return candidate
    return stem or filename


def get_route_artifact_by_path(artifact_path: str) -> dict | None:
    with _conn() as conn:
        return _fetch_one_dict(
            conn,
            "SELECT * FROM route_artifacts WHERE artifact_path = %s",
            (artifact_path,),
        )


def get_route_artifact_by_sha256(sha256: str) -> dict | None:
    with _conn() as conn:
        return _fetch_one_dict(
            conn,
            "SELECT * FROM route_artifacts WHERE sha256 = %s ORDER BY id DESC LIMIT 1",
            (sha256,),
        )


def upsert_route_artifact(record: dict) -> dict:
    artifact_path = str(record.get("artifact_path", "")).strip()
    if not artifact_path:
        raise ValueError("artifact_path required")

    artifact_relative_path = record.get("artifact_relative_path")
    filename = str(record.get("filename") or Path(artifact_path).name).strip()
    route_id = str(record.get("route_id") or _infer_route_id_from_filename(filename)).strip()
    source = str(record.get("source") or "rwgps").strip() or "rwgps"
    export_format = str(record.get("export_format") or "gpx_track").strip() or "gpx_track"
    file_size_bytes = record.get("file_size_bytes")
    sha256 = str(record.get("sha256") or "").strip()
    if not sha256:
        raise ValueError("sha256 required")
    status = str(record.get("status") or "ok").strip() or "ok"
    parser_version = record.get("parser_version")
    source_artifact_sha256 = record.get("source_artifact_sha256") or sha256
    metadata_json = record.get("metadata_json") or {}

    with _conn() as conn:
        row = conn.execute(
            """
            INSERT INTO route_artifacts (
                route_id, source, export_format, artifact_path, artifact_relative_path,
                filename, file_size_bytes, sha256, parser_version, source_artifact_sha256,
                status, metadata_json
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s::jsonb
            )
            ON CONFLICT (artifact_path) DO UPDATE SET
                route_id = EXCLUDED.route_id,
                source = EXCLUDED.source,
                export_format = EXCLUDED.export_format,
                artifact_relative_path = EXCLUDED.artifact_relative_path,
                filename = EXCLUDED.filename,
                file_size_bytes = EXCLUDED.file_size_bytes,
                sha256 = EXCLUDED.sha256,
                updated_at = now(),
                parser_version = EXCLUDED.parser_version,
                source_artifact_sha256 = EXCLUDED.source_artifact_sha256,
                status = EXCLUDED.status,
                metadata_json = EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                route_id,
                source,
                export_format,
                artifact_path,
                artifact_relative_path,
                filename,
                file_size_bytes,
                sha256,
                parser_version,
                source_artifact_sha256,
                status,
                json.dumps(metadata_json, ensure_ascii=False),
            ),
        ).fetchone()
        conn.commit()
        return dict(row)


def upsert_route_parse_result(record: dict) -> dict:
    route_artifact_id = int(record["route_artifact_id"])
    parser_version = str(record.get("parser_version") or "").strip()
    if not parser_version:
        raise ValueError("parser_version required")
    source_artifact_sha256 = str(record.get("source_artifact_sha256") or "").strip()
    if not source_artifact_sha256:
        raise ValueError("source_artifact_sha256 required")
    summary_json = record.get("summary_json") or {}

    with _conn() as conn:
        row = conn.execute(
            """
            INSERT INTO route_parse_results (
                route_artifact_id, parser_version, source_artifact_sha256,
                track_points, distance_m, distance_km, elevation_gain_m, elevation_loss_m,
                bbox_min_lat, bbox_min_lon, bbox_max_lat, bbox_max_lon,
                start_lat, start_lon, end_lat, end_lon,
                min_ele, max_ele, looks_valid, summary_json
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (route_artifact_id, parser_version, source_artifact_sha256) DO UPDATE SET
                parsed_at = now(),
                track_points = EXCLUDED.track_points,
                distance_m = EXCLUDED.distance_m,
                distance_km = EXCLUDED.distance_km,
                elevation_gain_m = EXCLUDED.elevation_gain_m,
                elevation_loss_m = EXCLUDED.elevation_loss_m,
                bbox_min_lat = EXCLUDED.bbox_min_lat,
                bbox_min_lon = EXCLUDED.bbox_min_lon,
                bbox_max_lat = EXCLUDED.bbox_max_lat,
                bbox_max_lon = EXCLUDED.bbox_max_lon,
                start_lat = EXCLUDED.start_lat,
                start_lon = EXCLUDED.start_lon,
                end_lat = EXCLUDED.end_lat,
                end_lon = EXCLUDED.end_lon,
                min_ele = EXCLUDED.min_ele,
                max_ele = EXCLUDED.max_ele,
                looks_valid = EXCLUDED.looks_valid,
                summary_json = EXCLUDED.summary_json
            RETURNING *
            """,
            (
                route_artifact_id,
                parser_version,
                source_artifact_sha256,
                record.get("track_points"),
                record.get("distance_m"),
                record.get("distance_km"),
                record.get("elevation_gain_m"),
                record.get("elevation_loss_m"),
                record.get("bbox_min_lat"),
                record.get("bbox_min_lon"),
                record.get("bbox_max_lat"),
                record.get("bbox_max_lon"),
                record.get("start_lat"),
                record.get("start_lon"),
                record.get("end_lat"),
                record.get("end_lon"),
                record.get("min_ele"),
                record.get("max_ele"),
                record.get("looks_valid"),
                json.dumps(summary_json, ensure_ascii=False),
            ),
        ).fetchone()
        conn.commit()
        return dict(row)


def upsert_route_surface_profile(record: dict) -> dict:
    route_artifact_id = int(record["route_artifact_id"])
    enrichment_version = str(record.get("enrichment_version") or "").strip()
    if not enrichment_version:
        raise ValueError("enrichment_version required")
    source_artifact_sha256 = str(record.get("source_artifact_sha256") or "").strip()
    if not source_artifact_sha256:
        raise ValueError("source_artifact_sha256 required")
    surface_summary_json = record.get("surface_summary_json") or {}
    surface_segments_json = record.get("surface_segments_json")

    with _conn() as conn:
        row = conn.execute(
            """
            INSERT INTO route_surface_profiles (
                route_artifact_id, enrichment_version, source_artifact_sha256,
                surface_source, sample_every_m, confidence, coverage_pct,
                sampled_points, matched_points, unmatched_points, dominant_surface,
                status, surface_summary_json, surface_segments_json, surface_segments_path
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s::jsonb, %s::jsonb, %s
            )
            ON CONFLICT (route_artifact_id, enrichment_version, source_artifact_sha256, sample_every_m) DO UPDATE SET
                enriched_at = now(),
                surface_source = EXCLUDED.surface_source,
                confidence = EXCLUDED.confidence,
                coverage_pct = EXCLUDED.coverage_pct,
                sampled_points = EXCLUDED.sampled_points,
                matched_points = EXCLUDED.matched_points,
                unmatched_points = EXCLUDED.unmatched_points,
                dominant_surface = EXCLUDED.dominant_surface,
                status = EXCLUDED.status,
                surface_summary_json = EXCLUDED.surface_summary_json,
                surface_segments_json = EXCLUDED.surface_segments_json,
                surface_segments_path = EXCLUDED.surface_segments_path
            RETURNING *
            """,
            (
                route_artifact_id,
                enrichment_version,
                source_artifact_sha256,
                record.get("surface_source", "unknown"),
                record.get("sample_every_m"),
                record.get("confidence"),
                record.get("coverage_pct"),
                record.get("sampled_points"),
                record.get("matched_points"),
                record.get("unmatched_points"),
                record.get("dominant_surface"),
                record.get("status", "ok"),
                json.dumps(surface_summary_json, ensure_ascii=False),
                json.dumps(surface_segments_json, ensure_ascii=False) if surface_segments_json is not None else None,
                record.get("surface_segments_path"),
            ),
        ).fetchone()
        conn.commit()
        return dict(row)


def replace_route_surface_segments(route_surface_profile_id: int, segments: list[dict]) -> int:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM route_surface_segments WHERE route_surface_profile_id = %s",
            (route_surface_profile_id,),
        )
        inserted = 0
        for idx, segment in enumerate(segments):
            conn.execute(
                """
                INSERT INTO route_surface_segments (
                    route_surface_profile_id, segment_index, distance_m, surface,
                    confidence, source, start_lat, start_lon, end_lat, end_lon, geometry_json
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (route_surface_profile_id, segment_index) DO UPDATE SET
                    distance_m = EXCLUDED.distance_m,
                    surface = EXCLUDED.surface,
                    confidence = EXCLUDED.confidence,
                    source = EXCLUDED.source,
                    start_lat = EXCLUDED.start_lat,
                    start_lon = EXCLUDED.start_lon,
                    end_lat = EXCLUDED.end_lat,
                    end_lon = EXCLUDED.end_lon,
                    geometry_json = EXCLUDED.geometry_json
                """,
                (
                    route_surface_profile_id,
                    idx,
                    segment.get("distance_m"),
                    segment.get("surface"),
                    segment.get("confidence"),
                    segment.get("source"),
                    segment.get("start_lat"),
                    segment.get("start_lon"),
                    segment.get("end_lat"),
                    segment.get("end_lon"),
                    json.dumps(segment.get("geometry"), ensure_ascii=False) if segment.get("geometry") is not None else None,
                ),
            )
            inserted += 1
        conn.commit()
        return inserted


def rwgps_storage_overview() -> dict:
    table_names = [
        "route_artifacts",
        "route_parse_results",
        "route_surface_profiles",
        "route_surface_segments",
    ]

    def _table_exists(conn, table_name: str) -> bool:
        row = conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL AS exists",
            (f"public.{table_name}",),
        ).fetchone()
        return bool(row["exists"]) if row else False

    def _safe_count(conn, table_name: str) -> int | None:
        try:
            return int(conn.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}").fetchone()["cnt"])
        except Exception:
            return None

    def _latest_row(conn, table_name: str) -> dict | None:
        try:
            if table_name == "route_artifacts":
                query = (
                    "SELECT id, route_id, artifact_path, filename, sha256, created_at, updated_at "
                    "FROM route_artifacts ORDER BY id DESC LIMIT 1"
                )
            elif table_name == "route_parse_results":
                query = (
                    "SELECT id, route_artifact_id, parser_version, source_artifact_sha256, parsed_at "
                    "FROM route_parse_results ORDER BY id DESC LIMIT 1"
                )
            elif table_name == "route_surface_profiles":
                query = (
                    "SELECT id, route_artifact_id, enrichment_version, source_artifact_sha256, enriched_at, sample_every_m "
                    "FROM route_surface_profiles ORDER BY id DESC LIMIT 1"
                )
            else:
                query = (
                    "SELECT id, route_surface_profile_id, segment_index, surface, source "
                    "FROM route_surface_segments ORDER BY id DESC LIMIT 1"
                )
            return _fetch_one_dict(conn, query)
        except Exception:
            return None

    with _conn() as conn:
        tables = {}
        missing_tables: list[str] = []
        for table_name in table_names:
            exists = _table_exists(conn, table_name)
            tables[table_name] = {
                "exists": exists,
                "count": _safe_count(conn, table_name) if exists else None,
                "latest": _latest_row(conn, table_name) if exists else None,
            }
            if not exists:
                missing_tables.append(table_name)

    route_artifacts_count = tables["route_artifacts"]["count"] or 0
    parse_count = tables["route_parse_results"]["count"] or 0
    surface_count = tables["route_surface_profiles"]["count"] or 0
    segment_count = tables["route_surface_segments"]["count"] or 0
    schema_ready = not missing_tables

    if not schema_ready:
        status = "ERROR"
        seed_status = "MISSING_SCHEMA"
    elif route_artifacts_count == 0:
        status = "WARN"
        seed_status = "EMPTY"
    elif parse_count == 0 and surface_count == 0:
        status = "WARN"
        seed_status = "ARTIFACTS_ONLY"
    else:
        status = "OK"
        seed_status = "SEEDED"

    return {
        "status": status,
        "schema_ready": schema_ready,
        "seed_status": seed_status,
        "missing_tables": missing_tables,
        "tables": tables,
        "summary": {
            "route_artifacts_count": route_artifacts_count,
            "route_parse_results_count": parse_count,
            "route_surface_profiles_count": surface_count,
            "route_surface_segments_count": segment_count,
        },
        "recommended_actions": (
            [] if schema_ready else ["run init_db() to create RWGPS storage tables"]
        ),
    }


def save_tool_call(tool: str, args: dict, result: dict) -> int:
    args_json = json.dumps(args or {}, ensure_ascii=False)
    result_json = json.dumps(result or {}, ensure_ascii=False)
    with _conn() as conn:
        row = conn.execute(
            "INSERT INTO tool_calls (tool, args, result) VALUES (%s, %s, %s) RETURNING id",
            (tool, args_json, result_json),
        ).fetchone()
        conn.commit()
        return row["id"]


def select_tool_calls(limit: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, tool, args, result, created_at "
            "FROM tool_calls ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def ping() -> bool:
    try:
        with _conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def db_overview() -> dict:
    with _conn() as conn:
        version_row = conn.execute("SELECT version()").fetchone()
        pg_ver = version_row["version"] if version_row else "unknown"
        count = conn.execute("SELECT COUNT(*) AS cnt FROM tool_calls").fetchone()["cnt"]
        last = conn.execute(
            "SELECT created_at FROM tool_calls ORDER BY id DESC LIMIT 1"
        ).fetchone()
        rows = conn.execute(
            "SELECT result FROM tool_calls ORDER BY id DESC LIMIT 1000"
        ).fetchall()
        def _safe_count(table: str):
            try:
                return conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()["cnt"]
            except Exception:
                return None

        route_artifacts_count = _safe_count("route_artifacts")
        route_parse_results_count = _safe_count("route_parse_results")
        route_surface_profiles_count = _safe_count("route_surface_profiles")
        route_surface_segments_count = _safe_count("route_surface_segments")
    ok_count = 0
    error_count = 0
    for r in rows:
        try:
            res = json.loads(r["result"]) if isinstance(r["result"], str) else (r["result"] or {})
            error_count += 1 if "error" in res else 0
            ok_count += 1 if "error" not in res else 0
        except Exception:
            ok_count += 1
    return {
        "postgres_version": pg_ver,
        "tool_calls_count": count,
        "last_tool_call_at": last["created_at"].isoformat() if last else None,
        "status_counts": {"ok": ok_count, "error": error_count},
        "route_artifacts_count": route_artifacts_count,
        "route_parse_results_count": route_parse_results_count,
        "route_surface_profiles_count": route_surface_profiles_count,
        "route_surface_segments_count": route_surface_segments_count,
    }
