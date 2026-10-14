"""Radar opadu QBot (Pogoda, krok 1) -- kompozyt EUMETNET OPERA + ruch opadu + krotka prognoza dla punktu.

Zrodlo: EUMETNET OPERA, kompozyt maksymalnej odbiciowosci (DBZH), co 5 min, 1 km, licencja CC BY 4.0
(podpis "EUMETNET OPERA" obowiazkowy). Publiczny zasobnik S3 (CloudFerro, bez klucza), 24 h wstecz.
Zawiera wszystkie 10 polskich radarow IMGW. W pliku: NaN = radar widzi, brak echa; -9999000 = brak pokrycia.

Co robi:
  sync()          -- pobiera brakujace klatki z ostatnich KEEP_MIN minut, przycina do BBOX (Europa Srodkowa),
                     przelicza na siatke Web Mercator (pod mape Leaflet), zapisuje klatke (.npz) + warstwe PNG.
  motion()        -- ruch opadu: korelacja fazowa kafelkow z 3 klatek (t-30, t-15, t); kafelek liczy sie
                     tylko gdy ruch w 1. i 2. polowce sie zgadza (odrzuca szum i opad, ktory rosnie/zanika).
  nowcast_point() -- os czasu dla punktu: historia z radaru + przesuwanie najnowszego obrazu wzdluz ruchu.

Uczciwe granice: przesuwanie obrazu zaklada, ze opad nie zmienia ksztaltu ani sily. Dla deszczu z frontu
sensowne do ~1-2 h, dla przelotnych opadow/burz ~30-60 min. Radar nie widzi opadu, ktory dopiero powstanie.
Dalszy horyzont = model (ICON-D2) -- osobna warstwa. Dok.: docs/POGODA_RADAR.md
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import threading
import urllib.request
from zoneinfo import ZoneInfo

import numpy as np

BASE = "https://s3.waw3-1.cloudferro.com/openradar-24h"
CACHE = os.getenv("QBOT_RADAR_CACHE", "/opt/qbot/artifacts/radar_cache")
BBOX = (11.0, 47.5, 27.0, 56.5)       # lon_min, lat_min, lon_max, lat_max (Polska + sasiedzi = widac co nadchodzi)
PX_M = 1500.0                          # piksel siatki Web Mercator [m merc] (~0,9 km w terenie na 52N)
KEEP_MIN = 120                         # ile minut historii trzymamy (animacja)
EVERY_S = 300                          # co ile sekund petla w tle
DBZ_SHOW = 12.0                        # ponizej nie rysujemy (mzawka/szum)
DBZ_RAIN = 18.0                        # ~0,5 mm/h (Marshall-Palmer) = "pada"
DBZ_NONE = -31.5                       # "radar widzi, brak echa"
PAIR_MIN = 30                          # odstep skrajnych klatek do liczenia ruchu
TILE = 128                             # kafelek ruchu [px] (~120 km w terenie)
CONS_KMH = 15.0                        # max roznica ruchu 1. vs 2. polowki okna (zgodnosc)
ATTR = "Radar: EUMETNET OPERA (CC BY 4.0)"
TZ = ZoneInfo("Europe/Warsaw")
UA = {"User-Agent": "QBot/1.0 (radar; qbot.cytr.us)"}

_LOCK = threading.Lock()
_R = 6378137.0


def _merc(lon: float, lat: float) -> tuple[float, float]:
    return math.radians(lon) * _R, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * _R


def _unmerc(x: float, y: float) -> tuple[float, float]:
    return math.degrees(x / _R), math.degrees(2 * math.atan(math.exp(y / _R)) - math.pi / 2)


X0, Y0 = _merc(BBOX[0], BBOX[1])
_X1, _Y1 = _merc(BBOX[2], BBOX[3])
W = int(round((_X1 - X0) / PX_M))
H = int(round((_Y1 - Y0) / PX_M))
X1, Y1 = X0 + W * PX_M, Y0 + H * PX_M


def bounds_latlon() -> list:
    """Rogi warstwy dla Leaflet imageOverlay: [[lat_s, lon_w], [lat_n, lon_e]]."""
    lw, ls = _unmerc(X0, Y0)
    le, ln = _unmerc(X1, Y1)
    return [[round(ls, 5), round(lw, 5)], [round(ln, 5), round(le, 5)]]


def to_px(lat: float, lon: float) -> tuple[float, float]:
    x, y = _merc(lon, lat)
    return (x - X0) / PX_M, (Y1 - y) / PX_M      # (kolumna, wiersz)


def ground_km_per_px(lat: float) -> float:
    return PX_M * math.cos(math.radians(lat)) / 1000.0


def dbz_to_mmh(dbz: float) -> float:
    """Marshall-Palmer Z = 200 R^1.6."""
    if dbz is None or not math.isfinite(dbz) or dbz < DBZ_SHOW:
        return 0.0
    return round((10 ** (dbz / 10.0) / 200.0) ** (1 / 1.6), 1)


# ---------------------------------------------------------------- pobieranie i cache

def _get(url: str, timeout: float = 40.0) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _list_day(day: dt.date) -> list[str]:
    keys, token = [], None
    while True:
        url = f"{BASE}?list-type=2&prefix={day:%Y/%m/%d}/OPERA/COMP/"
        if token:
            url += "&continuation-token=" + urllib.request.quote(token, safe="")
        xml = _get(url, 20).decode()
        keys += re.findall(r"<Key>([^<]+)</Key>", xml)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", xml)
        if "<IsTruncated>true" not in xml or not m:
            return keys
        token = m.group(1)


def _key_ts(key: str) -> dt.datetime | None:
    m = re.search(r"OPERA@(\d{8}T\d{4})@0@DBZH\.tiff$", key)
    if not m:
        return None
    return dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M").replace(tzinfo=dt.timezone.utc)


def _fname(ts: dt.datetime, ext: str) -> str:
    return os.path.join(CACHE, f"{ts:%Y%m%dT%H%M}.{ext}")


def _fetch(key: str) -> np.ndarray:
    """Klatka OPERA -> siatka Web Mercator (H x W) w dBZ; NaN = brak pokrycia, DBZ_NONE = brak echa."""
    import rasterio
    from affine import Affine
    from rasterio.warp import Resampling, reproject

    raw = _get(f"{BASE}/{key}")
    dst = np.full((H, W), np.nan, dtype=np.float32)
    with rasterio.MemoryFile(raw) as mf, mf.open() as ds:
        src = ds.read(1).astype(np.float32)
        nodata = (src == ds.nodata) if ds.nodata is not None else np.zeros(src.shape, bool)
        src[np.isnan(src)] = DBZ_NONE          # w pliku NaN = radar widzi, brak echa
        src[nodata] = np.nan                   # brak pokrycia
        reproject(source=src, destination=dst, src_transform=ds.transform, src_crs=ds.crs,
                  src_nodata=np.nan, dst_nodata=np.nan,
                  dst_transform=Affine(PX_M, 0, X0, 0, -PX_M, Y1), dst_crs="EPSG:3857",
                  resampling=Resampling.nearest)
    return dst


def _encode(a: np.ndarray) -> np.ndarray:
    """dBZ -> uint8: 0 = brak pokrycia, 1..255 = (dBZ+32)*2 (krok 0,5 dBZ)."""
    u = np.clip(np.round((np.nan_to_num(a, nan=-99.0) + 32.0) * 2.0), 1, 255).astype(np.uint8)
    u[~np.isfinite(a)] = 0
    return u


def _decode(u: np.ndarray) -> np.ndarray:
    a = u.astype(np.float32) / 2.0 - 32.0
    a[u == 0] = np.nan
    return a


# paleta dBZ -> RGBA (klasyczna skala radarowa, przezroczystosc dla slabych ech)
_PAL = [(12, (155, 200, 245, 110)), (18, (80, 160, 235, 170)), (24, (40, 110, 210, 190)),
        (30, (40, 175, 70, 200)), (35, (130, 205, 50, 210)), (40, (245, 220, 40, 220)),
        (45, (245, 150, 30, 230)), (50, (230, 60, 40, 235)), (55, (190, 30, 120, 240)),
        (60, (150, 60, 200, 245))]


def _lut() -> np.ndarray:
    lut = np.zeros((256, 4), dtype=np.uint8)
    for code in range(1, 256):
        dbz = code / 2.0 - 32.0
        col = None
        for thr, c in _PAL:
            if dbz >= thr:
                col = c
        if col:
            lut[code] = col
    return lut


_LUT = _lut()


def _png(u: np.ndarray, path: str) -> None:
    from PIL import Image
    Image.fromarray(_LUT[u], "RGBA").save(path, optimize=True)


def frames() -> list[dt.datetime]:
    if not os.path.isdir(CACHE):
        return []
    out = []
    for f in os.listdir(CACHE):
        m = re.match(r"(\d{8}T\d{4})\.npz$", f)
        if m:
            out.append(dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M").replace(tzinfo=dt.timezone.utc))
    return sorted(out)


def load(ts: dt.datetime) -> np.ndarray:
    with np.load(_fname(ts, "npz")) as z:
        return _decode(z["u"])


def sync(now: dt.datetime | None = None, keep_min: int = KEEP_MIN) -> dict:
    """Dociaga brakujace klatki, kasuje stare, przelicza ruch. Bezpieczne do wolania w petli."""
    with _LOCK:
        now = now or dt.datetime.now(dt.timezone.utc)
        os.makedirs(CACHE, exist_ok=True)
        since = now - dt.timedelta(minutes=keep_min)
        avail = {}
        for day in sorted({since.date(), now.date()}):
            for k in _list_day(day):
                ts = _key_ts(k)
                if ts and ts >= since:
                    avail[ts] = k
        have = set(frames())
        new = []
        for ts in sorted(avail):
            if ts in have:
                continue
            u = _encode(_fetch(avail[ts]))
            tmp = _fname(ts, "tmp")
            _png(u, tmp + ".png")
            os.replace(tmp + ".png", _fname(ts, "png"))
            np.savez_compressed(tmp + ".npz", u=u)          # npz ostatni: jego obecnosc = klatka gotowa
            os.replace(tmp + ".npz", _fname(ts, "npz"))
            new.append(ts)
        cut = max(avail) - dt.timedelta(minutes=keep_min) if avail else since
        removed = 0
        for f in os.listdir(CACHE):
            m = re.match(r"(\d{8}T\d{4})\.(npz|png)$", f)
            if m and dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M").replace(tzinfo=dt.timezone.utc) < cut:
                os.remove(os.path.join(CACHE, f))
                removed += 1
        mot = None
        if new or not os.path.exists(os.path.join(CACHE, "motion.json")):
            mot = motion()
            with open(os.path.join(CACHE, "motion.json.tmp"), "w") as fh:
                json.dump(mot, fh)
            os.replace(os.path.join(CACHE, "motion.json.tmp"), os.path.join(CACHE, "motion.json"))
        fr = frames()
        return {"status": "OK", "nowe": len(new), "usuniete": removed, "klatek": len(fr),
                "najnowsza": fr[-1].isoformat() if fr else None,
                "ruch_kafelkow": (mot or {}).get("n")}


# ---------------------------------------------------------------- ruch opadu

def _field(a: np.ndarray) -> np.ndarray:
    return np.clip(np.nan_to_num(a, nan=DBZ_NONE) - DBZ_SHOW, 0.0, 40.0)


def _hann(n: int) -> np.ndarray:
    w = np.hanning(n)
    return np.outer(w, w).astype(np.float32)


_HANN = _hann(TILE)


def _sub(r: np.ndarray, i: int, n: int, axis: int) -> float:
    """Dokladnosc ponizej piksela: parabola przez szczyt i sasiadow."""
    if axis == 0:
        a, b, c = r[(i - 1) % n, :].max(), r[i, :].max(), r[(i + 1) % n, :].max()
    else:
        a, b, c = r[:, (i - 1) % n].max(), r[:, i].max(), r[:, (i + 1) % n].max()
    d = a - 2 * b + c
    return 0.0 if d == 0 else 0.5 * (a - c) / d


def _phase(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Przesuniecie b wzgledem a [px] + wartosc szczytu. Korelacja czesciowo wybielona (|X|^0,5):
    test 14.10.2026 -- pelne wybielenie (fazowa) dawalo slabe szczyty przy rzadkim opadzie, zwykla
    korelacja wiekszy rozrzut; wariant posredni = najwiecej zgodnych kafelkow."""
    fa, fb = np.fft.fft2((a - a.mean()) * _HANN), np.fft.fft2((b - b.mean()) * _HANN)
    x = fb * np.conj(fa)
    r = np.fft.ifft2(x / (np.sqrt(np.abs(x)) + 1e-9)).real
    iy, ix = np.unravel_index(int(np.argmax(r)), r.shape)
    peak = float(r[iy, ix])
    dy = iy + _sub(r, iy, r.shape[0], 0)
    dx = ix + _sub(r, ix, r.shape[1], 1)
    if dy > r.shape[0] / 2:
        dy -= r.shape[0]
    if dx > r.shape[1] / 2:
        dx -= r.shape[1]
    return float(dx), float(dy), peak


