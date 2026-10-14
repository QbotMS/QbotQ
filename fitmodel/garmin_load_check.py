"""Walidacja ModelQ obciazeniem Garmina ([GARMIN-DANE] Etap 6, decyzja 2026-10-14).

ModelQ (modelq2_ride.xss_total, z MOCY) vs Garmin (training_sessions.activity_training_load, z TETNA/EPOC).
Garmin liczy obciazenie dla plikow z Karoo (wysylanych jako "Tacx"), wiec mamy pary dla prawie kazdej jazdy.
ModelQ zostaje zrodlem decyzji -- Garmin tylko do porownania.

Model normy (kalibracja na Twoich jazdach z 365 dni, xss_source='power', >15 min, xss>20):
    ln(Garmin / ModelQ) = a + b * ln(godziny)      -- Garmin systematycznie zaniza DLUGIE jazdy
Rozbieznosc = |reszta| > 1.5 SD (ok. 14% jazd, ~2/mies.). Dane 2026-10-14: n=173, korelacja 0.87,
mediana Garmin/ModelQ 0.91, a=-0.03, b=-0.25, SD reszt 0.29.
(Pierwsza propozycja "+-40% od 0.75" byla liczona na nieaktualnym fitmodel_daily.xss_daily -- poprawione.)
Dok.: docs/GARMIN_DANE.md
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

WINDOW_DAYS = 365
MIN_N = 40
K_SD = 1.5
MIN_XSS = 20.0
MIN_DUR_S = 900

SQL_PAIRS = """
SELECT t.external_id, t.date, t.duration_s, t.activity_training_load AS g, m.xss_total AS x
FROM qbot_v2.training_sessions t JOIN qbot_v2.modelq2_ride m ON m.external_id = t.external_id
WHERE t.date BETWEEN %s AND %s AND m.xss_source = 'power'
  AND t.activity_training_load > 0 AND m.xss_total > %s AND t.duration_s > %s
ORDER BY t.date"""

TXT = {
    "wyzej": "Garmin (z tętna) ocenił tę jazdę wyraźnie ciężej niż ModelQ (z mocy): tętno wysoko względem mocy — "
             "zmęczenie, upał, choroba lub stres.",
    "nizej": "Garmin (z tętna) ocenił tę jazdę wyraźnie lżej niż ModelQ (z mocy): tętno nisko względem mocy — "
             "zimno, bardzo spokojna jazda albo sprawdź pas HR.",
}


def _row(r, *keys):
    return tuple(r[k] for k in keys) if isinstance(r, dict) else tuple(r[: len(keys)])


def load_pairs(cur, until: date) -> list[dict]:
    cur.execute(SQL_PAIRS, (until - timedelta(days=WINDOW_DAYS), until, MIN_XSS, MIN_DUR_S))
    out = []
    for r in cur.fetchall():
        eid, d, dur, g, x = _row(r, "external_id", "date", "duration_s", "g", "x")
        out.append({"id": str(eid), "date": d, "h": float(dur) / 3600.0, "g": float(g), "x": float(x)})
    return out


def fit(pairs: list[dict]) -> dict | None:
    """OLS ln(g/x) ~ a + b ln(h). None gdy za malo par."""
    if len(pairs) < MIN_N:
        return None
    xs = [math.log(p["h"]) for p in pairs]
    ys = [math.log(p["g"] / p["x"]) for p in pairs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    a = my - b * mx
    res = [y - (a + b * x) for x, y in zip(xs, ys)]
    sd = math.sqrt(sum(e * e for e in res) / (n - 2))
    return {"a": a, "b": b, "sd": sd, "n": n}


def evaluate(pair: dict, model: dict) -> dict[str, Any]:
    exp_ratio = math.exp(model["a"] + model["b"] * math.log(pair["h"]))
    e = math.log(pair["g"] / pair["x"]) - math.log(exp_ratio)
    flag = "wyzej" if e > K_SD * model["sd"] else "nizej" if e < -K_SD * model["sd"] else None
    return {"garmin": round(pair["g"]), "xss": round(pair["x"]), "garmin_expected": round(pair["x"] * exp_ratio),
            "dev_pct": round((math.exp(e) - 1) * 100), "flag": flag, "text": TXT.get(flag)}


def check_ride(cur, external_id: str, until: date | None = None) -> dict[str, Any] | None:
    """Ocena jednej jazdy; model z 365 dni BEZ tej jazdy. None gdy brak pary lub za malo historii."""
    pairs = load_pairs(cur, until or date.today())
    me = next((p for p in pairs if p["id"] == str(external_id)), None)
    if not me:
        return None
    model = fit([p for p in pairs if p["id"] != str(external_id)])
    return evaluate(me, model) if model else None


def week_line(cur, d0: date, d1: date) -> str | None:
    """Linia do tygodniowego rozliczenia Trenera: sumy obu systemow + rozbiezne jazdy."""
    pairs = load_pairs(cur, d1)
    model = fit(pairs)
    week = [p for p in pairs if d0 <= p["date"] <= d1]
    if not model or not week:
        return None
    gs, xs = sum(p["g"] for p in week), sum(p["x"] for p in week)
    exp_g = sum(evaluate(p, model)["garmin_expected"] for p in week)
    flagged = [(p, evaluate(p, model)) for p in week]
    flagged = [(p, ev) for p, ev in flagged if ev["flag"]]
    line = (f"📊 ModelQ vs Garmin: obciążenie tygodnia {xs:.0f} XSS · Garmin {gs:.0f} "
            f"(przy Twojej normie spodziewane ~{exp_g:.0f}).")
    if flagged:
        line += " Rozbieżne jazdy: " + "; ".join(
            f"{p['date'].strftime('%d.%m')} — tętno {'wysoko' if ev['flag'] == 'wyzej' else 'nisko'} względem mocy ({ev['dev_pct']:+d}%)"
            for p, ev in flagged) + "."
    else:
        line += " Bez rozbieżności."
    return line
