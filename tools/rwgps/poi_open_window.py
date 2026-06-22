from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Any

import httpx

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
_DAY_TO_IDX = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}
_IDX_TO_DAY = {v: k for k, v in _DAY_TO_IDX.items()}


def _load_env_local() -> None:
    p = Path(__file__).resolve().parents[2] / ".env.local"
    if not p.exists():
        return
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)
    except (OSError, PermissionError):
        return


def _api_key() -> str | None:
    _load_env_local()
    return os.environ.get("GOOGLE_PLACES_API_KEY")


def _norm_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    return text


def _parse_time_token(token: str) -> int | None:
    token = token.strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", token)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _expand_days(spec: str) -> list[int] | None:
    days: list[int] = []
    for token in [part.strip() for part in spec.split(",") if part.strip()]:
        if "-" in token:
            left, right = [part.strip() for part in token.split("-", 1)]
            if left not in _DAY_TO_IDX or right not in _DAY_TO_IDX:
                return None
            start = _DAY_TO_IDX[left]
            end = _DAY_TO_IDX[right]
            if start <= end:
                days.extend(range(start, end + 1))
            else:
                days.extend(range(start, 7))
                days.extend(range(0, end + 1))
            continue
        if token not in _DAY_TO_IDX:
            return None
        days.append(_DAY_TO_IDX[token])
    return sorted(set(days))


def parse_osm_opening_hours(s: str) -> dict[str, Any] | None:
    text = re.sub(r"\s+", " ", str(s or "")).strip()
    if not text:
        return None
    if text.lower() == "24/7":
        return {"raw": text, "always_open": True, "rules": []}

    rules: list[dict[str, Any]] = []
    for clause in [part.strip() for part in text.split(";") if part.strip()]:
        low = clause.lower()
        if low in {"off", "closed"}:
            rules.append({"days": list(range(7)), "closed": True, "ranges": []})
            continue

        day_part = ""
        time_part = clause
        m = re.match(r"^((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:\s*,\s*(?:Mo|Tu|We|Th|Fr|Sa|Su)|\s*-\s*(?:Mo|Tu|We|Th|Fr|Sa|Su))*)\s+(.*)$", clause)
        if m:
            day_part = m.group(1).strip()
            time_part = m.group(2).strip()

        days = _expand_days(day_part) if day_part else list(range(7))
        if days is None:
            return None

        ranges: list[tuple[int, int]] = []
        for piece in [part.strip() for part in re.split(r"\s*,\s*", time_part) if part.strip()]:
            m_range = re.fullmatch(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", piece)
            if not m_range:
                return None
            start = _parse_time_token(m_range.group(1))
            end = _parse_time_token(m_range.group(2))
            if start is None or end is None:
                return None
            ranges.append((start, end))
        if not ranges:
            return None
        rules.append({"days": days, "closed": False, "ranges": ranges})

    return {"raw": text, "always_open": False, "rules": rules}


def osm_open_at(parsed: dict[str, Any] | None, dt: datetime) -> bool | None:
    if parsed is None:
        return None
    if parsed.get("always_open"):
        return True
    rules = parsed.get("rules") or []
    if not rules:
        return None

    weekday = int(dt.weekday())
    minute = dt.hour * 60 + dt.minute
    matched_day = False
    for rule in rules:
        days = rule.get("days") or []
        if weekday not in days:
            continue
        matched_day = True
        if rule.get("closed"):
            continue
        for start, end in rule.get("ranges") or []:
            if start <= end:
                if start <= minute < end:
                    return True
            else:
                if minute >= start:
                    return True

    prev_weekday = (weekday - 1) % 7
    for rule in rules:
        days = rule.get("days") or []
        if prev_weekday not in days:
            continue
        if rule.get("closed"):
            matched_day = True
            continue
        for start, end in rule.get("ranges") or []:
            if start > end and minute < end:
                return True

    return False if matched_day else False


def eta_at_km(route_km: float, ride_start_dt: datetime, avg_speed_kmh: float) -> datetime:
    try:
        speed = float(avg_speed_kmh)
    except (TypeError, ValueError):
        speed = 18.0
    if speed <= 0:
        speed = 18.0
    try:
        route = float(route_km)
    except (TypeError, ValueError):
        route = 0.0
    return ride_start_dt + timedelta(hours=route / speed)


def _day_to_sunday(dt: datetime) -> datetime:
    offset = (dt.weekday() + 1) % 7
    base = dt.date() - timedelta(days=offset)
    return datetime.combine(base, dtime.min, tzinfo=dt.tzinfo)


def google_hours(lat: float, lon: float, name: str, api_key: str | None) -> dict[str, Any] | None:
    if not api_key:
        return None

    try:
        payload = {
            "includedTypes": [
                "supermarket",
                "grocery_store",
                "convenience_store",
                "restaurant",
                "cafe",
                "bakery",
                "bar",
            ],
            "maxResultCount": 10,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": float(lat), "longitude": float(lon)},
                    "radius": 150.0,
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.regularOpeningHours,places.currentOpeningHours,places.id,places.location",
        }
        resp = httpx.post(PLACES_URL, json=payload, headers=headers, timeout=10.0)
        resp.raise_for_status()
        places = resp.json().get("places", [])
        if not isinstance(places, list) or not places:
            return None

        query_name = _norm_text(name)

        def _distance_m(place: dict[str, Any]) -> float:
            loc = place.get("location") or {}
            try:
                plat = float(loc.get("latitude"))
                plon = float(loc.get("longitude"))
            except (TypeError, ValueError):
                return 10**9
            dlat = math.radians(plat - float(lat))
            dlon = math.radians(plon - float(lon))
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(float(lat))) * math.cos(math.radians(plat)) * math.sin(dlon / 2) ** 2
            return 6371000.0 * 2 * math.asin(math.sqrt(a))

        best_place: dict[str, Any] | None = None
        best_score = float("-inf")
        for place in places:
            display = place.get("displayName") or {}
            display_name = _norm_text(display.get("text"))
            distance = _distance_m(place)
            name_score = 0.0
            if query_name and display_name:
                if query_name == display_name:
                    name_score = 100.0
                elif query_name in display_name or display_name in query_name:
                    name_score = 75.0
                else:
                    query_words = [w for w in query_name.split() if len(w) > 2]
                    overlap = sum(1 for word in query_words if word in display_name)
                    name_score = float(overlap * 10)
            elif query_name:
                name_score = 10.0 if query_name in display_name else 0.0
            score = name_score - (distance / 50.0)
            if score > best_score:
                best_score = score
                best_place = place

        if not best_place:
            return None
        regular = best_place.get("regularOpeningHours") or best_place.get("currentOpeningHours")
        display = best_place.get("displayName") or {}
        return {
            "regularOpeningHours": regular,
            "displayName": display.get("text") if isinstance(display, dict) else display,
            "id": best_place.get("id"),
        }
    except Exception:
        return None


