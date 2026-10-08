# -*- coding: utf-8 -*-
"""Blok PREDKOSCI raportu z jazdy (2026-10-06).

Liczy z rekordow FIT tej jazdy:
- srednia NETTO (dystans / czas ruchu) i BRUTTO (dystans / czas calkowity z postojami),
- czas ruchu / calkowity / postojow,
- ODNIESIENIE do WLASNEJ tabeli predkosci uzytkownika (model czasu przejazdu v2,
  qbot_route_time_tools.SPEED_TABLE: nawierzchnia x nachylenie, poziomy normalny/sport/wyscig),
  policzone NA TYM SAMYM SLADZIE: nachylenie oknem 200 m z wysokosci FIT, nawierzchnia z r["scat"]
  (kategoria 1 = twarda -> paved, 2..5 -> unpaved, brak -> srednia paved/unpaved jak w modelu),
- to samo per klasa nawierzchni,
- postoje realne vs automatyczne postoje modelu (mikro + krotkie, bez dlugich).
Wiatr NIE jest w modelu (tabela jest z jazd mieszanych) -- odchylka moze z niego wynikac.
Czas ruchu = liczba rekordow z predkoscia > 0.5 m/s (zgodnie z load.dur_moving_s).
"""
from __future__ import annotations

MOVE_MPS = 0.5
MODES = ("normalny", "sport", "wyscig")


def _cls(scat):
    if scat is None:
        return None
    try:
        return "paved" if int(scat) == 1 else "unpaved"
    except (TypeError, ValueError):
        return None


def _grades(D, A, half=100.0):
    """Nachylenie [%] per rekord: (alt(d+100) - alt(d-100)) / odleglosc, okno 200 m."""
    n = len(D)
    out = [0.0] * n
    lo = hi = 0
    for i in range(n):
        while lo < i and D[i] - D[lo] > half:
            lo += 1
        if hi < i:
            hi = i
        while hi + 1 < n and D[hi + 1] - D[i] <= half:
            hi += 1
        dd = D[hi] - D[lo]
        if dd >= 50.0 and A[hi] is not None and A[lo] is not None:
            g = (A[hi] - A[lo]) / dd * 100.0
            out[i] = max(-25.0, min(25.0, g))
    return out


def _level(v, ref):
    """Slowny poziom wzgledem Twoich progow normalny/sport/wyscig."""
    n, s, w = ref.get("normalny"), ref.get("sport"), ref.get("wyscig")
    if not (v and n):
        return None
    if v < n * 0.95:
        return "ponizej Twojego normalnego tempa"
    if s is None or v < (n + s) / 2.0:
        return "Twoje normalne tempo"
    if w is None or v < (s + w) / 2.0:
        return "Twoje tempo sportowe"
    return "Twoje tempo wyscigowe"


def speed_block(recs):
    try:
        import qbot_route_time_tools as RT
    except ModuleNotFoundError:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import qbot_route_time_tools as RT

    if not recs or len(recs) < 60:
        return {"value": None, "tier": "C", "source": "fit", "reason": "za malo rekordow"}

    D = [float(r.get("dist") or 0.0) for r in recs]
    A = [r.get("alt") for r in recs]
    last = None
    for i, a in enumerate(A):
        if a is None:
            A[i] = last
        else:
            last = a
    first = next((a for a in A if a is not None), None)
    A = [a if a is not None else first for a in A]
    G = _grades(D, A)

    dist_m = D[-1] - D[0] if D[-1] > D[0] else D[-1]
    moving_s = sum(1 for r in recs if (r.get("spd") or 0) > MOVE_MPS)
    elapsed_s = int(recs[-1]["sec"] - recs[0]["sec"])
    if dist_m <= 0 or moving_s <= 0 or elapsed_s <= 0:
        return {"value": None, "tier": "C", "source": "fit", "reason": "brak dystansu/czasu"}

    exp_h = {m: 0.0 for m in MODES}
    per = {}  # klasa -> dist_m, mov_s, exp_norm_h
    known_m = 0.0
    for i in range(1, len(recs)):
        dm = D[i] - D[i - 1]
        moving = (recs[i].get("spd") or 0) > MOVE_MPS
        c = _cls(recs[i].get("scat"))
        key = c or "nieznana"
        b = per.setdefault(key, {"dist_m": 0.0, "mov_s": 0, "exp_h": 0.0})
        if moving:
            b["mov_s"] += 1
        if dm <= 0 or dm > 200:
            continue
        b["dist_m"] += dm
        if c:
            known_m += dm
        for m in MODES:
            v = RT.segment_speed_kmh(G[i], c, m)
            if v and v > 0:
                exp_h[m] += (dm / 1000.0) / v
                if m == "normalny":
                    b["exp_h"] += (dm / 1000.0) / v

    dist_km = dist_m / 1000.0
    v_net = dist_km / (moving_s / 3600.0)
    v_gross = dist_km / (elapsed_s / 3600.0)
    model = {m: round(dist_km / exp_h[m], 1) for m in MODES if exp_h[m] > 0}
    vs = {m: round((v_net / model[m] - 1.0) * 100.0) for m in model}

    stops = RT.stops_minutes(dist_km, moving_h=exp_h.get("normalny") or None)
    stop_model_min = stops["mikro_min"] + stops["krotkie_min"]
    stop_real_min = max(0.0, (elapsed_s - moving_s) / 60.0)
    gross_model = None
    if exp_h.get("normalny"):
        gross_model = round(dist_km / (exp_h["normalny"] + stop_model_min / 60.0), 1)

    labels = {"paved": "asfalt / twarda", "unpaved": "szuter / teren", "nieznana": "nieznana"}
    by_surface = []
    for k in ("paved", "unpaved", "nieznana"):
        b = per.get(k)
        if not b or b["dist_m"] < 500 or b["mov_s"] < 60:
            continue
        kmh = (b["dist_m"] / 1000.0) / (b["mov_s"] / 3600.0)
        mk = ((b["dist_m"] / 1000.0) / b["exp_h"]) if b["exp_h"] > 0 else None
        by_surface.append({
            "klasa": labels[k],
            "dist_km": round(b["dist_m"] / 1000.0, 1),
            "kmh": round(kmh, 1),
            "model_kmh": round(mk, 1) if mk else None,
            "roznica_pct": round((kmh / mk - 1.0) * 100.0) if mk else None,
        })

    cover = round(100.0 * known_m / dist_m, 1) if dist_m else 0.0
    value = {
        "netto_kmh": round(v_net, 1),
        "brutto_kmh": round(v_gross, 1),
        "moving_s": int(moving_s),
        "elapsed_s": int(elapsed_s),
        "stop_s": int(max(0, elapsed_s - moving_s)),
        "model_kmh": model,
        "vs_model_pct": vs,
        "poziom": _level(v_net, model),
        "postoje_min": round(stop_real_min, 1),
        "postoje_model_min": round(stop_model_min, 1),
        "brutto_model_kmh": gross_model,
        "by_surface": by_surface,
        "nawierzchnia_znana_pct": cover,
        "uwaga": ("Model = Twoja tabela predkosci (nawierzchnia x nachylenie 200 m) przylozona do tego sladu; "
                  "bez wiatru. Brutto modelu = jazda w tempie normalnym + typowe krotkie postoje (bez dlugich)."),
    }
    return {"value": value, "tier": "A", "source": "fit + tabela predkosci (model czasu v2)"}
