"""RSRV v2 -- zapas na jazde w stylu Garmin Stamina, tylko z czujnikow (DECISIONS 2026-10-08).

WZORZEC dla QExt2 (com.qext2.primary.engine.ReserveModelV2) -- obie implementacje musza dawac te same liczby
(tests/test_rsrv_v2.py i StatsCalculatorTest w QExt2 maja te same przypadki i wyniki).

Zasada:
- start zawsze 100 %; zapas tylko maleje (bez odbudowy na postoju, bez sztucznej podlogi);
- co sekunde jazdy (ruch + swieza moc) ubywa 1 / T(x), gdzie T(x) = czas do wyczerpania przy intensywnosci
  x = moc / CP (krzywa moc-czas wytrenowanego kolarza; zgodna z rekordami 1-6 h Michala);
- x z mocy usrednionej EMA 20 min (krotkie zrywy liczy W'bal, nie RSRV);
- tetno (jak Garmin): gdy organizm pracuje wyraznie ciezej niz zwykle przy tej mocy, x podbija tetno:
  x_hr = HR_A + HR_B * (HR - RHR) / (LTHR - RHR) (zaleznosc dopasowana do jazd od 04.2026, 10,6 tys. probek),
  liczone tylko powyzej progu szumu HR_DEADBAND i tylko przy realnym pedalowaniu; tetno nigdy nie obniza x;
- kilka jazd jednego dnia sumuje obciazenie (dzienna baza), nowy dzien = 100 %.
Bez: XSS, formy dnia, cisnienia, dryfu, odbudowy na postoju, wpisow recznych.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

TAU_S = 1200.0
HR_A = 0.087
HR_B = 0.683
RHR_BPM = 47.0
HR_DEADBAND = 0.05
HR_MIN_SAMPLES = 300
HR_MIN_VALID = 60
MIN_PEDAL_FRACTION = 0.3
CURVE_X = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2)
CURVE_T_H = (40.0, 22.0, 13.0, 8.0, 4.0, 2.0, 1.0, 0.33)


def rate_per_second(x: float) -> float:
    """Ulamek zapasu zuzywany w 1 s przy intensywnosci x (= moc / CP)."""
    if x <= 0.0:
        return 0.0
    if x <= CURVE_X[0]:
        t_h = CURVE_T_H[0] * (CURVE_X[0] / x) ** 4.6
    elif x >= CURVE_X[-1]:
        t_h = CURVE_T_H[-1]
    else:
        j = 1
        while j < len(CURVE_X) and CURVE_X[j] <= x:
            j += 1
        x0, x1 = CURVE_X[j - 1], CURVE_X[j]
        t0, t1 = CURVE_T_H[j - 1], CURVE_T_H[j]
        t_h = math.exp(math.log(t0) + (math.log(t1) - math.log(t0)) * (x - x0) / (x1 - x0))
    return 1.0 / (t_h * 3600.0)


@dataclass
class ReserveState:
    ema_p: float = 0.0
    ema_h: float = 0.0
    n_p: int = 0
    n_h: int = 0
    load: float = 0.0


def tick(s: ReserveState, power_w: float, hr_bpm: float | None, cp_w: float, lthr_bpm: float,
         hr_max: int = 184, dt_s: float = 1.0) -> None:
    """Jedna sekunda jazdy (ruch + swieza moc; 0 W na zjezdzie tez). Postoj = nie wolac."""
    if cp_w <= 0.0:
        return
    s.n_p += 1
    p = max(0.0, float(power_w))
    s.ema_p += (p - s.ema_p) * (1.0 / TAU_S if s.n_p >= TAU_S else 1.0 / s.n_p)
    if hr_bpm is not None and HR_MIN_VALID <= hr_bpm <= hr_max:
        s.n_h += 1
        s.ema_h += (hr_bpm - s.ema_h) * (1.0 / TAU_S if s.n_h >= TAU_S else 1.0 / s.n_h)
    x = s.ema_p / cp_w
    if s.n_h >= HR_MIN_SAMPLES and s.ema_p > MIN_PEDAL_FRACTION * cp_w and lthr_bpm > RHR_BPM + 10.0:
        x_hr = HR_A + HR_B * (s.ema_h - RHR_BPM) / (lthr_bpm - RHR_BPM)
        if x_hr - HR_DEADBAND > x:
            x = x_hr - HR_DEADBAND
    s.load += rate_per_second(x) * max(0.0, dt_s)


def percent(daily_base_load: float, session_load: float) -> int:
    """RSRV w % (zaokraglenie jak Kotlin roundToInt: polowka w gore)."""
    v = 100.0 * (1.0 - max(0.0, daily_base_load) - max(0.0, session_load))
    return int(min(100, max(0, math.floor(v + 0.5))))
