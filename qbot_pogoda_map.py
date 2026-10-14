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
STEPS = list(range(0, 25)) + list(range(27, 121, 3))   # 14.10: do +120 h (weekend); ICON-EU co 1 h do +78, dalej co 3 h
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
            np.savez_compressed(os.path.join(out, f"pola_{sid}.npz"), t=t.astype(np.float16), w=ws.astype(np.float16), g=gust.astype(np.float16))
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
        meta_eps = eps_build(run, out)   # szansa opadu z zespolu (warstwa 'szansa'); bez niej mapa dziala dalej
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


# ---------------------------------------------------------------- SZANSA opadu z zespolu ICON-EU-EPS (14.10.2026)
# Decyzja Michala: zamiast "pada / nie pada" z jednego przebiegu (zgodnosc z radarem na teraz ~0,33) mapa szansy opadu:
# odsetek z 40 wariantow modelu z opadem >= EPS_PROG mm/h. Siatka ikosaedryczna (~20 km) -> najblizsza komorka dla piksela
# naszej siatki (cKDTree, indeks w CACHE/eps_idx.npz). Ok. 8 MB na krok (40 wariantow w jednym pliku).
EPS_BASE = "https://opendata.dwd.de/weather/nwp/icon-eu-eps/grib/{run:02d}/{p}/"
EPS_F = "icon-eu-eps_europe_icosahedral_single-level_{ymdh}_{step:03d}_tot_prec.grib2.bz2"
EPS_TI = "icon-eu-eps_europe_icosahedral_time-invariant_{ymdh}_{p}.grib2.bz2"
EPS_PROG = 0.2   # mm/h -- "pada" dla rowerzysty
EPS_ATTR = "Szansa opadu: ICON-EU-EPS (40 wariantow), DWD (CC BY 4.0)"
PAL["szansa"] = _ramp([(0.05, (120, 170, 235, 0)), (0.1, (120, 170, 235, 70)), (0.3, (70, 140, 230, 125)), (0.5, (40, 100, 215, 165)),
                       (0.7, (95, 60, 200, 195)), (0.9, (150, 40, 160, 225)), (1.0, (170, 30, 140, 235))])
LEGENDA["szansa"] = [["#78aaeb", "10%"], ["#468ce6", "30%"], ["#2864d7", "50%"], ["#5f3cc8", "70%"], ["#9628a0", "90%"]]


def _decode_all(raw: bytes):
    import eccodes
    out = []
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf:
        tf.write(raw); tf.flush()
        with open(tf.name, "rb") as fh:
            while True:
                g = eccodes.codes_grib_new_from_file(fh)
                if g is None:
                    break
                try:
                    out.append(eccodes.codes_get_values(g))
                finally:
                    eccodes.codes_release(g)
    return out


def _eps_index(run: dt.datetime):
    p = os.path.join(CACHE, "eps_idx.npz")
    if os.path.exists(p):
        with np.load(p) as z:
            return z["idx"]
    from scipy.spatial import cKDTree
    ymdh = run.strftime("%Y%m%d%H")
    clat = _decode_all(bz2.decompress(_get(EPS_BASE.format(run=run.hour, p="clat") + EPS_TI.format(ymdh=ymdh, p="clat"))))[0]
    clon = _decode_all(bz2.decompress(_get(EPS_BASE.format(run=run.hour, p="clon") + EPS_TI.format(ymdh=ymdh, p="clon"))))[0]
    if np.nanmax(np.abs(clat)) < 4:            # radiany
        clat, clon = np.degrees(clat), np.degrees(clon)
    clon = np.where(clon > 180, clon - 360, clon)
    xs = X0 + (np.arange(W) + 0.5) * PX_M; ys = Y1 - (np.arange(H) + 0.5) * PX_M
    lon = np.degrees(xs / _R); lat = np.degrees(2 * np.arctan(np.exp(ys / _R)) - np.pi / 2)
    LON, LAT = np.meshgrid(lon, lat)
    k = math.cos(math.radians(52))
    tree = cKDTree(np.c_[clon * k, clat])
    _, idx = tree.query(np.c_[LON.ravel() * k, LAT.ravel()])
    idx = idx.reshape(H, W).astype(np.int32)
    np.savez_compressed(p, idx=idx)
    return idx


