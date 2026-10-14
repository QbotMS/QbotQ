"""Sygnal "Organizm pod obciazeniem" z temperatury skory ([GARMIN-DANE] Etap 4, decyzja 2026-10-14).

Temperatura skory z Garmina (qbot_wellness_daily.skin_temp_dev_c) jest JUZ odchyleniem od normy
Garmina (srednia 0.0, typowo +-0.25 C) -- wlasnej normy nie liczymy.
Sama temperatura bywa falszywym alarmem (ciepla sypialnia), niska nic nie znaczy -> sygnal LACZONY:
    temp >= +0.4 C  ORAZ  (HRV tej nocy >= 5 ms ponizej normy  LUB  tetno spocz. >= +3 bpm)
    norma = srednia z 60 poprzednich nocy z danymi (min. 30).
Dane 2025-05..2026-10: noc >= +0.4 podwaja szanse spadku HRV (42% vs 21%), RHR +1.3;
regula laczona ~1x/mies., czesto po ciezkich jazdach (31.08, 05.10.2026).
NIE wchodzi do gotowosci ModelQ (decyzja: obserwacja -- TODO Etap 3b). Dok.: docs/GARMIN_DANE.md
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

TEMP_MIN = 0.4
HRV_DROP_MS = 5.0
RHR_RISE_BPM = 3.0
BASE_N = 60
BASE_MIN = 30

SQL = ("SELECT date, skin_temp_dev_c, hrv_ms, resting_hr_bpm FROM qbot_v2.qbot_wellness_daily "
       "WHERE source = 'garmin' AND date BETWEEN %s AND %s ORDER BY date")


def _pl(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if len(xs) >= BASE_MIN else None


def evaluate(rows: list[tuple]) -> dict[str, Any] | None:
    """rows: (data, temp, hrv, rhr) rosnaco po dacie. Ocena OSTATNIEJ nocy z temperatura."""
    rows = list(rows)
    idx = next((i for i in range(len(rows) - 1, -1, -1) if rows[i][1] is not None), None)
    if idx is None:
        return None
    d, t, h, r = rows[idx]
    base = rows[max(0, idx - BASE_N): idx]
    hn, rn = _mean([x[2] for x in base]), _mean([x[3] for x in base])
    t = float(t)
    reasons = []
    if h is not None and hn is not None and float(h) <= hn - HRV_DROP_MS:
        reasons.append(f"HRV {float(h):.0f} ms (norma {hn:.0f})")
    if r is not None and rn is not None and float(r) >= rn + RHR_RISE_BPM:
        reasons.append(f"tętno spocz. {float(r):.0f} (norma {rn:.0f})")
    signal = t >= TEMP_MIN and bool(reasons)
    sign = "+" if t > 0 else ""
    out = {"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "temp": round(t, 1),
           "hrv": float(h) if h is not None else None, "hrv_norm": round(hn, 1) if hn else None,
           "rhr": float(r) if r is not None else None, "rhr_norm": round(rn, 1) if rn else None,
           "signal": signal, "reasons": reasons, "text": None}
    if signal:
        out["text"] = (f"Organizm pod obciążeniem: temp. skóry {sign}{_pl(t)} °C, " + ", ".join(reasons)
                       + " — możliwa choroba, przeciążenie, alkohol lub upał. Rozważ lżejszy dzień.")
    return out


def load_rows(cur, today: date, days: int = 75) -> list[tuple]:
    """Wiersze (data, temp, hrv, rhr) z bazy; kursor z wierszami-krotkami lub slownikami."""
    cur.execute(SQL, (today - timedelta(days=days), today))
    out = []
    for x in cur.fetchall():
        if isinstance(x, dict):
            out.append((x["date"], x["skin_temp_dev_c"], x["hrv_ms"], x["resting_hr_bpm"]))
        else:
            out.append(tuple(x[:4]))
    return out


def today_signal(cur, today: date) -> dict[str, Any] | None:
    """Ocena tylko gdy ostatnia noc z temperatura to DZIS (swieze dane) -- do porannej wiadomosci."""
    ev = evaluate(load_rows(cur, today))
    return ev if ev and ev["date"] == today.isoformat() else None
