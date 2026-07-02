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

# Najciasniejszy TTL wsrod dostawcow (google_places=14 dni, patrz _stale_after_for_item).
# Cache starszy niz to NIE jest juz uzywany biernie — ensure_route_poi wymusza
# swiezy fetch zamiast go przepisywac z falszywa data "teraz".
POI_CACHE_MAX_AGE_DAYS = 14


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


def _cached_route_poi_analysis(route_id: str) -> tuple[dict[str, Any], datetime] | None:
    """Zwraca (payload, prawdziwa_data_pliku_na_dysku) albo None gdy brak cache.

    2026-07-02 decyzja: fetched_at zapisywany do route_poi_layer MUSI odzwierciedlac
    kiedy dane naprawde przyszly z Google/OSM, nie moment wywolania ensure_route_poi.
    Wczesniej kazde wywolanie ensure_route_poi wstawialo tu datetime.now(), wiec
    stale_after (licznik przeterminowania) nigdy sie nie zbliezal — zbadano na zywo:
    trasa 55864231 miala w bazie fetched_at=2026-07-01, a prawdziwy plik cache byl
    z 2026-06-30 (prawie 2 dni klamstwa, ktore urosloby przy kazdym kolejnym wywolaniu).
    Zgodnie z docs/DECISIONS.md ("Polstalosc i swiezosc POI"): fetched_at ma byc
    prawdziwe, a gdy dane sa stare — system ma odswiezyc zrodlo albo ostrzec.
    """
    patterns = [
        ARTIFACTS_ROOT / "reports" / f"poi_analysis_{route_id}_*.json",
        ARTIFACTS_ROOT / "reports" / f"tuscany_2026_stage_01_poi_analysis_{route_id}_*.json",
        ARTIFACTS_ROOT / "old" / "reports" / f"poi_analysis_{route_id}_*.json",
        ARTIFACTS_ROOT / "old" / "reports" / f"tuscany_2026_stage_01_poi_analysis_{route_id}_*.json",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(sorted(pattern.parent.glob(pattern.name)))
    if not candidates:
        return None

    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict) and str(payload.get("route_id") or "").strip() == route_id:
        payload.setdefault("source_report_path", str(latest))
        payload.setdefault("analysis_cache_path", str(latest))
        real_fetched_at = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
        return payload, real_fetched_at
    return None


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
        cached = _cached_route_poi_analysis(route_id)
        analysis: dict[str, Any] | None = None
        fetched_at: datetime | None = None
        if cached is not None:
            cached_payload, cached_fetched_at = cached
            cache_age = datetime.now(timezone.utc) - cached_fetched_at
            if cache_age <= timedelta(days=POI_CACHE_MAX_AGE_DAYS):
                analysis = cached_payload
                fetched_at = cached_fetched_at
            # cache istnieje ale jest przeterminowany (> POI_CACHE_MAX_AGE_DAYS) ->
            # traktujemy jak brak cache i lecimy w dol po swieze dane (refresh, nie WARN)

        if analysis is None:
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

        with conn.transaction():
            poi_layer_count = _upsert_route_poi_layer(conn, rows)
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
