"""Lokalne źródło miejscowości (GeoNames) — offline, bez żywego API.

Zastępuje Overpassowe węzły place=* w pipeline POI. Dane pochodzą z
dumpów GeoNames (CC-BY), przefiltrowanych do klasy cech P (miasto/wieś)
i zapisanych jako lekkie pliki TSV w GEONAMES_DIR: kolumny
name, lat, lon, feature_code, population.

Skanuje WSZYSTKIE pliki *_places.tsv, więc dołożenie kolejnego kraju
(np. IT_places.tsv, ES_places.tsv na wyprawę) nie wymaga zmiany kodu.

Atrybucja: dane miejscowości pochodzą z GeoNames (https://www.geonames.org,
licencja CC-BY 4.0).
"""
from __future__ import annotations

import csv
import glob
import os
from typing import Any

GEONAMES_DIR = "/opt/qbot/artifacts/geonames"

# cache w pamięci procesu: lista rekordów wczytana raz
_PLACES_CACHE: list[dict[str, Any]] | None = None
_LOADED_FILES: tuple[str, ...] = ()


def _load_all() -> list[dict[str, Any]]:
    """Wczytuje i cache'uje wszystkie *_places.tsv z GEONAMES_DIR."""
    global _PLACES_CACHE, _LOADED_FILES
    if _PLACES_CACHE is not None:
        return _PLACES_CACHE

    records: list[dict[str, Any]] = []
    files = tuple(sorted(glob.glob(os.path.join(GEONAMES_DIR, "*_places.tsv"))))
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    try:
                        lat = float(row["lat"])
                        lon = float(row["lon"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    name = (row.get("name") or "").strip()
                    if not name:
                        continue
                    try:
                        pop = int(row.get("population") or 0)
                    except (TypeError, ValueError):
                        pop = 0
                    records.append({
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "feature_code": (row.get("feature_code") or "").strip(),
                        "population": pop,
                    })
        except OSError:
            continue

    _PLACES_CACHE = records
    _LOADED_FILES = files
    return records


def loaded_files() -> tuple[str, ...]:
    _load_all()
    return _LOADED_FILES


def places_in_bbox(bbox: dict[str, float]) -> list[dict[str, Any]]:
    """Miejscowości (klasa P) mieszczące się w podanym bbox.

    bbox: {min_lat, max_lat, min_lon, max_lon}. Zwraca surowe rekordy
    (name, lat, lon, feature_code, population); projekcję na trasę i
    liczenie route_km/distance robi wołający (route_analyzer), żeby
    uniknąć importu cyklicznego.
    """
    try:
        min_lat = float(bbox["min_lat"]); max_lat = float(bbox["max_lat"])
        min_lon = float(bbox["min_lon"]); max_lon = float(bbox["max_lon"])
    except (KeyError, TypeError, ValueError):
        return []

    out: list[dict[str, Any]] = []
    for rec in _load_all():
        if min_lat <= rec["lat"] <= max_lat and min_lon <= rec["lon"] <= max_lon:
            out.append(rec)
    return out
