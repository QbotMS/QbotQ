"""Filar 1 -- MPA (Maximal Power Available) tick-po-ticku.

CZYSTA implementacja wg SPEC Filar 1. Bez cf-oddychania, bez mieszania z XSS,
z poprawnym CP (z sygnatury) od poczatku.

Model (W'bal Skiba differential, odwrocony do MPA):
  wydatek:     P > TP  -> wbal -= (P - TP) * dt
  regeneracja: P <= TP -> tau = 546*exp(-0.01*(TP-P)) + 316
                          wbal = W' - (W' - wbal) * exp(-dt/tau)
  MPA(t) = TP + (PP - TP) * (wbal / W')
    wbal=W' (swiezy) -> MPA=PP ; wbal=0 (pusty) -> MPA=TP

Wejscie: lista (ts, power_w) z 1Hz + Signature.
Wyjscie: szereg MPA/wbal + statystyki (min_wbal, itd).

3s smoothing mocy: zgodnie z Karoo SMOOTHED_3S_AVERAGE_POWER i ustaleniem ze
redukuje blad replay. Wlaczalne (domyslnie ON).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
import math

from fitmodel.modelq2.signature import Signature

GAP_THRESHOLD_S = 30.0      # przerwa >= tyle -> traktuj jako postoj (analityczna regen.)
SMOOTH_WINDOW = 3           # sekundy usredniania mocy dla wbal


@dataclass
class MpaResult:
    signature: Signature
    n_ticks: int
    duration_s: float
    min_wbal_j: float
    min_wbal_pct: float
    final_wbal_pct: float
    # szereg do dalszej analizy (przebicia, XSS) -- lista dictow per tick
    series: list = field(default_factory=list)  # {ts, power, power_eff, mpa, wbal, exceed}

    def to_dict(self) -> dict:
        return {
            "signature": self.signature.to_dict(),
            "n_ticks": self.n_ticks,
            "duration_s": round(self.duration_s, 0),
            "min_wbal_kj": round(self.min_wbal_j / 1000.0, 2),
            "min_wbal_pct": round(self.min_wbal_pct, 1),
            "final_wbal_pct": round(self.final_wbal_pct, 1),
        }


def replay_mpa(rows: list, sig: Signature, smooth: bool = True,
               keep_series: bool = True) -> MpaResult:
    """rows: iterowalne (ts, power_w). ts = datetime, power_w = float|None.
    Zwraca MpaResult. NIC nie zapisuje.
    """
    wprime = sig.hie_j
    wbal = wprime                 # start pelny (odpoczety)
    tp = sig.tp_w
    pp = sig.pp_w

    buf: deque = deque(maxlen=SMOOTH_WINDOW)
    prev_ts = None
    n_ticks = 0
    dur = 0.0
    min_wbal = wprime
    series = []

    for ts, power in rows:
        if power is None:
            continue
        if prev_ts is None:
            dt = 1.0
        else:
            dt = (ts - prev_ts).total_seconds()
        if dt <= 0:
            dt = 1.0

        # przerwa -> regeneracja analityczna przez dt, bufor 3s traci sens
        if dt >= GAP_THRESHOLD_S and prev_ts is not None:
            dcp = max(tp - 0.0, 0.0)
            tau = 546.0 * math.exp(-0.01 * dcp) + 316.0
            wbal = wprime - (wprime - wbal) * math.exp(-dt / tau)
            wbal = max(0.0, min(wbal, wprime))
            buf.clear()
            prev_ts = ts
            continue

        prev_ts = ts
        p = float(power)
        buf.append(p)
        pe = (sum(buf) / len(buf)) if smooth else p

        # MPA PRZED wydatkiem tej sekundy (stan "ile mam teraz")
        mpa = tp + (pp - tp) * (wbal / wprime)
        exceed = pe - mpa

        if keep_series:
            series.append({"ts": ts, "power": p, "power_eff": pe,
                           "mpa": mpa, "wbal": wbal, "exceed": exceed})

        # aktualizacja wbal
        if pe > tp:
            wbal -= (pe - tp) * dt
        else:
            tau = 546.0 * math.exp(-0.01 * (tp - pe)) + 316.0
            wbal = wprime - (wprime - wbal) * math.exp(-dt / tau)
        wbal = max(0.0, min(wbal, wprime))

        min_wbal = min(min_wbal, wbal)
        n_ticks += 1
        dur += dt

    return MpaResult(
        signature=sig,
        n_ticks=n_ticks,
        duration_s=dur,
        min_wbal_j=min_wbal,
        min_wbal_pct=100.0 * min_wbal / wprime if wprime > 0 else 0.0,
        final_wbal_pct=100.0 * wbal / wprime if wprime > 0 else 0.0,
        series=series if keep_series else [],
    )
