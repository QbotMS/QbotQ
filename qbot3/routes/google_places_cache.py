"""Pamiec podreczna odpowiedzi Google Places (Nearby Search) - 2026-10-06.

Po co: kazde przeliczenie trasy odpytywalo Google od nowa (05.10: te same punkty
Orlich Gniazd 3x -> limit dzienny wyczerpany, przebiegi uciete). Teraz odpowiedz dla
tego samego punktu/promienia/typow jest brana z bazy przez TTL dni i NIE zuzywa limitu
(google_places_budget) ani darmowego progu Google.

Klucz: lat/lon zaokraglone do 4 miejsc (~11 m), promien, posortowane typy, maxResultCount,
wersja maski pol. Zmiana maski/liczby wynikow -> nowy klucz (stare wpisy wygasaja same).
Tabela: qbot_v2.google_places_cache. TTL: QBOT_GOOGLE_CACHE_TTL_DAYS (domyslnie 30),
wylacznik: QBOT_GOOGLE_CACHE=0. Blad bazy = brak cache (zapytanie idzie normalnie).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import psycopg

log = logging.getLogger("qbot.google_cache")
FIELDMASK_VERSION = "v1"  # podbic przy zmianie X-Goog-FieldMask w route_analyzer
_ensured = False


def enabled() -> bool:
    return os.getenv("QBOT_GOOGLE_CACHE", "1").strip() not in {"0", "false", "no"}


def ttl_days() -> int:
    try:
        return max(1, min(int(os.getenv("QBOT_GOOGLE_CACHE_TTL_DAYS", "30")), 365))
    except ValueError:
        return 30


def cache_key(lat: float, lon: float, radius_m: float, included_types: list[str] | None, max_results: int) -> str:
    raw = json.dumps({
        "lat": round(float(lat), 4), "lon": round(float(lon), 4), "r": round(float(radius_m)),
        "t": sorted(included_types or []), "n": int(max_results), "f": FIELDMASK_VERSION,
    }, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def _ensure(conn) -> None:
    global _ensured
    if _ensured:
        return
    conn.execute(
        "CREATE TABLE IF NOT EXISTS qbot_v2.google_places_cache ("
        "cache_key text PRIMARY KEY, request_json jsonb NOT NULL, places_json jsonb NOT NULL, "
        "fetched_at timestamptz NOT NULL DEFAULT now())"
    )
    _ensured = True


def get(key: str) -> list[dict[str, Any]] | None:
    if not enabled():
        return None
    try:
        with _conn() as conn:
            _ensure(conn)
            row = conn.execute(
                "SELECT places_json FROM qbot_v2.google_places_cache "
                "WHERE cache_key=%s AND fetched_at > now() - make_interval(days => %s)",
                (key, ttl_days()),
            ).fetchone()
        return list(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("google cache get failed: %s", exc)
        return None


def put(key: str, request: dict[str, Any], places: list[dict[str, Any]]) -> None:
    if not enabled():
        return
    try:
        with _conn() as conn:
            _ensure(conn)
            conn.execute(
                "INSERT INTO qbot_v2.google_places_cache (cache_key, request_json, places_json, fetched_at) "
                "VALUES (%s, %s::jsonb, %s::jsonb, now()) ON CONFLICT (cache_key) DO UPDATE SET "
                "request_json=EXCLUDED.request_json, places_json=EXCLUDED.places_json, fetched_at=now()",
                (key, json.dumps(request, ensure_ascii=False), json.dumps(places, ensure_ascii=False)),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("google cache put failed: %s", exc)


def has(key: str) -> bool:
    return get(key) is not None
