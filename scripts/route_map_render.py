#!/usr/bin/env python3
"""Renderer mapy trasy do raportu QBot.

Cel wizualny:
- format landscape (szerszy niz wyzszy; min. aspect wymuszany),
- zoom dobierany pod CZYTELNOSC (nazwy miejscowosci, detal), nie pod wpasowanie,
- plotno przycinane CIASNO do bbox trasy + ~40px (~1cm) marginesu,
- jednolita grubosc kreski, gladka (supersampling 3x) + biala obwodka,
- podklad OSM standard (carto) = ma nazwy miejscowosci.

Wejscie: track_points z cache RWGPS + segmenty nawierzchni z qbot_v2 (po dystansie).
Uzycie:
  .venv/bin/python scripts/route_map_render.py --route-id 55798129
  (legacy: --margin 40 --max-px 1200 --min-aspect 1.30 --zoom auto --out /sciezka.png)
  (report: --mode report --width 1400 --height 900 --target-fill 0.82 --max-fill 0.94 --alerts-json /sciezka.json)
"""
from __future__ import annotations
import argparse, json, math, os, io, time
from pathlib import Path

from PIL import Image, ImageDraw

APP = Path("/opt/qbot/app")
RWGPS_CACHE = APP / "data/routes/rwgps_route_cache.json"
TILE_CACHE = Path("/opt/qbot/artifacts/tiles_osm")
TILE_CACHE.mkdir(parents=True, exist_ok=True)
OUT_DIR = Path("/opt/qbot/artifacts/maps")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
UA = "QBot/3.0 route-report map (kontakt: qbot@olga181.mikrus.xyz)"
TILE = 256

# --- kolory zgodne z legenda raportu ---
COLORS = {
    "asfalt":   (58, 63, 71),
    "szuter":   (184, 190, 200),
    "grunt":    (199, 154, 91),
    "piach":    (194, 69, 47),
    "nieznana": (194, 69, 47),
}
# mapowanie surowych nawierzchni qbot_v2 -> kubelek
BUCKET = {
    "asfalt": "asfalt", "beton": "asfalt", "concrete:plates": "asfalt",
    "kostka brukowa": "asfalt",
    "gravel/żwir": "szuter", "gravel drobny": "szuter", "ubita nawierzchnia": "szuter",
    "szuter": "szuter", "szuter ubity": "szuter",
    "ziemia/grunt": "grunt", "grunt": "grunt", "nieutwardzona": "grunt",
    "trawa": "grunt", "gruntowa/szuter": "grunt",
    "piach": "piach", "piasek": "piach", "sand": "piach",
}

def bucket_of(surface: str) -> str:
    if not surface:
        return "nieznana"
    s = surface.strip().lower()
    if s in ("nieznana", "unknown", ""):
        return "nieznana"
    return BUCKET.get(surface.strip(), BUCKET.get(s, "nieznana"))

# --- env / db ---
def load_env():
    p = APP / ".env.local"
    if not p.exists():
        return
    try:
        content = p.read_text()
    except OSError:
        return
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)

def db_connect():
    load_env()
    try:
        import psycopg2 as pg
    except ModuleNotFoundError:
        import psycopg as pg
    return pg.connect(host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
                      user=os.getenv("PGUSER", "qbot"), dbname=os.getenv("PGDATABASE", "qbot"),
                      password=os.getenv("PGPASSWORD"))

# --- dane trasy ---
def load_track(route_id: str):
    d = json.loads(RWGPS_CACHE.read_text())
    r = d[str(route_id)]["route"]
    tp = r["track_points"]
    pts = [(p["x"], p["y"], p.get("d", 0.0)) for p in tp]  # lon, lat, cumdist_m
    return pts, r

def load_segments(route_id: str):
    con = db_connect(); cur = con.cursor()
    cur.execute("select id from qbot_v2.route_artifacts where route_id=%s order by id desc limit 1", (str(route_id),))
    row = cur.fetchone()
    if not row:
        return []
    aid = row[0]
    cur.execute("select id from qbot_v2.route_surface_profiles where route_artifact_id=%s order by id desc limit 1", (aid,))
    row = cur.fetchone()
    if not row:
        return []
    pid = row[0]
    cur.execute("select segment_index, distance_m, surface from qbot_v2.route_surface_segments "
                "where route_surface_profile_id=%s order by segment_index", (pid,))
    segs = cur.fetchall()
    con.close()
    return segs  # [(idx, dist_m, surface)]

