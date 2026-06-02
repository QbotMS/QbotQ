"""QBot — GPX History Tile Loader"""
import glob, json, math, os
import xml.etree.ElementTree as ET
from datetime import datetime

TILE_DEG = 0.01
CACHE_FILE = "/opt/qbot/artifacts/tiles/gpx_history_cache.json"
GPX_SEARCH_PATHS = [
    "/opt/qbot/artifacts/routes/**/*.gpx",
    "/opt/qbot/artifacts/exports/rwgps/*.gpx",
    "/opt/qbot/artifacts/exports/rwgps/**/*.gpx",
    "/root/gpx/*.gpx",
    "/root/gpx/**/*.gpx",
]

def latlon_to_tile(lat, lon):
    return (int(math.floor(lon / TILE_DEG)), int(math.floor(lat / TILE_DEG)))

def parse_gpx_trackpoints(gpx_path):
    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()
    except ET.ParseError:
        return []
    ns = root.tag.rstrip("gpx").strip("{}") if "{" in root.tag else ""
    prefix = "{" + ns + "}" if ns else ""
    points = []
    for trkpt in root.iter(prefix + "trkpt"):
        try:
            points.append((float(trkpt.attrib["lat"]), float(trkpt.attrib["lon"])))
        except (KeyError, ValueError):
            continue
    if not points:
        for rtept in root.iter(prefix + "rtept"):
            try:
                points.append((float(rtept.attrib["lat"]), float(rtept.attrib["lon"])))
            except (KeyError, ValueError):
                continue
    return points

def gpx_to_tiles(gpx_path):
    return {latlon_to_tile(lat, lon) for lat, lon in parse_gpx_trackpoints(gpx_path)}

def _load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"files": {}, "tiles": []}

def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

def load_tiles_from_gpx_history(paths=None, force_rebuild=False, verbose=True):
    if paths is None:
        paths = GPX_SEARCH_PATHS
    cache = {} if force_rebuild else _load_cache()
    file_cache = cache.get("files", {})
    all_tiles = set(tuple(t) for t in cache.get("tiles", []))
    gpx_files = []
    for pattern in paths:
        gpx_files.extend(glob.glob(pattern, recursive=True))
    gpx_files = list(set(gpx_files))
    if verbose:
        print(f"Znaleziono {len(gpx_files)} plikow GPX")
    new_files = 0
    for gpx_path in sorted(gpx_files):
        mtime = os.path.getmtime(gpx_path)
        key = gpx_path
        if key in file_cache and file_cache[key]["mtime"] == mtime:
            continue
        tiles = gpx_to_tiles(gpx_path)
        if verbose:
            print(f"  {os.path.basename(gpx_path)}: {len(tiles)} kafelkow")
        file_cache[key] = {"mtime": mtime, "tile_count": len(tiles), "tiles": [list(t) for t in tiles]}
        new_files += 1
    if new_files > 0 or force_rebuild:
        all_tiles = set()
        for fdata in file_cache.values():
            for t in fdata.get("tiles", []):
                all_tiles.add(tuple(t))
        _save_cache({"files": file_cache, "tiles": [list(t) for t in all_tiles], "updated": datetime.now().isoformat()})
    if verbose:
        print(f"Lacznie kafelkow: {len(all_tiles)} ({'przebudowano' if new_files else 'z cache'})")
    return all_tiles

def get_tiles_gpx_or_api(share_id=None, prefer_api=True, verbose=True):
    if prefer_api and share_id:
        try:
            from tools.tile_store import fetch_tiles
            data = fetch_tiles(share_id)
            if data and data.get("tiles"):
                return data
        except Exception:
            pass
    tiles = load_tiles_from_gpx_history(verbose=verbose)
    return {"tiles": tiles, "source": "gpx_history", "count": len(tiles)}

if __name__ == "__main__":
    import sys
    tiles = load_tiles_from_gpx_history(force_rebuild="--rebuild" in sys.argv, verbose=True)
    if tiles:
        xs = [t[0] for t in tiles]
        ys = [t[1] for t in tiles]
        print(f"Kafelki: {len(tiles)}, bbox lon: {min(xs)*TILE_DEG:.2f}-{max(xs)*TILE_DEG:.2f}, lat: {min(ys)*TILE_DEG:.2f}-{max(ys)*TILE_DEG:.2f}")
    else:
        print("Brak plikow GPX w skonfigurowanych sciezkach.")
