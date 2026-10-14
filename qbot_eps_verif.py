"""Sprawdzalnosc SZANSY opadu (zespol ICON-EU-EPS) vs radar. Dok.: docs/POGODA_SPRAWDZALNOSC.md (sekcja Szansa)

Co godzine H (gdy radar ma >= 10 klatek z [H-1 h, H]): obserwacja w pikselu siatki mapy (6 km) = srednia intensywnosc z radaru
(Marshall-Palmer, blok 4x4 pikseli radaru) >= OBS_PROG mm/h. Prognoza = szansa z archiwum zespolu (CACHE/eps_arch/<run>/prob_<krok>.npz,
3 doby) dla wszystkich przebiegow, ktore maja krok o waznosci H; wyprzedzenie = H - przebieg. Tylko obszar Polski z pokryciem radaru.
Zapis: liczebnosc i liczba opadow w przedzialach szansy (co 10%) per (H, wyprzedzenie). Podsumowanie: krzywa wiarygodnosci (szansa vs
czestosc), Brier i BSS wzgledem klimatologii probki, wg grup wyprzedzenia 0-12 / 12-24 / 24-48 / 48-60 h.
"""
from __future__ import annotations

import datetime as dt
import os
import re

import numpy as np

import qbot_pogoda_map as M
import qbot_radar as R

OBS_PROG = 0.2
BINS = np.linspace(0, 1, 11)
GRUPY = ((0, 12), (12, 24), (24, 48), (48, 61))
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.pogoda_eps_verif (ts timestamptz, lead_h smallint, bin smallint, n int, n_obs int,
  sum_p double precision, PRIMARY KEY (ts, lead_h, bin))"""
ARCH = os.path.join(M.CACHE, "eps_arch")


def ensure(cur):
    cur.execute(DDL)


def _obs(H: dt.datetime):
    fr = [t for t in R.frames() if H - dt.timedelta(hours=1) < t <= H]
    if len(fr) < 10:
        return None
    acc = None; cnt = None
    for t in fr:
        a = R.load(t)
        rr = np.where(np.isfinite(a), np.where(a >= R.DBZ_SHOW, (10 ** (a / 10.0) / 200.0) ** (1 / 1.6), 0.0), np.nan)
        acc = np.nan_to_num(rr) if acc is None else acc + np.nan_to_num(rr)
        cnt = np.isfinite(rr).astype(float) if cnt is None else cnt + np.isfinite(rr)
    mean = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    f = int(round(M.PX_M / R.PX_M)); hh, ww = min(mean.shape[0] // f, M.H), min(mean.shape[1] // f, M.W)
    blk = mean[:hh * f, :ww * f].reshape(hh, f, ww, f)
    ok = np.isfinite(blk).all(axis=(1, 3))
    out = np.full((M.H, M.W), np.nan, np.float32)
    out[:hh, :ww] = np.where(ok, np.nanmean(blk, axis=(1, 3)), np.nan)
    LON, LAT = M._pix_latlon()
    out[~((LAT >= 49.0) & (LAT <= 54.9) & (LON >= 14.1) & (LON <= 24.2))] = np.nan
    return out


def evaluate_hour(cur, H: dt.datetime) -> dict:
    ensure(cur)
    cur.execute("SELECT 1 FROM qbot_v2.pogoda_eps_verif WHERE ts=%s LIMIT 1", (H,))
    if cur.fetchone():
        return {}
    if not os.path.isdir(ARCH):
        return {}
    obs = None; done = {}
    for run in sorted(os.listdir(ARCH)):
        if not re.fullmatch(r"\d{10}", run):
            continue
        r0 = dt.datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
        lead = int(round((H - r0).total_seconds() / 3600))
        p = os.path.join(ARCH, run, f"prob_{lead:03d}.npz")
        if lead < 1 or not os.path.exists(p):
            continue
        if obs is None:
            obs = _obs(H)
            if obs is None:
                return {"status": "MALO_KLATEK"}
        with np.load(p) as z:
            pr = z["p"].astype(np.float32)
        m = np.isfinite(obs)
        pv, ov = pr[m], (obs[m] >= OBS_PROG)
        b = np.clip(np.digitize(pv, BINS) - 1, 0, 9)
        for k in range(10):
            sel = b == k
            n = int(sel.sum())
            if n:
                cur.execute("INSERT INTO qbot_v2.pogoda_eps_verif VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (H, lead, k, n, int(ov[sel].sum()), float(pv[sel].sum())))
        done[lead] = int(m.sum())
    return done


def tick(cur) -> dict:
    """Ocena ostatnich pelnych godzin, ktore radar jeszcze pokrywa (wolane przy nowej klatce radaru)."""
    fr = R.frames()
    if not fr:
        return {}
    out = {}
    H = fr[-1].replace(minute=0, second=0, microsecond=0)
    for k in range(0, 2):
        h = H - dt.timedelta(hours=k)
        d = evaluate_hour(cur, h)
        if d:
            out[h.strftime("%H UTC")] = d
    return out


def summary(cur, dni: int = 14) -> dict:
    ensure(cur)
    cur.execute("""SELECT lead_h AS l, bin AS b, sum(n) AS n, sum(n_obs) AS o, sum(sum_p) AS sp, min(ts) AS od, max(ts) AS do_, count(DISTINCT ts) AS godz
                   FROM qbot_v2.pogoda_eps_verif WHERE ts >= now() - (%s || ' days')::interval GROUP BY lead_h, bin""", (str(dni),))
    rows = [list(r.values()) if isinstance(r, dict) else list(r) for r in cur.fetchall()]
    if not rows:
        return {"status": "BRAK_DANYCH", "dni": dni}
    grupy = []
    for a, b in GRUPY:
        sel = [r for r in rows if a < r[0] <= b] if a else [r for r in rows if r[0] <= b]
        if not sel:
            continue
        kr = []
        N = sum(r[2] for r in sel); O = sum(r[3] for r in sel)
        brier = 0.0
        for k in range(10):
            rs = [r for r in sel if r[1] == k]
            n = sum(r[2] for r in rs); o = sum(r[3] for r in rs); sp = sum(r[4] for r in rs)
            if n:
                pm = sp / n
                kr.append({"przedzial": f"{k * 10}-{k * 10 + 10}%", "szansa_sr": round(pm, 3), "czestosc": round(o / n, 3), "n": n})
                brier += o * (1 - pm) ** 2 + (n - o) * pm ** 2      # przyblizenie srodkiem przedzialu
        clim = O / N if N else 0
        bs = brier / N if N else None; bsc = clim * (1 - clim)
        grupy.append({"wyprzedzenie_h": f"{a}-{b if b != 61 else 60}", "n": N, "czestosc_opadu": round(clim, 3), "brier": round(bs, 4) if bs is not None else None,
                      "bss": round(1 - bs / bsc, 2) if bs is not None and bsc > 0 else None, "krzywa": kr})
    return {"status": "OK", "dni": dni, "godzin": max(r[7] for r in rows), "grupy": grupy, "prog_obs_mmh": OBS_PROG,
            "okres": [min(r[5] for r in rows).isoformat(), max(r[6] for r in rows).isoformat()]}
