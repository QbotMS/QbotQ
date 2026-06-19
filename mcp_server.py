import os, json, base64
from datetime import date
from pathlib import Path, PurePosixPath
from dotenv import load_dotenv
import httpx
import db
from qlab_replay_export import export_qlab_replay, find_fit_files
from qbot_recovery import select_recovery_records, sleep_data_date_marker
from tools.rwgps.client import (
    get_route as rwgps_get_route,
    get_route_cue_sheet as rwgps_get_route_cue_sheet,
    get_route_export_links as rwgps_get_route_export_links,
    get_route_geometry as rwgps_get_route_geometry,
    download_route_fit as rwgps_download_route_fit,
    download_route_gpx as rwgps_download_route_gpx,
    download_route_tcx as rwgps_download_route_tcx,
    list_collections as rwgps_list_collections,
    list_planned_routes as rwgps_list_planned_routes,
    list_routes as rwgps_list_routes,
    export_route_to_artifact as rwgps_export_route_to_artifact,
    summarize_rwgps_artifact as rwgps_summarize_rwgps_artifact,
    extract_artifact_points as rwgps_extract_artifact_points,
)

load_dotenv()
db.init()

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("Q — Rowerowy Asystent", host="127.0.0.1", port=8000)

ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "")
API_KEY    = os.getenv("INTERVALS_API_KEY", "")
LOC_LAT    = float(os.getenv("LOCATION_LAT",  "52.2297"))
LOC_LON    = float(os.getenv("LOCATION_LON",  "21.0122"))
LOC_NAME   = os.getenv("LOCATION_NAME", "Warszawa")
CRONOMETER_EMAIL    = os.getenv("CRONOMETER_EMAIL", "")
CRONOMETER_PASSWORD = os.getenv("CRONOMETER_PASSWORD", "")
XERT_EMAIL    = os.getenv("XERT_EMAIL", "")
XERT_PASSWORD = os.getenv("XERT_PASSWORD", "")
GARMIN_EMAIL    = os.getenv("GARMIN_EMAIL", "")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD", "")

def _env_int(name: str):
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
        return value if value > 0 else None
    except ValueError:
        print(f"⚠️ Invalid integer env {name}={raw!r}", flush=True)
        return None

RIDER_MAX_HR_BPM = _env_int("RIDER_MAX_HR_BPM")
RIDER_MAX_HR_SOURCE = os.getenv("RIDER_MAX_HR_SOURCE", "").strip() or None
ROUTE_SURFACE_CACHE = Path("/opt/qbot/app/data/route_surface_cache.json")
ARTIFACT_ROOT = Path("/opt/qbot/artifacts")
ALLOWED_ARTIFACT_PREFIXES = ("routes/", "reports/", "imports/", "exports/", "qexp/", "inbox/")
ARTIFACT_PREVIEW_BYTES = 200_000
ARTIFACT_PREVIEW_LINES = 200


def _load_route_surface_cache() -> dict:
    try:
        return json.loads(ROUTE_SURFACE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cached_route_surface(activity_id: str, error: str | None = None) -> str | None:
    item = _load_route_surface_cache().get(str(activity_id))
    if not isinstance(item, dict):
        return None
    result = dict(item)
    result["cache_hit"] = True
    if error:
        result["cache_reason"] = error
    return json.dumps(result, ensure_ascii=False)


def _save_route_surface_cache(activity_id: str, payload: dict) -> None:
    if not payload or payload.get("error"):
        return
    cache = _load_route_surface_cache()
    cache[str(activity_id)] = {**payload, "cache_hit": False, "cached_at": date.today().isoformat()}
    if len(cache) > 300:
        keep = sorted(cache.keys())[-300:]
        cache = {k: cache[k] for k in keep}
    ROUTE_SURFACE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ROUTE_SURFACE_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _route_surface_error(activity_id: str, message: str) -> str:
    cached = _cached_route_surface(activity_id, message)
    if cached:
        return cached
    return json.dumps({"error": message}, ensure_ascii=False)


def validate_artifact_relative_path(relative_path: str) -> str:
    if not isinstance(relative_path, str):
        raise ValueError("relative_path must be a string")
    raw = relative_path.strip()
    if not raw:
        raise ValueError("relative_path must not be empty")

    path = PurePosixPath(raw)
    if path.is_absolute():
        raise ValueError("relative_path must be relative")
    if any(part == ".." for part in path.parts):
        raise ValueError("relative_path must not contain ..")

    normalized_parts = [part for part in path.parts if part not in ("", ".")]
    if not normalized_parts:
        raise ValueError("relative_path must not be empty")

    normalized = PurePosixPath(*normalized_parts).as_posix()
    if normalized in ("", "."):
        raise ValueError("relative_path must not be empty")
    if not any(normalized.startswith(prefix) for prefix in ALLOWED_ARTIFACT_PREFIXES):
        allowed = ", ".join(ALLOWED_ARTIFACT_PREFIXES)
        raise ValueError(f"relative_path must start with one of: {allowed}")
    return normalized


def artifact_absolute_path(relative_path: str) -> Path:
    return ARTIFACT_ROOT / validate_artifact_relative_path(relative_path)


def _artifact_root_resolved() -> Path:
    return ARTIFACT_ROOT.resolve(strict=False)


def _artifact_relative_path(path: Path) -> str:
    return path.relative_to(_artifact_root_resolved()).as_posix()


def _artifact_list_entries() -> list[Path]:
    root = _artifact_root_resolved()
    if not root.exists():
        return []
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            resolved = path.resolve(strict=False)
            if not resolved.is_relative_to(root):
                continue
        except Exception:
            continue
        paths.append(path)
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def _artifact_metadata(path: Path) -> dict[str, object]:
    stat = path.stat()
    resolved = path.resolve(strict=False)
    return {
        "relative_path": _artifact_relative_path(path),
        "absolute_path": str(path),
        "resolved_path": str(resolved),
        "size_bytes": stat.st_size,
        "modified_at": date.fromtimestamp(stat.st_mtime).isoformat(),
        "is_symlink": path.is_symlink(),
        "suffix": path.suffix.lower(),
    }


def _resolve_artifact_path(path_or_name: str) -> Path:
    if not isinstance(path_or_name, str):
        raise ValueError("INVALID_PATH: path_or_name must be a string")
    raw = path_or_name.strip()
    if not raw:
        raise ValueError("INVALID_PATH: path_or_name must not be empty")

    root = _artifact_root_resolved()
    if "/" in raw or "\\" in raw:
        normalized = validate_artifact_relative_path(raw.replace("\\", "/"))
        path = artifact_absolute_path(normalized)
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise PermissionError("PERMISSION_DENIED: resolved path escapes artifacts root")
        if not path.exists():
            raise FileNotFoundError("NOT_FOUND: artifact does not exist")
        return path

    exact_matches = [path for path in _artifact_list_entries() if path.name == raw]
    if not exact_matches:
        casefold_matches = [path for path in _artifact_list_entries() if path.name.casefold() == raw.casefold()]
        exact_matches = casefold_matches
    if not exact_matches:
        raise FileNotFoundError("NOT_FOUND: artifact does not exist")
    if len(exact_matches) > 1:
        rels = ", ".join(_artifact_relative_path(path) for path in exact_matches[:8])
        raise ValueError(f"INVALID_PATH: ambiguous artifact name; matches: {rels}")
    return exact_matches[0]


def _read_text_preview(path: Path, max_bytes: int, preview_lines: int) -> tuple[str, bool]:
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    if preview_lines > 0:
        lines = text.splitlines()
        if len(lines) > preview_lines:
            text = "\n".join(lines[:preview_lines])
            truncated = True
    return text, truncated


@mcp.tool()
def list_qbot_artifacts(limit: int = 200, prefix: str = None) -> str:
    """List available QBot artifacts from /opt/qbot/artifacts. Optional prefix filter (e.g. 'exports/rwgps/')."""
    try:
        if limit <= 0:
            raise ValueError("INVALID_PATH: limit must be positive")
        root = _artifact_root_resolved()
        if not root.exists():
            return json.dumps({
                "status": "NOT_FOUND",
                "root": str(ARTIFACT_ROOT),
                "count": 0,
                "artifacts": [],
                "error": "artifacts root does not exist",
            }, ensure_ascii=False)
        if not os.access(root, os.R_OK | os.X_OK):
            return json.dumps({
                "status": "PERMISSION_DENIED",
                "root": str(ARTIFACT_ROOT),
                "count": 0,
                "artifacts": [],
                "error": "artifacts root is not readable",
            }, ensure_ascii=False)

        entries = _artifact_list_entries()
        if prefix:
            prefix = prefix.strip()
            entries = [p for p in entries if _artifact_relative_path(p).startswith(prefix)]
        artifacts = [_artifact_metadata(path) for path in entries[:limit]]
        return json.dumps({
            "status": "ok",
            "root": str(ARTIFACT_ROOT),
            "count": len(artifacts),
            "prefix": prefix or None,
            "artifacts": artifacts,
        }, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({
            "status": "INVALID_PATH",
            "root": str(ARTIFACT_ROOT),
            "count": 0,
            "artifacts": [],
            "error": str(exc),
        }, ensure_ascii=False)
    except PermissionError as exc:
        return json.dumps({
            "status": "PERMISSION_DENIED",
            "root": str(ARTIFACT_ROOT),
            "count": 0,
            "artifacts": [],
            "error": str(exc),
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "root": str(ARTIFACT_ROOT),
            "count": 0,
            "artifacts": [],
            "error": str(exc),
        }, ensure_ascii=False)


@mcp.tool()
def read_qbot_artifact(path_or_name: str, max_bytes: int = ARTIFACT_PREVIEW_BYTES, preview_lines: int = ARTIFACT_PREVIEW_LINES) -> str:
    """Read a QBot artifact by safe relative path or unique file name."""
    try:
        if max_bytes <= 0:
            raise ValueError("INVALID_PATH: max_bytes must be positive")
        if preview_lines < 0:
            raise ValueError("INVALID_PATH: preview_lines must be non-negative")
        path = _resolve_artifact_path(path_or_name)
        root = _artifact_root_resolved()
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise PermissionError("PERMISSION_DENIED: resolved path escapes artifacts root")
        if not path.exists():
            raise FileNotFoundError("NOT_FOUND: artifact does not exist")
        if not os.access(path, os.R_OK):
            raise PermissionError("PERMISSION_DENIED: artifact is not readable")

        text, truncated = _read_text_preview(path, max_bytes=max_bytes, preview_lines=preview_lines)
        return json.dumps({
            "status": "ok",
            "root": str(ARTIFACT_ROOT),
            "relative_path": _artifact_relative_path(path),
            "absolute_path": str(path),
            "resolved_path": str(resolved),
            "size_bytes": path.stat().st_size,
            "bytes_read": min(path.stat().st_size, max_bytes),
            "truncated": truncated,
            "content": text,
        }, ensure_ascii=False)
    except FileNotFoundError as exc:
        return json.dumps({
            "status": "NOT_FOUND",
            "root": str(ARTIFACT_ROOT),
            "relative_path": path_or_name,
            "absolute_path": None,
            "resolved_path": None,
            "size_bytes": 0,
            "bytes_read": 0,
            "truncated": False,
            "content": None,
            "error": str(exc),
        }, ensure_ascii=False)
    except PermissionError as exc:
        return json.dumps({
            "status": "PERMISSION_DENIED",
            "root": str(ARTIFACT_ROOT),
            "relative_path": path_or_name,
            "absolute_path": None,
            "resolved_path": None,
            "size_bytes": 0,
            "bytes_read": 0,
            "truncated": False,
            "content": None,
            "error": str(exc),
        }, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({
            "status": "INVALID_PATH",
            "root": str(ARTIFACT_ROOT),
            "relative_path": path_or_name,
            "absolute_path": None,
            "resolved_path": None,
            "size_bytes": 0,
            "bytes_read": 0,
            "truncated": False,
            "content": None,
            "error": str(exc),
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "root": str(ARTIFACT_ROOT),
            "relative_path": path_or_name,
            "absolute_path": None,
            "resolved_path": None,
            "size_bytes": 0,
            "bytes_read": 0,
            "truncated": False,
            "content": None,
            "error": str(exc),
        }, ensure_ascii=False)

_b64 = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
HDR  = {"Authorization": f"Basic {_b64}"}
BASE = "https://intervals.icu/api/v1"

async def icu(endpoint, params=None):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BASE}{endpoint}", headers=HDR,
            params={k:v for k,v in (params or {}).items() if v is not None})
        r.raise_for_status()
        return r.json()

WMO = {0:"Czyste niebo",1:"Bezchmurnie",2:"Częściowe zachmurzenie",
    3:"Pochmurno",45:"Mgła",48:"Mgła z szronem",
    51:"Mżawka",53:"Mżawka",55:"Gęsta mżawka",
    56:"Marznąca mżawka",57:"Marznąca mżawka",
    61:"Deszcz",63:"Deszcz",65:"Silny deszcz",
    66:"Marznący deszcz",67:"Marznący deszcz",
    71:"Śnieg",73:"Śnieg",75:"Silny śnieg",77:"Ziarnisty śnieg",
    80:"Przelotne opady",81:"Przelotne opady",82:"Gwałtowne opady",
    85:"Przelotny śnieg",86:"Silny przelotny śnieg",
    95:"Burza",96:"Burza z gradem",99:"Burza z gradem"}

# ── INTERVALS.ICU ─────────────────────────────────────────────────────────────

@mcp.tool()
async def get_activities(oldest: str = None, newest: str = None, limit: int = 20) -> str:
    """Pobierz listę aktywności treningowych (treningi, HR, moc, TSS)"""
    from datetime import date, timedelta
    if not oldest:
        oldest = (date.today() - timedelta(days=90)).isoformat()
    if not newest:
        newest = date.today().isoformat()
    data = await icu(f"/athlete/{ATHLETE_ID}/activities",
        {"oldest": oldest, "newest": newest, "limit": limit})
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
async def get_activity_details(activity_id: str) -> str:
    """
    Pobierz szczegóły jednej aktywności z lapami i danymi odcinkowymi.
    Zwraca: strefy mocy i HR, interwały, lapy z mocą/HR/kadencją/przewyższeniem,
    profil terenu (altitude), współczynnik efektywności, decoupling.
    activity_id: ID z get_activities (np. i147247620)
    """
    data = await icu(f"/athlete/{ATHLETE_ID}/activities/{activity_id}")
    if isinstance(data, list):
        data = data[0] if data else {}

    # FIT z Garmin Connect — per-sekundowe dane: kadencja, moc, HR, prędkość, alt, temp
    import io, zipfile
    from fitparse import FitFile
    from datetime import datetime, timedelta
    import asyncio as _aio

    fit_streams = {}
    blocks = []
    try:
        start_local = data.get("start_date_local", "")[:19]
        act_date = start_local[:10]
        act_start = datetime.fromisoformat(start_local)
        g = _garmin_client()
        garmin_acts = await _aio.get_event_loop().run_in_executor(
            None, lambda: g.get_activities_by_date(act_date, act_date))
        best_id, best_diff = None, timedelta(hours=2)
        for ga in garmin_acts:
            gs = ga.get("startTimeLocal", "")[:19]
            if not gs:
                continue
            try:
                diff = abs(datetime.fromisoformat(gs) - act_start)
                if diff < best_diff:
                    best_diff, best_id = diff, ga["activityId"]
            except Exception:
                continue
        if best_id:
            fit_zip = await _aio.get_event_loop().run_in_executor(
                None, lambda: g.download_activity(
                    best_id, dl_fmt=g.ActivityDownloadFormat.ORIGINAL))
            z = zipfile.ZipFile(io.BytesIO(fit_zip))
            fit_raw = z.read(z.namelist()[0]) if fit_zip[:2] == b"PK" else fit_zip
            fit = FitFile(io.BytesIO(fit_raw))
            records = []
            t0 = None
            for msg in fit.get_messages("record"):
                row = {}
                for f in msg:
                    n, v = f.name, f.value
                    if v is None:
                        continue
                    if n == "timestamp":
                        row["ts"] = v
                    elif n == "cadence":
                        row["cad"] = int(v)
                    elif n == "power":
                        row["pwr"] = int(v)
                    elif n == "heart_rate":
                        row["hr"] = int(v)
                    elif n in ("enhanced_speed", "speed") and "spd" not in row:
                        row["spd"] = round(float(v) * 3.6, 1)
                    elif n == "altitude":
                        row["alt"] = round(float(v), 1)
                    elif n == "temperature":
                        row["temp"] = int(v)
                if "ts" not in row:
                    continue
                if t0 is None:
                    t0 = row["ts"]
                row["t"] = int((row["ts"] - t0).total_seconds())
                del row["ts"]
                records.append(row)
            # Podsumowanie streamów
            for field, label in [("cad","cadence"),("pwr","power"),("hr","heart_rate"),
                                  ("spd","speed"),("alt","altitude"),("temp","temperature")]:
                vals = [r[field] for r in records if field in r]
                if not vals:
                    continue
                fit_streams[label] = {
                    "avg": round(sum(vals)/len(vals), 1),
                    "min": min(vals), "max": max(vals),
                    "probki_co_30s": vals[::30],
                }
                if field == "cad":
                    pedaling = [v for v in vals if v > 0]
                    if pedaling:
                        fit_streams[label]["avg_tylko_pedalowanie"] = round(sum(pedaling)/len(pedaling), 1)
                        fit_streams[label]["pct_powyzej_70rpm"] = round(sum(1 for v in pedaling if v >= 70)/len(pedaling)*100, 0)
                        fit_streams[label]["pct_powyzej_80rpm"] = round(sum(1 for v in pedaling if v >= 80)/len(pedaling)*100, 0)
            # Ciągłe bloki (przerwa >5s = nowy blok, min 60s)
            blk_start = 0
            def _save_block(recs):
                if len(recs) < 60:
                    return None
                ped = [r["cad"] for r in recs if r.get("cad", 0) > 0]
                if not ped:
                    return None
                alts = [r["alt"] for r in recs if "alt" in r]
                gain = sum(max(0, alts[j+1]-alts[j]) for j in range(len(alts)-1)) if len(alts) > 1 else 0
                return {
                    "t_start_s": recs[0]["t"],
                    "czas_min": round((recs[-1]["t"]-recs[0]["t"])/60, 1),
                    "cad_avg": round(sum(ped)/len(ped), 1),
                    "cad_pct_pedaling": round(len(ped)/len(recs)*100, 0),
                    "pwr_avg": round(sum(r["pwr"] for r in recs if "pwr" in r)/max(1,sum(1 for r in recs if "pwr" in r)), 0),
                    "hr_avg": round(sum(r["hr"] for r in recs if "hr" in r)/max(1,sum(1 for r in recs if "hr" in r)), 0),
                    "alt_gain_m": round(gain, 0),
                }
            for i in range(1, len(records)):
                if records[i]["t"] - records[i-1]["t"] > 5:
                    b = _save_block(records[blk_start:i])
                    if b:
                        blocks.append(b)
                    blk_start = i
            b = _save_block(records[blk_start:])
            if b:
                blocks.append(b)
    except Exception as e:
        fit_streams["error"] = str(e)

    data["fit_streams"] = fit_streams
    data["continuous_blocks"] = blocks
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
async def get_route_surface(activity_id: str) -> str:
    """
    Analizuje nawierzchnię trasy na podstawie GPS z Garmin Connect i OpenStreetMap.
    Zwraca: lokalizację (miasto/dzielnica), % nawierzchni, typ drogi, kontekst kadencji.
    Wywołuj przy każdej ocenie jazdy przed interpretacją kadencji i prędkości.
    activity_id: ID z get_activities (np. i147247620)
    """
    import math, io, zipfile
    from fitparse import FitFile
    from datetime import datetime, timedelta
    import asyncio
    activity_id = str(activity_id)

    # 1. Pobierz datę startu jazdy z Intervals
    try:
        act_data = await icu(f"/athlete/{ATHLETE_ID}/activities/{activity_id}")
        if isinstance(act_data, list):
            act_data = act_data[0] if act_data else {}
        start_local = act_data.get("start_date_local", "")[:19]
        act_date = start_local[:10]
        act_start = datetime.fromisoformat(start_local)
    except Exception as e:
        return _route_surface_error(activity_id, f"Błąd pobierania aktywności: {e}")

    # 2. Znajdź pasującą aktywność w Garmin po dacie i czasie startu
    try:
        g = _garmin_client()
        garmin_acts = await asyncio.get_event_loop().run_in_executor(
            None, lambda: g.get_activities_by_date(act_date, act_date))
        best_id = None
        best_diff = timedelta(hours=2)
        for ga in garmin_acts:
            gs = ga.get("startTimeLocal", "")[:19]
            if not gs:
                continue
            try:
                gdt = datetime.fromisoformat(gs)
                diff = abs(gdt - act_start)
                if diff < best_diff:
                    best_diff = diff
                    best_id = ga["activityId"]
            except Exception:
                continue
        if not best_id:
            return _route_surface_error(activity_id, f"Brak aktywności Garmin z dnia {act_date}")
    except Exception as e:
        return _route_surface_error(activity_id, f"Błąd Garmin: {e}")

    # 3. Pobierz FIT file z Garmina i wyciągnij GPS
    try:
        fit_zip = await asyncio.get_event_loop().run_in_executor(
            None, lambda: g.download_activity(
                best_id, dl_fmt=g.ActivityDownloadFormat.ORIGINAL))
        if fit_zip[:2] == b'PK':
            z = zipfile.ZipFile(io.BytesIO(fit_zip))
            fit_raw = z.read(z.namelist()[0])
        else:
            fit_raw = fit_zip
        fit = FitFile(io.BytesIO(fit_raw))
        latlng_data = []
        for record in fit.get_messages('record'):
            lat = lon = None
            for field in record:
                if field.name == 'position_lat' and field.value:
                    lat = field.value * (180 / 2**31)
                if field.name == 'position_long' and field.value:
                    lon = field.value * (180 / 2**31)
            if lat and lon:
                latlng_data.append([lat, lon])
    except Exception as e:
        return _route_surface_error(activity_id, f"Błąd FIT: {e}")

    if len(latlng_data) < 2:
        return _route_surface_error(activity_id, "Brak danych GPS w pliku FIT")

    # 4. Próbkowanie — max 80 punktów równomiernie
    STEP = max(1, len(latlng_data) // 80)
    samples = latlng_data[::STEP]

    # 5. Bounding box z marginesem
    lats = [p[0] for p in samples]
    lons = [p[1] for p in samples]
    south = min(lats) - 0.005
    north = max(lats) + 0.005
    west  = min(lons) - 0.005
    east  = max(lons) + 0.005

    # 6. Jedno zapytanie Overpass
    query = f"[out:json][timeout:25];way[highway]({south},{west},{north},{east});out tags geom;"
    try:
        ways = await _overpass_post_async(query, timeout=30)
    except Exception as e:
        return _route_surface_error(activity_id, f"Błąd Overpass API: {e}")

    if not ways:
        return _route_surface_error(activity_id, "Brak danych OSM dla tej trasy")

    # 7. Dopasowanie próbek GPS do najbliższej drogi
    def dist_m(lat1, lon1, lat2, lon2):
        dlat = (lat2 - lat1) * 111320
        dlon = (lon2 - lon1) * 111320 * math.cos(math.radians(lat1))
        return math.sqrt(dlat**2 + dlon**2)

    def nearest_way(lat, lon):
        best_dist, best_tags = float("inf"), {}
        for way in ways:
            for node in way.get("geometry", []):
                d = dist_m(lat, lon, node["lat"], node["lon"])
                if d < best_dist:
                    best_dist = d
                    best_tags = way.get("tags", {})
        return best_tags, best_dist

    SURFACE_PL = {
        "asphalt": "asfalt", "paved": "asfalt", "concrete": "beton",
        "cobblestone": "kocie łby", "sett": "kocie łby",
        "paving_stones": "kostka brukowa",
        "gravel": "gravel/żwir", "fine_gravel": "gravel drobny",
        "compacted": "ubita nawierzchnia",
        "dirt": "ziemia/grunt", "ground": "grunt",
        "grass": "trawa", "sand": "piasek", "unpaved": "nieutwardzona",
    }
    CADENCE_CONTEXT = {
        "asfalt":             "Gładki asfalt — optymalna kadencja 78–88 rpm (gravel, korby 160mm)",
        "beton":              "Beton — kadencja 78–88 rpm",
        "kocie łby":          "Kocie łby — niższa kadencja (65–75 rpm) naturalna, wyższy VI akceptowalny",
        "kostka brukowa":     "Kostka — kadencja 68–78 rpm, wyższy VI akceptowalny",
        "gravel/żwir":        "Gravel/żwir — kadencja 68–80 rpm, niższa prędkość i wyższy VI normalne",
        "gravel drobny":      "Gravel drobny — kadencja 72–82 rpm",
        "ubita nawierzchnia": "Ubita nawierzchnia — kadencja 72–85 rpm",
        "ziemia/grunt":       "Grunt/dirt — kadencja 60–75 rpm, wskaźniki nieporównywalne z asfaltem",
        "grunt":              "Grunt/dirt — kadencja 60–75 rpm, wskaźniki nieporównywalne z asfaltem",
    }

    surface_counts, highway_counts = {}, {}
    for pt in samples:
        tags, d = nearest_way(pt[0], pt[1])
        if d > 100:
            continue
        raw_surf = tags.get("surface")
        label = SURFACE_PL.get(raw_surf, raw_surf or "nieznana")
        surface_counts[label] = surface_counts.get(label, 0) + 1
        hw = tags.get("highway")
        if hw:
            highway_counts[hw] = highway_counts.get(hw, 0) + 1

    total = sum(surface_counts.values()) or 1
    dominant = max(surface_counts, key=surface_counts.get) if surface_counts else "nieznana"

    # 8. Reverse geocoding
    lokalizacja = {}
    try:
        center_lat = (min(lats) + max(lats)) / 2
        center_lon = (min(lons) + max(lons)) / 2
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": center_lat, "lon": center_lon,
                        "format": "json", "zoom": 13,
                        "accept-language": "pl"},
                headers={"User-Agent": "Q-rowerowy-asystent/1.0"}
            )
            if r.status_code == 200:
                geo = r.json()
                addr = geo.get("address", {})
                lokalizacja = {
                    "miasto":    addr.get("city") or addr.get("town") or addr.get("village"),
                    "dzielnica": addr.get("suburb") or addr.get("quarter") or addr.get("neighbourhood"),
                    "gmina":     addr.get("municipality") or addr.get("county"),
                    "kraj":      addr.get("country"),
                }
    except Exception:
        pass

    result = {
        "activity_id":       activity_id,
        "garmin_id":         best_id,
        "punkty_gps":        len(latlng_data),
        "lokalizacja":       lokalizacja,
        "nawierzchnia": {k: f"{round(v/total*100)}%"
                         for k, v in sorted(surface_counts.items(), key=lambda x: -x[1])},
        "dominujaca":        dominant,
        "kontekst_kadencji": CADENCE_CONTEXT.get(dominant, "Mieszana — interpretuj wskaźniki ostrożnie"),
        "typy_drog_osm":     {k: f"{round(v/total*100)}%"
                              for k, v in sorted(highway_counts.items(), key=lambda x: -x[1])},
    }
    _save_route_surface_cache(activity_id, result)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_wellness(oldest: str = None, newest: str = None) -> str:
    """Pobierz dane zdrowotne: HRV, tętno spoczynkowe, waga, sen, nastrój, CTL/ATL/TSB"""
    data = await icu(f"/athlete/{ATHLETE_ID}/wellness",
        {"oldest": oldest, "newest": newest})
    return json.dumps(data, ensure_ascii=False)

