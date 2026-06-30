#!/usr/bin/env python3
"""B4 (uproszczony) — szacowanie czasu ZAPLANOWANEJ trasy z predkosci historycznej.

Model DETERMINISTYCZNY (route_time_estimate):
  predkosc bazowa = predkosc WAZONA CZASEM z 10 ostatnich jazd OUTDOOR:
      v_kmh = (suma distance_km) / (suma duration_sec / 3600)
  czas trasy = distance_km / v_kmh

Jazdy OUTDOOR = qbot_v2.training_sessions, filtr po sport_type:
  cycling_types (qbot_query_handler.py:1603) MINUS virtual_ride
  = {cycling, biking, mountain_biking, road_biking, gravel_cycling}
Guard: distance_m > 0 AND duration_s > 0. Kolejnosc: date DESC, started_at DESC, LIMIT 10.

Tylko ODCZYT. Model UPROSZCZONY: bez nawierzchni, przewyzszen, pogody i formy.
Zrodlo dystansu trasy: param distance_km, albo route_id -> route_parse_results
(distance_km) z fallbackiem na qbot_v2.route_frames (max dist_end_m).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# cycling_types (qbot_query_handler.py:1603) MINUS virtual_ride => jazdy OUTDOOR
_OUTDOOR_CYCLING_TYPES: tuple[str, ...] = (
    "cycling",
    "biking",
    "mountain_biking",
    "road_biking",
    "gravel_cycling",
)
_RECENT_LIMIT = 10
_APP_ROOT = Path("/opt/qbot/app")


def _load_env_files() -> None:
    """Wczytaj PG* z .env.local i .env (setdefault), jak inne narzedzia tras."""
    for name in (".env.local", ".env"):
        p = _APP_ROOT / name
        if not p.exists():
            continue
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
        except Exception:
            continue


def _db_connect():
    try:
        import psycopg2
    except ModuleNotFoundError:
        import psycopg as psycopg2
    _load_env_files()
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _recent_outdoor_rides(limit: int = _RECENT_LIMIT) -> list[dict[str, Any]]:
    """10 ostatnich jazd OUTDOOR (date DESC) z guardem distance/duration > 0."""
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT date, started_at, sport_type, distance_m, duration_s "
                "FROM qbot_v2.training_sessions "
                "WHERE lower(sport_type) = ANY(%s) "
                "  AND distance_m > 0 AND duration_s > 0 "
                "ORDER BY date DESC, started_at DESC "
                "LIMIT %s",
                (list(_OUTDOOR_CYCLING_TYPES), int(limit)),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    rides: list[dict[str, Any]] = []
    for d, started_at, sport, dist_m, dur_s in rows:
        rides.append({
            "date": d,
            "started_at": started_at,
            "sport_type": sport,
            "distance_km": float(dist_m) / 1000.0,
            "duration_sec": float(dur_s),
        })
    return rides


def _weighted_speed_kmh(rides: list[dict[str, Any]]) -> tuple[float | None, list[dict[str, Any]]]:
    """v_kmh = suma_km / suma_h; liczone tylko z jazd o distance_km>0 i duration_sec>0."""
    valid = [
        r for r in rides
        if (r.get("distance_km") or 0) > 0 and (r.get("duration_sec") or 0) > 0
    ]
    sum_km = sum(float(r["distance_km"]) for r in valid)
    sum_sec = sum(float(r["duration_sec"]) for r in valid)
    if sum_sec <= 0 or sum_km <= 0:
        return None, valid
    return sum_km / (sum_sec / 3600.0), valid


def _fmt_hmm(hours: float) -> str:
    total_min = int(round(hours * 60))
    return f"{total_min // 60}:{total_min % 60:02d}"


def _route_distance_km(route_id: str) -> tuple[float | None, str | None]:
    rid = str(route_id).strip().split("/")[-1].split("?")[0]
    if not rid:
        return None, None
    try:
        from qbot3.routes.route_canonical_read import read_canonical_route

        canonical = read_canonical_route(route_id=rid)
        route_base = canonical.get("route_base") if isinstance(canonical, dict) else None
        if canonical.get("read_path") == "canonical" and isinstance(route_base, dict):
            distance_km = route_base.get("distance_m")
            if distance_km is not None:
                return float(distance_km) / 1000.0, "route_base"
    except Exception:
        pass
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT pr.distance_km "
                    "FROM route_parse_results pr "
                    "JOIN route_artifacts ra ON ra.id = pr.route_artifact_id "
                    "WHERE ra.route_id = %s AND pr.distance_km IS NOT NULL "
                    "ORDER BY pr.parsed_at DESC LIMIT 1",
                    (rid,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return float(row[0]), "route_parse_results"
            except Exception:
                conn.rollback()
            try:
                cur.execute(
                    "SELECT max(dist_end_m) / 1000.0 "
                    "FROM qbot_v2.route_frames WHERE route_id = %s",
                    (rid,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return float(row[0]), "route_frames"
            except Exception:
                conn.rollback()
    finally:
        conn.close()
    return None, None


def _tool_route_time_estimate(args: dict | None = None) -> dict[str, Any]:
    a = args or {}

    # 1) dystans planowanej trasy
    distance_km = a.get("distance_km")
    route_id = (a.get("route_id") or a.get("route_ref") or a.get("route")
                or a.get("artifact_route_id"))
    dist_src = None
    if distance_km is not None:
        try:
            distance_km = float(distance_km)
        except (TypeError, ValueError):
            distance_km = None
        if distance_km is not None:
            dist_src = "parametr distance_km"
    if distance_km is None and route_id is not None:
        distance_km, resolver = _route_distance_km(route_id)
        if distance_km is not None:
            rid = str(route_id).strip().split("/")[-1].split("?")[0]
            dist_src = f"trasa {rid} ({resolver})"

    if distance_km is None or distance_km <= 0:
        return {
            "status": "NEEDS_INPUT",
            "analysis": (
                "## Szacowany czas trasy - B4 (uproszczony)\n"
                "Brak dystansu trasy. Podaj `distance_km` (km) albo `route_id` "
                "zaplanowanej trasy, dla ktorej policze czas."
            ),
            "notes": "Brak dystansu wejsciowego (distance_km/route_id).",
            "data": {"distance_km": None},
        }

    # 2) predkosc bazowa z historii
    rides = _recent_outdoor_rides(_RECENT_LIMIT)
    v_kmh, used = _weighted_speed_kmh(rides)
    if v_kmh is None or not used:
        return {
            "status": "NO_DATA",
            "analysis": (
                "## Szacowany czas trasy - B4 (uproszczony)\n"
                "Brak jazd OUTDOOR z dystansem i czasem > 0 w historii "
                "(qbot_v2.training_sessions) - nie moge policzyc predkosci bazowej."
            ),
            "notes": "Brak jazd OUTDOOR z guardem distance/duration > 0.",
            "data": {"distance_km": distance_km, "v_kmh": None, "n_rides": 0},
        }

    n = len(used)
    est_h = distance_km / v_kmh
    dates = [r["date"] for r in used if r.get("date") is not None]
    date_from = min(dates).isoformat() if dates else "?"
    date_to = max(dates).isoformat() if dates else "?"

    lines = [
        "## Szacowany czas trasy - B4 (uproszczony)",
        f"- Dystans trasy: **{distance_km:.1f} km**" + (f" ({dist_src})" if dist_src else ""),
        f"- Predkosc bazowa (wazona czasem): **{v_kmh:.1f} km/h**",
        f"- Szacowany czas: **{_fmt_hmm(est_h)}** (h:mm)",
        f"- Podstawa: {n} ostatnich jazd OUTDOOR (zakres dat: {date_from} - {date_to})",
    ]
    if n < _RECENT_LIMIT:
        lines.append(
            f"- UWAGA: tylko {n} < {_RECENT_LIMIT} jazd w historii - "
            f"oszacowanie mniej pewne."
        )
    lines.append("")
    lines.append("### Uzyte jazdy (najnowsze pierwsze)")
    for r in used:
        d = r["date"].isoformat() if r.get("date") else "?"
        dist = r["distance_km"]
        dur_h = r["duration_sec"] / 3600.0
        vr = dist / dur_h if dur_h > 0 else 0.0
        lines.append(f"- {d}: {dist:.1f} km / {_fmt_hmm(dur_h)} -> {vr:.1f} km/h ({r.get('sport_type')})")
    lines.append("")
    lines.append(
        "_Model UPROSZCZONY - bez nawierzchni, przewyzszen, pogody i formy. "
        "v_kmh = suma dystans_km / suma czas_h (10 ostatnich jazd OUTDOOR); czas = dystans / v_kmh._"
    )
    analysis = "\n".join(lines)

    return {
        "status": "OK",
        "analysis": analysis,
        "notes": (
            f"B4 uproszczony: v_kmh={v_kmh:.2f} (wazona czasem, n={n}), "
            f"czas={_fmt_hmm(est_h)} dla {distance_km:.1f} km. Bez nawierzchni/pogody/formy."
        ),
        "data": {
            "distance_km": round(distance_km, 3),
            "v_kmh": round(v_kmh, 3),
            "est_time_h": round(est_h, 4),
            "est_time_hmm": _fmt_hmm(est_h),
            "n_rides": n,
            "n_below_target": n < _RECENT_LIMIT,
            "date_from": date_from,
            "date_to": date_to,
            "rides": [
                {
                    "date": (r["date"].isoformat() if r.get("date") else None),
                    "sport_type": r.get("sport_type"),
                    "distance_km": round(r["distance_km"], 3),
                    "duration_sec": int(r["duration_sec"]),
                }
                for r in used
            ],
        },
    }
