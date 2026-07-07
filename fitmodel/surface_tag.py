from __future__ import annotations

"""FITMODEL E6 (czesc 1) -- otagowanie segmentow nawierzchnia + kalibracja mnoznikow.

Pomysl: segment to ustalony wysilek w realnej jezdzie. Bierzemy GPS z pliku FIT
dla okna [started_at, started_at+dur_s], pytamy OSM (Overpass, around:20m per punkt)
o nawierzchnie najblizszej drogi i mapujemy surowy tag OSM na slownik FITMODEL
(asphalt/compacted/gravel/sand/unpaved). Dominanta -> fitmodel_segment.surface_type.

Po otagowaniu (--calibrate): mult[typ] = EF_asfalt_med / EF_typ_med dla typow z n>=10
(spec 4.7 / E6). Asfalt = referencja 1.00.

Mechanizm Overpass mirrorowany ze sprawdzonego mcp_server._overpass_post
(same mirrory/backoff). Klasyfikacja: surowy tag surface + fallback tracktype/highway.
Cache wynikow OSM per-segment w /opt/qbot/app/data/fitmodel_surface_cache.json.
"""

import argparse
import json
import math
import os
import sys
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

import httpx

try:
    import fitparse
except ModuleNotFoundError:
    fitparse = None

from fitmodel.ftp_resolver import _db_connect, _coerce_date

FIT_DIR = Path("/opt/qbot/artifacts/fit")
CACHE_PATH = Path("/opt/qbot/app/data/fitmodel_surface_cache.json")
SEMICIRCLE_TO_DEG = 180.0 / (2 ** 31)

# ── Overpass (mirror mcp_server) ─────────────────────────────────────────
_OVERPASS_ENDPOINTS = [
    u.strip() for u in os.getenv(
        "QBOT_OVERPASS_URLS", "https://overpass-api.de/api/interpreter"
    ).split(",") if u.strip()
]
_OVERPASS_RETRIES = int(os.getenv("QBOT_OVERPASS_RETRIES", "4"))
_OVERPASS_BACKOFF = float(os.getenv("QBOT_OVERPASS_BACKOFF", "3.0"))
_OVERPASS_SLEEP = float(os.getenv("QBOT_OVERPASS_SLEEP", "1.0"))
BATCH_SIZE = 15
MAX_MATCH_DIST_M = 150
SAMPLE_EVERY_M = 100.0
MAX_SAMPLES_PER_SEG = 30

# ── Mapowanie surowego tagu OSM -> slownik FITMODEL ──────────────────────
_PAVED = {"asphalt", "paved", "concrete", "concrete:plates", "concrete:lanes",
          "chipseal", "metal", "wood", "paving_stones", "sett", "cobblestone",
          "unhewn_cobblestone", "bricks", "brick"}
_COMPACTED = {"compacted", "fine_gravel"}
_GRAVEL = {"gravel", "pebblestone", "rock", "stone"}
_SAND = {"sand"}
_UNPAVED = {"unpaved", "ground", "dirt", "earth", "mud", "grass", "clay",
            "soil", "woodchips"}


def _surface_to_bucket(tags: dict) -> str | None:
    """Surowe tagi OSM -> jeden z 5 kubelkow FITMODEL (lub None gdy brak sygnalu)."""
    surf = (tags.get("surface") or "").lower().strip()
    if surf:
        if surf in _PAVED:
            return "asphalt"
        if surf in _COMPACTED:
            return "compacted"
        if surf in _GRAVEL:
            return "gravel"
        if surf in _SAND:
            return "sand"
        if surf in _UNPAVED:
            return "unpaved"
        # heurystyka na nieznany string
        if any(k in surf for k in ("asph", "paved", "concrete")):
            return "asphalt"
        if "fine_gravel" in surf or "compact" in surf:
            return "compacted"
        if "gravel" in surf:
            return "gravel"
        if "sand" in surf:
            return "sand"
        if any(k in surf for k in ("ground", "dirt", "earth", "mud", "unpaved")):
            return "unpaved"
    # fallback: tracktype
    tt = (tags.get("tracktype") or "").lower().strip()
    if tt:
        return {"grade1": "compacted", "grade2": "gravel", "grade3": "unpaved",
                "grade4": "unpaved", "grade5": "unpaved"}.get(tt)
    # fallback: highway
    hw = (tags.get("highway") or "").lower().strip()
    if hw:
        if hw in {"track", "path", "bridleway"}:
            return "unpaved"
        # drogi jezdne bez tagu surface zakladamy asfalt
        if hw in {"motorway", "trunk", "primary", "secondary", "tertiary",
                  "unclassified", "residential", "service", "living_street",
                  "cycleway", "road", "motorway_link", "trunk_link",
                  "primary_link", "secondary_link", "tertiary_link"}:
            return "asphalt"
    return None


def _dist_fast(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111320
    dlon = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlon * dlon)