def _nearest(fr: list, t1: dt.datetime, mins: float) -> dt.datetime:
    return min(fr, key=lambda t: abs((t1 - t).total_seconds() / 60 - mins))


def motion() -> dict:
    """Pole ruchu: wektory kafelkow [px/min] z klatek t0 (~-30), tm (~-15), t1 (najnowsza)."""
    fr = frames()
    if len(fr) < 3:
        return {"status": "BRAK_DANYCH", "n": 0, "vec": []}
    t1 = fr[-1]
    tm, t0 = _nearest(fr, t1, PAIR_MIN / 2), _nearest(fr, t1, PAIR_MIN)
    m_all, m_a, m_b = [(x - y).total_seconds() / 60 for x, y in ((t1, t0), (tm, t0), (t1, tm))]
    if m_a < 5 or m_b < 5:
        return {"status": "BRAK_DANYCH", "n": 0, "vec": []}
    a0, am, a1 = _field(load(t0)), _field(load(tm)), _field(load(t1))
    thr = DBZ_RAIN - DBZ_SHOW
    cons_px = CONS_KMH / (ground_km_per_px(52.0) * 60.0)
    vec, step, lim, odrz = [], TILE // 2, TILE * 0.4, 0
    for r0 in range(0, H - TILE + 1, step):
        for c0 in range(0, W - TILE + 1, step):
            sl = (slice(r0, r0 + TILE), slice(c0, c0 + TILE))
            if min((a0[sl] > thr).mean(), (am[sl] > thr).mean(), (a1[sl] > thr).mean()) < 0.03:
                continue
            xa, ya, _ = _phase(a0[sl], am[sl])
            xb, yb, _ = _phase(am[sl], a1[sl])
            if max(abs(xa), abs(ya), abs(xb), abs(yb)) > lim or \
                    math.hypot(xa / m_a - xb / m_b, ya / m_a - yb / m_b) > cons_px:
                odrz += 1
                continue
            waga = float((a1[sl] > thr).mean())       # wiecej opadu w kafelku = pewniejszy wektor
            vec.append([c0 + TILE / 2, r0 + TILE / 2, (xa + xb) / (m_a + m_b), (ya + yb) / (m_a + m_b),
                        round(waga, 3)])
    return {"status": "OK" if vec else "BRAK_OPADU", "t0": t0.isoformat(), "t1": t1.isoformat(),
            "minuty": m_all, "n": len(vec), "odrzucone": odrz, "vec": vec}


