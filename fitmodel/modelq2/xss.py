"""Filar 4 -- XSS (Xert Strain Score) rozbity na Low/High/Peak.

Liczony z serii MPA (uwzglednia zmeczenie wzgledem MPA). Trzy systemy energetyczne:
  Low  -- praca do progu TP (tlenowa)
  High -- nadwyzka nad TP w zakresie VO2 (srodek zakresu TP..PP)
  Peak -- nadwyzka blisko PP (sprint, gora zakresu)

Kalibracja normalizacji: 1h @ TP swiezo = 100 XSS (Low). Nadwyzka wazona zmeczeniem.
Metoda work-allocation zwalidowana wstepnie vs Xert CSV (6.07: 73.8/10.3/0.4 vs 82.6/7.9/1.5).
Wagi do dostrojenia na benchmarku 759 dni.

Ten modul liczy XSS z activity_record (przez replay MPA). NIE dotyka starego xss_daily
(skazony duplikatami). Czyste zrodlo.
"""
from __future__ import annotations
from dataclasses import dataclass

from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2.mpa import replay_mpa

UNIT = 100.0 / 3600.0    # 1h @ TP swiezo = 100 XSS


@dataclass
class XssSplit:
    low: float
    high: float
    peak: float

    @property
    def total(self) -> float:
        return self.low + self.high + self.peak

    def to_dict(self) -> dict:
        return {"low": round(self.low, 1), "high": round(self.high, 2),
                "peak": round(self.peak, 3), "total": round(self.total, 1)}


def compute_xss(rows: list, sig: Signature, smooth: bool = True) -> XssSplit:
    """Liczy XSS Low/High/Peak dla jazdy. rows: [(ts, power_w)]."""
    res = replay_mpa(rows, sig, smooth=smooth, keep_series=True)
    TP, PP, W = sig.tp_w, sig.pp_w, sig.hie_j
    span = PP - TP
    low = high = peak = 0.0
    for t in res.series:
        p = t["power_eff"]
        wbal = t["wbal"]
        fatigue = 1.0 - (wbal / W) if W > 0 else 0.0
        if fatigue < 0.0:
            fatigue = 0.0
        if p <= TP:
            low += (p / TP) * UNIT
        else:
            low += UNIT  # pelna praca progowa
            over = p - TP
            hp_frac = min(over / span, 1.0) if span > 0 else 0.0
            peak_share = hp_frac ** 2           # sprint rosnie kwadratowo
            over_unit = (over / TP) * UNIT * (1.0 + fatigue)
            high += over_unit * (1.0 - peak_share)
            peak += over_unit * peak_share
    return XssSplit(low=low, high=high, peak=peak)
