#!/usr/bin/env python3
"""Writer kanonicznej warstwy przewyzszen/podjazdow (2C).

Lustro route_base_store / route_surface_store: ten sam _db_conn, rozwiazanie
route_base po route_base_id (lub route_id), transakcja, CLI z --repeat.

Buduje gesty profil wysokosci (SRTM30m) i wykrywa podjazdy (progi Karoo) przez
qbot3/routes/route_elevation_engine, po czym zapisuje do:
- qbot_v2.route_elevation_samples (profil; upsert po (route_base_id, sample_index)),
- qbot_v2.route_climb_events (podjazdy; delete+insert, bo liczba zmienna).

NIE rusza route_base, route_analysis_run, surface/landcover/poi, pogody ani raportu.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed
from qbot3.routes.route_elevation_engine import (
    ClimbEvent,
    ElevationSample,
    build_route_elevation_profile,
    detect_route_climb_events,
    summarize,
)

ARTIFACTS_ROOT = Path("/opt/qbot/artifacts")


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


def _normalize_route_id(route_id: str | int) -> str:
    text = str(route_id).strip()
    if not text:
        raise ValueError("route_id required")
    return text


def _route_base_row(conn, *, route_base_id: int | None = None, route_id: str | None = None) -> dict[str, Any] | None:
    if route_base_id is not None:
        row = conn.execute(
            """
            SELECT route_base_id, route_id, route_artifact_id, route_version_key, status, source_path
            FROM qbot_v2.route_base
            WHERE route_base_id = %s
            LIMIT 1
            """,
            (route_base_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT route_base_id, route_id, route_artifact_id, route_version_key, status, source_path
            FROM qbot_v2.route_base
            WHERE route_id = %s
            ORDER BY updated_at DESC, route_base_id DESC
            LIMIT 1
            """,
            (route_id,),
        ).fetchone()
    return dict(row) if row else None


def _load_points(base_row: dict[str, Any]) -> list[tuple[float, float, float]]:
    """Punkty trasy (distance_m, lat, lon) z GPX wskazanego przez route_base.source_path.
    Fallback: load_route_base_source(route_id) jesli sciezka nieobecna."""
    source_path = base_row.get("source_path")
    file_path = Path(str(source_path)) if source_path else None
    if not (file_path and file_path.exists()):
        from qbot3.routes.route_base_store import load_route_base_source
        src = load_route_base_source(str(base_row["route_id"]))
        return [(float(p["cum_m"]), float(p["lat"]), float(p["lon"])) for p in src.detailed_points]
    points = _parse_gpx_file_detailed(file_path)
    if not points:
        raise ValueError(f"Brak punktow GPX w {file_path}")
    return [
        (round(float(p.get("cum_km") or 0.0) * 1000.0, 3), float(p["lat"]), float(p["lon"]))
        for p in points
    ]


def build_rows(
    samples: list[ElevationSample],
    climbs: list[ClimbEvent],
    route_base_id: int,
    route_version_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Czysta funkcja: dataclasses silnika -> wiersze DB. Testowalna offline."""
    sample_rows = [
        {
            "route_base_id": route_base_id,
            "route_version_key": route_version_key,
            "sample_index": s.sample_index,
            "distance_m": s.distance_m,
            "lat": s.lat,
            "lon": s.lon,
            "elevation_m": s.elevation_m,
            "source": s.source,
            "smoothing_version": s.smoothing_version,
            "elevation_meta_json": {},
        }
        for s in samples
    ]
    event_rows = [
        {
            "route_base_id": route_base_id,
            "route_version_key": route_version_key,
            "event_index": c.event_index,
            "start_m": c.start_m,
            "end_m": c.end_m,
            "length_m": c.length_m,
            "elevation_gain_m": c.elevation_gain_m,
            "avg_gradient_pct": c.avg_gradient_pct,
            "max_gradient_pct": c.max_gradient_pct,
            "severity": c.severity,
            "segments_json": [asdict(seg) for seg in c.segments],
            "source": c.source,
            "detection_version": c.detection_version,
            "climb_meta_json": {},
        }
        for c in climbs
    ]
    return sample_rows, event_rows


def _upsert_samples(conn, rows: list[dict[str, Any]]) -> int:
    for r in rows:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_elevation_samples (
                route_base_id, route_version_key, sample_index, distance_m,
                lat, lon, elevation_m, source, smoothing_version, elevation_meta_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (route_base_id, sample_index) DO UPDATE SET
                route_version_key = EXCLUDED.route_version_key,
                distance_m = EXCLUDED.distance_m,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                elevation_m = EXCLUDED.elevation_m,
                source = EXCLUDED.source,
                smoothing_version = EXCLUDED.smoothing_version,
                elevation_meta_json = EXCLUDED.elevation_meta_json,
                updated_at = now()
            """,
            (
                r["route_base_id"], r["route_version_key"], r["sample_index"], r["distance_m"],
                r["lat"], r["lon"], r["elevation_m"], r["source"], r["smoothing_version"],
                json.dumps(r["elevation_meta_json"], ensure_ascii=False),
            ),
        )
    return len(rows)


