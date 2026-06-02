"""
tools/route_generator.py
Handler: generowanie trasy od zera przez Valhalla (bicycle/gravel profile).

qbot.query examples:
  "generuj trasę 80km start 43.318,11.330"
  "zaplanuj pętlę 60km 40% nowych kafelków"
  "generuj trasę 100km überkwadrat"
  "nowa trasa 80km start 52.23,21.01 gravel 70%"
"""
from __future__ import annotations
import json, math, os, random, re, time, urllib.request, urllib.error
from dataclasses import dataclass, field
from typing import Optional

VALHALLA_ROUTE = "https://valhalla1.openstreetmap.de/route"
TILE_DEG = 0.01

# ---------------------------------------------------------------------------
# Struktury
# ---------------------------------------------------------------------------
@dataclass
class RouteConstraints:
    start_lat: float
    start_lon: float
    target_km: float
    new_tile_pct: float = 0.3
    gravel_ratio: float = 0.5
    loop: bool = True
    expand_uberkwadrat: bool = False
    existing_tiles: set = field(default_factory=set)
    uberkwadrat: Optional[tuple] = None
    max_retries: int = 5

@dataclass
class GeneratedRoute:
    waypoints: list
    distance_km: float
    new_tiles: int
    total_tiles: int
    new_tile_pct: float
    score: float
    gpx_path: Optional[str] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _latlon_to_tile(lat, lon):
    return (int(math.floor(lon/TILE_DEG)), int(math.floor(lat/TILE_DEG)))

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2-lat1); dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.asin(math.sqrt(a))

def _point_at(lat, lon, dist_km, bearing_deg):
    R = 6371; d = dist_km/R; b = math.radians(bearing_deg)
    lat1 = math.radians(lat); lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1)*math.cos(d)+math.cos(lat1)*math.sin(d)*math.cos(b))
    lon2 = lon1+math.atan2(math.sin(b)*math.sin(d)*math.cos(lat1), math.cos(d)-math.sin(lat1)*math.sin(lat2))
    return (math.degrees(lat2), math.degrees(lon2))

def _track_to_tiles(track):
    return {_latlon_to_tile(lat,lon) for lat,lon in track}

