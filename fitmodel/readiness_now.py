"""Gotowosc TERAZ — korekta gotowosci porannej po dzisiejszych jazdach (2026-10-08).

Gotowosc w fitmodel_daily liczy sie z nocy (HRV/RHR/sen), wiec dzisiejszej jazdy w niej nie ma.
Ten modul dokłada kare za KAZDA dzisiejsza jazde, malejaca wykladniczo od jej konca:

    kara_i(t) = K * (XSS_i / CTL) * 0.5 ** (godziny_od_konca_i / HALF_LIFE_H)
    gotowosc_teraz = gotowosc_3d - sum(kara_i)

Kalibracja (dane 06.2025-10.2026, ~500 dni, zmiana readiness_score do nastepnego ranka):
brak jazdy +0.08; XSS/CTL 0.5-1: -0.06; 1-2.5: -0.03; >2.5: -0.21 => jazda ~1 dnia formy
zostawia rano ok. -0.15 wzgledem dnia wolnego. K=0.6 i polowa co 5.5 h daja rano (~16 h) ok. -0.08..-0.13.
Wartosc tuz po jezdzie to ZALOZENIE (HRV mierzone tylko w nocy) — decyzja Michala 2026-10-08.
Liczone na zywo przy kazdym odczycie, nic nie zapisuje do bazy. Front: forma2-data.js (licznik Gotowosc).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

K = 0.6
HALF_LIFE_H = 5.5
FLOOR = 0.02      # kara ponizej tego = pomijalna (nie pokazujemy)
RECOVERED = 0.05  # "wrocisz do porannej" = kara spadnie ponizej tej wartosci


def _g(r, i, key):
    try:
        return r[key]
    except (TypeError, KeyError, IndexError):
        return r[i]


def compute(conn, day: str, now: datetime | None = None) -> dict | None:
    """Gotowosc 'teraz' dla dnia `day` (tylko dzisiaj ma sens). None = brak jazd / danych."""
    now = now or datetime.now(timezone.utc).astimezone()
    if day != now.date().isoformat():
        return None
    f = conn.execute(
        "SELECT COALESCE(readiness_3d, readiness_effective, readiness_score) AS base, ctl_xss AS ctl "
        "FROM qbot_v2.fitmodel_daily WHERE day = %s", (day,)).fetchone()
    if not f:
        return None
    base, ctl = _g(f, 0, "base"), _g(f, 1, "ctl")
    if base is None or not ctl:
        return None
    base, ctl = float(base), float(ctl)
    rows = conn.execute(
        "SELECT t.started_at, GREATEST(COALESCE(t.duration_s,0), COALESCE(m.duration_s,0)) AS dur, "
        "m.xss_total AS xss, t.activity_name AS name "
        "FROM qbot_v2.training_sessions t JOIN qbot_v2.modelq2_ride m ON m.external_id = t.external_id "
        "WHERE t.date = %s AND m.xss_total IS NOT NULL ORDER BY t.started_at",
        (day,),
    ).fetchall()
    rides, total = [], 0.0
    for r in rows:
        st, dur, xss, name = _g(r, 0, "started_at"), _g(r, 1, "dur"), _g(r, 2, "xss"), _g(r, 3, "name")
        if st is None or not xss:
            continue
        end = st + timedelta(seconds=int(dur or 0))
        h = max(0.0, (now - end).total_seconds() / 3600.0)
        p0 = K * float(xss) / ctl
        p = p0 * 0.5 ** (h / HALF_LIFE_H)
        total += p
        rides.append({"name": name, "end": end.astimezone(now.tzinfo).strftime("%H:%M"), "xss": round(float(xss), 1),
                      "hours_since": round(h, 1), "penalty_start": round(-p0, 2), "penalty_now": round(-p, 2)})
    if not rides or total < FLOOR:
        return None
    back_at = now + timedelta(hours=HALF_LIFE_H * max(0.0, math.log2(total / RECOVERED)))
    return {
        "base": round(base, 3),
        "now": round(base - total, 3),
        "penalty": round(-total, 3),
        "rides": rides,
        "recovered_at": back_at.strftime("%H:%M") if back_at.date() == now.date() else "rano",
        "model": {"k": K, "half_life_h": HALF_LIFE_H},
    }