@mcp.tool()
def list_local_fit_files(search_dirs: str = None) -> str:
    """
    Znajdź lokalne pliki FIT po stronie QBot/Q.
    search_dirs: opcjonalna lista katalogów rozdzielona dwukropkiem.
    """
    files = find_fit_files(search_dirs)
    return json.dumps({"fit_files": [str(p) for p in files], "count": len(files)}, ensure_ascii=False)

@mcp.tool()
def export_fit_to_qlab_replay(search_dirs: str = None, output_path: str = None) -> str:
    """
    Eksportuj lokalne FIT do qbot_replay_log.json dla QLab passthrough.
    QBot znajduje i parsuje FIT, zwraca ReplayTick[] w polu ticks.
    Brakujące dane pozostają null; QBot nie wylicza brakujących pól.
    """
    return json.dumps(export_qlab_replay(search_dirs, output_path), ensure_ascii=False)

# ── SPRZĘT (ROWERY) ──────────────────────────────────────────────────────────

@mcp.tool()
async def get_gear() -> str:
    """
    Pobierz listę sprzętu (rowerów) zsynchronizowanych ze Stravy przez Intervals.icu.
    Zwraca: ID sprzętu, nazwa, dystans, czy główny. Używaj do identyfikacji roweru
    użytego w danej aktywności (pole gear.id w get_activities/get_activity_details).
    """
    data = await icu(f"/athlete/{ATHLETE_ID}/gear")
    clean = []
    for g in (data or []):
        clean.append({
            "strava_gear_id": g.get("id"),
            "nazwa":          g.get("name"),
            "typ":            g.get("type"),
            "glowny":         g.get("primary"),
            "dystans_km":     round(g.get("distance", 0) / 1000) if g.get("distance") else None,
        })
    return json.dumps(clean, ensure_ascii=False)

# ── POGODA ────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_weather(days: int = 7, location: str = "Marki") -> str:
    """Pobierz aktualną pogodę i prognozę godzinową (24h) oraz dzienną. Parametry: location - nazwa miasta (np. 'Florencja', 'Płock'), domyślnie Marki; days - liczba dni prognozy (1-7). Zwraca: teraz (aktualne warunki), godzinowo (24 godziny co 1h: temperatura, wiatr, zachmurzenie, opady), prognoza (dni). Jednostki: Celsius, m/s."""
    from datetime import datetime, timezone

    WIND_DIR = {0:"N",45:"NE",90:"E",135:"SE",180:"S",225:"SW",270:"W",315:"NW",360:"N"}
    def wind_dir(deg):
        if deg is None: return None
        return WIND_DIR.get(round(deg / 45) * 45 % 360, "?")

    DEFAULT_LOCATION = "Marki"
    days = max(1, min(days, 7))
    lat, lon, loc_name = LOC_LAT, LOC_LON, LOC_NAME

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if location and location != DEFAULT_LOCATION:
                geo = await c.get("https://geocoding-api.open-meteo.com/v1/search",
                                  params={"name": location, "count": 1, "language": "pl"})
                geo.raise_for_status()
                results = geo.json().get("results")
                if not results:
                    return json.dumps({"error": f"Nie znaleziono lokalizacji: {location}"}, ensure_ascii=False)
                lat      = results[0]["latitude"]
                lon      = results[0]["longitude"]
                loc_name = results[0].get("name", location)

            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude":  lat, "longitude": lon,
                "current":   "temperature_2m,apparent_temperature,precipitation,weathercode,"
                             "windspeed_10m,winddirection_10m,cloudcover,relativehumidity_2m",
                "hourly":    "temperature_2m,precipitation_probability,precipitation,"
                             "windspeed_10m,winddirection_10m,cloudcover,weathercode",
                "daily":     "weathercode,temperature_2m_max,temperature_2m_min,"
                             "precipitation_sum,windspeed_10m_max,winddirection_10m_dominant,"
                             "cloudcover_mean,precipitation_probability_max",
                "forecast_days": days, "timezone": "auto",
                "wind_speed_unit": "ms", "temperature_unit": "celsius",
                "models": "ecmwf_ifs025",
            })
            r.raise_for_status()
            raw = r.json()
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    cur = raw["current"]
    d   = raw["daily"]
    h   = raw["hourly"]

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    h_times = h.get("time", [])
    try:
        start = next(i for i, t in enumerate(h_times) if t >= now_str)
    except StopIteration:
        start = 0

    godzinowo = [
        {
            "czas":           h_times[i],
            "temperatura":    f"{h['temperature_2m'][i]}°C",
            "szansa_deszczu": f"{h['precipitation_probability'][i]}%",
            "opady_mm":       h["precipitation"][i],
            "wiatr_ms":       f"{h['windspeed_10m'][i]} m/s",
            "kierunek_wiatru": wind_dir(h["winddirection_10m"][i]),
            "zachmurzenie":   f"{h['cloudcover'][i]}%",
            "warunki":        WMO.get(h["weathercode"][i], str(h["weathercode"][i])),
        }
        for i in range(start, min(start + 24, len(h_times)))
    ]

    return json.dumps({
        "lokalizacja": loc_name,
        "teraz": {
            "temperatura":     f"{cur['temperature_2m']}°C",
            "odczuwalna":      f"{cur['apparent_temperature']}°C",
            "warunki":         WMO.get(cur['weathercode'], str(cur['weathercode'])),
            "wiatr_ms":        f"{cur['windspeed_10m']} m/s",
            "kierunek_wiatru": wind_dir(cur['winddirection_10m']),
            "zachmurzenie":    f"{cur['cloudcover']}%",
            "wilgotnosc":      f"{cur['relativehumidity_2m']}%",
        },
        "hourly_forecast": godzinowo,
        "prognoza": [
            {
                "data":          d["time"][i],
                "warunki":       WMO.get(d["weathercode"][i], "?"),
                "temp_max":      f"{d['temperature_2m_max'][i]}°C",
                "temp_min":      f"{d['temperature_2m_min'][i]}°C",
                "szansa_deszcz": f"{d['precipitation_probability_max'][i]}%",
                "opady_mm":      d["precipitation_sum"][i],
                "max_wiatr_ms":  f"{d['windspeed_10m_max'][i]} m/s",
                "kierunek_wiatru": wind_dir(d["winddirection_10m_dominant"][i]),
                "zachmurzenie":  f"{d['cloudcover_mean'][i]}%",
            }
            for i in range(len(d["time"]))
        ]
    }, ensure_ascii=False)