def _overpass_post(query: str, timeout: int = 30) -> list:
    from urllib.parse import urlencode
    body = urlencode({"data": query}).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Q-rowerowy-asystent/1.0 (cycling training tool)",
    }
    last = None
    for endpoint in _OVERPASS_ENDPOINTS:
        for attempt in range(_OVERPASS_RETRIES):
            try:
                with httpx.Client(timeout=timeout) as c:
                    r = c.post(endpoint, content=body, headers=headers)
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    try:
                        delay = float(ra) if ra else _OVERPASS_BACKOFF * (2 ** attempt)
                    except ValueError:
                        delay = _OVERPASS_BACKOFF * (2 ** attempt)
                    _time.sleep(min(delay, 30))
                    continue
                if r.status_code in (502, 503, 504):
                    _time.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
                    continue
                r.raise_for_status()
                return r.json().get("elements", [])
            except Exception as exc:
                last = exc
                _time.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
                continue
    raise RuntimeError(f"Overpass: wszystkie mirrory zawiodly ({last})")


# ── Cache ────────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
                          encoding="utf-8")


# ── FIT -> GPS okna segmentu ──────────────────────────────────────────────
_FIT_GPS_CACHE: dict[str, list] = {}


def _ride_gps(ride_id: str) -> list[tuple[datetime, float, float]]:
    """Lista (naive_ts, lat_deg, lon_deg) dla calej jazdy; cache w pamieci."""
    if ride_id in _FIT_GPS_CACHE:
        return _FIT_GPS_CACHE[ride_id]
    if fitparse is None:
        raise RuntimeError("brak fitparse w venv")
    path = FIT_DIR / f"{ride_id}.fit"
    pts: list[tuple[datetime, float, float]] = []
    if path.exists():
        fit = fitparse.FitFile(str(path))
        for rec in fit.get_messages("record"):
            d = {x.name: x.value for x in rec}
            ts = d.get("timestamp")
            lat = d.get("position_lat")
            lon = d.get("position_long")
            if ts is None or lat is None or lon is None:
                continue
            ts_naive = ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts
            pts.append((ts_naive, lat * SEMICIRCLE_TO_DEG, lon * SEMICIRCLE_TO_DEG))
    _FIT_GPS_CACHE[ride_id] = pts
    return pts


def _segment_samples(ride_id: str, started_at: datetime, dur_s: int) -> list[tuple[float, float]]:
    """Punkty GPS w oknie segmentu, przerzedzone co SAMPLE_EVERY_M (max MAX_SAMPLES)."""
    start = started_at.replace(tzinfo=None) if started_at.tzinfo else started_at
    end = start + timedelta(seconds=int(dur_s))
    win = [(la, lo) for (ts, la, lo) in _ride_gps(ride_id) if start <= ts <= end]
    if not win:
        return []
    samples = [win[0]]
    acc = 0.0
    for i in range(1, len(win)):
        acc += _dist_fast(win[i - 1][0], win[i - 1][1], win[i][0], win[i][1])
        if acc >= SAMPLE_EVERY_M:
            samples.append(win[i])
            acc = 0.0
    if len(samples) > MAX_SAMPLES_PER_SEG:
        step = len(samples) / MAX_SAMPLES_PER_SEG
        samples = [samples[int(i * step)] for i in range(MAX_SAMPLES_PER_SEG)]
    return samples


def _classify_points(samples: list[tuple[float, float]]) -> dict[str, Any]:
    """Overpass dla punktow -> rozklad kubelkow FITMODEL + dominanta + pokrycie."""
    bucket_counts: dict[str, int] = {}
    matched = 0
    n = len(samples)
    for b0 in range(0, n, BATCH_SIZE):
        batch = samples[b0:b0 + BATCH_SIZE]
        around = "".join(f"  way[highway](around:20,{p[0]},{p[1]});\n" for p in batch)
        query = f"[out:json][timeout:25];(\n{around});out tags geom;"
        try:
            ways = _overpass_post(query, timeout=30)
        except Exception:
            ways = []
        if _OVERPASS_SLEEP > 0 and b0 + BATCH_SIZE < n:
            _time.sleep(_OVERPASS_SLEEP)
        if not ways:
            continue
        for pt in batch:
            best_tags, best_dist = {}, float("inf")
            for way in ways:
                for node in way.get("geometry", []):
                    d = _dist_fast(pt[0], pt[1], node["lat"], node["lon"])
                    if d < best_dist:
                        best_dist, best_tags = d, way.get("tags", {})
            if best_dist > MAX_MATCH_DIST_M:
                continue
            bucket = _surface_to_bucket(best_tags)
            if bucket:
                matched += 1
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    dominant = max(bucket_counts, key=bucket_counts.get) if bucket_counts else None
    coverage = round(matched / n * 100, 1) if n else 0.0
    return {"dominant": dominant, "coverage_pct": coverage,
            "n_samples": n, "n_matched": matched, "buckets": bucket_counts}