def _motion_cached() -> dict:
    p = os.path.join(CACHE, "motion.json")
    if os.path.exists(p):
        with open(p) as fh:
            return json.load(fh)
    return motion()


def local_motion(lat: float, lon: float, mot: dict | None = None, radius_km: float = 200.0) -> dict | None:
    """Wektor ruchu dla punktu: wazona mediana kafelkow w promieniu; inaczej mediana z calej mapy."""
    mot = mot or _motion_cached()
    v = mot.get("vec") or []
    if not v:
        return None
    col, row = to_px(lat, lon)
    kmpx = ground_km_per_px(lat)
    arr = np.array(v, dtype=float)
    d_km = np.hypot(arr[:, 0] - col, arr[:, 1] - row) * kmpx
    near = d_km <= radius_km
    zakres = "lokalny"
    if near.sum() < 2:
        near, zakres = np.ones(len(arr), bool), "cala mapa"
    sel = arr[near]
    w = sel[:, 4] / (1.0 + d_km[near] / 50.0)

    def wmed(x):
        o = np.argsort(x)
        cw = np.cumsum(w[o])
        return float(x[o][np.searchsorted(cw, cw[-1] / 2)])

    vx, vy = wmed(sel[:, 2]), wmed(sel[:, 3])
    spd = math.hypot(vx, vy) * kmpx * 60.0
    # kierunek DOKAD przesuwa sie opad (0 = na polnoc, zgodnie z zegarem); wiersz rosnie na poludnie
    dokad = (math.degrees(math.atan2(vx, -vy)) + 360) % 360
    rozrzut = float(np.hypot(sel[:, 2] - vx, sel[:, 3] - vy).std() * kmpx * 60.0) if len(sel) > 1 else None
    return {"vx": vx, "vy": vy, "kmh": round(spd, 1), "dokad_deg": round(dokad),
            "dokad": _kier(dokad), "skad": _kier((dokad + 180) % 360),
            "kafelkow": int(near.sum()), "zakres": zakres,
            "rozrzut_kmh": round(rozrzut, 1) if rozrzut is not None else None}