# ── GARAŻ ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def garage_overview() -> str:
    """Pełny przegląd garażu: rowery, komponenty, odzież, notatki"""
    return json.dumps(db.garage_overview(), ensure_ascii=False)

@mcp.tool()
def get_bike(bike_id: int) -> str:
    """Szczegóły jednego roweru z komponentami i fittingiem"""
    return json.dumps(db.get_bike(bike_id), ensure_ascii=False)

@mcp.tool()
def save_bike(name: str, brand: str = None, model: str = None,
    type: str = None, year: int = None, color: str = None,
    weight_kg: float = None, frame_size: str = None,
    purchase_date: str = None, purchase_price: float = None,
    notes: str = None, id: int = None) -> str:
    """Zapisz lub zaktualizuj rower w garażu"""
    data = {k: v for k, v in locals().items() if v is not None}
    return json.dumps(db.save_bike(data), ensure_ascii=False)

@mcp.tool()
def save_component(category: str, brand: str = None, model: str = None,
    bike_id: int = None, position: str = None, spec: str = None,
    weight_g: int = None, purchase_date: str = None,
    purchase_price: float = None, mileage_km: float = None,
    serial_number: str = None, notes: str = None, id: int = None) -> str:
    """Zapisz komponent roweru (kaseta, łańcuch, opona, siodło, pedały itp.)"""
    data = {k: v for k, v in locals().items() if v is not None}
    return json.dumps(db.save_component(data), ensure_ascii=False)

@mcp.tool()
def save_fitting(bike_id: int, saddle_height_mm: float = None,
    saddle_setback_mm: float = None, saddle_tilt_deg: float = None,
    reach_mm: float = None, stack_mm: float = None, drop_mm: float = None,
    handlebar_width_mm: int = None, stem_length_mm: int = None,
    stem_angle_deg: int = None, crank_length_mm: int = None,
    cleat_left: str = None, cleat_right: str = None,
    shoe_size: str = None, notes: str = None,
    date_set: str = None, fitter_name: str = None, id: int = None) -> str:
    """Zapisz ustawienia fitingowe roweru"""
    data = {k: v for k, v in locals().items() if v is not None}
    return json.dumps(db.save_fitting(data), ensure_ascii=False)

@mcp.tool()
def save_gear(category: str, brand: str = None, model: str = None,
    size: str = None, color: str = None, purchase_date: str = None,
    purchase_price: float = None, condition: str = None,
    notes: str = None, id: int = None) -> str:
    """Zapisz odzież lub sprzęt (kask, buty, kurtka, rękawiczki itp.)"""
    data = {k: v for k, v in locals().items() if v is not None}
    return json.dumps(db.save_gear(data), ensure_ascii=False)

@mcp.tool()
def save_memory(topic: str, content: str) -> str:
    """Dopisz notatkę do garażu bez dublowania dokładnie tej samej treści."""
    return json.dumps(db.save_memory_append(topic, content), ensure_ascii=False)