# ---------------------------------------------------------------------------
# Valhalla
# ---------------------------------------------------------------------------
def _valhalla_route(waypoints, gravel_ratio=0.5):
    locations = [{"lat":lat,"lon":lon} for lat,lon in waypoints]
    use_roads = 1.0 - gravel_ratio
    payload = {
        "locations": locations,
        "costing": "bicycle",
        "costing_options": {"bicycle": {
            "bicycle_type": "Cross",
            "use_roads": round(use_roads, 2),
            "use_hills": 0.5,
            "avoid_bad_surfaces": max(0, gravel_ratio - 0.5),
        }},
        "directions_options": {"units": "km"},
        "shape_format": "geojson",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(VALHALLA_ROUTE, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def _decode_polyline(encoded, precision=6):
    """Decode Valhalla encoded polyline (precision 6)."""
    inv = 1.0 / 10**precision
    decoded = []
    lat = lon = 0
    i = 0
    while i < len(encoded):
        shift = result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lat += (~(result >> 1) if (result & 1) else (result >> 1))
        shift = result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lon += (~(result >> 1) if (result & 1) else (result >> 1))
        decoded.append((lat * inv, lon * inv))
    return decoded

def _parse_track(resp):
    shape = resp["trip"]["legs"][0]["shape"]
    if isinstance(shape, str):
        return _decode_polyline(shape)
    coords = shape["coordinates"]
    return [(c[1],c[0]) for c in coords]

def _parse_dist(resp):
    return resp["trip"]["summary"]["length"]

# ---------------------------------------------------------------------------
# Waypoint strategies
# ---------------------------------------------------------------------------
def _waypoints_loop(c: RouteConstraints, n: int):
    r = min(c.target_km/(2*math.pi), 80)
    base = random.uniform(0,360)
    wps = [(c.start_lat, c.start_lon)]
    for i in range(n):
        ang = (base + i*360/(n+1) + random.uniform(-25,25)) % 360
        wps.append(_point_at(c.start_lat, c.start_lon, r*random.uniform(0.8,1.2), ang))
    wps.append((c.start_lat, c.start_lon))
    return wps

def _waypoints_tile_biased(c: RouteConstraints, n: int):
    r = min(c.target_km/(2*math.pi), 80)
    r_tiles = int(r/(TILE_DEG*111))+1
    stx, sty = _latlon_to_tile(c.start_lat, c.start_lon)
    unvisited = []
    for dx in range(-r_tiles, r_tiles+1):
        for dy in range(-r_tiles, r_tiles+1):
            tx, ty = stx+dx, sty+dy
            if (tx,ty) not in c.existing_tiles:
                lat = (ty+0.5)*TILE_DEG; lon = (tx+0.5)*TILE_DEG
                d = _haversine(c.start_lat, c.start_lon, lat, lon)
                if d <= r*1.3:
                    unvisited.append((lat,lon,d))
    if not unvisited:
        return _waypoints_loop(c, n)
    target_d = r*0.8
    unvisited.sort(key=lambda x: abs(x[2]-target_d))
    selected = []
    for lat,lon,_ in unvisited[:n*3]:
        if not any(_haversine(lat,lon,wl,wn)<r*0.2 for wl,wn in selected):
            selected.append((lat,lon))
        if len(selected)>=n: break
    wps = [(c.start_lat, c.start_lon)] + selected
    if c.loop: wps.append((c.start_lat, c.start_lon))
    return wps

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _score(track, c: RouteConstraints, dist_km):
    route_tiles = _track_to_tiles(track)
    new_tiles = route_tiles - c.existing_tiles
    total = len(route_tiles)
    new_pct = len(new_tiles)/max(total,1)
    dist_score = max(0, 1-abs(dist_km/c.target_km-1)*2)
    tile_score = min(new_pct/max(c.new_tile_pct,0.01), 1.0)
    w_dist = 0.40; w_tile = 0.60
    return {
        "score": round(w_dist*dist_score + w_tile*tile_score, 3),
        "new_tiles": len(new_tiles), "total_tiles": total,
        "new_tile_pct": round(new_pct*100,1), "distance_km": round(dist_km,1),
    }

# ---------------------------------------------------------------------------
# GPX export
# ---------------------------------------------------------------------------
def _to_gpx(route: GeneratedRoute, name: str) -> str:
    pts = "\n".join(f'    <trkpt lat="{lat:.6f}" lon="{lon:.6f}"></trkpt>' for lat,lon in route.waypoints)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="QBot RouteGenerator" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata><name>{name}</name></metadata>
  <trk><name>{name}</name><trkseg>
{pts}
  </trkseg></trk>
</gpx>"""

# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
def generate_route(c: RouteConstraints) -> Optional[GeneratedRoute]:
    strategies = [_waypoints_tile_biased, _waypoints_loop]
    best = None; best_score = -1.0
    for i in range(c.max_retries):
        strategy = strategies[i % len(strategies)]
        n = random.choice([2,3,4])
        try:
            wps = strategy(c, n_intermediate=n) if 'n_intermediate' in strategy.__code__.co_varnames else strategy(c, n)
            resp = _valhalla_route(wps, c.gravel_ratio)
            track = _parse_track(resp)
            dist = _parse_dist(resp)
            sc = _score(track, c, dist)
            if sc["score"] > best_score:
                best_score = sc["score"]
                best = GeneratedRoute(
                    waypoints=track, distance_km=dist,
                    new_tiles=sc["new_tiles"], total_tiles=sc["total_tiles"],
                    new_tile_pct=sc["new_tile_pct"], score=sc["score"],
                )
            if sc["score"] >= 0.7:
                break
            time.sleep(0.5)
        except Exception:
            time.sleep(1)
    return best

# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
def handle_route_generate(question: str) -> dict:
    ql = question.lower()

    # Dystans
    dist_m = re.search(r"(\d+)\s*km", ql)
    if not dist_m:
        return {"answer":"Podaj dystans, np. 'generuj trasę 80km'.", "data":{}, "sources":[]}
    target_km = int(dist_m.group(1))

    # Punkt startowy
    coord_m = re.search(r"start\s+([\d.]+)[,\s]+([\d.]+)", ql)
    if coord_m:
        start_lat, start_lon = float(coord_m.group(1)), float(coord_m.group(2))
    else:
        # Domyślnie: Warszawa (fallback — w praktyce Michał poda zawsze)
        start_lat = float(os.getenv("LOCATION_LAT", "52.23"))
        start_lon = float(os.getenv("LOCATION_LON", "21.01"))

    # Parametry opcjonalne
    tile_m = re.search(r"(\d+)%\s*nowych", ql)
    new_tile_pct = int(tile_m.group(1))/100 if tile_m else 0.3

    gravel_m = re.search(r"gravel\s+(\d+)%|(\d+)%\s*gravel", ql)
    gravel_ratio = int((gravel_m.group(1) or gravel_m.group(2)))/100 if gravel_m else 0.5

    expand_uber = bool(re.search(r"[üu]berkwadrat|uber", ql))

    # Pobierz istniejące kafelki (opcjonalne — graceful degradation)
    existing_tiles = set()
    uberkwadrat = None
    try:
        from tools.gpx_history_loader import load_tiles_from_gpx_history
        existing_tiles = load_tiles_from_gpx_history(verbose=False)
        if expand_uber and existing_tiles:
            from tools.tile_store import find_uberkwadrat
            uberkwadrat = find_uberkwadrat(existing_tiles)
    except Exception:
        pass

    c = RouteConstraints(
        start_lat=start_lat, start_lon=start_lon, target_km=target_km,
        new_tile_pct=new_tile_pct, gravel_ratio=gravel_ratio,
        loop=True, expand_uberkwadrat=expand_uber,
        existing_tiles=existing_tiles, uberkwadrat=uberkwadrat,
        max_retries=5,
    )

    route = generate_route(c)
    if not route:
        return {"answer":"Nie udało się wygenerować trasy (Valhalla niedostępna?).", "data":{}, "sources":["valhalla"]}

    # Zapisz GPX
    gpx_dir = "/opt/qbot/artifacts/routes/generated"
    os.makedirs(gpx_dir, exist_ok=True)
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    gpx_name = f"generated_{target_km}km_{ts}"
    gpx_path = f"{gpx_dir}/{gpx_name}.gpx"
    with open(gpx_path, "w") as f:
        f.write(_to_gpx(route, gpx_name))
    route.gpx_path = gpx_path

    answer = (
        f"Trasa wygenerowana:\n"
        f"  Dystans: {route.distance_km:.1f} km (cel: {target_km} km)\n"
        f"  Nowe kafelki: {route.new_tiles} ({route.new_tile_pct:.0f}%)\n"
        f"  Score: {route.score:.2f}/1.0\n"
        f"  GPX: {gpx_path}"
    )
    return {
        "answer": answer,
        "data": {"distance_km": route.distance_km, "new_tiles": route.new_tiles,
                 "score": route.score, "gpx_path": gpx_path},
        "sources": ["valhalla", "gpx_history"],
    }


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "generuj trasę 80km start 43.318,11.330"
    r = handle_route_generate(q)
    print(r["answer"])