def _google_open_on_day(period: dict[str, Any], dt: datetime) -> bool | None:
    open_part = period.get("open") or {}
    close_part = period.get("close") or None
    try:
        open_day = int(open_part.get("day"))
        open_hour = int(open_part.get("hour", 0))
        open_minute = int(open_part.get("minute", 0))
    except (TypeError, ValueError):
        return None
    open_dt = _day_to_sunday(dt) + timedelta(days=open_day, hours=open_hour, minutes=open_minute)
    if close_part is None:
        return dt >= open_dt
    try:
        close_day = int(close_part.get("day"))
        close_hour = int(close_part.get("hour", 0))
        close_minute = int(close_part.get("minute", 0))
    except (TypeError, ValueError):
        return None
    close_dt = _day_to_sunday(dt) + timedelta(days=close_day, hours=close_hour, minutes=close_minute)
    if close_dt <= open_dt:
        close_dt += timedelta(days=7)
    if dt < open_dt:
        return False
    return dt < close_dt


def google_open_at(google_obj: dict[str, Any] | None, dt: datetime) -> bool | None:
    if not google_obj:
        return None
    regular = google_obj.get("regularOpeningHours") or {}
    periods = regular.get("periods")
    if not isinstance(periods, list) or not periods:
        return None
    for period in periods:
        if not isinstance(period, dict):
            continue
        result = _google_open_on_day(period, dt)
        if result is True:
            return True
    return False


def _opening_hours_from_source_tags(source_tags: Any) -> str | None:
    if not isinstance(source_tags, str) or not source_tags:
        return None
    m = re.search(r"(?:^|[;,]\s*)opening_hours=([^;]+)", source_tags)
    if not m:
        return None
    return m.group(1).strip() or None


def enrich_open_window(
    items: list[dict[str, Any]],
    *,
    ride_start: datetime | None = None,
    avg_speed_kmh: float = 18.0,
    use_google: bool = False,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return items

    google_key = api_key or _api_key()
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_hours = item.get("opening_hours_osm")
        if not raw_hours:
            raw_hours = _opening_hours_from_source_tags(item.get("source_tags"))
            if raw_hours:
                item["opening_hours_osm"] = raw_hours

        eta = None
        if ride_start is not None:
            try:
                eta = eta_at_km(float(item.get("route_km") or 0.0), ride_start, avg_speed_kmh)
                item["eta_iso"] = eta.isoformat()
            except Exception:
                eta = None

        if eta is None:
            if raw_hours:
                item["open_at_arrival"] = None
            else:
                item.setdefault("open_at_arrival", None)
            item.setdefault("open_source", "unknown")
            continue

        osm_parsed = parse_osm_opening_hours(str(raw_hours)) if raw_hours else None
        osm_open = osm_open_at(osm_parsed, eta)
        if osm_open is not None:
            item["open_at_arrival"] = osm_open
            item["open_source"] = "osm"
            continue

        if use_google and google_key:
            google_obj = google_hours(
                float(item.get("lat") or 0.0),
                float(item.get("lon") or 0.0),
                str(item.get("name") or ""),
                google_key,
            )
            if google_obj:
                item["google_name"] = google_obj.get("displayName") or item.get("google_name")
                item["google_place_id"] = google_obj.get("id") or item.get("google_place_id")
                google_open = google_open_at(google_obj, eta)
                item["open_at_arrival"] = google_open
                item["open_source"] = "google" if google_open is not None else "unknown"
                continue

        item["open_at_arrival"] = None
        item["open_source"] = "unknown"

    return items