@mcp.tool()
def save_qbot_artifact(relative_path: str, content: str, overwrite: bool = False) -> str:
    """Zapisz wygenerowany artefakt QBot do kontrolowanego katalogu /opt/qbot/artifacts."""
    try:
        normalized_relative_path = validate_artifact_relative_path(relative_path)
        absolute_path = artifact_absolute_path(normalized_relative_path)
        artifacts_root = ARTIFACT_ROOT.resolve(strict=False)
        resolved_target = absolute_path.resolve(strict=False)
        if not resolved_target.is_relative_to(artifacts_root):
            raise ValueError("resolved path escapes artifacts root")
        if not isinstance(content, str):
            raise ValueError("content must be a string")

        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        existed = absolute_path.exists()
        if existed and not overwrite:
            return json.dumps({
                "status": "rejected",
                "absolute_path": str(absolute_path),
                "relative_path": normalized_relative_path,
                "bytes_written": 0,
                "overwritten": False,
                "error": "file exists and overwrite is false",
            }, ensure_ascii=False)

        absolute_path.write_text(content, encoding="utf-8")
        return json.dumps({
            "status": "ok",
            "absolute_path": str(absolute_path),
            "relative_path": normalized_relative_path,
            "bytes_written": len(content.encode("utf-8")),
            "overwritten": existed,
        }, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({
            "status": "rejected",
            "absolute_path": None,
            "relative_path": relative_path,
            "bytes_written": 0,
            "overwritten": False,
            "error": str(exc),
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "absolute_path": str(absolute_path) if "absolute_path" in locals() else None,
            "relative_path": relative_path,
            "bytes_written": 0,
            "overwritten": False,
            "error": str(exc),
        }, ensure_ascii=False)


@mcp.tool()
def replace_memory(topic: str, content: str) -> str:
    """Zastąp treść notatki w garażu. Używaj tylko dla snapshotów/stanu bieżącego."""
    return json.dumps(db.save_memory(topic, content), ensure_ascii=False)

@mcp.tool()
def search_garage(query: str) -> str:
    """Szukaj w całym garażu po słowie kluczowym"""
    return json.dumps(db.search_garage(query), ensure_ascii=False)

@mcp.tool()
def update_item(table: str, item_id: int, changes: dict) -> str:
    """Zaktualizuj dowolny rekord w garażu"""
    return json.dumps(db.update_item(table, item_id, changes), ensure_ascii=False)

@mcp.tool()
def delete_item(table: str, item_id: int) -> str:
    """Usuń lub dezaktywuj rekord z garażu"""
    return json.dumps(db.delete_item(table, item_id), ensure_ascii=False)

# ── PODRÓŻE ───────────────────────────────────────────────────────────────────

@mcp.tool()
def get_trips(status: str = None) -> str:
    """Pobierz listę wyjazdów i bikepackingów"""
    return json.dumps(db.get_trips(status), ensure_ascii=False)

@mcp.tool()
def get_trip(trip_id: int) -> str:
    """Szczegóły wyjazdu z listą pakowania"""
    return json.dumps(db.get_trip(trip_id), ensure_ascii=False)

@mcp.tool()
def save_trip(name: str, destination: str = None, country: str = None,
    start_date: str = None, end_date: str = None, type: str = None,
    distance_km: float = None, elevation_m: int = None,
    bike_id: int = None, accommodation: str = None,
    notes: str = None, status: str = None, id: int = None) -> str:
    """Zapisz wyjazd lub bikepacking"""
    data = {k: v for k, v in locals().items() if v is not None}
    return json.dumps(db.save_trip(data), ensure_ascii=False)

@mcp.tool()
def create_packing_list(trip_id: int, name: str, items: list) -> str:
    """Utwórz listę pakowania dla wyjazdu"""
    return json.dumps(db.create_packing_list(trip_id, name, items), ensure_ascii=False)

@mcp.tool()
def update_packing_item(item_id: int, packed: bool = None, notes: str = None) -> str:
    """Oznacz przedmiot jako spakowany lub dodaj notatkę"""
    return json.dumps(db.update_packing_item(item_id, packed, notes), ensure_ascii=False)

@mcp.tool()
def get_packing_summary(list_id: int) -> str:
    """Podsumowanie postępu pakowania"""
    return json.dumps(db.get_packing_summary(list_id), ensure_ascii=False)

# ── RWGPS / TRASY ───────────────────────────────────────────────────────────

@mcp.tool()
def get_rwgps_routes(limit: int = 20, offset: int = 0, sort: str = "updated_at",
    order: str = "desc", search: str = None) -> str:
    """Pobierz listę tras z Ride With GPS"""
    return json.dumps(
        rwgps_list_routes(limit=limit, offset=offset, sort=sort, order=order, search=search),
        ensure_ascii=False,
    )


@mcp.tool()
def get_rwgps_route(route_id: str) -> str:
    """Pobierz szczegóły jednej trasy RWGPS"""
    return json.dumps(rwgps_get_route(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_route_export_links(route_id: str) -> str:
    """Pobierz dostępne linki eksportowe trasy RWGPS"""
    return json.dumps(rwgps_get_route_export_links(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_route_geometry(route_id: str) -> str:
    """Pobierz geometrię trasy RWGPS"""
    return json.dumps(rwgps_get_route_geometry(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_route_cue_sheet(route_id: str) -> str:
    """Pobierz cue sheet trasy RWGPS"""
    return json.dumps(rwgps_get_route_cue_sheet(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_route_gpx(route_id: str) -> str:
    """Wygeneruj GPX z trasy RWGPS"""
    return json.dumps(rwgps_download_route_gpx(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_route_tcx(route_id: str) -> str:
    """Wygeneruj TCX z trasy RWGPS"""
    return json.dumps(rwgps_download_route_tcx(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_route_fit(route_id: str) -> str:
    """Pobierz FIT trasy RWGPS, jeśli klient to obsługuje"""
    return json.dumps(rwgps_download_route_fit(route_id), ensure_ascii=False)


@mcp.tool()
def get_rwgps_planned_routes(limit: int = 4) -> str:
    """Pobierz ostatnie lub planowane trasy z RWGPS"""
    return json.dumps(rwgps_list_planned_routes(limit=limit), ensure_ascii=False)


@mcp.tool()
def get_rwgps_collections() -> str:
    """Pobierz kolekcje tras RWGPS"""
    return json.dumps(rwgps_list_collections(), ensure_ascii=False)


@mcp.tool()
def qbot_manifest_version() -> str:
    """
    Diagnostyka serwera MCP. Zwraca: pid, ścieżkę skryptu, timestamp startu,
    liczbę zarejestrowanych tools, wersję Pythona.
    """
    import sys
    import os as _os
    from datetime import datetime
    return json.dumps({
        "pid": _os.getpid(),
        "script_path": __file__ if "__file__" in dir() else str(Path(__file__)),
        "python_version": sys.version,
        "registered_tools": len(mcp._tool_manager._tools) if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools") else None,
        "server_started_at": None,
        "artifact_root": str(ARTIFACT_ROOT),
        "router_count": len(mcp._tool_manager._tools) if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools") else "unknown",
    }, ensure_ascii=False)


@mcp.tool()
def export_rwgps_route_to_artifact(route_id: str, format: str = "gpx") -> str:
    """
    Eksportuj trasę RWGPS do artefaktu (plik GPX/TCX/JSON) po stronie QBot.
    NIE zwraca pełnej geometrii w odpowiedzi MCP — tylko metadane i ścieżkę do pliku.
    format: gpx, tcx, json
    """
    return json.dumps(rwgps_export_route_to_artifact(route_id, format), ensure_ascii=False)


@mcp.tool()
def summarize_rwgps_artifact(artifact_path_or_name: str) -> str:
    """
    Podsumowanie zapisanego artefaktu GPX/TCX/JSON RWGPS.
    Zwraca: point_count, bounds, distance_km, elevation_gain_m, elevation_loss_m,
    min/max elevation, first/last point, looks_valid, cue_count (dla JSON).
    """
    return json.dumps(rwgps_summarize_rwgps_artifact(artifact_path_or_name), ensure_ascii=False)


# -- OVERPASS: helper z fallbackiem mirrorow + backoff na 429/5xx --------------
import time as _time

_OVERPASS_ENDPOINTS = [
    u.strip() for u in os.getenv(
        "QBOT_OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter",
    ).split(",") if u.strip()
]
_OVERPASS_RETRIES = int(os.getenv("QBOT_OVERPASS_RETRIES", "4"))
_OVERPASS_BACKOFF = float(os.getenv("QBOT_OVERPASS_BACKOFF", "3.0"))
_OVERPASS_SLEEP = float(os.getenv("QBOT_OVERPASS_SLEEP", "1.0"))


def _overpass_post(query: str, timeout: int = 30) -> list:
    """POST do Overpass z rotacja mirrorow i backoffem.

    Kolejnosc endpointow z env QBOT_OVERPASS_URLS (CSV). Na 429 przeskakuje
    od razu na nastepny mirror; na 5xx/timeout/blad sieci ponawia ten sam
    endpoint z wykladniczym backoffem. Zwraca liste elements OSM.
    Rzuca RuntimeError gdy wszystkie mirrory zawioda.
    """
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
                    last = f"429 Too Many Requests @ {endpoint}"
                    ra = r.headers.get("Retry-After")
                    try:
                        delay = float(ra) if ra else _OVERPASS_BACKOFF * (2 ** attempt)
                    except ValueError:
                        delay = _OVERPASS_BACKOFF * (2 ** attempt)
                    _time.sleep(min(delay, 30))
                    continue
                if r.status_code in (502, 503, 504):
                    last = f"{r.status_code} @ {endpoint}"
                    _time.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
                    continue
                r.raise_for_status()
                return r.json().get("elements", [])
            except Exception as exc:
                last = exc
                _time.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
                continue
    raise RuntimeError(f"Overpass: wszystkie mirrory zawiodly ({last})")


async def _overpass_post_async(query: str, timeout: int = 30) -> list:
    """Async wariant _overpass_post -- ta sama logika mirrorow + backoff."""
    import asyncio
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
                async with httpx.AsyncClient(timeout=timeout) as c:
                    r = await c.post(endpoint, content=body, headers=headers)
                if r.status_code == 429:
                    last = f"429 Too Many Requests @ {endpoint}"
                    ra = r.headers.get("Retry-After")
                    try:
                        delay = float(ra) if ra else _OVERPASS_BACKOFF * (2 ** attempt)
                    except ValueError:
                        delay = _OVERPASS_BACKOFF * (2 ** attempt)
                    await asyncio.sleep(min(delay, 30))
                    continue
                if r.status_code in (502, 503, 504):
                    last = f"{r.status_code} @ {endpoint}"
                    await asyncio.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
                    continue
                r.raise_for_status()
                return r.json().get("elements", [])
            except Exception as exc:
                last = exc
                await asyncio.sleep(min(_OVERPASS_BACKOFF * (2 ** attempt), 30))
                continue
    raise RuntimeError(f"Overpass: wszystkie mirrory zawiodly ({last})")


@mcp.tool()
def analyze_rwgps_artifact_surface(path_or_name: str, sample_distance_m: int = 80) -> str:
    """
    Analizuje nawierzchnię trasy z artefaktu RWGPS (GPX/JSON) przez OpenStreetMap/Overpass.

    Wczytuje punkty z pliku GPX/TCX/JSON, próbkuje co sample_distance_m metrów,
    odpytuje Overpass API o drogi i klasyfikuje nawierzchnię.

    Zwraca: surface_percentages, dominant_surface, road_type_percentages,
    tracktype_percentages, coverage, bounds, point_count, sampled_points,
    matched/unmatched, confidence, warnings.

    Wynik jest cache'owany w /opt/qbot/artifacts/analysis/.
    """
    import hashlib
    import math
    from urllib.parse import urlencode

    path_or_name = str(path_or_name).strip()
    if not path_or_name:
        return json.dumps({"ok": False, "error": "INVALID_PATH", "reason": "path_or_name must not be empty"}, ensure_ascii=False)

    sample_distance_m = max(100, min(sample_distance_m, 5000))

    CACHE_ROOT = Path("/opt/qbot/artifacts/analysis")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    # Determine file and sha256
    try:
        from tools.rwgps.client import ARTIFACT_RWGPS_EXPORT_DIR, _resolve_artifact_for_summary
        file_path = _resolve_artifact_for_summary(path_or_name)
    except Exception as exc:
        return json.dumps({"ok": False, "error": "NOT_FOUND", "reason": str(exc), "path_or_name": path_or_name}, ensure_ascii=False)

    try:
        file_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
    except Exception as exc:
        return json.dumps({"ok": False, "error": "WRITE_FAILED", "reason": str(exc), "path": str(file_path)}, ensure_ascii=False)

    cache_name = f"surface_{file_path.stem}_{sample_distance_m}m.json"
    cache_path = CACHE_ROOT / cache_name


    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached.get("ok"):
                cached["cache_hit"] = True
                return json.dumps(cached, ensure_ascii=False)
        except Exception:
            pass

    # Extract points
    try:
        points = rwgps_extract_artifact_points(path_or_name)
    except Exception as exc:
        return json.dumps({"ok": False, "error": "RWGPS_EXPORT_FAILED", "reason": str(exc), "path_or_name": path_or_name}, ensure_ascii=False)

    if len(points) < 2:
        return json.dumps({"ok": False, "error": "NO_POINTS", "reason": "Artifact has fewer than 2 points", "path_or_name": path_or_name, "point_count": len(points)}, ensure_ascii=False)

    # Compute cumulative distance and sample
    def _dist_fast(lat1, lon1, lat2, lon2):
        dlat = (lat2 - lat1) * 111320
        dlon = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
        return math.sqrt(dlat * dlat + dlon * dlon)

    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + _dist_fast(points[i-1][0], points[i-1][1], points[i][0], points[i][1]))

    samples = [points[0]]
    next_target = sample_distance_m
    for i in range(1, len(points)):
        if dists[i] >= next_target:
            samples.append(points[i])
            next_target += sample_distance_m

    if samples[-1] != points[-1]:
        samples.append(points[-1])

    _lats = [p[0] for p in points]
    _lngs = [p[1] for p in points]
    south, north = (min(_lats), max(_lats)) if _lats else (0.0, 0.0)
    west, east = (min(_lngs), max(_lngs)) if _lngs else (0.0, 0.0)

    sample_dists = [0.0]
    for _i in range(1, len(samples)):
        sample_dists.append(sample_dists[-1] + _dist_fast(samples[_i - 1][0], samples[_i - 1][1], samples[_i][0], samples[_i][1]))
    sample_surfaces = [None] * len(samples)

    # Nie ograniczamy liczby probek - wiecej probek = lepsza jakosc
    # Batchujemy po 15 punktow, kazdy batch to osobne zapytanie Overpass around:20m

    # Bounding box — tylko do raportu (bounds w wyniku/bledach); sampling per-punkt around:20m
    lats = [p[0] for p in samples]
    lons = [p[1] for p in samples]
    south = min(lats) - 0.005
    north = max(lats) + 0.005
    west = min(lons) - 0.005
    east = max(lons) + 0.005

    # Batch Overpass queries — around:20m per punkt (zamiast bbox)
    BATCH_SIZE = 15
    sample_batches = [samples[i:i + BATCH_SIZE] for i in range(0, len(samples), BATCH_SIZE)]

    SURFACE_MAP = {
        "asphalt": "asfalt", "paved": "asfalt", "concrete": "beton",
        "cobblestone": "kocie łby", "sett": "kocie łby",
        "paving_stones": "kostka brukowa",
        "gravel": "gravel/żwir", "fine_gravel": "gravel drobny",
        "compacted": "ubita nawierzchnia",
        "dirt": "ziemia/grunt", "ground": "grunt",
        "grass": "trawa", "sand": "piasek", "unpaved": "nieutwardzona",
    }

    SMOOTHNESS_MAP: dict[str, str] = {
        "excellent": "doskonała", "good": "dobra", "intermediate": "średnia",
        "bad": "słaba", "very_bad": "bardzo słaba",
        "horrible": "okropna", "very_horrible": "bardzo okropna",
        "impassable": "nieprzejezdna",
    }

    surface_counts: dict[str, int] = {}
    highway_counts: dict[str, int] = {}
    tracktype_counts: dict[str, int] = {}
    smoothness_counts: dict[str, int] = {}
    matched = 0
    unmatched = 0
    MAX_MATCH_DIST_M = 150
    osm_errors: list[str] = []

    for batch_idx, batch in enumerate(sample_batches):
        # around:20m per punkt - pobiera droge najblizej punktu GPS
        around_parts = "".join(
            f"  way[highway](around:20,{pt[0]},{pt[1]});\n"
            for pt in batch
        )
        batch_query = f"[out:json][timeout:25];(\n{around_parts});out tags geom;"
        batch_ways = []
        try:
            batch_ways = _overpass_post(batch_query, timeout=30)
        except Exception as exc:
            osm_errors.append(f"batch {batch_idx + 1}/{len(sample_batches)}: {exc}")
            unmatched += len(batch)
            continue
        if _OVERPASS_SLEEP > 0 and batch_idx + 1 < len(sample_batches):
            _time.sleep(_OVERPASS_SLEEP)

        if not batch_ways:
            unmatched += len(batch)
            continue

        for _local_i, pt in enumerate(batch):
            _gidx = batch_idx * BATCH_SIZE + _local_i
            best_tags = {}
            best_dist = float("inf")
            for way in batch_ways:
                for node in way.get("geometry", []):
                    d = _dist_fast(pt[0], pt[1], node["lat"], node["lon"])
                    if d < best_dist:
                        best_dist = d
                        best_tags = way.get("tags", {})
            if best_dist > MAX_MATCH_DIST_M:
                unmatched += 1
                continue
            matched += 1
            raw_surf = best_tags.get("surface")
            label = SURFACE_MAP.get(raw_surf, raw_surf or "nieznana")
            surface_counts[label] = surface_counts.get(label, 0) + 1
            if 0 <= _gidx < len(sample_surfaces):
                sample_surfaces[_gidx] = label
            hw = best_tags.get("highway")
            if hw:
                highway_counts[hw] = highway_counts.get(hw, 0) + 1
            tt = best_tags.get("tracktype")
            if tt:
                tracktype_counts[tt] = tracktype_counts.get(tt, 0) + 1
            sm = best_tags.get("smoothness")
            if sm:
                sm_label = SMOOTHNESS_MAP.get(sm, sm)
                smoothness_counts[sm_label] = smoothness_counts.get(sm_label, 0) + 1

    if not surface_counts and osm_errors:
        return json.dumps({"ok": False, "error": "OSM_UNAVAILABLE", "reason": f"Overpass API errors: {'; '.join(osm_errors[:3])}", "bounds": {"sw": [south, west], "ne": [north, east]}, "point_count": len(points), "sampled_points": len(samples)}, ensure_ascii=False)
    if not surface_counts:
        return json.dumps({"ok": False, "error": "OSM_UNAVAILABLE", "reason": "No OSM data found for any batch", "bounds": {"sw": [south, west], "ne": [north, east]}, "point_count": len(points), "sampled_points": len(samples)}, ensure_ascii=False)

    surface_segments = []
    _n = len(samples)
    _i = 0
    while _i < _n:
        _lab = sample_surfaces[_i] if (_i < len(sample_surfaces) and sample_surfaces[_i]) else "nieznana"
        _j = _i + 1
        while _j < _n and (sample_surfaces[_j] if sample_surfaces[_j] else "nieznana") == _lab:
            _j += 1
        _start_d = sample_dists[_i] if _i < len(sample_dists) else 0.0
        _end_d = sample_dists[_j] if _j < len(sample_dists) else sample_dists[-1]
        surface_segments.append({
            "surface": _lab,
            "distance_m": round(max(0.0, _end_d - _start_d), 1),
            "source": "osm_overpass",
            "start_lat": samples[_i][0],
            "start_lon": samples[_i][1],
            "end_lat": samples[_j - 1][0],
            "end_lon": samples[_j - 1][1],
        })
        _i = _j

    total = sum(surface_counts.values()) or 1
    dominated_by = max(surface_counts, key=surface_counts.get) if surface_counts else "nieznana"
    coverage_pct = round(matched / max(1, len(samples)) * 100, 1)

    warnings_list = []
    if unmatched > matched:
        warnings_list.append(f"Niski zasięg OSM: tylko {coverage_pct}% punktów dopasowanych")
    if dominated_by == "nieznana":
        warnings_list.append("Dominująca nawierzchnia nieznana — OSM może nie mieć tagów surface dla tej trasy")
    if osm_errors:
        warnings_list.append(f"Błędy Overpass: {len(osm_errors)}/{len(sample_batches)} batchy nieudane")

    smoothness_total = sum(smoothness_counts.values()) or 1
    result = {
        "ok": True,
        "status": "OK",
        "source": "rwgps_artifact",
        "artifact_path": str(file_path),
        "artifact_name": file_path.name,
        "artifact_sha256": file_sha,
        "sample_distance_m": sample_distance_m,
        "point_count": len(points),
        "distance_km": round(dists[-1] / 1000, 3),
        "sampled_points": len(samples),
        "matched_points": matched,
        "unmatched_points": unmatched,
        "coverage_pct": coverage_pct,
        "segments": surface_segments,
        "bounds": {"sw_lat": south + 0.005, "sw_lng": west + 0.005, "ne_lat": north - 0.005, "ne_lng": east - 0.005},
        "surface_percentages": {k: round(v / total * 100, 1) for k, v in sorted(surface_counts.items(), key=lambda x: -x[1])},
        "dominant_surface": dominated_by,
        "road_type_percentages": {k: round(v / total * 100, 1) for k, v in sorted(highway_counts.items(), key=lambda x: -x[1])} if highway_counts else {},
        "tracktype_percentages": {k.replace("grade", ""): round(v / total * 100, 1) for k, v in sorted(tracktype_counts.items())} if tracktype_counts else {},
        "smoothness_summary": {k: round(v / smoothness_total * 100, 1) for k, v in sorted(smoothness_counts.items(), key=lambda x: -x[1])} if smoothness_counts else {},
        "confidence": "high" if coverage_pct >= 80 else "medium" if coverage_pct >= 50 else "low",
        "warnings": warnings_list if warnings_list else None,
        "cache_hit": False,
    }

    try:
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def save_wellness(
    date: str,
    comments: str = None,
    mood: int = None,
    fatigue: int = None,
    motivation: int = None,
    sleep_quality: int = None,
    sleep_hours: float = None,
    resting_hr: int = None,
    hrv: float = None,
    weight: float = None,
    injury: str = None
) -> str:
    """
    Zapisz dane wellness do Intervals.icu dla podanej daty.
    Skale 1-5: mood (nastrój), fatigue (zmęczenie), motivation, sleep_quality.
    Wyżej = lepiej dla mood/motivation/sleep_quality. Wyżej = gorzej dla fatigue.
    date: YYYY-MM-DD
    """
    body = {}
    if mood:          body["mood"]         = mood
    if fatigue:       body["fatigue"] = fatigue
    if motivation:    body["motivation"]   = motivation
    if sleep_quality: body["sleepQuality"] = sleep_quality
    if sleep_hours:   body["sleepSecs"]    = int(sleep_hours * 3600)
    if resting_hr:    body["restingHR"]    = resting_hr
    if hrv:           body["hrvSDNN"]      = hrv
    if weight:        body["weight"]       = weight
    if injury:        body["injury"]       = injury

    if not body and not comments:
        return json.dumps({"error": "Brak danych do zapisania"})

    async with httpx.AsyncClient(timeout=10) as c:
        # Pobierz istniejące dane — nie nadpisuj tego co już jest
        existing_data = {}
        existing = await c.get(
            f"{BASE}/athlete/{ATHLETE_ID}/wellness/{date}",
            headers=HDR
        )
        if existing.status_code == 200:
            existing_data = existing.json()

        if comments:
            old_comments = existing_data.get("comments", "") or ""
            if old_comments and comments not in old_comments:
                body["comments"] = old_comments + "\n" + comments
            elif not old_comments:
                body["comments"] = comments
            # jeśli comments już jest identyczny — nie zapisuj ponownie

        # Nie nadpisuj pól które już mają wartość
        for field, key in [("mood","mood"),("motivation","motivation"),
                            ("fatigue","fatigue"),("sleepQuality","sleepQuality"),
                            ("restingHR","restingHR"),("hrvSDNN","hrv")]:
            if key in body and existing_data.get(field) is not None:
                pass  # zostaw nową wartość — użytkownik świadomie aktualizuje

        r = await c.put(
            f"{BASE}/athlete/{ATHLETE_ID}/wellness/{date}",
            headers={**HDR, "Content-Type": "application/json"},
            json=body
        )
        r.raise_for_status()
        return json.dumps({"saved": date, "fields": list(body.keys())}, ensure_ascii=False)


@mcp.tool()
async def get_events(oldest: str, newest: str) -> str:
    """
    Pobierz wpisy z kalendarza Intervals.icu (zaplanowane treningi, notatki, eventy).
    oldest/newest: YYYY-MM-DD
    """
    data = await icu(f"/athlete/{ATHLETE_ID}/events",
                     {"oldest": oldest, "newest": newest})
    events = []
    for e in (data if isinstance(data, list) else []):
        events.append({
            "id":          e.get("id"),
            "date":        (e.get("start_date_local") or "")[:10],
            "name":        e.get("name"),
            "category":    e.get("category"),
            "description": (e.get("description") or "")[:200],
        })
    return json.dumps(events, ensure_ascii=False)


@mcp.tool()
async def delete_event(event_id: int) -> str:
    """Usuń wpis z kalendarza Intervals.icu po ID."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.delete(
            f"{BASE}/athlete/{ATHLETE_ID}/events/{event_id}",
            headers=HDR
        )
        r.raise_for_status()
        return json.dumps({"deleted": event_id})


@mcp.tool()
async def create_event(date: str, title: str, description: str = None) -> str:
    """
    Utwórz wpis w kalendarzu Intervals.icu — trening, delegacja, rest day, cokolwiek.
    date: YYYY-MM-DD
    title: tytuł wpisu, np. "Trening Z2 1h", "Delegacja Wrocław", "Rest day"
    """
    body = {
        "start_date_local": f"{date}T09:00:00",
        "name": title,
        "category": "NOTE",
        "description": (description or "") + "\n📧 Q-raport reply",
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{BASE}/athlete/{ATHLETE_ID}/events",
            headers={**HDR, "Content-Type": "application/json"},
            json=body
        )
        r.raise_for_status()
        event = r.json()
        return json.dumps({"created": True, "event_id": event.get("id"),
                           "title": title, "date": date}, ensure_ascii=False)


def _cronometer_client():
    from cronometer_mcp import CronometerClient
    os.environ['CRONOMETER_USERNAME'] = CRONOMETER_EMAIL
    os.environ['CRONOMETER_PASSWORD'] = CRONOMETER_PASSWORD
    c = CronometerClient()
    c.authenticate()
    return c

@mcp.tool()
def get_cronometer_nutrition(date: str = None, days: int = 1) -> str:
    """
    Pobiera dane żywieniowe z Cronometer.
    date: YYYY-MM-DD (domyślnie wczoraj), days: ile dni wstecz (1-30).
    Zwraca kcal, białko, węgle, tłuszcze, błonnik.
    """
    from datetime import date as dt, timedelta
    end   = dt.fromisoformat(date) if date else dt.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    try:
        rows = _cronometer_client().get_daily_summary(start, end)
        clean = [{
            "data":      r.get("Date", ""),
            "kcal":      r.get("Energy (kcal)", ""),
            "bialko_g":  r.get("Protein (g)", ""),
            "wegle_g":   r.get("Carbs (g)", ""),
            "tluszcz_g": r.get("Fat (g)", ""),
            "blonnik_g": r.get("Fiber (g)", ""),
        } for r in rows]
        return json.dumps(clean, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── OPENMAPS ────────────────────────────────────────────────────────────────────


@mcp.tool()
def openmaps_healthcheck() -> str:
    """
    Sprawdź stan integracji z OpenStreetMap/Overpass API.
    Zwraca JSON: ok, status, overpass_endpoint, cache_status, reason.
    """
    endpoint = "https://overpass-api.de/api/interpreter"
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get("https://overpass-api.de/api/status",
                       headers={"User-Agent": "Q-rowerowy-asystent/1.0"})
            if r.status_code == 200:
                return json.dumps({
                    "ok": True,
                    "status": "OK",
                    "overpass_endpoint": endpoint,
                    "cache_status": "OK",
                    "reason": "Overpass API dostępny, status HTTP 200",
                }, ensure_ascii=False)
            return json.dumps({
                "ok": False,
                "status": "DEGRADED",
                "overpass_endpoint": endpoint,
                "cache_status": "OK",
                "reason": f"Overpass API odpowiedział kodem {r.status_code}",
            }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "ok": False,
            "status": "ERROR",
            "overpass_endpoint": endpoint,
            "cache_status": "DISABLED",
            "reason": f"Nie można połączyć się z Overpass API: {exc}",
        }, ensure_ascii=False)


@mcp.tool()
def openmaps_query_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    features: list[str] | None = None,
    timeout_sec: int | None = None,
) -> str:
    """
    Odpytaj Overpass API o elementy OSM w zadanym bounding boxie.

    south/west/north/east: współrzędne geograficzne (stopnie)
    features: lista kategorii — roads, surface, amenities, barriers, access
    timeout_sec: timeout Overpass w sekundach (domyślnie 25)

    Zwraca JSON: ok, status (OK/NO_DATA/ERROR), elements[], source, reason.
    """
    if not (-90 <= south <= 90):
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"south latitude {south} out of range [-90, 90]"},
                          ensure_ascii=False)
    if not (-90 <= north <= 90):
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"north latitude {north} out of range [-90, 90]"},
                          ensure_ascii=False)
    if not (-180 <= west <= 180):
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"west longitude {west} out of range [-180, 180]"},
                          ensure_ascii=False)
    if not (-180 <= east <= 180):
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"east longitude {east} out of range [-180, 180]"},
                          ensure_ascii=False)
    if south >= north:
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"south ({south}) must be less than north ({north})"},
                          ensure_ascii=False)
    if west >= east:
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"west ({west}) must be less than east ({east})"},
                          ensure_ascii=False)

    lat_span = north - south
    lon_span = east - west
    if lat_span > 1.0 or lon_span > 1.0:
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"bbox too large: {lat_span:.3f}° lat × {lon_span:.3f}° lon exceeds 1.0° limit"},
                          ensure_ascii=False)

    timeout_val = timeout_sec if timeout_sec and timeout_sec > 0 else 25

    valid_features = {"roads", "surface", "amenities", "barriers", "access"}
    if not features:
        selected = sorted(valid_features)
    else:
        selected = sorted(set(f.lower() for f in features if isinstance(f, str) and f.lower() in valid_features))
    if not selected:
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": "no valid features selected"},
                          ensure_ascii=False)

    bbox_str = f"({south},{west},{north},{east})"
    feature_queries = {
        "access": f"way[highway][access]{bbox_str};",
        "amenities": f"node[amenity]{bbox_str};way[amenity]{bbox_str};",
        "barriers": f"node[barrier]{bbox_str};way[barrier]{bbox_str};",
        "roads": f"way[highway]{bbox_str};",
        "surface": f"way[highway][surface]{bbox_str};",
    }
    query_parts = [feature_queries[f] for f in selected]
    query = f"[out:json][timeout:{timeout_val}];({' '.join(query_parts)});out tags geom;"

    try:
        elements = _overpass_post(query, timeout=timeout_val + 5)
    except Exception as exc:
        return json.dumps({"ok": False, "status": "ERROR", "elements": [], "source": "overpass",
                           "reason": f"Overpass API error: {exc}"},
                          ensure_ascii=False)

    if not elements:
        return json.dumps({"ok": True, "status": "NO_DATA", "elements": [], "source": "overpass",
                           "reason": f"no OSM elements in bbox ({south},{west},{north},{east}) for: {', '.join(selected)}"},
                          ensure_ascii=False)

    return json.dumps({"ok": True, "status": "OK", "elements": elements, "source": "overpass",
                       "reason": f"{len(elements)} elements found for: {', '.join(selected)}"},
                      ensure_ascii=False)


@mcp.tool()
def openmaps_enrich_rwgps_track(
    points_json: str,
    track_id: str | None = None,
    buffer_m: int = 60,
    sample_step_m: int = 100,
) -> str:
    """
    Wzbogać track RWGPS/GPX o segmenty nawierzchni z OpenStreetMap.

    points_json: JSON array of {lat, lon, ele?, distance_m?, timestamp?}
    track_id: opcjonalny identyfikator trasy
    buffer_m: promień bufora OSM wokół każdego punktu (30–200 m)
    sample_step_m: krok próbkowania punktów (50–500 m)

    Zwraca JSON: ok, status, track_id, segments[], summary{}, source, reason.
    """
    import math
    from urllib.parse import urlencode

    try:
        points = json.loads(points_json)
    except Exception:
        return json.dumps({"ok": False, "status": "ERROR", "track_id": track_id, "segments": [],
                           "summary": {}, "source": "osm_overpass",
                           "reason": "invalid points_json: not valid JSON"},
                          ensure_ascii=False)

    if not isinstance(points, list) or len(points) < 2:
        return json.dumps({"ok": False, "status": "ERROR", "track_id": track_id, "segments": [],
                           "summary": {}, "source": "osm_overpass",
                           "reason": f"need at least 2 points, got {len(points) if isinstance(points, list) else 'non-list'}"},
                          ensure_ascii=False)

    for i, p in enumerate(points):
        if not isinstance(p, dict):
            return json.dumps({"ok": False, "status": "ERROR", "track_id": track_id, "segments": [],
                               "summary": {}, "source": "osm_overpass",
                               "reason": f"point[{i}] is not a dict"},
                              ensure_ascii=False)
        lat = p.get("lat")
        lon = p.get("lon")
        if lat is None or lon is None:
            return json.dumps({"ok": False, "status": "ERROR", "track_id": track_id, "segments": [],
                               "summary": {}, "source": "osm_overpass",
                               "reason": f"point[{i}] missing lat or lon"},
                              ensure_ascii=False)
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return json.dumps({"ok": False, "status": "ERROR", "track_id": track_id, "segments": [],
                               "summary": {}, "source": "osm_overpass",
                               "reason": f"point[{i}] lat/lon must be numbers"},
                              ensure_ascii=False)
        if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
            return json.dumps({"ok": False, "status": "ERROR", "track_id": track_id, "segments": [],
                               "summary": {}, "source": "osm_overpass",
                               "reason": f"point[{i}] lat/lon has NaN or Infinity"},
                              ensure_ascii=False)

    buffer_m = max(30, min(buffer_m, 200))
    sample_step_m = max(50, min(sample_step_m, 500))

    def _dist_m(lat1, lon1, lat2, lon2):
        dlat = (lat2 - lat1) * 111320.0
        dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
        return math.sqrt(dlat * dlat + dlon * dlon)

    dists = [0.0]
    for i in range(1, len(points)):
        d_val = points[i].get("distance_m")
        if isinstance(d_val, (int, float)) and d_val is not None and not math.isnan(d_val) and not math.isinf(d_val) and d_val >= 0:
            dists.append(float(d_val))
        else:
            prev = dists[-1]
            step = _dist_m(points[i - 1]["lat"], points[i - 1]["lon"], points[i]["lat"], points[i]["lon"])
            dists.append(prev + step)

    total_dist = dists[-1]

    samples = []
    next_target = sample_step_m
    for i in range(len(points)):
        if dists[i] >= next_target or i == len(points) - 1:
            samples.append((i, float(points[i]["lat"]), float(points[i]["lon"]), dists[i]))
            next_target += sample_step_m
    if len(samples) < 2:
        samples = [(0, float(points[0]["lat"]), float(points[0]["lon"]), 0.0),
                   (len(points) - 1, float(points[-1]["lat"]), float(points[-1]["lon"]), total_dist)]
    if len(samples) > 80:
        step = len(samples) / 80
        samples = [samples[int(i * step)] for i in range(80)]

    BATCH_SIZE = 8
    batches = [samples[i:i + BATCH_SIZE] for i in range(0, len(samples), BATCH_SIZE)]

    _PAVED = {"asphalt", "paved", "concrete", "paving_stones"}
    _FAST_SURF = {"compacted", "fine_gravel"}
    _DIRT_SURF = {"earth", "mud", "sand", "grass"}
    _GRAVEL_SURF = {"gravel", "ground", "dirt", "unpaved"}

    def _surface_class_and_confidence(tags):
        surf = (tags.get("surface") or "").lower()
        tt = (tags.get("tracktype") or "").lower()
        sm = (tags.get("smoothness") or "").lower()
        bad_cond = tt in ("grade3", "grade4", "grade5") or sm in ("bad", "very_bad", "horrible", "very_horrible", "impassable")
        if surf in _PAVED:
            return "paved", 0.9
        if surf in _FAST_SURF:
            return "fast_gravel", 0.85
        if surf == "gravel":
            if bad_cond:
                return "rough_gravel", 0.6
            return "fast_gravel", 0.75
        if surf in _GRAVEL_SURF:
            if bad_cond:
                return "rough_gravel", 0.55
            if tt in ("grade1", "grade2") or sm in ("excellent", "good", "intermediate"):
                return "fast_gravel", 0.6
            return "rough_gravel", 0.55
        if surf in _DIRT_SURF:
            return "dirt", 0.65
        if tags.get("highway"):
            return "unknown", 0.3
        return "unknown", 0.2

    lat_per_m = 1.0 / 111320.0
    buffer_deg = buffer_m * lat_per_m

    sample_tags = []
    osm_errors = 0

    for batch in batches:
        b_lats = [s[1] for s in batch]
        b_lons = [s[2] for s in batch]
        b_south = min(b_lats) - buffer_deg
        b_north = max(b_lats) + buffer_deg
        mid_lat = sum(b_lats) / len(b_lats)
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(mid_lat)))
        b_west = min(b_lons) - buffer_m * lon_per_m
        b_east = max(b_lons) + buffer_m * lon_per_m

        query = f"[out:json][timeout:25];way[highway]({b_south},{b_west},{b_north},{b_east});out tags geom;"
        ways = []
        try:
            ways = _overpass_post(query, timeout=30)
        except Exception:
            osm_errors += len(batch)
            for s in batch:
                sample_tags.append((s[3], None, "unknown", 0.2,
                                   "Overpass API unavailable"))
            continue

        if not ways:
            for s in batch:
                sample_tags.append((s[3], None, "unknown", 0.2,
                                   "no OSM data in buffer"))
            continue

        for s in batch:
            s_lat, s_lon, s_dist = s[1], s[2], s[3]
            best_dist = float("inf")
            best_tags = {}
            for way in ways:
                for node in way.get("geometry", []):
                    d = _dist_m(s_lat, s_lon, node["lat"], node["lon"])
                    if d < best_dist:
                        best_dist = d
                        best_tags = way.get("tags", {})
            max_match = buffer_m * 1.5
            if best_dist > max_match or not best_tags.get("highway"):
                sc, cf = "unknown", 0.2
                reason = f"nearest OSM way {best_dist:.0f}m away exceeds buffer {max_match:.0f}m" if best_dist > max_match else "no highway tag on nearest way"
            else:
                sc, cf = _surface_class_and_confidence(best_tags)
                reason = f"matched OSM way at {best_dist:.0f}m"
            sample_tags.append((s_dist, best_tags if best_tags.get("highway") else None, sc, cf, reason))

    segments = []
    seg_start = None
    seg_tags = None
    seg_class = None
    seg_conf = None

    for i, (st_dist, tags, sc, cf, reason) in enumerate(sample_tags):
        if seg_start is None:
            seg_start = st_dist
            seg_tags = tags
            seg_class = sc
            seg_conf = cf
            seg_reason = reason
        elif sc != seg_class:
            seg_end = st_dist
            if seg_end - seg_start > 1.0:
                segments.append(_build_segment(seg_start, seg_end, seg_tags, seg_class, seg_conf, seg_reason))
            seg_start = st_dist
            seg_tags = tags
            seg_class = sc
            seg_conf = cf
            seg_reason = reason
        else:
            if tags and not seg_tags:
                seg_tags = tags
                seg_reason = reason
            seg_end = st_dist

    if seg_start is not None:
        seg_end = sample_tags[-1][0] if sample_tags else total_dist
        if seg_end - seg_start > 1.0:
            segments.append(_build_segment(seg_start, seg_end, seg_tags, seg_class, seg_conf, seg_reason))

    # Summary
    paved_m = sum(s["distance_m"] for s in segments if s["surface_class"] == "paved")
    gravel_m = sum(s["distance_m"] for s in segments if s["surface_class"] == "fast_gravel")
    rough_m = sum(s["distance_m"] for s in segments if s["surface_class"] == "rough_gravel")
    dirt_m = sum(s["distance_m"] for s in segments if s["surface_class"] == "dirt")
    unknown_m = sum(s["distance_m"] for s in segments if s["surface_class"] == "unknown")

    status = "OK"
    reason_text = f"{len(segments)} segments from {len(samples)} samples"
    if not segments:
        status = "NO_DATA"
        reason_text = "no OSM data found for any sample"
    elif osm_errors > 0:
        status = "PARTIAL"
        reason_text = f"{len(segments)} segments ({osm_errors} OSM errors)"

    return json.dumps({
        "ok": True,
        "status": status,
        "track_id": track_id,
        "segments": segments,
        "summary": {
            "distance_m": round(total_dist, 1),
            "paved_m": round(paved_m, 1),
            "gravel_m": round(gravel_m, 1),
            "rough_m": round(rough_m, 1),
            "dirt_m": round(dirt_m, 1),
            "unknown_m": round(unknown_m, 1),
        },
        "source": "osm_overpass",
        "reason": reason_text,
    }, ensure_ascii=False)


def _build_segment(from_m, to_m, tags, surface_class, confidence, reason):
    return {
        "from_m": round(from_m, 1),
        "to_m": round(to_m, 1),
        "distance_m": round(to_m - from_m, 1),
        "road_type": tags.get("highway") if tags else None,
        "surface": tags.get("surface") if tags else None,
        "surface_class": surface_class,
        "tracktype": tags.get("tracktype") if tags else None,
        "smoothness": tags.get("smoothness") if tags else None,
        "access": tags.get("access") if tags else None,
        "bicycle": tags.get("bicycle") if tags else None,
        "confidence": confidence,
        "source": "osm_overpass",
        "reason": reason,
    }


@mcp.tool()
def openmaps_find_pois_near_track(
    points_json: str,
    radius_m: int = 500,
    poi_types_json: str | None = None,
) -> str:
    """
    Znajdź POI (punkty użyteczności) w pobliżu trasy przez Overpass API.

    points_json: JSON array of {lat, lon, distance_m?}
    radius_m: promień od trasy w metrach (50–3000)
    poi_types_json: opcjonalnie JSON array typów POI:
      drinking_water, cafe, shelter, shop, bicycle_service

    Zwraca JSON: ok, status (OK/NO_DATA/ERROR), pois[], source, reason.
    """
    import math
    from urllib.parse import urlencode

    try:
        points = json.loads(points_json)
    except Exception:
        return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                           "reason": "invalid points_json: not valid JSON"}, ensure_ascii=False)

    if not isinstance(points, list) or len(points) < 2:
        return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                           "reason": f"need at least 2 points, got {len(points) if isinstance(points, list) else 'non-list'}"},
                          ensure_ascii=False)

    radius_m = max(50, min(radius_m, 3000))

    _POI_QUERY = {
        "drinking_water": "node[amenity=drinking_water]",
        "cafe": "node[amenity=cafe]",
        "shelter": "node[amenity=shelter];node[tourism=alpine_hut]",
        "shop": "node[shop=convenience];node[shop=supermarket]",
        "bicycle_service": "node[shop=bicycle]",
    }

    if poi_types_json:
        try:
            requested = json.loads(poi_types_json)
            if not isinstance(requested, list):
                requested = []
        except Exception:
            return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                               "reason": "invalid poi_types_json: not valid JSON array"}, ensure_ascii=False)
        poi_types = [t.lower() for t in requested if isinstance(t, str) and t.lower() in _POI_QUERY]
    else:
        poi_types = list(_POI_QUERY.keys())

    if not poi_types:
        return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                           "reason": "no valid POI types selected"}, ensure_ascii=False)

    query_parts = [_POI_QUERY[t] for t in poi_types]

    for i, p in enumerate(points):
        if not isinstance(p, dict):
            return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                               "reason": f"point[{i}] is not a dict"}, ensure_ascii=False)
        lat = p.get("lat")
        lon = p.get("lon")
        if lat is None or lon is None:
            return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                               "reason": f"point[{i}] missing lat or lon"}, ensure_ascii=False)
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                               "reason": f"point[{i}] lat/lon must be numbers"}, ensure_ascii=False)
        if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
            return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                               "reason": f"point[{i}] lat/lon has NaN or Infinity"}, ensure_ascii=False)

    def _dist_m(lat1, lon1, lat2, lon2):
        dlat = (lat2 - lat1) * 111320.0
        dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
        return math.sqrt(dlat * dlat + dlon * dlon)

    lats_all = [p["lat"] for p in points]
    lons_all = [p["lon"] for p in points]
    lat_per_m = 1.0 / 111320.0
    mid_lat = sum(lats_all) / len(lats_all)
    lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(mid_lat)))
    buffer_lat = radius_m * lat_per_m
    buffer_lon = radius_m * lon_per_m

    south = min(lats_all) - buffer_lat
    north = max(lats_all) + buffer_lat
    west = min(lons_all) - buffer_lon
    east = max(lons_all) + buffer_lon

    if (north - south) > 2.0 or (east - west) > 2.0:
        return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                           "reason": f"track bbox too large: {north - south:.2f}° × {east - west:.2f}° exceeds 2.0° limit"},
                          ensure_ascii=False)

    bbox_str = f"({south},{west},{north},{east})"
    query = f"[out:json][timeout:25];({' '.join(f'{qp}{bbox_str};' for qp in query_parts)});out tags center;"

    elements = []
    try:
        elements = _overpass_post(query, timeout=30)
    except Exception as exc:
        return json.dumps({"ok": False, "status": "ERROR", "pois": [], "source": "osm_overpass",
                           "reason": f"Overpass API error: {exc}"}, ensure_ascii=False)

    if not elements:
        return json.dumps({"ok": True, "status": "NO_DATA", "pois": [], "source": "osm_overpass",
                           "reason": f"no POIs found in {radius_m}m around track for: {', '.join(poi_types)}"},
                          ensure_ascii=False)

    def _poi_type_from_tags(tags):
        amenity = (tags.get("amenity") or "").lower()
        shop = (tags.get("shop") or "").lower()
        tourism = (tags.get("tourism") or "").lower()
        if amenity == "drinking_water": return "drinking_water"
        if amenity == "cafe": return "cafe"
        if amenity == "shelter" or tourism == "alpine_hut": return "shelter"
        if shop in ("convenience", "supermarket"): return "shop"
        if shop == "bicycle": return "bicycle_service"
        return None

    pois = []
    for el in elements:
        tags = el.get("tags") or {}
        poi_type = _poi_type_from_tags(tags)
        if poi_type is None:
            continue
        name = tags.get("name") or None
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            continue

        min_dist = float("inf")
        nearest_on_route = 0.0
        for pi, p in enumerate(points):
            d = _dist_m(lat, lon, p["lat"], p["lon"])
            if d < min_dist:
                min_dist = d
                dm = p.get("distance_m")
                if isinstance(dm, (int, float)):
                    nearest_on_route = float(dm)
                else:
                    nearest_on_route = 0.0

        if min_dist > radius_m:
            continue

        if name:
            confidence_val = 0.9
            reason_text = f"{poi_type}: {name}, {min_dist:.0f}m from track"
        else:
            confidence_val = 0.75
            reason_text = f"{poi_type}: unnamed, {min_dist:.0f}m from track"

        pois.append({
            "type": poi_type,
            "name": name,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "distance_from_track_m": round(min_dist, 1),
            "nearest_track_distance_m": round(min_dist, 1),
            "nearest_track_distance_m_on_route": round(nearest_on_route, 1) if nearest_on_route else None,
            "tags": tags,
            "source": "osm_overpass",
            "confidence": confidence_val,
            "reason": reason_text,
        })

    if not pois:
        return json.dumps({"ok": True, "status": "NO_DATA", "pois": [], "source": "osm_overpass",
                           "reason": f"no matching POI types found in {radius_m}m (got {len(elements)} raw elements)"},
                          ensure_ascii=False)

    pois.sort(key=lambda x: x["distance_from_track_m"])

    return json.dumps({"ok": True, "status": "OK", "pois": pois, "source": "osm_overpass",
                       "reason": f"{len(pois)} POIs found within {radius_m}m"},
                      ensure_ascii=False)


@mcp.tool()
def openmaps_detect_route_risks(
    points_json: str,
    enriched_segments_json: str | None = None,
    pois_json: str | None = None,
) -> str:
    """
    Wykryj ryzyka gravelowe i logistyczne na podstawie tracka i danych OSM.

    points_json: JSON array of {lat, lon, ele?, distance_m?}
    enriched_segments_json: opcjonalnie wynik openmaps_enrich_rwgps_track.segments
    pois_json: opcjonalnie wynik openmaps_find_pois_near_track.pois

    Zwraca JSON: ok, status, risks[], source, reason.
    Nie wykonuje zapytań HTTP/Overpass — działa tylko na danych wejściowych.
    """
    import math

    try:
        points = json.loads(points_json)
    except Exception:
        return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                           "reason": "invalid points_json: not valid JSON"}, ensure_ascii=False)

    if not isinstance(points, list) or len(points) < 2:
        return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                           "reason": f"need at least 2 points, got {len(points) if isinstance(points, list) else 'non-list'}"},
                          ensure_ascii=False)

    for i, p in enumerate(points):
        if not isinstance(p, dict):
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": f"point[{i}] is not a dict"}, ensure_ascii=False)
        lat = p.get("lat")
        lon = p.get("lon")
        if lat is None or lon is None:
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": f"point[{i}] missing lat or lon"}, ensure_ascii=False)
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": f"point[{i}] lat/lon must be numbers"}, ensure_ascii=False)
        if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": f"point[{i}] lat/lon has NaN or Infinity"}, ensure_ascii=False)

    segments = []
    if enriched_segments_json:
        try:
            segments = json.loads(enriched_segments_json)
        except Exception:
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": "invalid enriched_segments_json: not valid JSON"}, ensure_ascii=False)
        if not isinstance(segments, list):
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": "enriched_segments_json must be a list"}, ensure_ascii=False)

    pois = []
    if pois_json:
        try:
            pois = json.loads(pois_json)
        except Exception:
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": "invalid pois_json: not valid JSON"}, ensure_ascii=False)
        if not isinstance(pois, list):
            return json.dumps({"ok": False, "status": "ERROR", "risks": [], "source": "route_analysis",
                               "reason": "pois_json must be a list"}, ensure_ascii=False)

    def _dist_m(lat1, lon1, lat2, lon2):
        dlat = (lat2 - lat1) * 111320.0
        dlon = (lon2 - lon1) * 111320.0 * math.cos(math.radians((lat1 + lat2) / 2.0))
        return math.sqrt(dlat * dlat + dlon * dlon)

    dists = [0.0]
    for i in range(1, len(points)):
        d_val = points[i].get("distance_m")
        if isinstance(d_val, (int, float)) and d_val is not None and not math.isnan(d_val) and not math.isinf(d_val) and d_val >= 0:
            dists.append(float(d_val))
        else:
            prev = dists[-1]
            step = _dist_m(points[i - 1]["lat"], points[i - 1]["lon"], points[i]["lat"], points[i]["lon"])
            dists.append(prev + step)

    total_dist = dists[-1]
    has_elevation = all(isinstance(p.get("ele"), (int, float)) and not math.isnan(p.get("ele")) and not math.isinf(p.get("ele")) for p in points)

    risks = []

    for seg in segments:
        if not isinstance(seg, dict):
            continue
        sc = seg.get("surface_class", "")
        conf = seg.get("confidence", 0)
        if not isinstance(conf, (int, float)):
            conf = 0
        from_m = seg.get("from_m", 0)
        to_m = seg.get("to_m", 0)
        tags = seg.get("tags") if isinstance(seg.get("tags"), dict) else {}
        access = (tags.get("access") or seg.get("access") or "").lower()
        bicycle = (tags.get("bicycle") or seg.get("bicycle") or "").lower()
        barrier = (tags.get("barrier") or "").lower()
        ford = (tags.get("ford") or "").lower()

        seg_lat = None
        seg_lon = None
        for pi, p in enumerate(points):
            if dists[pi] >= from_m and dists[pi] <= to_m:
                seg_lat = p["lat"]
                seg_lon = p["lon"]
                break

        # unknown_surface
        if sc == "unknown" or conf <= 0.3:
            risks.append({
                "type": "unknown_surface",
                "from_m": round(from_m, 1) if isinstance(from_m, (int, float)) else None,
                "to_m": round(to_m, 1) if isinstance(to_m, (int, float)) else None,
                "lat": round(seg_lat, 6) if seg_lat is not None else None,
                "lon": round(seg_lon, 6) if seg_lon is not None else None,
                "severity": "MEDIUM" if conf <= 0.3 else "LOW",
                "confidence": round(1.0 - max(conf, 0.2), 2),
                "source": "osm_overpass",
                "reason": "segment surface unknown" if sc == "unknown" else f"low OSM confidence ({conf})",
            })

        # private_access
        if access in ("private", "no") or bicycle == "no":
            risks.append({
                "type": "private_access",
                "from_m": round(from_m, 1) if isinstance(from_m, (int, float)) else None,
                "to_m": round(to_m, 1) if isinstance(to_m, (int, float)) else None,
                "lat": round(seg_lat, 6) if seg_lat is not None else None,
                "lon": round(seg_lon, 6) if seg_lon is not None else None,
                "severity": "HIGH",
                "confidence": 0.85,
                "source": "osm_overpass",
                "reason": f"access={access}" if access else f"bicycle={bicycle}",
            })

        # gate
        if barrier in ("gate", "lift_gate", "swing_gate", "bollard"):
            risks.append({
                "type": "gate",
                "from_m": round(from_m, 1) if isinstance(from_m, (int, float)) else None,
                "to_m": round(to_m, 1) if isinstance(to_m, (int, float)) else None,
                "lat": round(seg_lat, 6) if seg_lat is not None else None,
                "lon": round(seg_lon, 6) if seg_lon is not None else None,
                "severity": "MEDIUM",
                "confidence": 0.75,
                "source": "osm_overpass",
                "reason": f"barrier={barrier} on segment",
            })

        # ford
        if ford == "yes":
            risks.append({
                "type": "ford",
                "from_m": round(from_m, 1) if isinstance(from_m, (int, float)) else None,
                "to_m": round(to_m, 1) if isinstance(to_m, (int, float)) else None,
                "lat": round(seg_lat, 6) if seg_lat is not None else None,
                "lon": round(seg_lon, 6) if seg_lon is not None else None,
                "severity": "HIGH",
                "confidence": 0.85,
                "source": "osm_overpass",
                "reason": "ford=yes on segment",
            })

        # steep_unpaved_climb / rough_descent — need elevation data
        if has_elevation and sc in ("rough_gravel", "dirt", "fast_gravel"):
            seg_points = [p for i, p in enumerate(points) if from_m <= dists[i] <= to_m]
            if len(seg_points) >= 2:
                elev_start = seg_points[0].get("ele")
                elev_end = seg_points[-1].get("ele")
                seg_dist = to_m - from_m
                if isinstance(elev_start, (int, float)) and isinstance(elev_end, (int, float)) and seg_dist > 0:
                    grade_pct = round((elev_end - elev_start) / seg_dist * 100, 1)
                    if grade_pct > 5:
                        risks.append({
                            "type": "steep_unpaved_climb",
                            "from_m": round(from_m, 1),
                            "to_m": round(to_m, 1),
                            "lat": round(seg_lat, 6) if seg_lat is not None else None,
                            "lon": round(seg_lon, 6) if seg_lon is not None else None,
                            "severity": "HIGH",
                            "confidence": 0.8,
                            "source": "track_elevation",
                            "reason": f"{sc} surface with {grade_pct}% grade climb",
                        })
                    elif grade_pct < -5:
                        risks.append({
                            "type": "rough_descent",
                            "from_m": round(from_m, 1),
                            "to_m": round(to_m, 1),
                            "lat": round(seg_lat, 6) if seg_lat is not None else None,
                            "lon": round(seg_lon, 6) if seg_lon is not None else None,
                            "severity": "MEDIUM",
                            "confidence": 0.7,
                            "source": "track_elevation",
                            "reason": f"{sc} surface with {grade_pct}% grade descent",
                        })

    # long_no_resupply from POIs
    if pois:
        resupply_types = {"drinking_water", "cafe", "shop"}
        resupply = sorted(
            [p for p in pois if isinstance(p, dict) and p.get("type") in resupply_types],
            key=lambda x: x.get("nearest_track_distance_m_on_route") or 0,
        )
        prev_positions = [0.0]
        for rp in resupply:
            pos = rp.get("nearest_track_distance_m_on_route") if isinstance(rp.get("nearest_track_distance_m_on_route"), (int, float)) else None
            if pos is not None:
                prev_positions.append(pos)
        prev_positions.append(total_dist)

        for j in range(1, len(prev_positions)):
            gap = prev_positions[j] - prev_positions[j - 1]
            if gap > 30000:
                gap_from = prev_positions[j - 1]
                gap_to = prev_positions[j]
                gap_lat = None
                gap_lon = None
                for pi, p in enumerate(points):
                    if dists[pi] >= gap_from and dists[pi] <= gap_to:
                        gap_lat = p["lat"]
                        gap_lon = p["lon"]
                        break
                risks.append({
                    "type": "long_no_resupply",
                    "from_m": round(gap_from, 1),
                    "to_m": round(gap_to, 1),
                    "lat": round(gap_lat, 6) if gap_lat is not None else None,
                    "lon": round(gap_lon, 6) if gap_lon is not None else None,
                    "severity": "MEDIUM" if gap > 50000 else "LOW",
                    "confidence": 0.7,
                    "source": "route_analysis",
                    "reason": f"{gap / 1000:.1f} km without resupply (water/cafe/shop)",
                })

    if not risks:
        return json.dumps({"ok": True, "status": "NO_DATA", "risks": [], "source": "route_analysis",
                           "reason": "no route risks detected from provided data"}, ensure_ascii=False)

    only_segment_based = all(r["source"] == "osm_overpass" for r in risks) and segments
    risks.sort(key=lambda r: (0 if r["severity"] == "HIGH" else 1 if r["severity"] == "MEDIUM" else 2, r.get("from_m") or 0))

    return json.dumps({"ok": True, "status": "OK", "risks": risks, "source": "route_analysis",
                       "reason": f"{len(risks)} risks detected"},
                      ensure_ascii=False)


@mcp.tool()
def openmaps_build_route_snapshot(
    points_json: str,
    track_id: str | None = None,
    route_id: str | None = None,
    buffer_m: int = 60,
    sample_step_m: int = 100,
    poi_radius_m: int = 500,
    poi_types_json: str | None = None,
) -> str:
    """
    Zbuduj pełny snapshot trasy: nawierzchnia + POI + ryzyka + podsumowanie.

    Uruchamia pipeline openmaps_enrich_rwgps_track →
    openmaps_find_pois_near_track → openmaps_detect_route_risks
    i zwraca zagregowany wynik jako JSON.

    points_json: JSON array of {lat, lon, ele?, distance_m?, timestamp?}
    track_id, route_id: opcjonalne identyfikatory
    buffer_m: bufor OSM dla enrich (30–200)
    sample_step_m: krok próbkowania dla enrich (50–500)
    poi_radius_m: promień POI (50–3000)
    poi_types_json: opcjonalny filtr typów POI

    Zwraca JSON: ok, status, route_id, track_id, generated_at, input_track_hash,
    osm_query_version, summary, segments[], pois[], risks[], warnings[], source, reason.
    """
    import hashlib
    import math
    from datetime import datetime, timezone

    try:
        points = json.loads(points_json)
    except Exception:
        return json.dumps({"ok": False, "status": "ERROR", "route_id": route_id, "track_id": track_id,
                           "generated_at": None, "input_track_hash": None, "osm_query_version": "openmaps_v1",
                           "summary": {}, "segments": [], "pois": [], "risks": [], "warnings": [],
                           "source": "openmaps_pipeline",
                           "reason": "invalid points_json: not valid JSON"}, ensure_ascii=False)

    if not isinstance(points, list) or len(points) < 2:
        return json.dumps({"ok": False, "status": "ERROR", "route_id": route_id, "track_id": track_id,
                           "generated_at": None, "input_track_hash": None, "osm_query_version": "openmaps_v1",
                           "summary": {}, "segments": [], "pois": [], "risks": [], "warnings": [],
                           "source": "openmaps_pipeline",
                           "reason": f"need at least 2 points, got {len(points) if isinstance(points, list) else 'non-list'}"},
                          ensure_ascii=False)

    for i, p in enumerate(points):
        if not isinstance(p, dict):
            return json.dumps({"ok": False, "status": "ERROR", "route_id": route_id, "track_id": track_id,
                               "generated_at": None, "input_track_hash": None, "osm_query_version": "openmaps_v1",
                               "summary": {}, "segments": [], "pois": [], "risks": [], "warnings": [],
                               "source": "openmaps_pipeline",
                               "reason": f"point[{i}] is not a dict"}, ensure_ascii=False)
        lat = p.get("lat")
        lon = p.get("lon")
        if lat is None or lon is None:
            return json.dumps({"ok": False, "status": "ERROR", "route_id": route_id, "track_id": track_id,
                               "generated_at": None, "input_track_hash": None, "osm_query_version": "openmaps_v1",
                               "summary": {}, "segments": [], "pois": [], "risks": [], "warnings": [],
                               "source": "openmaps_pipeline",
                               "reason": f"point[{i}] missing lat or lon"}, ensure_ascii=False)
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return json.dumps({"ok": False, "status": "ERROR", "route_id": route_id, "track_id": track_id,
                               "generated_at": None, "input_track_hash": None, "osm_query_version": "openmaps_v1",
                               "summary": {}, "segments": [], "pois": [], "risks": [], "warnings": [],
                               "source": "openmaps_pipeline",
                               "reason": f"point[{i}] lat/lon must be numbers"}, ensure_ascii=False)
        if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
            return json.dumps({"ok": False, "status": "ERROR", "route_id": route_id, "track_id": track_id,
                               "generated_at": None, "input_track_hash": None, "osm_query_version": "openmaps_v1",
                               "summary": {}, "segments": [], "pois": [], "risks": [], "warnings": [],
                               "source": "openmaps_pipeline",
                               "reason": f"point[{i}] lat/lon has NaN or Infinity"}, ensure_ascii=False)

    generated_at = datetime.now(timezone.utc).isoformat()
    track_hash = hashlib.sha256(points_json.encode("utf-8")).hexdigest()[:16]

    warnings = []
    segments = []
    pois = []
    risks = []
    status = "OK"
    reason_parts = []

    # Stage 1: enrich
    enrich_raw = openmaps_enrich_rwgps_track(
        points_json=points_json, track_id=track_id,
        buffer_m=buffer_m, sample_step_m=sample_step_m,
    )
    try:
        enrich_result = json.loads(enrich_raw)
    except Exception:
        enrich_result = {}
    enrich_ok = enrich_result.get("ok", False)
    enrich_status = enrich_result.get("status", "ERROR")
    segments = enrich_result.get("segments", []) if isinstance(enrich_result.get("segments"), list) else []

    if not enrich_ok:
        warnings.append({"stage": "enrich", "status": enrich_status, "reason": enrich_result.get("reason", "enrich failed")})
        if enrich_status == "ERROR":
            status = "ERROR"
            reason_parts.append("enrich failed")
    elif enrich_status in ("NO_DATA", "PARTIAL"):
        warnings.append({"stage": "enrich", "status": enrich_status, "reason": enrich_result.get("reason", "")})
        if status == "OK":
            status = "PARTIAL"
    else:
        reason_parts.append(f"{len(segments)} surface segments")

    # Stage 2: pois
    pois_raw = openmaps_find_pois_near_track(
        points_json=points_json, radius_m=poi_radius_m,
        poi_types_json=poi_types_json,
    )
    try:
        pois_result = json.loads(pois_raw)
    except Exception:
        pois_result = {}
    pois_ok = pois_result.get("ok", False)
    pois_status = pois_result.get("status", "ERROR")
    pois = pois_result.get("pois", []) if isinstance(pois_result.get("pois"), list) else []

    if not pois_ok:
        warnings.append({"stage": "pois", "status": pois_status, "reason": pois_result.get("reason", "pois failed")})
        if pois_status == "ERROR":
            status = "PARTIAL" if status == "OK" else status
    elif pois_status == "NO_DATA":
        warnings.append({"stage": "pois", "status": "NO_DATA", "reason": pois_result.get("reason", "")})
    else:
        reason_parts.append(f"{len(pois)} POIs")

    # Stage 3: risks
    enrich_segs_json = json.dumps(segments) if segments else None
    pois_for_risks = json.dumps(pois) if pois else None
    risks_raw = openmaps_detect_route_risks(
        points_json=points_json,
        enriched_segments_json=enrich_segs_json,
        pois_json=pois_for_risks,
    )
    try:
        risks_result = json.loads(risks_raw)
    except Exception:
        risks_result = {}
    risks_ok = risks_result.get("ok", False)
    risks_status = risks_result.get("status", "ERROR")
    risks = risks_result.get("risks", []) if isinstance(risks_result.get("risks"), list) else []

    if not risks_ok:
        warnings.append({"stage": "risks", "status": risks_status, "reason": risks_result.get("reason", "risks failed")})
    elif risks_status == "NO_DATA":
        pass
    else:
        reason_parts.append(f"{len(risks)} risks")

    # Summary from enrich summary
    enrich_summary = enrich_result.get("summary", {}) if isinstance(enrich_result.get("summary"), dict) else {}
    total_dist = enrich_summary.get("distance_m", 0) if isinstance(enrich_summary.get("distance_m"), (int, float)) else 0

    summary = {
        "distance_m": round(total_dist, 1),
        "paved_m": round(enrich_summary.get("paved_m", 0)) if isinstance(enrich_summary.get("paved_m"), (int, float)) else 0,
        "gravel_m": round(enrich_summary.get("gravel_m", 0)) if isinstance(enrich_summary.get("gravel_m"), (int, float)) else 0,
        "rough_m": round(enrich_summary.get("rough_m", 0)) if isinstance(enrich_summary.get("rough_m"), (int, float)) else 0,
        "dirt_m": round(enrich_summary.get("dirt_m", 0)) if isinstance(enrich_summary.get("dirt_m"), (int, float)) else 0,
        "unknown_m": round(enrich_summary.get("unknown_m", 0)) if isinstance(enrich_summary.get("unknown_m"), (int, float)) else 0,
        "poi_count": len(pois) if isinstance(pois, list) else 0,
        "risk_count": len(risks) if isinstance(risks, list) else 0,
    }

    if not reason_parts:
        reason_parts.append("snapshot assembled")
    reason_text = "; ".join(reason_parts)

    if status == "ERROR":
        ok = False
    else:
        ok = True

    return json.dumps({
        "ok": ok,
        "status": status,
        "route_id": route_id,
        "track_id": track_id,
        "generated_at": generated_at,
        "input_track_hash": track_hash,
        "osm_query_version": "openmaps_v1",
        "summary": summary,
        "segments": segments,
        "pois": pois,
        "risks": risks,
        "warnings": warnings,
        "source": "openmaps_pipeline",
        "reason": reason_text,
    }, ensure_ascii=False)


# ── START ─────────────────────────────────────────────────────────────────────


def _garmin_client():
    import json as _j
    from garminconnect import Garmin as _G
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise RuntimeError("Brak GARMIN_EMAIL / GARMIN_PASSWORD w .env")
    with open('/opt/qbot/app/.garmin_profile.json') as f:
        profile = _j.load(f)
    g = _G(GARMIN_EMAIL, GARMIN_PASSWORD)
    g.client.load('/opt/qbot/app/.garmin_tokens')
    g.display_name = profile['display_name']
    return g


@mcp.tool()
def get_garmin_wellness(date: str = None) -> str:
    """
    Pobiera szczegółowe dane zdrowotne z Garmin Connect:
    sen (fazy, SpO2, oddech), Body Battery, HRV, VO2max, stres.
    Używaj razem z get_xert_status dla pełnej analizy formy i regeneracji.
    date: YYYY-MM-DD (domyślnie wczoraj)
    """
    from datetime import date as dt, timedelta
    if date:
        d = date
    else:
        d = (dt.today() - timedelta(days=1)).isoformat()
    try:
        g = _garmin_client()

        # Sen
        sleep_raw = g.get_sleep_data(d)
        s = sleep_raw.get('dailySleepDTO', {})
        scores = s.get('sleepScores', {})
        sleep = {
            'czas_h':       round(s.get('sleepTimeSeconds', 0) / 3600, 1),
            'gleboki_min':  round(s.get('deepSleepSeconds', 0) / 60),
            'rem_min':      round(s.get('remSleepSeconds', 0) / 60),
            'lekki_min':    round(s.get('lightSleepSeconds', 0) / 60),
            'wybudzenia_min': round(s.get('awakeSleepSeconds', 0) / 60),
            'score':        scores.get('overall', {}).get('value'),
            'ocena':        scores.get('overall', {}).get('qualifierKey'),
            'rem_procent':  scores.get('remPercentage', {}).get('value'),
            'gleboki_procent': scores.get('deepPercentage', {}).get('value'),
            'spo2_avg':     s.get('averageSpO2Value'),
            'oddech_avg':   s.get('averageRespirationValue'),
            'stres_sen':    s.get('avgSleepStress'),
        }

        # Body Battery
        bb_raw = g.get_body_battery(d, d)
        bb = {}
        if bb_raw:
            b = bb_raw[0]
            vals = [v[1] for v in b.get('bodyBatteryValuesArray', [])]
            bb = {
                'naladowana':  b.get('charged'),
                'zuyta':       b.get('drained'),
                'max_rano':    max(vals) if vals else None,
                'min_wieczor': min(vals) if vals else None,
                'ocena_koniec_dnia': b.get('bodyBatteryDynamicFeedbackEvent', {}).get('bodyBatteryLevel'),
            }

        # HRV
        hrv_raw = g.get_hrv_data(d)
        h = hrv_raw.get('hrvSummary', {})
        hrv = {
            'srednia_noc':      h.get('lastNightAvg'),
            'szczyt_noc':       h.get('lastNight5MinHigh'),
            'srednia_tygodnia': h.get('weeklyAvg'),
            'status':           h.get('status'),
            'odchylenie_od_normy': round(h.get('lastNightAvg', 0) - h.get('weeklyAvg', 0), 1) if h.get('lastNightAvg') and h.get('weeklyAvg') else None,
        }

        # VO2max
        ts = g.get_training_status(d)
        vo2_raw = ts.get('mostRecentVO2Max', {}).get('generic', {})
        vo2 = {
            'wartosc':    vo2_raw.get('vo2MaxPreciseValue'),
            'data_pomiaru': vo2_raw.get('calendarDate'),
        }

        # Tętno spoczynkowe
        try:
            rhr_raw = g.get_rhr_day(d)
            rhr_val = (rhr_raw.get('allMetrics', {}).get('metricsMap', {})
                       .get('WELLNESS_RESTING_HEART_RATE', [{}])[0].get('value'))
            tetno_spoczynkowe = int(rhr_val) if rhr_val else None
        except Exception:
            tetno_spoczynkowe = None

        result = {
            'data': d,
            'sen':                  sleep,
            'body_battery':         bb,
            'hrv':                  hrv,
            'vo2max':               vo2,
            'tetno_spoczynkowe':    tetno_spoczynkowe,
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'error': str(e)})


def _garmin_recovery_records(days: int = 7) -> dict:
    """Fetch raw-enough Garmin sleep/HRV records for backend recovery selection."""
    from datetime import date as dt, datetime, timezone, timedelta
    from zoneinfo import ZoneInfo

    local_tz = ZoneInfo("Europe/Warsaw")

    def local_iso(value):
        if value in (None, ""):
            return None
        try:
            seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        except (TypeError, ValueError):
            return value
        # Garmin's *TimestampLocal fields are local wall time encoded as epoch ms.
        wall = datetime.fromtimestamp(seconds, timezone.utc).replace(tzinfo=local_tz)
        return wall.isoformat()

    def gmt_iso(value):
        if value in (None, ""):
            return None
        try:
            seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        except (TypeError, ValueError):
            return value
        return datetime.fromtimestamp(seconds, timezone.utc).astimezone(local_tz).isoformat()

    g = _garmin_client()
    sleep_records = []
    hrv_records = []
    errors = []
    sleep_end_by_date = {}

    for offset in range(max(1, days)):
        d = (dt.today() - timedelta(days=offset)).isoformat()

        try:
            sleep_raw = g.get_sleep_data(d) or {}
            s = sleep_raw.get("dailySleepDTO") or {}
            if s:
                sleep_date = s.get("calendarDate") or d
                sleep_start_local = local_iso(s.get("sleepStartTimestampLocal"))
                sleep_end_local = local_iso(s.get("sleepEndTimestampLocal"))
                sleep_end_by_date[sleep_date] = sleep_end_local
                sleep_records.append({
                    "source": "garmin",
                    "localDate": sleep_date,
                    "sleepStartTimestampLocal": sleep_start_local,
                    "sleepEndTimestampLocal": sleep_end_local,
                    "sleepStartTimestampGMT": gmt_iso(s.get("sleepStartTimestampGMT")),
                    "sleepEndTimestampGMT": gmt_iso(s.get("sleepEndTimestampGMT")),
                    "sleepTimeSeconds": s.get("sleepTimeSeconds"),
                    "sleepScore": ((s.get("sleepScores") or {}).get("overall") or {}).get("value"),
                })
        except Exception as exc:
            errors.append({"date": d, "type": "sleep", "error": str(exc)})

        try:
            hrv_raw = g.get_hrv_data(d) or {}
            h = hrv_raw.get("hrvSummary") or {}
            if h:
                hrv_date = h.get("calendarDate") or d
                hrv_records.append({
                    "source": "garmin",
                    "localDate": hrv_date,
                    "sourceTime": (
                        local_iso(h.get("lastNightEndTimeLocal"))
                        or gmt_iso(h.get("lastNightEndTimeGMT"))
                        or sleep_end_by_date.get(hrv_date)
                    ),
                    "lastNightAvg": h.get("lastNightAvg"),
                    "weeklyAvg": h.get("weeklyAvg"),
                    "status": h.get("status"),
                })
        except Exception as exc:
            errors.append({"date": d, "type": "hrv", "error": str(exc)})

    return {
        "sleepRecords": sleep_records,
        "hrvRecords": hrv_records,
        "errors": errors,
    }


def _xert_token():
    import requests as _r
    r = _r.post('https://www.xertonline.com/oauth/token',
        auth=('xert_public', 'xert_public'),
        data={'grant_type': 'password',
              'username': XERT_EMAIL,
              'password': XERT_PASSWORD}, timeout=10)
    return r.json()['access_token']


@mcp.tool()
def get_xert_status() -> str:
    """
    Pobiera pełny status treningowy z Xert — PRIORYTETOWE źródło danych o formie i FTP.
    Zwraca: TP (FTP dynamiczne), forma, zmęczenie, rekomendacje, cel eventowy, krzywą mocy.
    ZAWSZE używaj tego zamiast FTP z Intervals.icu.
    """
    import requests as _r
    try:
        token = _xert_token()
        HDR = {'Authorization': f'Bearer {token}'}

        t = _r.get('https://www.xertonline.com/oauth/training', headers=HDR, timeout=10).json()
        a = t.get('advice', {})
        sig = a.get('signature', {})
        ts  = a.get('training_status', {})
        at  = a.get('at_state', {})

        # Krzywa mocy — kluczowe punkty
        powers = {p['dur']: p['userp'] for p in a.get('current_minute_powers', [])
                  if p['dur'] in ['1','5','10','20:00','30:00','01:00:00','02:00:00']}

        result = {
            'zrodlo': 'Xert — priorytetowe nad Intervals.icu',
            'tp_ftp_watts':     round(sig.get('ftp', 0), 1),
            'pp_watts':         round(sig.get('pp', 0), 1),
            'ltp_watts':        round(sig.get('ltp', 0), 1),
            'hie_kj':           round(sig.get('atc', 0) / 1000, 1),
            'forma': {
                'status':       ts.get('form_cat', ''),
                'kategoria':    ts.get('cat', ''),
                'gwiazdki':     ts.get('no', 0),
                'training_load': round(ts.get('tl_total', 0), 1),
                'recovery_load': round(ts.get('rl_total', 0), 1),
                'form_score':   round(at.get('form', 0), 1),
                'recovery_needed': a.get('recovery_needed', False),
            },
            'trening_dziś': {
                'cel_xss':      a.get('xss_goal', 0),
                'wykonano_xss': a.get('completedXSS', {}).get('xlss', 0),
                'deficit_xss':  round(a.get('xss_deficit', 0), 1),
                'tryb':         a.get('mode', ''),
                'zalecany_focus': a.get('recommended_focus_text', ''),
                'zalecany_typ':  a.get('recommended_athlete', ''),
                'trudnosc':     a.get('difficulty_rating', ''),
            },
            'cel_eventowy': {
                'data':         a.get('target_event_date', ''),
                'typ_zawodnika': a.get('target_athlete', ''),
                'tygodnie_do_eventu': round(
                    max(0, a.get('target_event_timestamp', 0) - __import__('time').time()) / 604800, 1
                ),
            },
            'krzywa_mocy_watts': powers,
            'jutro': {
                'status':       a.get('tomorrow_status', {}).get('form_cat', ''),
                'tl':           round(a.get('tomorrow_status', {}).get('tl_total', 0), 1),
            }
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'error': str(e)})


@mcp.tool()
def get_xert_activities(limit: int = 10) -> str:
    """
    Pobiera ostatnie aktywności z Xert z danymi o mocy, HR i stresie treningowym.
    Priorytetowe źródło danych treningowych nad Intervals.icu.
    """
    import requests as _r
    try:
        token = _xert_token()
        r = _r.get('https://www.xertonline.com/oauth/activities',
                   headers={'Authorization': f'Bearer {token}'},
                   params={'limit': limit}, timeout=10)
        acts = r.json().get('activities', {}).get('data', [])
        clean = []
        for a in acts:
            sessions = a.get('sessions', [])
            s = sessions[0] if sessions else {}
            clean.append({
                'name':          a.get('name'),
                'date':          s.get('timestamp', '')[:10],
                'sport':         s.get('sport'),
                'sub_sport':     s.get('sub_sport'),
                'czas_min':      round(s.get('total_timer_time', 0) / 60),
                'dystans_km':    round(s.get('total_distance', 0) / 1000, 1) if s.get('total_distance') else None,
                'avg_power':     round(s.get('avg_power', 0)) if s.get('avg_power') else None,
                'norm_power':    s.get('normalized_power'),
                'max_power':     s.get('max_power'),
                'avg_hr':        round(s.get('avg_heart_rate', 0)) if s.get('avg_heart_rate') else None,
                'max_hr':        s.get('max_heart_rate'),
                'tss':           s.get('training_stress_score'),
                'if':            s.get('intensity_factor'),
                'kalorie':       s.get('total_calories'),
                'threshold_power': s.get('threshold_power'),
            })
        return json.dumps(clean, ensure_ascii=False)
    except Exception as e:
        return json.dumps({'error': str(e)})

# ── RIDE READINESS REST ───────────────────────────────────────────────────────

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _baro_multiplier(pressure_hpa, pressure_change_24h):
    deficit = 1013.25 - (pressure_hpa or 1013.25)
    drop    = -(pressure_change_24h or 0)

    if deficit < 5:    deficit_penalty = 1.00
    elif deficit < 15: deficit_penalty = 0.97
    elif deficit < 25: deficit_penalty = 0.94
    else:              deficit_penalty = 0.90

    if drop < 3:    change_penalty = 1.00
    elif drop < 6:  change_penalty = 0.97
    elif drop < 10: change_penalty = 0.94
    else:           change_penalty = 0.90

    return round(deficit_penalty * change_penalty, 4)

def _compute_today_factor(hrv_dev, bb, form, sleep_dev, hr_dev):
    hrv_norm   = _clamp(1.0 + (hrv_dev   / 25.0) * 0.15 if hrv_dev >= 0
                        else 1.0 + (hrv_dev  / 15.0) * 0.45, 0.60, 1.10)
    hr_norm    = _clamp(1.0 + (hr_dev    / 8.0)   * 0.20,    0.60, 1.10)
    bb_norm    = _clamp(0.70 + (bb       / 100.0) * 0.40,    0.60, 1.10)
    form_norm  = _clamp(1.0  + (form     / 30.0)  * 0.10,    0.60, 1.10)
    sleep_norm = _clamp(1.0  + (sleep_dev / 4.0)  * 0.08 if sleep_dev >= 0
                        else 1.0 + (sleep_dev / 2.5) * 0.40, 0.60, 1.10)
    raw = 0.55*hrv_norm + 0.10*hr_norm + 0.15*bb_norm + 0.10*form_norm + 0.10*sleep_norm
    return round(_clamp(raw, 0.70, 1.10), 3)

@mcp.custom_route("/ride-readiness", methods=["GET"])
async def ride_readiness(request):
    """Return ride-readiness context for Karoo/QExt2.

    `sleepDataDate` is a stable marker for the selected nightly sleep record
    and changes only when a newer sleep record is selected.
    """
    import asyncio
    from starlette.responses import JSONResponse
    from datetime import date, timedelta

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    oldest_30 = (date.today() - timedelta(days=30)).isoformat()

    async def fetch_wellness():
        return await icu(f"/athlete/{ATHLETE_ID}/wellness",
                         {"oldest": oldest_30, "newest": today})

    async def fetch_garmin():
        loop = asyncio.get_event_loop()
        return json.loads(await loop.run_in_executor(None, get_garmin_wellness, yesterday))

    async def fetch_garmin_recovery():
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _garmin_recovery_records, 7)

    async def fetch_xert():
        loop = asyncio.get_event_loop()
        return json.loads(await loop.run_in_executor(None, get_xert_status))

    async def fetch_weather():
        from datetime import datetime, timezone as _tz
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": LOC_LAT, "longitude": LOC_LON,
                "current":  "relativehumidity_2m,surface_pressure",
                "hourly":   "surface_pressure",
                "past_days": 1, "forecast_days": 1,
                "timezone": "auto",
            })
            r.raise_for_status()
            raw = r.json()
        now_str  = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:00")
        ago24_str= (datetime.now(_tz.utc) - __import__('datetime').timedelta(hours=24)).strftime("%Y-%m-%dT%H:00")
        times    = raw.get("hourly", {}).get("time", [])
        pressures= raw.get("hourly", {}).get("surface_pressure", [])
        p_map    = dict(zip(times, pressures))
        raw["_pressure_now"]  = p_map.get(now_str)
        raw["_pressure_24h"]  = p_map.get(ago24_str)
        return raw

    results = await asyncio.gather(
        asyncio.wait_for(fetch_wellness(), timeout=10),
        asyncio.wait_for(fetch_garmin(),   timeout=30),
        asyncio.wait_for(fetch_garmin_recovery(), timeout=45),
        asyncio.wait_for(fetch_xert(),     timeout=10),
        asyncio.wait_for(fetch_weather(),  timeout=10),
        return_exceptions=True,
    )
    raw_wellness, raw_garmin, raw_recovery, raw_xert, raw_weather = results

    sources = []
    partial = False

    if isinstance(raw_wellness, Exception):
        print(f"⚠️  ride-readiness: intervals error: {raw_wellness}")
        w = {}; ctl = atl = None; wellness_all = []; partial = True
    else:
        wellness_all = raw_wellness or []
        w = next((x for x in wellness_all if x.get("id") == today), {})
        ctl = w.get("ctl"); atl = w.get("atl")
        sources.append("intervals")

    # 30-dniowe baseline HRV i snu z wellness (bez dzisiaj)
    past_wellness = sorted(
        [x for x in wellness_all if x.get("id") != today],
        key=lambda x: x.get("id", ""), reverse=True
    )
    hrv_vals   = [x["hrv"]       for x in past_wellness if x.get("hrv")]
    sleep_vals = [x["sleepSecs"] for x in past_wellness if x.get("sleepSecs")]
    hrv_baseline_30d = round(sum(hrv_vals)   / len(hrv_vals),   1) if hrv_vals   else None
    sleep_baseline_h = round(sum(v / 3600 for v in sleep_vals) / len(sleep_vals), 2) if sleep_vals else None
    sleep_days_with_data = len(sleep_vals)
    sleep_days_null      = len(past_wellness) - sleep_days_with_data

    # RHR baseline z 30 dni
    rhr_vals     = [x["restingHR"] for x in past_wellness if x.get("restingHR")]
    rhr_baseline = round(sum(rhr_vals) / len(rhr_vals), 1) if rhr_vals else None
    rhr_today    = w.get("restingHR")

    if isinstance(raw_garmin, Exception) or (isinstance(raw_garmin, dict) and "error" in raw_garmin):
        print(f"⚠️  ride-readiness: garmin error: {raw_garmin}")
        garmin = {}; partial = True
    else:
        garmin = raw_garmin
        sources.append("garmin")

    if isinstance(raw_recovery, Exception):
        print(f"⚠️  ride-readiness: garmin recovery error: {raw_recovery}")
        recovery_raw = {"sleepRecords": [], "hrvRecords": [], "errors": [str(raw_recovery)]}
        partial = True
    else:
        recovery_raw = raw_recovery or {"sleepRecords": [], "hrvRecords": []}

    if isinstance(raw_xert, Exception) or (isinstance(raw_xert, dict) and "error" in raw_xert):
        print(f"⚠️  ride-readiness: xert error: {raw_xert}")
        xert = {}; partial = True
    else:
        xert = raw_xert
        sources.append("xert")

    humidity = pressure_now = pressure_change = None
    if not isinstance(raw_weather, Exception):
        humidity      = (raw_weather.get("current") or {}).get("relativehumidity_2m")
        p_now         = raw_weather.get("_pressure_now")
        p_24h         = raw_weather.get("_pressure_24h")
        pressure_now  = round(p_now, 1) if p_now is not None else None
        pressure_change = round(p_now - p_24h, 1) if (p_now is not None and p_24h is not None) else None

    if partial:
        sources.append("partial")

    bb         = (garmin.get("body_battery") or {}).get("naladowana") or 75
    form_score = (xert.get("forma") or {}).get("form_score") or 0
    ftp_watts  = xert.get("tp_ftp_watts")
    ltp_watts  = xert.get("ltp_watts")
    w_prime_kj = xert.get("hie_kj")
    xert_status= (xert.get("forma") or {}).get("status")

    recovery = select_recovery_records(
        recovery_raw.get("sleepRecords") or [],
        recovery_raw.get("hrvRecords") or [],
    )
    sleep_today_h = recovery["sleepTodayH"]
    sleep_date = (recovery["recoverySource"] or {}).get("sleepLocalDate")
    hrv_today = recovery["hrvToday"]
    if hrv_baseline_30d is None and recovery.get("hrvBaseline") is not None:
        hrv_baseline_30d = recovery["hrvBaseline"]

    recovery_source = recovery["recoverySource"]
    sleep_min = recovery_source.get("sleepDurationMin")
    sleep_data_date = sleep_data_date_marker(recovery_source)
    if recovery["completeSleepCandidates"]:
        print(
            "QBOT_RECOVERY_SELECT "
            f"candidates={recovery['candidates']} "
            f"selectedSleepDate={recovery_source.get('sleepLocalDate')} "
            f"selectedSleepStart={recovery_source.get('sleepStartTime')} "
            f"selectedSleepEnd={recovery_source.get('sleepEndTime')} "
            f"selectedHrvDate={recovery_source.get('hrvLocalDate')} "
            f"hrv={hrv_today} sleepMin={sleep_min}",
            flush=True,
        )
    else:
        print(
            "QBOT_RECOVERY_SELECT no complete sleep record "
            f"candidates={recovery['candidates']} "
            "selectedSleepDate=None selectedSleepStart=None selectedSleepEnd=None "
            f"selectedHrvDate={recovery_source.get('hrvLocalDate')} "
            f"hrv={hrv_today} sleepMin={sleep_min}",
            flush=True,
        )

    # HRV: wybrany rekord nocny z Garmina, odchylenie od baseline
    hrv_dev_30d    = round(hrv_today - hrv_baseline_30d, 1) if (hrv_today and hrv_baseline_30d) else 0

    # Sen: odchylenie od 30d baseline
    sleep_dev = round(sleep_today_h - sleep_baseline_h, 2) if (sleep_today_h and sleep_baseline_h) else 0

    # RHR odchylenie: baseline - dziś (dodatnie = lepiej)
    hr_dev = round(rhr_baseline - rhr_today, 1) if (rhr_baseline and rhr_today) else 0

    weight_raw = w.get("weight")
    body_weight_kg = round(weight_raw, 1) if weight_raw else None
    body_weight_date = today if weight_raw else None
    if body_weight_kg is None:
        for past in sorted(wellness_all, key=lambda x: x.get("id", ""), reverse=True):
            if past.get("weight") and past.get("id") != today:
                body_weight_kg = round(past["weight"], 1)
                body_weight_date = past["id"]
                break

    today_factor = _compute_today_factor(hrv_dev_30d, bb, form_score, sleep_dev, hr_dev)

    payload = {
        "hrvToday":           hrv_today,
        "sleepTodayH":        sleep_today_h,
        "hrvBaseline30d":     hrv_baseline_30d,
        "sleepBaseline":      sleep_baseline_h,
        "recoverySource":     recovery_source,
        "sleepDataDate":      sleep_data_date,
        "todayFactor":        today_factor,
        "ftpWatts":           ftp_watts,
        "ltpWatts":           ltp_watts,
        "wPrimeKj":           w_prime_kj,
        "bodyWeightKg":       body_weight_kg,
        "bodyWeightDate":     body_weight_date,
        "humidityPercent":    humidity,
        "pressureHpa":        pressure_now,
        "pressureChange24h":  pressure_change,
        "pressureDeficit":    round(1013.25 - pressure_now, 2) if pressure_now is not None else None,
        "baroMultiplier":     _baro_multiplier(pressure_now, pressure_change),
        "restingHrToday":     rhr_today,
        "restingHrBaseline":  rhr_baseline,
        "maxHrBpm":           RIDER_MAX_HR_BPM,
        "maxHrSource":        RIDER_MAX_HR_SOURCE if RIDER_MAX_HR_BPM else None,
        "ctl":                round(ctl, 1) if ctl is not None else None,
        "atl":                round(atl, 1) if atl is not None else None,
        "signals": {
            "hrvToday":        hrv_today,
            "hrvBaseline30d":  hrv_baseline_30d,
            "hrvDeviation30d": hrv_dev_30d,
            "restingHrDev":    hr_dev,
            "bodyBattery":     bb,
            "sleepTodayH":       sleep_today_h,
            "sleepDate":         sleep_date,
            "sleepBaseline30d":  sleep_baseline_h,
            "sleepDaysWithData": sleep_days_with_data,
            "sleepDaysNull":     sleep_days_null,
            "sleepDev":          sleep_dev,
            "sleepDataDate":     sleep_data_date,
            "recoverySource":    recovery_source,
            "maxHrBpm":         RIDER_MAX_HR_BPM,
            "maxHrSource":      RIDER_MAX_HR_SOURCE if RIDER_MAX_HR_BPM else None,
            "formScore":       form_score,
            "xertStatus":      xert_status,
        },
        "dataAge": today,
        "sources": sources,
    }

    print(f"🚦 ride-readiness | factor={today_factor} ftp={ftp_watts} "
          f"hrv_dev={hrv_dev_30d} hr_dev={hr_dev} bb={bb} "
          f"sleep_dev={sleep_dev} pressure={pressure_now}({pressure_change:+.1f}) "
          f"sources={sources}", flush=True)

    return JSONResponse(payload, headers={"Access-Control-Allow-Origin": "*"})

if __name__ == "__main__":
    print(f"🚴 Q MCP Server | Athlete: {ATHLETE_ID} | {LOC_NAME}")
    print(f"📡 SSE endpoint: http://0.0.0.0:8000/sse")
    mcp.run(transport="streamable-http")