def color_per_point(pts, segs):
    """Przypisz kubelek nawierzchni kazdemu punktowi sladu po dystansie."""
    track_total = pts[-1][2] or 1.0
    seg_total = sum(s[1] or 0 for s in segs) or track_total
    scale = track_total / seg_total
    ranges = []
    acc = 0.0
    for _, dist, surf in segs:
        start = acc * scale
        acc += (dist or 0)
        end = acc * scale
        ranges.append((start, end, bucket_of(surf)))
    if not ranges:
        return ["nieznana"] * len(pts)
    out = []
    j = 0
    for (_, _, d) in pts:
        while j < len(ranges) - 1 and d > ranges[j][1]:
            j += 1
        out.append(ranges[j][2])
    return out

# --- projekcja merkatora (piksele globalne) ---
def lonlat_to_px(lon, lat, z):
    n = TILE * (2 ** z)
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y

def route_px_bbox(pts, z):
    xs = []; ys = []
    for lon, lat, _ in pts:
        x, y = lonlat_to_px(lon, lat, z)
        xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)

def pick_zoom_for_detail(pts, max_px=1200, zmin=8, zmax=16):
    """Najwiekszy zoom, przy ktorym dluzszy bok trasy <= max_px.

    Wyzszy zoom = wiecej nazw miejscowosci i detalu. Cap max_px chroni przed
    gigantycznym obrazem. Trasa wypelnia obraz bo plotno jest przycinane do niej.
    """
    best = zmin
    for z in range(zmin, zmax + 1):
        x0, y0, x1, y1 = route_px_bbox(pts, z)
        if max(x1 - x0, y1 - y0) <= max_px:
            best = z
        else:
            break
    return best

