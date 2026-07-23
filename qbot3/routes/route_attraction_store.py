"""Atomic store and shared reader for canonical route attractions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from qbot3.routes.route_attraction_engine import ALGORITHM_VERSION, rank_candidates, result_hash


def _description(row: dict[str, Any]) -> str:
    parts = [row.get("category_label"), f"ok. {row.get('visit_min')} min" if row.get("visit_min") else None]
    if row.get("why"):
        parts.append(row["why"])
    if row.get("nearby"):
        parts.append("w pobliżu: " + ", ".join(row["nearby"][:3]))
    return " · ".join(str(part) for part in parts if part)


def _publishable_attraction_run(*, sources_complete: bool, candidate_count: int) -> bool:
    return bool(sources_complete and int(candidate_count) >= 1)


def get_route_attractions(
    conn,
    route_base_id: int,
    *,
    km_from: float | None = None,
    km_to: float | None = None,
    tier: str = "candidates",
) -> list[dict[str, Any]] | None:
    """Read one published version. None means schema/data absent: use legacy."""
    # A Planner day is only a geometry slice. Reuse the parent's published
    # attraction run and remap km to the beginning of the day. This is the
    # important no-refetch boundary: no Wikipedia/Wikidata/Google call occurs.
    try:
        lineage_table = conn.execute("SELECT to_regclass('qbot_v2.route_stage_lineage')").fetchone()
        lineage_value = next(iter(lineage_table.values())) if isinstance(lineage_table, dict) else (lineage_table[0] if lineage_table else None)
        lineage = None
        if lineage_value:
            lineage = conn.execute(
                "SELECT parent_route_base_id, parent_km_from, parent_km_to "
                "FROM qbot_v2.route_stage_lineage "
                "WHERE stage_route_base_id=%s AND active=true LIMIT 1",
                (int(route_base_id),),
            ).fetchone()
        if lineage:
            inherited = dict(lineage) if isinstance(lineage, dict) else {
                "parent_route_base_id": lineage[0], "parent_km_from": lineage[1], "parent_km_to": lineage[2],
            }
            parent_start = float(inherited["parent_km_from"])
            parent_end = float(inherited["parent_km_to"])
            child_from = max(0.0, float(km_from)) if km_from is not None else 0.0
            child_to = min(parent_end - parent_start, float(km_to)) if km_to is not None else parent_end - parent_start
            rows = get_route_attractions(
                conn,
                int(inherited["parent_route_base_id"]),
                km_from=parent_start + child_from,
                km_to=parent_start + child_to,
                tier=tier,
            )
            if rows is None:
                return None
            output = []
            for original in rows:
                row = dict(original)
                row["parent_km"] = row.get("km")
                row["km"] = round(float(row["km"]) - parent_start, 1)
                row["inherited_from_route_base_id"] = int(inherited["parent_route_base_id"])
                output.append(row)
            return output
    except Exception as exc:
        if getattr(exc, "sqlstate", None) not in {"42P01", "42703"}:
            raise
        try:
            conn.rollback()
        except Exception:
            pass

    where = ["r.route_base_id=%s", "r.status='complete'", "r.published=true"]
    params: list[Any] = [int(route_base_id)]
    if tier == "recommended":
        where.append("a.is_recommended=true")
    elif tier != "candidates":
        raise ValueError("tier must be candidates or recommended")
    if km_from is not None:
        where.append("a.km_on_route >= %s")
        params.append(float(km_from))
    if km_to is not None:
        where.append("a.km_on_route <= %s")
        params.append(float(km_to))
    columns = (
        "candidate_key", "name", "category", "category_label", "km_on_route",
        "distance_from_route_m", "lat", "lon", "visit_min", "score", "selection_score",
        "candidate_rank", "is_recommended", "recommended_rank", "why", "extract",
        "wiki_url", "wikidata_id", "image_url", "rating", "rating_count", "nearby_json",
    )
    try:
        available = conn.execute(
            "SELECT to_regclass('qbot_v2.route_attraction_run') AS run_table, "
            "to_regclass('qbot_v2.route_attraction_layer') AS layer_table"
        ).fetchone()
        values = list(available.values()) if isinstance(available, dict) else list(available or [])
        if len(values) < 2 or not all(values):
            return None
        prefs_table = conn.execute("SELECT to_regclass('qbot_v2.route_poi_prefs')").fetchone()
        prefs_value = next(iter(prefs_table.values())) if isinstance(prefs_table, dict) else (prefs_table[0] if prefs_table else None)
        if prefs_value:
            preference = conn.execute(
                "SELECT attractions_enabled FROM qbot_v2.route_poi_prefs p "
                "JOIN qbot_v2.route_base b ON b.route_id=p.route_id WHERE b.route_base_id=%s",
                (int(route_base_id),),
            ).fetchone()
            enabled = (preference.get("attractions_enabled") if isinstance(preference, dict) else preference[0]) if preference else False
            if not enabled:
                return []
        published = conn.execute(
            "SELECT run_id FROM qbot_v2.route_attraction_run "
            "WHERE route_base_id=%s AND status='complete' AND published=true LIMIT 1",
            (int(route_base_id),),
        ).fetchone()
        if not published:
            return None
        rows = conn.execute(
            "SELECT a.candidate_key, a.name, a.category, a.category_label, a.km_on_route, "
            "a.distance_from_route_m, a.lat, a.lon, a.visit_min, a.score, a.selection_score, "
            "a.candidate_rank, a.is_recommended, a.recommended_rank, a.why, a.extract, "
            "a.wiki_url, a.wikidata_id, a.image_url, a.rating, a.rating_count, a.nearby_json "
            "FROM qbot_v2.route_attraction_run r "
            "JOIN qbot_v2.route_attraction_layer a ON a.run_id=r.run_id "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY a.km_on_route, a.candidate_rank",
            tuple(params),
        ).fetchall()
    except Exception as exc:
        # Rolling deployment: tolerate a schema mismatch and keep legacy output.
        if getattr(exc, "sqlstate", None) in {"42P01", "42703"}:
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        raise
    if not rows:
        return []
    output = []
    for original in rows:
        row = dict(original) if isinstance(original, dict) else dict(zip(columns, original))
        row.update({
            "km": round(float(row.pop("km_on_route")), 1),
            "dist_m": round(float(row.pop("distance_from_route_m"))) if row.get("distance_from_route_m") is not None else None,
            "place_id": row.get("candidate_key"),
            "desc": _description(row),
        })
        output.append(row)
    return output


def _insert_layer(conn, run_id: int, route_base_id: int, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_attraction_layer (
                run_id, route_base_id, candidate_key, name, category, category_label,
                km_on_route, distance_from_route_m, lat, lon, visit_min, score,
                selection_score, candidate_rank, is_recommended, recommended_rank,
                why, extract, wiki_url, wikidata_id, image_url, rating, rating_count,
                components_json, sources_json, osm_ids_json, nearby_json
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb
            )
            """,
            (run_id, route_base_id, row["candidate_key"], row["name"], row["category"],
             row["category_label"], row["km"], row["distance_m"], row["lat"], row["lon"],
             row["visit_min"], row["score"], row["selection_score"], row["candidate_rank"],
             row["is_recommended"], row["recommended_rank"], row["why"], row["extract"],
             row.get("wiki"), row.get("qid"), row.get("image"), row.get("rating"),
             row.get("rating_count"), json.dumps(row["components"], ensure_ascii=False),
             json.dumps(row["sources"], ensure_ascii=False), json.dumps(row["osm_ids"], ensure_ascii=False),
             json.dumps(row["nearby"], ensure_ascii=False)),
        )