def _replace_events(conn, route_base_id: int, rows: list[dict[str, Any]]) -> int:
    conn.execute("DELETE FROM qbot_v2.route_climb_events WHERE route_base_id = %s", (route_base_id,))
    for r in rows:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_climb_events (
                route_base_id, route_version_key, event_index, start_m, end_m, length_m,
                elevation_gain_m, avg_gradient_pct, max_gradient_pct, severity,
                segments_json, source, detection_version, climb_meta_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
            """,
            (
                r["route_base_id"], r["route_version_key"], r["event_index"],
                r["start_m"], r["end_m"], r["length_m"], r["elevation_gain_m"],
                r["avg_gradient_pct"], r["max_gradient_pct"], r["severity"],
                json.dumps(r["segments_json"], ensure_ascii=False),
                r["source"], r["detection_version"],
                json.dumps(r["climb_meta_json"], ensure_ascii=False),
            ),
        )
    return len(rows)


def _content_hash(conn, route_base_id: int) -> str:
    """Hash deterministyczny zawartosci DB dla trasy — dowod idempotencji."""
    s = conn.execute(
        """
        SELECT sample_index, distance_m, lat, lon, elevation_m, source, smoothing_version
        FROM qbot_v2.route_elevation_samples WHERE route_base_id = %s ORDER BY sample_index
        """,
        (route_base_id,),
    ).fetchall()
    e = conn.execute(
        """
        SELECT event_index, start_m, end_m, length_m, elevation_gain_m, avg_gradient_pct,
               max_gradient_pct, severity, segments_json, source, detection_version
        FROM qbot_v2.route_climb_events WHERE route_base_id = %s ORDER BY event_index
        """,
        (route_base_id,),
    ).fetchall()
    payload = json.dumps([[dict(r) for r in s], [dict(r) for r in e]],
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_route_elevation(
    *,
    route_base_id: int | None = None,
    route_id: str | int | None = None,
) -> dict[str, Any]:
    with _db_conn() as conn:
        base = _route_base_row(
            conn,
            route_base_id=int(route_base_id) if route_base_id is not None else None,
            route_id=_normalize_route_id(route_id) if route_id is not None else None,
        )
        if not base:
            raise LookupError(f"Brak route_base (route_base_id={route_base_id!r}, route_id={route_id!r})")
        rb_id = int(base["route_base_id"])
        rvk = str(base["route_version_key"])

        points = _load_points(base)
        samples = build_route_elevation_profile(points)
        climbs = detect_route_climb_events(samples)
        sample_rows, event_rows = build_rows(samples, climbs, rb_id, rvk)

        with conn.transaction():
            n_samples = _upsert_samples(conn, sample_rows)
            n_events = _replace_events(conn, rb_id, event_rows)

        content_hash = _content_hash(conn, rb_id)
        summary = summarize(samples)

    return {
        "status": "OK",
        "route_id": str(base["route_id"]),
        "route_base_id": rb_id,
        "route_version_key": rvk,
        "elevation_samples_count": n_samples,
        "climb_events_count": n_events,
        "content_hash": content_hash,
        "summary": summary,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write route elevation samples + climb events for a route_id.")
    parser.add_argument("route_id", help="RWGPS route_id")
    parser.add_argument("--repeat", type=int, default=1, help="Run N times for idempotency checks")
    args = parser.parse_args(argv)

    result: dict[str, Any] | None = None
    for run_idx in range(max(1, int(args.repeat))):
        result = ensure_route_elevation(route_id=args.route_id)
        print(json.dumps({
            "run": run_idx + 1,
            "route_id": result["route_id"],
            "route_base_id": result["route_base_id"],
            "route_version_key": result["route_version_key"],
            "elevation_samples_count": result["elevation_samples_count"],
            "climb_events_count": result["climb_events_count"],
            "content_hash": result["content_hash"],
            "ascent_smoothed_m": result["summary"]["ascent_smoothed_m"],
        }, ensure_ascii=False, sort_keys=True))
    return 0 if result else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
