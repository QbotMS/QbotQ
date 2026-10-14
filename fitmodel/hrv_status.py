"""Status HRV QBota ([GARMIN-DANE] Etap 3, decyzja 2026-10-14).

Metoda (Plews i in.; standard monitoringu HRV): na logarytmie HRV nocnego
  srednia 7 nocy (z biezaca)  vs  norma = srednia z 60 POPRZEDNICH nocy +- odchylenie.
  status:  nisko    7d < norma - 1.0 SD
           ponizej  7d < norma - 0.5 SD   (sygnal ostrzegawczy)
           powyzej  7d > norma + 0.5 SD   (informacyjnie, NIE alarm)
           norma    pozostale
Liczone po kolejnych NOCACH z danymi (nie dniach kalendarza); min. 30 nocy w normie.

Walidacja 2026-10-14 (2024..2026, ~950 nocy vs status Garmina): Garmin LOW -> nasze ponizej 52/52,
UNBALANCED -> ponizej 123/154, BALANCED -> norma 596 / powyzej 196 (Garmin nie oznacza "powyzej").
Srednia 7 nocy = weeklyAvg Garmina. Status Garmina (qbot_wellness_daily.garmin_hrv_status) tylko do porownan.
Do gotowosci (ModelQ) NIE wchodzi -- decyzja: najpierw obserwacja. Dok.: docs/GARMIN_DANE.md
"""
from __future__ import annotations

import math
from datetime import date
from typing import Iterable

WIN7 = 7
BASE_N = 60
BASE_MIN = 30
K_BAND = 0.5
K_LOW = 1.0

LABELS = {
    "norma": "w normie",
    "ponizej": "poniżej normy",
    "nisko": "nisko",
    "powyzej": "powyżej normy",
}
LEVEL = {"norma": "good", "powyzej": "good", "ponizej": "warn", "nisko": "bad"}


def _mean(xs):
    return sum(xs) / len(xs)


def _sd(xs):
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def compute_series(nights: Iterable[tuple[date, float]]) -> list[dict]:
    """nights: (data, hrv_ms) posortowane rosnaco. Zwraca dla kazdej nocy:
    date, hrv, avg7, norm, lo, hi (ms) i status (None gdy za malo historii)."""
    pts = [(d, float(h)) for d, h in nights if h is not None and float(h) > 0]
    logs = [math.log(h) for _, h in pts]
    out = []
    for i, (d, h) in enumerate(pts):
        l7 = _mean(logs[max(0, i - WIN7 + 1): i + 1])
        base = logs[max(0, i - BASE_N): i]
        row = {"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "hrv": round(h, 1),
               "avg7": round(math.exp(l7), 1), "norm": None, "lo": None, "hi": None, "status": None}
        if len(base) >= BASE_MIN:
            b, s = _mean(base), _sd(base)
            row.update(norm=round(math.exp(b), 1), lo=round(math.exp(b - K_BAND * s), 1),
                       hi=round(math.exp(b + K_BAND * s), 1))
            if l7 < b - K_LOW * s:
                row["status"] = "nisko"
            elif l7 < b - K_BAND * s:
                row["status"] = "ponizej"
            elif l7 > b + K_BAND * s:
                row["status"] = "powyzej"
            else:
                row["status"] = "norma"
        out.append(row)
    return out


def current(nights: Iterable[tuple[date, float]]) -> dict | None:
    """Ostatnia noc ze statusem + etykieta i poziom (good/warn/bad)."""
    for row in reversed(compute_series(nights)):
        if row["status"]:
            return {**row, "label": LABELS[row["status"]], "level": LEVEL[row["status"]]}
    return None
