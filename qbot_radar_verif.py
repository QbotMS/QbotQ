"""Sprawdzalnosc radaru (Pogoda, etap 2). Dok.: docs/POGODA_SPRAWDZALNOSC.md (sekcja Radar)

Przy kazdej nowej klatce T: dla wyprzedzen LEADS porownanie prognozy wydanej o T-L (najnowszy obraz z T-L przesuniety wg
ruchu z T-L -- dokladnie jak karta 'u Ciebie', qbot_radar.nowcast_point) z tym, co radar pokazal o T. Siatka PTS co 0,25 st
nad Polska (~1000 punktow). 'Pada' = >= 50% kola wokol punktu ma >= DBZ_RAIN (prognoza: kolo 2 km + 0,08 km/min, pomiar 2 km).
Odniesienie: 'bez przesuwania' (persystencja) = obraz z T-L bez ruchu. Miara: CSI = trafione / (trafione + falszywe + przegapione).
Horyzont radaru = najdluzsze wyprzedzenie, gdzie CSI radaru >= HORYZONT_CSI i radar >= persystencja (min. MIN_PRZYP przypadkow).
"""
from __future__ import annotations

import datetime as dt
import json
import os

import numpy as np

import qbot_radar as R

LEADS = (10, 20, 30, 45, 60, 90, 120)
PTS = [(float(la), float(lo)) for la in np.arange(49.125, 54.9, 0.25) for lo in np.arange(14.25, 24.2, 0.25)]
HORYZONT_CSI = 0.3
MIN_PRZYP = 300
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.pogoda_radar_verif (ts timestamptz, lead smallint, hit int, fa int, miss int, cn int,
  p_hit int, p_fa int, p_miss int, p_cn int, PRIMARY KEY (ts, lead))"""


def mot_file(ts: dt.datetime) -> str:
    return os.path.join(R.CACHE, f"motion_{ts:%Y%m%dT%H%M}.json")


def ensure(cur) -> None:
    cur.execute(DDL)


def _pada(a, col, row, r_px):
    v = R._disk(a, col, row, r_px)
    f = v[np.isfinite(v)]
    if f.size == 0:
        return None
    return bool((f >= R.DBZ_RAIN).mean() >= 0.5)


def save_motions() -> int:
    """Pole ruchu dla kazdej klatki z >= 30 min historii, ktora go jeszcze nie ma (tez wstecz po starcie)."""
    n = 0
    for t in R.frames():
        if os.path.exists(mot_file(t)):
            continue
        m = R.motion(t1=t)
        if m.get("status") in ("OK", "BRAK_OPADU") and m.get("t1", "").startswith(t.isoformat()[:16]):
            with open(mot_file(t) + ".tmp", "w") as fh:
                json.dump(m, fh)
            os.replace(mot_file(t) + ".tmp", mot_file(t)); n += 1
    keep = {mot_file(t) for t in R.frames()}
    for f in os.listdir(R.CACHE):
        p = os.path.join(R.CACHE, f)
        if f.startswith("motion_") and f.endswith(".json") and p not in keep:
            os.remove(p)
    return n


def evaluate(cur, T: dt.datetime) -> dict:
    fr = set(R.frames())
    if T not in fr:
        return {}
    obs, done = None, {}
    for L in LEADS:
        t0 = T - dt.timedelta(minutes=L)
        if t0 not in fr or not os.path.exists(mot_file(t0)):
            continue
        cur.execute("SELECT 1 FROM qbot_v2.pogoda_radar_verif WHERE ts=%s AND lead=%s", (T, L))
        if cur.fetchone():
            continue
        if obs is None:
            obs = R.load(T)
        src = R.load(t0)
        with open(mot_file(t0)) as fh:
            mot = json.load(fh)
        c = [0] * 8
        for la, lo in PTS:
            col, row = R.to_px(la, lo)
            kmpx = R.ground_km_per_px(la)
            o = _pada(obs, col, row, 2.0 / kmpx)
            p = _pada(src, col, row, 2.0 / kmpx)
            if o is None or p is None:
                continue
            lm = R.local_motion(la, lo, mot) if mot.get("vec") else None
            f = _pada(src, col - lm["vx"] * L, row - lm["vy"] * L, (2.0 + 0.08 * L) / kmpx) if lm else p
            if f is None:
                continue
            c[0 if f and o else 1 if f else 2 if o else 3] += 1
            c[4 + (0 if p and o else 1 if p else 2 if o else 3)] += 1
        cur.execute("""INSERT INTO qbot_v2.pogoda_radar_verif VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (T, L, *c))
        done[L] = c
    return done


def evaluate_new(cur) -> dict:
    ensure(cur)
    save_motions()
    out = {}
    for T in R.frames():
        d = evaluate(cur, T)
        if d:
            out[T.strftime("%H:%M")] = {k: v[0] for k, v in d.items()}
    return out


def summary(cur, dni: int = 7) -> dict:
    ensure(cur)
    cur.execute("""SELECT lead, sum(hit) AS h, sum(fa) AS f, sum(miss) AS m, sum(cn) AS cn, sum(p_hit) AS ph, sum(p_fa) AS pf,
                          sum(p_miss) AS pm, count(*) AS n, min(ts) AS od, max(ts) AS do_
                   FROM qbot_v2.pogoda_radar_verif WHERE ts >= now() - (%s || ' days')::interval GROUP BY lead ORDER BY lead""", (str(dni),))
    rows = [list(r.values()) if isinstance(r, dict) else list(r) for r in cur.fetchall()]
    wyn, hor, od, do = [], None, None, None
    for L, h, f, m, cn, ph, pf, pm, n, a, b in rows:
        den, pden = h + f + m, ph + pf + pm
        csi = round(h / den, 2) if den else None
        pcsi = round(ph / pden, 2) if pden else None
        wyn.append({"lead_min": L, "csi": csi, "csi_bez_ruchu": pcsi, "trafione": h, "falszywe": f, "przegapione": m,
                    "przypadkow_z_opadem": den, "porownan": n,
                    "pod": round(h / (h + m), 2) if h + m else None, "far": round(f / (h + f), 2) if h + f else None})
        od = a if od is None or (a and a < od) else od
        do = b if do is None or (b and b > do) else do
        if den >= MIN_PRZYP and csi is not None and csi >= HORYZONT_CSI and (pcsi is None or csi >= pcsi):
            hor = L
    wystarczy = any(w["przypadkow_z_opadem"] >= MIN_PRZYP for w in wyn)
    return {"status": "OK", "dni": dni, "wyniki": wyn, "horyzont_min": hor if wystarczy else None,
            "horyzont_domyslny": 120, "prog_csi": HORYZONT_CSI, "min_przypadkow": MIN_PRZYP,
            "okres": [od.isoformat() if od else None, do.isoformat() if do else None]}