# --- kafelki ---
def get_tile(z, x, y):
    fp = TILE_CACHE / f"{z}_{x}_{y}.png"
    if fp.exists():
        return Image.open(fp).convert("RGB")
    import httpx
    for attempt in range(3):
        try:
            r = httpx.get(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": UA}, timeout=20.0)
            if r.status_code == 200:
                fp.write_bytes(r.content)
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            pass
        time.sleep(0.4)
    return Image.new("RGB", (TILE, TILE), (235, 235, 232))

def build_basemap(pts, W, H, z, left, top, return_tile_count=False):
    """Sklej podklad o rozmiarze WxH, lewy-gorny rog w pikselach globalnych (left, top)."""
    tx0 = int(left // TILE); ty0 = int(top // TILE)
    tx1 = int((left + W) // TILE); ty1 = int((top + H) // TILE)
    canvas = Image.new("RGB", (W, H), (235, 235, 232))
    nmax = 2 ** z
    tile_count = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            if ty < 0 or ty >= nmax:
                continue
            tile = get_tile(z, tx % nmax, ty)
            px = int(tx * TILE - left); py = int(ty * TILE - top)
            canvas.paste(tile, (px, py))
            tile_count += 1
    if return_tile_count:
        return canvas, tile_count
    return canvas

def to_canvas(lon, lat, z, left, top):
    x, y = lonlat_to_px(lon, lat, z)
    return (x - left, y - top)

# --- alerty po dystansie ---
ALERT_COLORS = {
    "red": (194, 69, 47),
    "orange": (217, 138, 43),
    "info": (63, 111, 154),
}

def load_alerts_json(alerts_json):
    if not alerts_json:
        return []
    path = Path(alerts_json)
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("alerts-json must contain a JSON list")
    alerts = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            km_from = float(item["km_from"])
            km_to = float(item["km_to"])
            level = str(item["level"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if km_to <= km_from:
            continue
        alerts.append({"km_from": km_from, "km_to": km_to, "level": level})
    return alerts

def _interp_track_point(p0, p1, dist_m):
    d0 = p0[2]
    d1 = p1[2]
    if d1 <= d0:
        return (p0[0], p0[1], dist_m)
    t = (dist_m - d0) / float(d1 - d0)
    lon = p0[0] + (p1[0] - p0[0]) * t
    lat = p0[1] + (p1[1] - p0[1]) * t
    return (lon, lat, dist_m)

def track_segment_between_distances(pts, start_m, end_m):
    if not pts:
        return []
    total = pts[-1][2] or 0.0
    start = max(0.0, min(float(start_m), float(total)))
    end = max(0.0, min(float(end_m), float(total)))
    if end <= start:
        return []

    seg = []
    for i in range(len(pts) - 1):
        p0 = pts[i]
        p1 = pts[i + 1]
        d0 = p0[2]
        d1 = p1[2]
        if d1 < start:
            continue
        if d0 > end:
            break

        if not seg:
            if d0 <= start <= d1:
                seg.append(_interp_track_point(p0, p1, start))
            elif start <= d0 <= end:
                seg.append((p0[0], p0[1], d0))

        if start <= d1 <= end:
            seg.append((p1[0], p1[1], d1))

        if d0 <= end <= d1:
            end_pt = _interp_track_point(p0, p1, end)
            if not seg or seg[-1][2] != end_pt[2]:
                seg.append(end_pt)
            break

    cleaned = []
    for pt in seg:
        if not cleaned or cleaned[-1][:2] != pt[:2] or cleaned[-1][2] != pt[2]:
            cleaned.append(pt)
    return cleaned

def draw_alerts(base, pts, alerts, z, left, top, line_px=8, ss=3):
    if not alerts:
        return base
    W, H = base.size
    overlay = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for alert in alerts:
        seg_pts = track_segment_between_distances(
            pts,
            float(alert["km_from"]) * 1000.0,
            float(alert["km_to"]) * 1000.0,
        )
        if len(seg_pts) < 2:
            continue
        cpts = [to_canvas(lon, lat, z, left, top) for (lon, lat, _) in seg_pts]
        cpts = [(x * ss, y * ss) for (x, y) in cpts]
        col = ALERT_COLORS.get(alert["level"], ALERT_COLORS["orange"])
        od.line(cpts, fill=col + (255,), width=line_px * ss, joint="curve")
    overlay = overlay.resize((W, H), Image.LANCZOS)
    base = base.convert("RGBA")
    base.alpha_composite(overlay)
    return base.convert("RGB")

# --- rysowanie trasy ---
def draw_route(base, pts, colors, z, left, top, line_w=7, casing_w=5, ss=3):
    W, H = base.size
    overlay = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cpts = [to_canvas(lon, lat, z, left, top) for (lon, lat, _) in pts]
    cpts = [(x * ss, y * ss) for (x, y) in cpts]
    lw = line_w * ss
    cw = (line_w + casing_w) * ss

    # 1) biala obwodka calego sladu (czytelnosc na mapie)
    od.line(cpts, fill=(255, 255, 255, 235), width=cw, joint="curve")
    r = cw / 2
    for (x, y) in (cpts[0], cpts[-1]):
        od.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 235))

    # 2) kolorowe odcinki wg nawierzchni, jednolita grubosc, gladkie zlacza
    run_start = 0
    for i in range(1, len(cpts) + 1):
        if i == len(cpts) or colors[i] != colors[run_start]:
            seg = cpts[run_start:i + 1] if i < len(cpts) else cpts[run_start:i]
            if len(seg) >= 2:
                col = COLORS.get(colors[run_start], COLORS["nieznana"]) + (255,)
                od.line(seg, fill=col, width=lw, joint="curve")
            run_start = i
    overlay = overlay.resize((W, H), Image.LANCZOS)
    base = base.convert("RGBA")
    base.alpha_composite(overlay)

    # 3) markery start/meta na ostro
    d = ImageDraw.Draw(base)
    def marker(pt, fill, rad=9):
        x, y = pt
        d.ellipse([x - rad - 2, y - rad - 2, x + rad + 2, y + rad + 2], fill=(255, 255, 255, 255))
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=fill + (255,))
    start = to_canvas(pts[0][0], pts[0][1], z, left, top)
    meta = to_canvas(pts[-1][0], pts[-1][1], z, left, top)
    marker(start, (22, 163, 74))   # zielony start
    marker(meta, (17, 24, 39))     # czarna meta
    return base.convert("RGB")

def route_fill_for_bbox(x0, y0, x1, y1, width, height):
    return max((x1 - x0) / float(width), (y1 - y0) / float(height))

def pick_zoom_for_fill(pts, width, height, target_fill, max_fill=0.94, zmin=0, zmax=16):
    """Wybierz zoom z fill <= max_fill, jak najblizszy target_fill.

    Priorytet:
    1) nie przekroczyc max_fill,
    2) byc jak najblizej target_fill,
    3) jesli target_fill nie da sie osiagnac bez przekroczenia max_fill,
       zwroc najlepszy dostepny zoom i oznacz to warningiem w metadata.
    """
    best_safe = None
    best_safe_gap = None
    best_any = None
    best_any_gap = None

    for z in range(zmin, zmax + 1):
        bbox = route_px_bbox(pts, z)
        fill = route_fill_for_bbox(*bbox, width, height)
        gap = abs(fill - target_fill)

        if best_any is None or gap < best_any_gap or (gap == best_any_gap and fill > best_any[2]):
            best_any = (z, bbox, fill)
            best_any_gap = gap

        if fill <= max_fill + 1e-9:
            if best_safe is None or gap < best_safe_gap or (gap == best_safe_gap and fill > best_safe[2]):
                best_safe = (z, bbox, fill)
                best_safe_gap = gap

    if best_safe is not None:
        warning = None if best_safe[2] >= target_fill - 1e-9 else "target_fill_not_reached"
        return best_safe[0], best_safe[1], best_safe[2], warning

    if best_any is not None:
        return best_any[0], best_any[1], best_any[2], "target_fill_not_reached"

    raise ValueError("No zoom candidates available")

def render_legacy(route_id, margin=40, max_px=1200, min_aspect=1.30, zoom=None, out=None):
    pts, route = load_track(route_id)
    segs = load_segments(route_id)
    colors = color_per_point(pts, segs)
    z = zoom if zoom else pick_zoom_for_detail(pts, max_px)

    x0, y0, x1, y1 = route_px_bbox(pts, z)
    rw = x1 - x0; rh = y1 - y0
    W = int(math.ceil(rw)) + 2 * margin
    H = int(math.ceil(rh)) + 2 * margin

    # lekkie wymuszenie landscape (szerszy niz wyzszy)
    if W < H * min_aspect:
        W = int(round(H * min_aspect))

    # plotno wycentrowane na bbox trasy
    cx = (x0 + x1) / 2.0; cy = (y0 + y1) / 2.0
    left = cx - W / 2.0; top = cy - H / 2.0

    base = build_basemap(pts, W, H, z, left, top)
    img = draw_route(base, pts, colors, z, left, top)
    out = out or str(OUT_DIR / f"map_{route_id}_land.png")
    img.save(out, "PNG")
    return out, z, route.get("name"), len(pts), len(segs), W, H

def render_report(route_id, width=1400, height=900, target_fill=0.82, max_fill=0.94,
                  zoom=None, out=None, alerts_json=""):
    pts, route = load_track(route_id)
    segs = load_segments(route_id)
    colors = color_per_point(pts, segs)
    z, bbox, fill, warning = pick_zoom_for_fill(pts, width, height, target_fill, max_fill=max_fill)
    alerts = load_alerts_json(alerts_json)

    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    left = cx - width / 2.0
    top = cy - height / 2.0

    base, tile_count = build_basemap(pts, width, height, z, left, top, return_tile_count=True)
    img = draw_route(base, pts, colors, z, left, top)
    img = draw_alerts(img, pts, alerts, z, left, top, line_px=8, ss=3)
    out_path = Path(out) if out else OUT_DIR / f"map_{route_id}_report_{width}x{height}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    meta = {
        "output_path": str(out_path),
        "route_id": str(route_id),
        "width": width,
        "height": height,
        "zoom": z,
        "route_fill": round(fill, 4),
        "target_fill": round(target_fill, 4),
        "max_fill": round(max_fill, 4),
        "warning": warning,
        "bbox": {
            "x0": round(x0, 2),
            "y0": round(y0, 2),
            "x1": round(x1, 2),
            "y1": round(y1, 2),
        },
        "tile_count": tile_count,
        "alert_count": len(alerts),
        "alert_line_px": 8,
        "mode": "report",
    }
    meta_path = out_path.with_suffix(".json") if out_path.suffix else Path(str(out_path) + ".json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return str(out_path), meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--route-id", required=True)
    ap.add_argument("--mode", choices=("legacy", "report"), default="legacy")
    ap.add_argument("--margin", type=int, default=40, help="margines wokol trasy w px (~1cm)")
    ap.add_argument("--max-px", type=int, default=1200, help="cap dluzszego boku trasy (detal vs rozmiar)")
    ap.add_argument("--min-aspect", type=float, default=1.30, help="min. proporcja W/H (landscape)")
    ap.add_argument("--zoom", type=int, default=0)
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--target-fill", type=float, default=0.82)
    ap.add_argument("--max-fill", type=float, default=0.94)
    ap.add_argument("--alerts-json", default="", help="JSON list of alert ranges for report mode")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    zoom = a.zoom or None
    if a.mode == "report":
        out_path, meta = render_report(a.route_id, width=a.width, height=a.height,
                                       target_fill=a.target_fill, max_fill=a.max_fill,
                                       zoom=zoom, out=a.out or None, alerts_json=a.alerts_json)
        print("OK", out_path)
        print(json.dumps(meta, ensure_ascii=False, sort_keys=True))
    else:
        res = render_legacy(a.route_id, margin=a.margin, max_px=a.max_px,
                            min_aspect=a.min_aspect, zoom=zoom, out=a.out or None)
        print("OK", res)

if __name__ == "__main__":
    main()
