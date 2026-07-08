"""Filar 5 -- Training Load, Recovery Load, Form (3 systemy: Low/High/Peak).

Model (Banister/Coggan EWMA, jak CTL/ATL, ale 3 osobne strumienie):
  TL_sys(d)  = TL_sys(d-1) + (XSS_sys(d) - TL_sys(d-1)) / tau_tl     (tau_tl ~ 42 dni)
  RL_sys(d)  = RL_sys(d-1) + (XSS_sys(d) - RL_sys(d-1)) / tau_rl     (tau_rl ~ 7 dni)
  Form_sys   = TL_sys - RL_sys

Trzy systemy energetyczne (SPEC Filar 5):
  Low  -- praca <= TP (tlenowa). Dryfuje TP.
  High -- praca nad TP w zakresie VO2 (HIE). Dryfuje HIE.
  Peak -- praca sprinterska blisko PP. Dryfuje PP.

XSS wejsciowy: dostarczany z zewnatrz (xss.py 3-system). Ten modul NIE liczy XSS --
tylko akumuluje go w Training Loads. Czysta separacja.

Walidacja: suma TL (Low+High+Peak) ~ Xert training_load; dryf TP z TL_low ~ Xert progresja.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt

TAU_TL = 42.0    # dni, chroniczne obciazenie (jak CTL)
TAU_RL = 7.0     # dni, ostre obciazenie / recovery (jak ATL)


@dataclass
class LoadState:
    """Stan obciazenia dla jednego systemu (Low/High/Peak) w danym dniu."""
    tl: float = 0.0   # training load (chroniczne)
    rl: float = 0.0   # recovery load (ostre)

    @property
    def form(self) -> float:
        return self.tl - self.rl

    def step(self, xss: float, tau_tl: float = TAU_TL, tau_rl: float = TAU_RL) -> "LoadState":
        """Jeden dzien do przodu z danym XSS. Zwraca NOWY stan (nie mutuje)."""
        tl = self.tl + (xss - self.tl) / tau_tl
        rl = self.rl + (xss - self.rl) / tau_rl
        return LoadState(tl=tl, rl=rl)


@dataclass
class DayLoad:
    """Kompletne obciazenie dnia: 3 systemy."""
    day: dt.date
    low: LoadState
    high: LoadState
    peak: LoadState

    def to_dict(self) -> dict:
        return {
            "day": str(self.day),
            "tl_low": round(self.low.tl, 1), "tl_high": round(self.high.tl, 2),
            "tl_peak": round(self.peak.tl, 3),
            "rl_low": round(self.low.rl, 1), "rl_high": round(self.high.rl, 2),
            "rl_peak": round(self.peak.rl, 3),
            "form_low": round(self.low.form, 1), "form_high": round(self.high.form, 2),
            "form_peak": round(self.peak.form, 3),
            "tl_total": round(self.low.tl + self.high.tl + self.peak.tl, 1),
        }


def build_load_series(xss_by_day: dict, tau_tl: float = TAU_TL,
                      tau_rl: float = TAU_RL) -> list:
    """xss_by_day: {date: (xss_low, xss_high, xss_peak)}. Dni bez wpisu = 0 (odpoczynek).
    Zwraca liste DayLoad dzien-po-dniu (ciagle daty od min do max), z EWMA.
    """
    if not xss_by_day:
        return []
    days = sorted(xss_by_day.keys())
    d0, d1 = days[0], days[-1]
    low = LoadState(); high = LoadState(); peak = LoadState()
    out = []
    d = d0
    while d <= d1:
        xl, xh, xp = xss_by_day.get(d, (0.0, 0.0, 0.0))
        low = low.step(xl, tau_tl, tau_rl)
        high = high.step(xh, tau_tl, tau_rl)
        peak = peak.step(xp, tau_tl, tau_rl)
        out.append(DayLoad(day=d, low=low, high=high, peak=peak))
        d = d + dt.timedelta(days=1)
    return out
