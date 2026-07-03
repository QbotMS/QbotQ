"""Minimal writer for canonical route POI layer.

This module writes qbot_v2.route_poi_layer from the existing route POI
analysis result. It does not compute surface, land-cover, elevation,
weather, WBGT, or analysis runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from qbot3.artifacts.route_analyzer import analyze_route_poi_artifact


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
            SELECT route_base_id, route_id, route_artifact_id, route_version_key, source_path, distance_m, status
            FROM qbot_v2.route_base
            WHERE route_base_id = %s
            LIMIT 1
            """,
            (route_base_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT route_base_id, route_id, route_artifact_id, route_version_key, source_path, distance_m, status
            FROM qbot_v2.route_base
            WHERE route_id = %s
            ORDER BY updated_at DESC, route_base_id DESC
            LIMIT 1
            """,
            (route_id,),
        ).fetchone()
    return dict(row) if row else None


def _resolve_source_path(route_base: dict[str, Any], conn) -> Path:
    source_path = str(route_base.get("source_path") or "").strip()
    if source_path:
        candidate = Path(source_path)
        if candidate.exists():
            return candidate

    route_artifact_id = route_base.get("route_artifact_id")
    if route_artifact_id is not None:
        row = conn.execute(
            """
            SELECT artifact_path, artifact_relative_path
            FROM qbot_v2.route_artifacts
            WHERE id = %s
            LIMIT 1
            """,
            (route_artifact_id,),
        ).fetchone()
        if row:
            artifact_path = str(row.get("artifact_path") or "").strip()
            if artifact_path:
                candidate = Path(artifact_path)
                if candidate.exists():
                    return candidate
            artifact_relative_path = str(row.get("artifact_relative_path") or "").strip()
            if artifact_relative_path:
                candidate = ARTIFACTS_ROOT / artifact_relative_path
                if candidate.exists():
                    return candidate

    raise FileNotFoundError(f"Could not resolve source GPX for route_base_id={route_base['route_base_id']}")


def _provider_for_item(item: dict[str, Any]) -> str:
    provider_hint = str(item.get("provider") or "").strip().lower()
    if provider_hint:
        return provider_hint
    if item.get("google_place_id") or item.get("open_source") == "google":
        return "google_places"
    if item.get("osm_type") == "google_places":
        return "google_places"
    return "overpass"


def _stable_poi_key(
    *,
    provider: str,
    category: str | None,
    source_place_id: str | None,
    name: str | None,
    lat: float | None,
    lon: float | None,
    route_km: float | None,
    distance_from_route_m: float | None,
) -> str:
    if source_place_id:
        return f"{provider}:{source_place_id}"

    payload = {
        "provider": provider,
        "category": category,
        "name": name,
        "lat": round(float(lat), 6) if lat is not None else None,
        "lon": round(float(lon), 6) if lon is not None else None,
        "route_km": round(float(route_km), 3) if route_km is not None else None,
        "distance_from_route_m": round(float(distance_from_route_m), 1) if distance_from_route_m is not None else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{provider}:{category or 'poi'}:{digest}"


def _confidence_for_item(provider: str, source_place_id: str | None, item: dict[str, Any]) -> str:
    if provider == "google_places":
        return "high" if source_place_id else "medium"
    if source_place_id or item.get("osm_id") is not None:
        return "medium"
    return "low"


def _stale_after_for_item(provider: str, fetched_at: datetime) -> datetime:
    ttl_days = 14 if provider == "google_places" else 30
    return fetched_at + timedelta(days=ttl_days)


def _poi_rows_for_items(
    *,
    route_base: dict[str, Any],
    items: list[dict[str, Any]],
    category: str,
    fetched_at: datetime,
    analysis_status: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    route_version_key = str(route_base["route_version_key"])
    route_id = str(route_base["route_id"])
    route_base_id = int(route_base["route_base_id"])
    route_artifact_id = route_base.get("route_artifact_id")

    for item in items:
        if not isinstance(item, dict):
            continue

        provider = _provider_for_item(item)
        lat = item.get("lat")
        lon = item.get("lon")
        route_km = item.get("route_km")
        distance_from_route_m = item.get("distance_to_track_m")
        name = str(item.get("name") or "").strip() or None
        item_category = str(item.get("category") or category or "").strip() or None
        source_place_id = (
            str(item.get("source_place_id") or "").strip()
            or str(item.get("google_place_id") or "").strip()
            or (str(item.get("osm_id")).strip() if item.get("osm_id") not in (None, "") else "")
            or None
        )
        poi_key = _stable_poi_key(
            provider=provider,
            category=item_category,
            source_place_id=source_place_id,
            name=name,
            lat=float(lat) if lat is not None else None,
            lon=float(lon) if lon is not None else None,
            route_km=float(route_km) if route_km is not None else None,
            distance_from_route_m=float(distance_from_route_m) if distance_from_route_m is not None else None,
        )
        opening_hours = item.get("opening_hours_osm")
        if opening_hours in ("", None):
            opening_hours = None

        source_updated_at = fetched_at
        opening_hours_fetched_at = fetched_at if opening_hours is not None else None
        confidence = _confidence_for_item(provider, source_place_id, item)
        validity_hint = str(item.get("note") or provider).strip() or provider
        stale_after = _stale_after_for_item(provider, fetched_at)
        status = "active" if datetime.now(timezone.utc) <= stale_after else "stale"

        meta = {
            "route_base_id": route_base_id,
            "route_id": route_id,
            "route_artifact_id": route_artifact_id,
            "route_version_key": route_version_key,
            "analysis_status": analysis_status,
            "category": item_category,
            "provider": provider,
            "poi_key": poi_key,
            "source_place_id": source_place_id,
            "poi_id": source_place_id or poi_key,
            "name": name,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "km_on_route": float(route_km) if route_km is not None else None,
            "distance_from_route_m": float(distance_from_route_m) if distance_from_route_m is not None else None,
            "source_tags": item.get("source_tags"),
            "note": item.get("note"),
            "g_type_pl": item.get("g_type_pl"),
            "g_rating": item.get("g_rating"),
            "g_rating_n": item.get("g_rating_n"),
        }
        meta = {key: value for key, value in meta.items() if value is not None}

        rows.append(
            {
                "route_base_id": route_base_id,
                "route_version_key": route_version_key,
                "poi_key": poi_key,
                "poi_id": source_place_id or poi_key,
                "source_place_id": source_place_id,
                "provider": provider,
                "name": name,
                "category": item_category,
                "lat": float(lat) if lat is not None else None,
                "lon": float(lon) if lon is not None else None,
                "km_on_route": float(route_km) if route_km is not None else None,
                "distance_from_route_m": float(distance_from_route_m) if distance_from_route_m is not None else None,
                "opening_hours": opening_hours,
                "opening_hours_fetched_at": opening_hours_fetched_at,
                "source_updated_at": source_updated_at,
                "confidence": confidence,
                "validity_hint": validity_hint,
                "stale_after": stale_after,
                "status": status,
                "poi_meta_json": {
                    **meta,
                    "opening_hours": opening_hours,
                },
            }
        )

    return rows


def _upsert_route_poi_layer(conn, rows: list[dict[str, Any]]) -> int:
    upserted = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO qbot_v2.route_poi_layer (
                route_base_id,
                route_version_key,
                poi_key,
                poi_id,
                source_place_id,
                provider,
                name,
                category,
                lat,
                lon,
                km_on_route,
                distance_from_route_m,
                opening_hours,
                opening_hours_fetched_at,
                source_updated_at,
                confidence,
                validity_hint,
                stale_after,
                status,
                poi_meta_json
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (route_base_id, poi_key) DO UPDATE SET
                route_version_key = EXCLUDED.route_version_key,
                poi_id = EXCLUDED.poi_id,
                source_place_id = EXCLUDED.source_place_id,
                provider = EXCLUDED.provider,
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                km_on_route = EXCLUDED.km_on_route,
                distance_from_route_m = EXCLUDED.distance_from_route_m,
                opening_hours = EXCLUDED.opening_hours,
                opening_hours_fetched_at = EXCLUDED.opening_hours_fetched_at,
                source_updated_at = EXCLUDED.source_updated_at,
                confidence = EXCLUDED.confidence,
                validity_hint = EXCLUDED.validity_hint,
                stale_after = EXCLUDED.stale_after,
                status = EXCLUDED.status,
                poi_meta_json = EXCLUDED.poi_meta_json,
                updated_at = now()
            """,
            (
                row["route_base_id"],
                row["route_version_key"],
                row["poi_key"],
                row["poi_id"],
                row["source_place_id"],
                row["provider"],
                row["name"],
                row["category"],
                row["lat"],
                row["lon"],
                row["km_on_route"],
                row["distance_from_route_m"],
                row["opening_hours"],
                row["opening_hours_fetched_at"],
                row["source_updated_at"],
                row["confidence"],
                row["validity_hint"],
                row["stale_after"],
                row["status"],
                json.dumps(row["poi_meta_json"], ensure_ascii=False),
            ),
        )
        upserted += 1
    return upserted