def ensure_route_attractions(*, route_id: str | int | None = None, route_base_id: int | None = None, force: bool = False) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")
    # Heavy HTTP/DB adapters stay outside the shared WEB read path.
    from qbot3.routes.route_attraction_sources import discover_sources
    from qbot3.routes.route_poi_store import _db_conn, _resolve_source_path, _route_base_row

    conn = _db_conn()
    run_id: int | None = None
    try:
        base = _route_base_row(conn, route_base_id=route_base_id, route_id=str(route_id) if route_id is not None else None)
        if not base:
            raise LookupError(f"No route_base found for {route_id or route_base_id}")
        if not force:
            _existing = conn.execute(
                "SELECT run_id, algorithm_version, summary_json, fetched_at "
                "FROM qbot_v2.route_attraction_run "
                "WHERE route_base_id=%s AND published=true "
                "ORDER BY finished_at DESC NULLS LAST, run_id DESC LIMIT 1",
                (int(base["route_base_id"]),),
            ).fetchone()
            if _existing:
                _row = _existing if isinstance(_existing, dict) else {
                    "run_id": _existing[0], "algorithm_version": _existing[1],
                    "summary_json": _existing[2], "fetched_at": _existing[3]}
                return {
                    "status": "CACHED_KEPT",
                    "route_id": base["route_id"],
                    "route_base_id": int(base["route_base_id"]),
                    "route_version_key": str(base["route_version_key"]),
                    "run_id": int(_row["run_id"]),
                    "algorithm_version": _row["algorithm_version"],
                    "summary": _row["summary_json"],
                    "fetched_at": _row["fetched_at"],
                    "note": "istnieje opublikowany run atrakcji; pobranie z Google pominiete (force=false)",
                }
        source_path = _resolve_source_path(base, conn)
        distance_km = float(base.get("distance_m") or 0.0) / 1000.0
        if distance_km <= 0:
            raise ValueError("route has no usable distance")
        discovered = discover_sources(source_path, route_id=str(base["route_id"]), route_distance_km=distance_km)
        ranked = rank_candidates(discovered["source_rows"], discovered["google_rows"], discovered["wikidata"], distance_km)
        # Density is a target/cap for ranking, never a publication gate. A rural
        # route with one genuinely good place must publish that honest result.
        required_candidates = 1
        candidate_count = int(ranked["summary"].get("candidates") or 0)
        publishable = _publishable_attraction_run(
            sources_complete=bool(discovered["complete"]),
            candidate_count=candidate_count,
        )
        discovered["source_status"]["required_candidates"] = required_candidates
        discovered["source_status"]["candidate_count"] = candidate_count
        digest = result_hash(ranked)

        with conn.transaction():
            created = conn.execute(
                """
                INSERT INTO qbot_v2.route_attraction_run (
                    route_base_id, route_version_key, algorithm_version, status, published,
                    result_hash, source_status_json, summary_json, fetched_at, finished_at
                ) VALUES (%s,%s,%s,%s,false,%s,%s::jsonb,%s::jsonb,%s,%s)
                RETURNING run_id
                """,
                (int(base["route_base_id"]), str(base["route_version_key"]), ALGORITHM_VERSION,
                 "complete" if publishable else "partial", digest,
                 json.dumps(discovered["source_status"], ensure_ascii=False),
                 json.dumps(ranked["summary"], ensure_ascii=False), datetime.now(timezone.utc),
                 datetime.now(timezone.utc)),
            ).fetchone()
            run_id = int(created["run_id"] if isinstance(created, dict) else created[0])
            _insert_layer(conn, run_id, int(base["route_base_id"]), ranked["candidates"])
            if publishable:
                conn.execute(
                    "UPDATE qbot_v2.route_attraction_run SET published=false "
                    "WHERE route_base_id=%s AND published=true",
                    (int(base["route_base_id"]),),
                )
                conn.execute(
                    "UPDATE qbot_v2.route_attraction_run SET published=true WHERE run_id=%s",
                    (run_id,),
                )
        conn.commit()
        return {
            "status": "PUBLISHED" if publishable else "QUALITY_PARTIAL_KEPT_PREVIOUS",
            "route_id": base["route_id"], "route_base_id": int(base["route_base_id"]),
            "route_version_key": str(base["route_version_key"]),
            "run_id": run_id, "algorithm_version": ALGORITHM_VERSION,
            "summary": ranked["summary"], "source_status": discovered["source_status"],
        }
    except Exception as exc:
        conn.rollback()
        if run_id is not None:
            try:
                conn.execute(
                    "UPDATE qbot_v2.route_attraction_run SET status='failed', error=%s, finished_at=now() WHERE run_id=%s",
                    (str(exc)[:2000], run_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
        raise
    finally:
        conn.close()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and atomically publish canonical route attractions")
    parser.add_argument("--route-id")
    parser.add_argument("--route-base-id", type=int)
    args = parser.parse_args(argv)
    print(json.dumps(ensure_route_attractions(route_id=args.route_id, route_base_id=args.route_base_id),
                     ensure_ascii=False, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