def eps_build(run: dt.datetime, out: str) -> dict:
    """Dopisuje warstwe 'szansa' (PNG szansa_<krok>.png) do katalogu przebiegu i uzupelnia meta.json."""
    ymdh = run.strftime("%Y%m%d%H")
    try:
        idx = _eps_index(run)
        prev, prev_step, n = None, None, 0
        for step in [x for x in STEPS if x <= 60]:   # zespol: szansa do +60 h
            mem = _decode_all(bz2.decompress(_get(EPS_BASE.format(run=run.hour, p="tot_prec") + EPS_F.format(ymdh=ymdh, step=step))))
            cur = np.stack([m[idx] for m in mem])          # (warianty, H, W)
            if prev is not None:
                rate = np.clip(cur - prev, 0, None) / (step - prev_step)
                prob = (rate >= EPS_PROG).mean(axis=0)
                _png(PAL["szansa"](prob), os.path.join(out, f"szansa_{step:03d}.png")); n += 1
            prev, prev_step = cur, step
        mp = os.path.join(out, "meta.json")
        if os.path.exists(mp):
            with open(mp) as fh:
                m = json.load(fh)
            if "szansa" not in m["warstwy"]:
                m["warstwy"].append("szansa")
            m["legenda"]["szansa"] = LEGENDA["szansa"]; m["eps"] = {"warianty": len(mem), "prog_mmh": EPS_PROG, "zrodlo": EPS_ATTR}
            with open(mp + ".tmp", "w") as fh:
                json.dump(m, fh)
            os.replace(mp + ".tmp", mp)
        return {"status": "OK", "krokow": n, "wariantow": len(mem)}
    except Exception as e:
        return {"status": "BLAD", "error": f"{type(e).__name__}: {e}"[:300]}


# ---------------------------------------------------------------- GDZIE W WEEKEND (krok 3, 14.10.2026)
# Ocena 0-100 kazdego piksela (6 km) dla dnia i okna godzin (domyslnie okno Trenera na rower w tym dniu):
# kara = opad[mm w oknie] x 1,5 + max(0, sredni wiatr - 5 m/s) + max(0, poryw - 12) x 0,4 + max(0, 4 - temp sr.) x 0,35
#        + max(0, temp max - 28) x 0,5; ocena = 100 - 10 x kara. Najlepsze rejony: zachlannie co >= 60 km, nazwa = najblizsza
# miejscowosc >= 2000 mieszk. (GeoNames PL), punkty bez miejscowosci w 15 km (morze, zagranica) pomijane.
PLACES = "/opt/qbot/artifacts/geonames/PL_places.tsv"
PL_NAZWY = {"Warsaw": "Warszawa", "Cracow": "Kraków", "Krakow": "Kraków", "Wroclaw": "Wrocław", "Lodz": "Łódź", "Poznan": "Poznań",
            "Gdansk": "Gdańsk", "Szczecin": "Szczecin", "Bialystok": "Białystok", "Czestochowa": "Częstochowa", "Bydgoszcz": "Bydgoszcz"}
PAL["ocena"] = _ramp([(0, (192, 57, 43, 150)), (35, (232, 116, 59, 140)), (50, (240, 196, 25, 130)), (65, (154, 205, 50, 130)), (80, (46, 139, 87, 140)), (100, (30, 120, 70, 150))])
LEGENDA["ocena"] = [["#c0392b", "unikaj"], ["#e8743b", "słabo"], ["#f0c419", "tak sobie"], ["#9acd32", "dobrze"], ["#2e8b57", "jedź"]]
_PL: dict = {}