def _build_poi_meta_row(route_base: dict[str, Any], analysis: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
    """Zbiera metadane JAKOSCI analizy POI (poziom trasy) do jednego wiersza route_poi_meta.

    Wszystkie pola pochodza z analyze_route_poi_artifact (pobranie na zywo). "Braki chunkow"
    (missing_chunks) sa artefaktem momentu pobrania - nie da sie ich odtworzyc z zapisanych
    punktow, dlatego utrwalamy je tu, zeby raport mogl uczciwie ostrzec o niepelnym pokryciu.
    """
    buffers = dict(analysis.get("buffers") or {})
    missing_chunks = list(analysis.get("missing_chunks") or [])

    def _num(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return {
        "route_base_id": int(route_base["route_base_id"]),
        "route_version_key": route_base["route_version_key"],
        "analysis_status": str(analysis.get("status") or analysis.get("analysis_status") or "UNKNOWN").upper(),
        "supply_status": analysis.get("supply_status"),
        "technical_completeness": analysis.get("technical_completeness"),
        "supply_longest_gap_km": _num(analysis.get("supply_longest_gap_km")),
        "supply_longest_gap_from_km": _num(analysis.get("supply_longest_gap_from_km")),
        "supply_open_count": _int(analysis.get("supply_open_count")),
        "supply_unknown_count": _int(analysis.get("supply_unknown_count")),
        "supply_closed_count": _int(analysis.get("supply_closed_count")),
        "poi_source_mode": analysis.get("poi_source_mode"),
        "google_supply_count": _int(analysis.get("google_supply_count")),
        "missing_chunks_count": _int(analysis.get("missing_chunks_count")) if analysis.get("missing_chunks_count") is not None else len(missing_chunks),
        "km_from": _num(analysis.get("km_from")),
        "km_to": _num(analysis.get("km_to")),
        "avg_speed_kmh": _num(buffers.get("avg_speed_kmh")),
        "fetched_at": fetched_at,
        "missing_chunks_json": json.dumps(missing_chunks, ensure_ascii=False, default=str),
        "buffers_json": json.dumps(buffers, ensure_ascii=False, default=str),
    }


def _upsert_route_poi_meta(conn, meta_row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO qbot_v2.route_poi_meta (
            route_base_id,
            route_version_key,
            analysis_status,
            supply_status,
            technical_completeness,
            supply_longest_gap_km,
            supply_longest_gap_from_km,
            supply_open_count,
            supply_unknown_count,
            supply_closed_count,
            poi_source_mode,
            google_supply_count,
            missing_chunks_count,
            km_from,
            km_to,
            avg_speed_kmh,
            fetched_at,
            missing_chunks_json,
            buffers_json
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (route_base_id) DO UPDATE SET
            route_version_key = EXCLUDED.route_version_key,
            analysis_status = EXCLUDED.analysis_status,
            supply_status = EXCLUDED.supply_status,
            technical_completeness = EXCLUDED.technical_completeness,
            supply_longest_gap_km = EXCLUDED.supply_longest_gap_km,
            supply_longest_gap_from_km = EXCLUDED.supply_longest_gap_from_km,
            supply_open_count = EXCLUDED.supply_open_count,
            supply_unknown_count = EXCLUDED.supply_unknown_count,
            supply_closed_count = EXCLUDED.supply_closed_count,
            poi_source_mode = EXCLUDED.poi_source_mode,
            google_supply_count = EXCLUDED.google_supply_count,
            missing_chunks_count = EXCLUDED.missing_chunks_count,
            km_from = EXCLUDED.km_from,
            km_to = EXCLUDED.km_to,
            avg_speed_kmh = EXCLUDED.avg_speed_kmh,
            fetched_at = EXCLUDED.fetched_at,
            missing_chunks_json = EXCLUDED.missing_chunks_json,
            buffers_json = EXCLUDED.buffers_json,
            updated_at = now()
        """,
        (
            meta_row["route_base_id"],
            meta_row["route_version_key"],
            meta_row["analysis_status"],
            meta_row["supply_status"],
            meta_row["technical_completeness"],
            meta_row["supply_longest_gap_km"],
            meta_row["supply_longest_gap_from_km"],
            meta_row["supply_open_count"],
            meta_row["supply_unknown_count"],
            meta_row["supply_closed_count"],
            meta_row["poi_source_mode"],
            meta_row["google_supply_count"],
            meta_row["missing_chunks_count"],
            meta_row["km_from"],
            meta_row["km_to"],
            meta_row["avg_speed_kmh"],
            meta_row["fetched_at"],
            meta_row["missing_chunks_json"],
            meta_row["buffers_json"],
        ),
    )


def _ensure_poi_prefs_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qbot_v2.route_poi_prefs (
            route_id text PRIMARY KEY,
            attractions_enabled boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def get_route_poi_prefs(conn, route_id: str | int) -> dict[str, Any]:
    """Preferencje POI per-trasa (trwaly przelacznik). Domyslnie atrakcje OFF."""
    _ensure_poi_prefs_table(conn)
    row = conn.execute(
        "SELECT attractions_enabled FROM qbot_v2.route_poi_prefs WHERE route_id = %s",
        (str(route_id),),
    ).fetchone()
    if not row:
        return {"attractions_enabled": False}
    val = row[0] if not isinstance(row, dict) else row.get("attractions_enabled")
    return {"attractions_enabled": bool(val)}


def set_route_poi_attractions(route_id: str | int, enabled: bool) -> dict[str, Any]:
    """Ustawia trwaly przelacznik atrakcji dla trasy (uzywane przez narzedzie Alberta)."""
    conn = _db_conn()
    try:
        _ensure_poi_prefs_table(conn)
        conn.execute(
            """
            INSERT INTO qbot_v2.route_poi_prefs (route_id, attractions_enabled, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (route_id) DO UPDATE SET
                attractions_enabled = EXCLUDED.attractions_enabled,
                updated_at = now()
            """,
            (str(route_id), bool(enabled)),
        )
        conn.commit()
        return {"route_id": str(route_id), "attractions_enabled": bool(enabled)}
    finally:
        conn.close()


def ensure_route_poi(*, route_id: str | int | None = None, route_base_id: int | None = None) -> dict[str, Any]:
    if route_id is None and route_base_id is None:
        raise ValueError("route_id or route_base_id required")

    route_id_text = _normalize_route_id(route_id) if route_id is not None else None
    conn = _db_conn()
    try:
        route_base = _route_base_row(conn, route_base_id=route_base_id, route_id=route_id_text)
        if not route_base:
            raise LookupError(f"No route_base found for route_id={route_id_text or route_base_id!r}")

        source_path = _resolve_source_path(route_base, conn)
        route_distance_km = float(route_base.get("distance_m") or 0.0) / 1000.0
        if route_distance_km <= 0:
            raise ValueError(f"route_base_id={route_base['route_base_id']} has no usable distance_m")

        route_id = str(route_base["route_id"])
        poi_prefs = get_route_poi_prefs(conn, route_id)
        # 2026-07-02 decyzja: zasilanie route_poi_layer ZAWSZE pobiera na zywo
        # (Google Places + Overpass przez analyze_route_poi_artifact). Zadnego czytania
        # starych plikow z /artifacts/reports/ — to byl przeciek granicy (writer bazy
        # wsysal cudze, niekontrolowane artefakty po samym numerze trasy). fetched_at
        # jest teraz uczciwe: to naprawde moment tego pobrania. Zniesiono mechanizm
        # POI_CACHE_MAX_AGE_DAYS (auto-refresh po 14 dniach) — odswiezenie jest jawna
        # decyzja uzytkownika (route_recompute), a raport pokazuje date danych POI.
        analysis = analyze_route_poi_artifact(
            str(source_path),
            route_id=route_id,
            artifact_id=str(route_base["route_artifact_id"]) if route_base.get("route_artifact_id") is not None else None,
            project_id=None,
            km_from=0.0,
            km_to=route_distance_km,
            buffers={
                "google_hours": True,
                "open_window": False,
                "attractions_enabled": bool(poi_prefs.get("attractions_enabled")),
                "attractions_m": 1500.0,
            },
            focus="all",
            output_format="json",
        )
        fetched_at = datetime.now(timezone.utc)
        analysis_status = str(analysis.get("status") or "UNKNOWN").upper()
        categories = (
            ("hard_resupply", "hard_resupply"),
            ("soft_food_stop", "soft_food_stop"),
            ("water", "water"),
            ("attractions", "attraction"),
            ("town_fallback_check", "town"),
        )
        rows: list[dict[str, Any]] = []
        for key, category in categories:
            rows.extend(
                _poi_rows_for_items(
                    route_base=route_base,
                    items=list(analysis.get(key) or []),
                    category=category,
                    fetched_at=fetched_at,
                    analysis_status=analysis_status,
                )
            )

        poi_meta_row = _build_poi_meta_row(route_base, analysis, fetched_at)

        # 2026-07-02 straznik zapisu: nie nadpisuj istniejacego COMPLETE wynikiem
        # gorszym (PARTIAL/ERROR). Chroni baze przed zdegradowaniem, gdy pobranie
        # akurat sie nie domknelo. Pelny wynik zawsze wygrywa.
        new_complete = str(poi_meta_row.get("technical_completeness") or "").upper() == "COMPLETE"
        if not new_complete:
            existing = conn.execute(
                "SELECT technical_completeness FROM qbot_v2.route_poi_meta WHERE route_base_id = %s",
                (int(route_base["route_base_id"]),),
            ).fetchone()
            existing_tc = ""
            if existing:
                cell = existing[0] if not isinstance(existing, dict) else existing.get("technical_completeness")
                existing_tc = str(cell or "").upper()
            if existing_tc == "COMPLETE":
                conn.rollback()
                return {
                    "status": "SKIPPED_KEPT_COMPLETE",
                    "route_id": route_base["route_id"],
                    "route_base_id": int(route_base["route_base_id"]),
                    "reason": "nowy wynik nie jest COMPLETE; zachowano istniejacy pelny wynik POI",
                    "new_technical_completeness": poi_meta_row.get("technical_completeness"),
                }

        with conn.transaction():
            # 2026-07-02: recompute ZASTEPUJE cala warstwe POI trasy (idempotencja).
            # Wczesniej UPSERT po (route_base_id, poi_key) tylko doklejal — stare
            # punkty z poprzedniego zrodla/przebiegu zostawaly (np. Overpassowe
            # towny po przejsciu na GeoNames). Najpierw kasujemy, potem wstawiamy.
            conn.execute(
                "DELETE FROM qbot_v2.route_poi_layer WHERE route_base_id = %s",
                (int(route_base["route_base_id"]),),
            )
            poi_layer_count = _upsert_route_poi_layer(conn, rows)
            _upsert_route_poi_meta(conn, poi_meta_row)
        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    summary = dict(analysis.get("summary") or {})
    return {
        "status": "OK",
        "route_id": route_base["route_id"],
        "route_base_id": int(route_base["route_base_id"]),
        "route_version_key": route_base["route_version_key"],
        "route_artifact_id": route_base["route_artifact_id"],
        "poi_layer_count": poi_layer_count,
        "analysis_status": analysis_status,
        "summary": summary,
        "route_distance_km": round(route_distance_km, 3),
        "supply_status": poi_meta_row.get("supply_status"),
        "technical_completeness": poi_meta_row.get("technical_completeness"),
        "missing_chunks_count": poi_meta_row.get("missing_chunks_count"),
        "fetched_at": fetched_at.isoformat(),
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write canonical route POI layer from the existing POI analysis.")
    parser.add_argument("--route-id", dest="route_id")
    parser.add_argument("--route-base-id", dest="route_base_id", type=int)
    args = parser.parse_args(argv)
    result = ensure_route_poi(route_id=args.route_id, route_base_id=args.route_base_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
