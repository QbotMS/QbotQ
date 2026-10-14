"""Mapy modelu dla strony Pogoda: DWD ICON-EU (opendata, bez limitu), +1..60 h. Dok.: docs/POGODA_RADAR.md (sekcja Mapa modelu)

Wybor modelu: ICON-EU wygrywa najwiecej parametrow w sprawdzalnosci (qbot_pogoda_verif, 14.10.2026). Pliki: siatka 0,0625 st
(~7 km), GRIB2 bz2, caly obszar Europy, ~1 MB/parametr/krok. Wycinek = BBOX radaru, przeliczony na siatke Web Mercator
PX_M (dwuliniowo), zapis PNG per warstwa x krok w CACHE/<run>/. Kroki: co 1 h do +24, co 3 h do +60.
Warstwy: opad (mm/h z roznicy TOT_PREC), temp (T_2M), wiatr (U/V 10 m, m/s), porywy (VMAX_10M), lod (grunt T_G <= 0,5 C
i [opad 6 h > 0,1 mm albo punkt rosy >= T_G]), mgla (przyblizenie: T_2M - TD_2M < 1 C i wiatr < 3 m/s; ICON-EU nie ma widzialnosci).
Transfer: 7 parametrow x 37 krokow x ~1 MB ~ 260 MB na przebieg; domyslnie przebiegi RUNS.
"""
from __future__ import annotations

import bz2
import datetime as dt
import json
import math
import os
import re
import shutil
import tempfile
import threading
import urllib.request

import numpy as np

import qbot_radar as RAD

BASE = "https://opendata.dwd.de/weather/nwp/icon-eu/grib/{run:02d}/{p}/"
FNAME = "icon-eu_europe_regular-lat-lon_single-level_{ymdh}_{step:03d}_{P}.grib2.bz2"
CACHE = os.getenv("QBOT_POGODA_MAP_CACHE", "/opt/qbot/artifacts/pogoda_model")
RUNS = (0, 6, 12, 18)   # 14.10: 4 przebiegi -- swiezszy model = mniejszy rozjazd z radarem
STEPS = list(range(0, 25)) + list(range(27, 61, 3))
PARAMS = ("t_2m", "tot_prec", "u_10m", "v_10m", "vmax_10m", "t_g", "td_2m")
BBOX = (11.0, 47.5, 27.0, 56.5)
PX_M = 6000.0
MODEL = "ICON-EU 7 km (DWD)"
ATTR = "Model: ICON-EU, Deutscher Wetterdienst (CC BY 4.0)"
UA = {"User-Agent": "QBot/1.0 (pogoda-mapa)"}
_LOCK = threading.Lock()
_R = 6378137.0


def _merc(lon, lat):
    return math.radians(lon) * _R, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * _R


X0, Y0 = _merc(BBOX[0], BBOX[1]); _x1, _y1 = _merc(BBOX[2], BBOX[3])
W, H = int(round((_x1 - X0) / PX_M)), int(round((_y1 - Y0) / PX_M))
X1, Y1 = X0 + W * PX_M, Y0 + H * PX_M


def bounds_latlon():
    f = lambda x, y: (math.degrees(2 * math.atan(math.exp(y / _R)) - math.pi / 2), math.degrees(x / _R))
    s, w = f(X0, Y0); n, e = f(X1, Y1)
    return [[round(s, 5), round(w, 5)], [round(n, 5), round(e, 5)]]


def _get(u, t=90):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
        return r.read()


def latest_run(now=None):
    """Najnowszy przebieg z RUNS, ktory ma juz ostatni krok (+60 h) dla wszystkich parametrow."""
    now = now or dt.datetime.now(dt.timezone.utc)
    for back in range(0, 48, 6):
        t = (now - dt.timedelta(hours=back)).replace(minute=0, second=0, microsecond=0)
        t = t.replace(hour=t.hour - t.hour % 6)
        if t.hour not in RUNS:
            continue
        ymdh = t.strftime("%Y%m%d%H")
        try:
            ok = all(FNAME.format(ymdh=ymdh, step=STEPS[-1], P=p.upper()) in _get(BASE.format(run=t.hour, p=p), 20).decode()
                     for p in PARAMS)
        except Exception:
            ok = False
        if ok:
            return t
    return None