def tag_segments(db_conn, only_untagged: bool = True, use_cache: bool = True,
                 dry_run: bool = False) -> list[dict]:
    cache = _load_cache() if use_cache else {}
    with db_conn.cursor() as cur:
        where = "WHERE surface_type IS NULL" if only_untagged else ""
        cur.execute(
            f"SELECT id, ride_id, started_at, dur_s, ef_norm, hr_quality_ok "
            f"FROM qbot_v2.fitmodel_segment {where} ORDER BY started_at"
        )
        rows = cur.fetchall()

    results = []
    for seg_id, ride_id, started_at, dur_s, ef_norm, hq in rows:
        ckey = str(seg_id)
        if use_cache and ckey in cache:
            res = cache[ckey]
        else:
            samples = _segment_samples(ride_id, started_at, dur_s)
            if not samples:
                res = {"dominant": None, "coverage_pct": 0.0,
                       "n_samples": 0, "n_matched": 0, "buckets": {}}
            else:
                res = _classify_points(samples)
            cache[ckey] = res
            if use_cache:
                _save_cache(cache)
        results.append({"id": seg_id, "ride_id": ride_id,
                        "started_at": started_at, **res})

    if not dry_run:
        with db_conn.cursor() as cur:
            for r in results:
                if r["dominant"]:
                    cur.execute(
                        "UPDATE qbot_v2.fitmodel_segment SET surface_type=%s WHERE id=%s",
                        (r["dominant"], r["id"]),
                    )
        db_conn.commit()
    return results


def calibrate(db_conn, dry_run: bool = False, min_n: int = 10) -> dict:
    """mult[typ] = EF_asfalt_med / EF_typ_med; update tylko typy z n>=min_n."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT surface_type, ef_norm FROM qbot_v2.fitmodel_segment "
            "WHERE hr_quality_ok AND surface_type IS NOT NULL AND ef_norm IS NOT NULL"
        )
        by_type: dict[str, list[float]] = {}
        for st, ef in cur.fetchall():
            by_type.setdefault(st, []).append(float(ef))

    ef_asphalt = median(by_type["asphalt"]) if by_type.get("asphalt") else None
    report = {"ef_asphalt_med": ef_asphalt, "types": {}, "updated": []}
    for st, efs in sorted(by_type.items()):
        med_ef = median(efs)
        mult = round(ef_asphalt / med_ef, 4) if (ef_asphalt and med_ef) else None
        eligible = len(efs) >= min_n and ef_asphalt is not None
        report["types"][st] = {"n": len(efs), "ef_med": round(med_ef, 4),
                               "mult_proposed": mult, "eligible": eligible}
        if eligible and mult is not None and not dry_run:
            with db_conn.cursor() as cur:
                cur.execute(
                    "UPDATE qbot_v2.fitmodel_surface_cal "
                    "SET mult=%s, n_segments=%s, updated_at=now() WHERE surface_type=%s",
                    (mult, len(efs), st),
                )
            report["updated"].append(st)
    if not dry_run and report["updated"]:
        db_conn.commit()
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FITMODEL E6 -- tagowanie nawierzchni + kalibracja")
    ap.add_argument("--dry-run", action="store_true", help="policz i wypisz, bez zapisu")
    ap.add_argument("--all", action="store_true", help="przetagowuj rowniez juz otagowane")
    ap.add_argument("--no-cache", action="store_true", help="ignoruj cache OSM")
    ap.add_argument("--calibrate", action="store_true", help="po tagowaniu policz mnozniki")
    args = ap.parse_args()

    conn = _db_connect()
    try:
        res = tag_segments(conn, only_untagged=not args.all,
                           use_cache=not args.no_cache, dry_run=args.dry_run)
        print(f"{'DRY-RUN' if args.dry_run else 'ZAPIS'} -- {len(res)} segmentow:")
        print(f"  {'id':>4} {'data':10} {'naw.':10} {'cov%':>5} {'n/match':>8}  ride")
        tally: dict[str, int] = {}
        for r in res:
            dom = r['dominant'] or '-'
            tally[dom] = tally.get(dom, 0) + 1
            d = r['started_at'].date().isoformat() if r['started_at'] else '?'
            print(f"  {r['id']:>4} {d:10} {dom:10} {r['coverage_pct']:>5} "
                  f"{str(r['n_matched'])+'/'+str(r['n_samples']):>8}  {r['ride_id'][-12:]}")
        print("  ROZKLAD:", dict(sorted(tally.items(), key=lambda x: -x[1])))

        if args.calibrate:
            rep = calibrate(conn, dry_run=args.dry_run)
            print("\nKALIBRACJA (EF_asfalt_med =", rep["ef_asphalt_med"], "):")
            for st, info in rep["types"].items():
                flag = "-> UPDATE" if info["eligible"] else f"(n<{10}, zostaje literatura)"
                print(f"  {st:10} n={info['n']:>2} ef_med={info['ef_med']} "
                      f"mult={info['mult_proposed']} {flag}")
            print("  zaktualizowane typy:", rep["updated"] or "brak (za malo danych)")
    finally:
        conn.close()