def _kier(deg: float) -> str:
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


# ---------------------------------------------------------------- punkt

def _disk(a: np.ndarray, col: float, row: float, r_px: float) -> np.ndarray:
    r = int(math.ceil(r_px))
    c0, r0 = int(round(col)), int(round(row))
    ys, xs = np.mgrid[r0 - r:r0 + r + 1, c0 - r:c0 + r + 1]
    m = (np.hypot(xs - col, ys - row) <= max(r_px, 0.75)) & (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
    return a[ys[m], xs[m]]


def _stat(vals: np.ndarray) -> dict:
    fin = vals[np.isfinite(vals)]
    if fin.size == 0:
        return {"dbz": None, "mmh": None, "udzial": None, "pokrycie": False}
    mx = float(fin.max())
    return {"dbz": round(mx, 1), "mmh": dbz_to_mmh(mx),
            "udzial": round(float((fin >= DBZ_RAIN).mean()), 2), "pokrycie": True}


def nowcast_point(lat: float, lon: float, lead_max: int = 120, step: int = 5) -> dict:
    """Os czasu dla punktu: historia z radaru + prognoza przez przesuwanie najnowszego obrazu.

    udzial = jaka czesc otoczenia punktu ma opad >= DBZ_RAIN (miara szansy, rosnie promien niepewnosci).
    """
    fr = frames()
    if not fr:
        return {"status": "BRAK_DANYCH", "error": "Brak klatek radaru w cache."}
    col, row = to_px(lat, lon)
    if not (0 <= col < W and 0 <= row < H):
        return {"status": "POZA_ZASIEGIEM", "error": "Punkt poza obszarem radaru QBota."}
    kmpx = ground_km_per_px(lat)
    hist = []
    for ts in fr:
        s = _stat(_disk(load(ts), col, row, 2.0 / kmpx))
        hist.append({"t": ts.astimezone(TZ).strftime("%H:%M"), "iso": ts.isoformat(), **s})
    lm = local_motion(lat, lon)
    t1 = fr[-1]
    last = load(t1)
    prog = []
    if lm:
        for L in range(step, lead_max + 1, step):
            sc, sr = col - lm["vx"] * L, row - lm["vy"] * L
            r_km = 2.0 + 0.08 * L            # niepewnosc rosnie z czasem (60 min ~ 7 km)
            s = _stat(_disk(last, sc, sr, r_km / kmpx))
            ts = t1 + dt.timedelta(minutes=L)
            prog.append({"t": ts.astimezone(TZ).strftime("%H:%M"), "iso": ts.isoformat(), "min": L,
                         "pewnosc": "radar" if L <= 60 else "radar-orientacyjnie", **s})
    return {"status": "OK", "lat": lat, "lon": lon, "najnowsza": t1.astimezone(TZ).strftime("%H:%M"),
            "opoznienie_min": round((dt.datetime.now(dt.timezone.utc) - t1).total_seconds() / 60),
            "ruch": lm, "historia": hist, "prognoza": prog, "werdykt": _werdykt(hist, prog, lm),
            "zrodlo": ATTR}


def _pl(x) -> str:
    return str(x).replace(".", ",")


def _werdykt(hist: list, prog: list, lm: dict | None) -> str:
    teraz = hist[-1] if hist else {}
    if not teraz.get("pokrycie"):
        return "Brak pokrycia radarem w tym miejscu."
    pada = (teraz.get("udzial") or 0) >= 0.5
    if pada:
        for p in prog:
            if (p.get("udzial") or 0) < 0.3:
                return f"Pada teraz ({_pl(teraz.get('mmh'))} mm/h). Wg radaru przestanie ok. {p['t']}."
        return "Pada teraz i wg radaru potrwa dluzej niz horyzont prognozy radarowej -- sprawdz model."
    for p in prog:
        if (p.get("udzial") or 0) >= 0.5:
            return f"Teraz sucho. Opad dojdzie ok. {p['t']} (ok. {_pl(p.get('mmh'))} mm/h)."
    if not lm:
        return "Teraz sucho, w okolicy brak opadu do sledzenia."
    return "Teraz sucho. Wg radaru opad Cie omija w horyzoncie prognozy."