def _decode(raw: bytes):
    import eccodes
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf:
        tf.write(raw); tf.flush()
        with open(tf.name, "rb") as fh:
            g = eccodes.codes_grib_new_from_file(fh)
            try:
                ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
                la0 = eccodes.codes_get(g, "latitudeOfFirstGridPointInDegrees")
                lo0 = eccodes.codes_get(g, "longitudeOfFirstGridPointInDegrees")
                d = eccodes.codes_get(g, "iDirectionIncrementInDegrees")
                if lo0 > 180:
                    lo0 -= 360.0      # DWD: 336,5 = -23,5
                v = eccodes.codes_get_values(g).reshape(nj, ni)
            finally:
                eccodes.codes_release(g)
    return v, la0, lo0, d


_IDX = {}


def _resample(v, la0, lo0, d):
    """Siatka lat/lon -> siatka Mercator (H x W), dwuliniowo."""
    key = (v.shape, la0, lo0, d)
    if key not in _IDX:
        xs = X0 + (np.arange(W) + 0.5) * PX_M
        ys = Y1 - (np.arange(H) + 0.5) * PX_M
        lon = np.degrees(xs / _R)
        lat = np.degrees(2 * np.arctan(np.exp(ys / _R)) - np.pi / 2)
        fi = (lon - lo0) / d
        fj = (lat - la0) / d
        _IDX[key] = (fi, fj)
    fi, fj = _IDX[key]
    i0 = np.clip(np.floor(fi).astype(int), 0, v.shape[1] - 2); j0 = np.clip(np.floor(fj).astype(int), 0, v.shape[0] - 2)
    ti = (fi - i0)[None, :]; tj = (fj - j0)[:, None]
    J0, I0 = j0[:, None], i0[None, :]
    a = v[J0, I0] * (1 - ti) + v[J0, I0 + 1] * ti
    b = v[J0 + 1, I0] * (1 - ti) + v[J0 + 1, I0 + 1] * ti
    return (a * (1 - tj) + b * tj).astype(np.float32)


# ---------------------------------------------------------------- palety
def _ramp(stops):
    """stops: [(wartosc, (r,g,b,a)), ...] -> funkcja array -> RGBA (liniowo)."""
    xs = np.array([s[0] for s in stops], float); cs = np.array([s[1] for s in stops], float)
    def f(arr):
        out = np.zeros(arr.shape + (4,), np.uint8)
        for k in range(4):
            out[..., k] = np.interp(arr, xs, cs[:, k]).astype(np.uint8)
        return out
    return f


PAL = {
    "opad": _ramp([(0.05, (155, 200, 245, 0)), (0.1, (155, 200, 245, 120)), (0.5, (80, 160, 235, 170)), (1, (40, 110, 210, 190)),
                   (2.5, (40, 175, 70, 200)), (5, (245, 220, 40, 215)), (10, (245, 150, 30, 225)), (20, (230, 60, 40, 235)), (40, (150, 60, 200, 240))]),
    "temp": _ramp([(-20, (90, 40, 160, 150)), (-10, (40, 80, 200, 150)), (0, (110, 170, 230, 140)), (5, (150, 210, 230, 130)),
                   (10, (170, 220, 150, 130)), (15, (230, 225, 110, 140)), (20, (245, 180, 70, 150)), (25, (235, 110, 50, 160)), (35, (190, 30, 60, 170))]),
    "wiatr": _ramp([(0, (200, 220, 240, 0)), (3, (190, 215, 240, 80)), (6, (120, 190, 120, 150)), (9, (240, 200, 60, 175)),
                    (12, (235, 120, 40, 200)), (16, (200, 40, 50, 215)), (24, (130, 30, 140, 230))]),
}
PAL["porywy"] = PAL["wiatr"]
LEGENDA = {
    "opad": [["#9bc8f5", "0,1"], ["#50a0eb", "0,5"], ["#286ed2", "1"], ["#28af46", "2,5"], ["#f5dc28", "5"], ["#f59620", "10"], ["#e63c28", "20 mm/h"]],
    "temp": [["#5a28a0", "−20"], ["#2850c8", "−10"], ["#6eaae6", "0"], ["#aadc96", "10"], ["#e6e16e", "15"], ["#f5b446", "20"], ["#eb6e32", "25 °C"]],
    "wiatr": [["#bed7f0", "3"], ["#78be78", "6"], ["#f0c83c", "9"], ["#eb7828", "12"], ["#c82832", "16 m/s"]],
    "lod": [["#cfe3f8", "niskie"], ["#7fb3ec", "możliwe"], ["#286ed2", "wysokie"]],
    "mgla": [["#c4c4c4", "rosa/mgła możliwa"], ["#7d7d7d", "mgła prawdopodobna"]],
}
LEGENDA["porywy"] = LEGENDA["wiatr"]


def _png(rgba, path):
    from PIL import Image
    tmp = path + ".tmp.png"
    Image.fromarray(rgba, "RGBA").save(tmp, optimize=True)
    os.replace(tmp, path)