def _places():
    if "a" not in _PL:
        import csv
        rows = []
        with open(PLACES, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                try:
                    rows.append((r["name"], float(r["lat"]), float(r["lon"]), int(r["population"] or 0)))
                except ValueError:
                    pass
        a = np.array([(x[1], x[2]) for x in rows]); _PL.update(a=a, rows=rows, pop=np.array([x[3] for x in rows]))
    return _PL


def _pix_latlon():
    xs = X0 + (np.arange(W) + 0.5) * PX_M; ys = Y1 - (np.arange(H) + 0.5) * PX_M
    lon = np.degrees(xs / _R); lat = np.degrees(2 * np.arctan(np.exp(ys / _R)) - np.pi / 2)
    return np.meshgrid(lon, lat)


def ocena_dnia(day: dt.date, a_h: int = 8, b_h: int = 19) -> dict:
    from zoneinfo import ZoneInfo
    m = meta()
    if m.get("status") != "OK":
        return {"status": "BRAK_DANYCH"}
    out = os.path.join(CACHE, m["run"]); tz = ZoneInfo("Europe/Warsaw")
    key = f"ocena_{day:%Y%m%d}_{a_h:02d}{b_h:02d}"
    jp = os.path.join(out, key + ".json")
    if os.path.exists(jp):
        with open(jp) as fh:
            return json.load(fh)
    a = dt.datetime(day.year, day.month, day.day, a_h, tzinfo=tz); b = dt.datetime(day.year, day.month, day.day, b_h, tzinfo=tz)
    kroki = m["kroki"]; prev = None; rain = tsum = wsum = None; gmax = tmax = None; n = 0.0
    for k in kroki:
        t1 = dt.datetime.fromisoformat(k["iso"]); t0 = t1 - dt.timedelta(hours=(k["h"] - prev) if prev is not None else 1)
        prev = k["h"]
        ov = (min(t1, b) - max(t0, a)).total_seconds() / 3600
        if ov <= 0:
            continue
        po, pp = os.path.join(out, f"opad_{k['id']}.npz"), os.path.join(out, f"pola_{k['id']}.npz")
        if not (os.path.exists(po) and os.path.exists(pp)):
            return {"status": "BRAK_POL", "error": "przebieg bez pol do oceny (przebuduj)"}
        with np.load(po) as z:
            r = z["r"].astype(np.float32)
        with np.load(pp) as z:
            t, w, g = z["t"].astype(np.float32), z["w"].astype(np.float32), z["g"].astype(np.float32)
        rain = r * ov if rain is None else rain + r * ov
        tsum = t * ov if tsum is None else tsum + t * ov
        wsum = w * ov if wsum is None else wsum + w * ov
        gmax = g if gmax is None else np.maximum(gmax, g)
        tmax = t if tmax is None else np.maximum(tmax, t)
        n += ov
    if rain is None or n < (b_h - a_h) * 0.8:
        return {"status": "POZA_PROGNOZA", "error": "dzien poza zasiegiem prognozy przebiegu"}
    tm, wm = tsum / n, wsum / n
    # + drobny komfort (rozroznia remisy przy dobrej pogodzie): slabszy wiatr, temperatura blizej ~16 C
    kara = wm * 0.08 + np.abs(tm - 16) * 0.04 + rain * 1.5 + np.clip(wm - 5, 0, None) + np.clip(gmax - 12, 0, None) * 0.4 + np.clip(4 - tm, 0, None) * 0.35 + np.clip(tmax - 28, 0, None) * 0.5
    oc = np.clip(100 - 10 * kara, 0, 100)
    _png(PAL["ocena"](oc), os.path.join(out, key + ".png"))
    LON, LAT = _pix_latlon()
    P_ = _places(); big = P_["pop"] >= 2000
    from scipy.spatial import cKDTree
    kk = math.cos(math.radians(52))
    t_all = cKDTree(np.c_[P_["a"][:, 1] * kk, P_["a"][:, 0]]); t_big = cKDTree(np.c_[P_["a"][big, 1] * kk, P_["a"][big, 0]])
    bigrows = [x for x, f in zip(P_["rows"], big) if f]
    order = np.argsort(-oc.ravel()); picked = []
    for idx in order[:20000]:
        j, i = divmod(int(idx), W)
        la, lo = float(LAT[j, i]), float(LON[j, i])
        if not (49.0 <= la <= 54.9 and 14.1 <= lo <= 24.2):
            continue
        d0, _ = t_all.query([lo * kk, la])
        if d0 * 111 > 15:
            continue
        if any(math.hypot((la - p["lat"]) * 111, (lo - p["lon"]) * 111 * kk) < 60 for p in picked):
            continue
        db, ib = t_big.query([lo * kk, la])
        nm = bigrows[ib][0] if db * 111 <= 30 else P_["rows"][t_all.query([lo * kk, la])[1]][0]
        nm = PL_NAZWY.get(nm, nm)
        picked.append({"lat": round(la, 3), "lon": round(lo, 3), "nazwa": nm, "ocena": int(oc[j, i]), "opad_mm": round(float(rain[j, i]), 1),
                       "wiatr_ms": round(float(wm[j, i]), 1), "poryw_ms": round(float(gmax[j, i]), 1), "temp_sr": round(float(tm[j, i]), 1),
                       "temp_max": round(float(tmax[j, i]), 1)})
        if len(picked) >= 10:
            break
    pl_mask = (LAT >= 49.0) & (LAT <= 54.9) & (LON >= 14.1) & (LON <= 24.2)
    res = {"status": "OK", "dzien": day.isoformat(), "okno": [f"{a_h:02d}:00", f"{b_h:02d}:00"], "run": m["run"], "model": MODEL,
           "png": key, "bounds": m["bounds"], "legenda": LEGENDA["ocena"], "najlepsze": picked,
           "polska": {"srednia": int(oc[pl_mask].mean()), "udzial_dobrych": round(float((oc[pl_mask] >= 65).mean()), 2)}}
    with open(jp + ".tmp", "w") as fh:
        json.dump(res, fh)
    os.replace(jp + ".tmp", jp)
    return res