def build(run: dt.datetime | None = None) -> dict:
    """Pobiera i rysuje caly przebieg (wolac w tle). Pomija, jesli juz jest kompletny."""
    with _LOCK:
        run = run or latest_run()
        if not run:
            return {"status": "BRAK_PRZEBIEGU"}
        ymdh = run.strftime("%Y%m%d%H")
        out = os.path.join(CACHE, ymdh)
        if os.path.exists(os.path.join(out, "meta.json")):
            return {"status": "JUZ_JEST", "run": ymdh}
        os.makedirs(out, exist_ok=True)
        prev_prec, hist = None, []        # opad godzinowy z ostatnich krokow (do lodu)
        kroki = []
        for step in STEPS:
            f = {}
            for p in PARAMS:
                raw = bz2.decompress(_get(BASE.format(run=run.hour, p=p) + FNAME.format(ymdh=ymdh, step=step, P=p.upper())))
                f[p] = _resample(*_decode(raw))
            prec_tot = f["tot_prec"]
            if prev_prec is None:
                prev_prec, prev_step = prec_tot, step
                continue                   # krok 0: brak opadu godzinowego
            dh = step - prev_step
            mmh = np.clip((prec_tot - prev_prec) / dh, 0, None)
            prev_prec, prev_step = prec_tot, step
            hist.append((step, mmh * dh)); hist = [x for x in hist if x[0] > step - 6]
            p6 = sum(x[1] for x in hist)
            t = f["t_2m"] - 273.15; td = f["td_2m"] - 273.15; tg = f["t_g"] - 273.15
            ws = np.hypot(f["u_10m"], f["v_10m"]); gust = f["vmax_10m"]
            lod = np.zeros(t.shape, np.uint8)
            cold = tg <= 0.5
            wet = (p6 > 0.1) | (mmh > 0)
            frost = td >= tg
            lod[cold] = 1; lod[cold & (wet | frost)] = 2; lod[cold & wet & (tg <= -0.5)] = 3
            mg = np.zeros(t.shape, np.uint8)
            mg[(t - td < 2) & (ws < 4)] = 1; mg[(t - td < 0.7) & (ws < 3)] = 2
            lut_l = np.array([[0, 0, 0, 0], [207, 227, 248, 110], [127, 179, 236, 170], [40, 110, 210, 210]], np.uint8)
            lut_m = np.array([[0, 0, 0, 0], [196, 196, 196, 120], [125, 125, 125, 190]], np.uint8)
            sid = f"{step:03d}"
            # opad w SKALI RADARU: mm/h -> dBZ (Marshall-Palmer) -> ta sama paleta i prog co radar (spojny obraz na osi)
            dbz = np.where(mmh > 0.05, 10 * np.log10(200 * np.power(np.maximum(mmh, 1e-3), 1.6)), -32.0)
            _png(RAD._LUT[np.clip(np.round((dbz + 32) * 2), 1, 255).astype(np.uint8)], os.path.join(out, f"opad_{sid}.png"))
            np.savez_compressed(os.path.join(out, f"opad_{sid}.npz"), r=mmh.astype(np.float16))
            _png(PAL["temp"](t), os.path.join(out, f"temp_{sid}.png"))
            _png(PAL["wiatr"](ws), os.path.join(out, f"wiatr_{sid}.png"))
            _png(PAL["porywy"](gust), os.path.join(out, f"porywy_{sid}.png"))
            _png(lut_l[lod], os.path.join(out, f"lod_{sid}.png"))
            _png(lut_m[mg], os.path.join(out, f"mgla_{sid}.png"))
            kroki.append({"id": sid, "iso": (run + dt.timedelta(hours=step)).isoformat(), "h": step})
        meta = {"run": ymdh, "run_iso": run.isoformat(), "model": MODEL, "zrodlo": ATTR, "bounds": bounds_latlon(),
                "warstwy": ["opad", "temp", "wiatr", "porywy", "lod", "mgla"], "legenda": LEGENDA, "kroki": kroki}
        with open(os.path.join(out, "meta.json.tmp"), "w") as fh:
            json.dump(meta, fh)
        os.replace(os.path.join(out, "meta.json.tmp"), os.path.join(out, "meta.json"))
        # sprzatanie: zostaw 2 ostatnie kompletne przebiegi
        runs = sorted(d for d in os.listdir(CACHE) if re.fullmatch(r"\d{10}", d))
        for d in runs[:-2]:
            shutil.rmtree(os.path.join(CACHE, d), ignore_errors=True)
        return {"status": "OK", "run": ymdh, "krokow": len(kroki)}


def meta() -> dict:
    if not os.path.isdir(CACHE):
        return {"status": "BRAK_DANYCH"}
    runs = sorted(d for d in os.listdir(CACHE) if os.path.exists(os.path.join(CACHE, d, "meta.json")))
    if not runs:
        return {"status": "BRAK_DANYCH"}
    with open(os.path.join(CACHE, runs[-1], "meta.json")) as fh:
        m = json.load(fh)
    m["status"] = "OK"
    return m


def png_path(layer: str, run: str, sid: str) -> str | None:
    if not (re.fullmatch(r"[a-z]+", layer) and re.fullmatch(r"\d{10}", run) and re.fullmatch(r"\d{3}", sid)):
        return None
    p = os.path.join(CACHE, run, f"{layer}_{sid}.png")
    return p if os.path.exists(p) else None


# ---------------------------------------------------------------- korekta polozenia modelu wg radaru (14.10.2026)
_KOR = {"t": 0, "r": None}


def korekta() -> dict:
    """Przesuniecie [m merc] pola opadu modelu do zgodnosci z AKTUALNYM radarem (korelacja fazowa, czesciowo wybielona).
    Strona przesuwa mape modelu o (dx, dy) * waga, waga maleje liniowo do 0 po 6 h od klatki radaru."""
    import time as _t
    if _KOR["r"] and _KOR["t"] > _t.time() - 300:
        return _KOR["r"]
    m = meta()
    fr = RAD.frames()
    if m.get("status") != "OK" or not fr:
        return {"status": "BRAK_DANYCH"}
    t = fr[-1]
    kroki = [k for k in m["kroki"] if dt.datetime.fromisoformat(k["iso"]) >= t]
    if not kroki:
        return {"status": "BRAK_KROKU"}
    k = kroki[0]
    pz = os.path.join(CACHE, m["run"], f"opad_{k['id']}.npz")
    if not os.path.exists(pz):
        return {"status": "BRAK_POLA"}
    a = RAD.load(t)
    rr = np.where(np.isfinite(a) & (a >= RAD.DBZ_SHOW), (10 ** (a / 10.0) / 200.0) ** (1 / 1.6), 0.0)
    f = int(round(PX_M / RAD.PX_M))
    hh, ww = min(rr.shape[0] // f, H), min(rr.shape[1] // f, W)
    rb = rr[:hh * f, :ww * f].reshape(hh, f, ww, f).mean(axis=(1, 3))
    with np.load(pz) as z:
        mm = z["r"].astype(np.float64)[:hh, :ww]
    a1, b1 = np.log1p(mm), np.log1p(rb)
    fa, fb = (a1 > 0.1).mean(), (b1 > 0.1).mean()
    if fa < 0.02 or fb < 0.02:
        r = {"status": "MALO_OPADU", "radar": t.isoformat(), "model_krok": k["id"]}
    else:
        hn = np.outer(np.hanning(hh), np.hanning(ww))
        A, B = np.fft.fft2((a1 - a1.mean()) * hn), np.fft.fft2((b1 - b1.mean()) * hn)
        x = B * np.conj(A)
        c = np.fft.ifft2(x / (np.sqrt(np.abs(x)) + 1e-9)).real
        iy, ix = np.unravel_index(int(np.argmax(c)), c.shape)
        dy, dx = (iy - hh if iy > hh / 2 else iy), (ix - ww if ix > ww / 2 else ix)
        km = math.hypot(dx, dy) * PX_M * math.cos(math.radians(52)) / 1000
        deg = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
        def _zg(x, y):   # zgodnosc: korelacja pol log(1+mm/h)
            x, y = x.ravel() - x.mean(), y.ravel() - y.mean()
            return float((x * y).sum() / (math.sqrt((x * x).sum() * (y * y).sum()) + 1e-12))
        przed, po = _zg(a1, b1), _zg(np.roll(a1, (dy, dx), axis=(0, 1)), b1)
        stat = "ZA_DUZE" if km > 200 else ("BEZ_POPRAWY" if po < przed + 0.05 else "OK")
        r = {"status": stat, "dx_m": float(dx * PX_M), "dy_m": float(-dy * PX_M), "km": round(km), "dokad_deg": round(deg),
             "zgodnosc_przed": round(przed, 2), "zgodnosc_po": round(po, 2),
             "radar": t.isoformat(), "model_krok": k["id"], "run": m["run"], "udzial_radar": round(float(fb), 3), "udzial_model": round(float(fa), 3)}
        if r["status"] != "OK":
            r.update(dx_m=0, dy_m=0)
    _KOR.update(t=_t.time(), r=r)
    return r
