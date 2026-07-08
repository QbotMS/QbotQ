"""Filar 3+6 -- Signature Decay: dzienna sygnatura podazajaca za forma.

Sygnatura danego dnia NIE jest stala -- oddycha z Training Load (dowod: TP~TL_low r=0.77,
PP~TL_peak r=0.65, HIE~TL_high r=0.50 na 272 dniach vs Xert). Zima TL_low=29 -> TP=238;
lato TL_low=80 -> TP=262. To Filar 3 Xerta (decay + follow training loads).

Model dziennej sygnatury:
  TP_day  = kotwica_TP * (TL_low_day / TL_low_anchor) ... ale prosciej: TP z cp_v3 (juz dryfuje).
  HIE_day = HIE_anchor * (TL_high_day / TL_high_anchor)   -- proporcja do obciazenia VO2
  PP_day  = PP_anchor  * (TL_peak_day / TL_peak_anchor)   -- proporcja do obciazenia sprint

Kotwica = punkt odniesienia (dzien z wiarygodna sygnatura, np. z przebicia lub seed).
Dryf jest LAGODNY (ograniczony), bo TL zmienia sie wolno (EWMA tau=42).

WAZNE: to daje BAZE dzienna. Przebicia (extract.py) koryguja ja w GORE gdy rider pokaze
wiecej niz baza przewiduje. decay bez przebic = ostrozne oszacowanie z formy.
"""
from __future__ import annotations
from dataclasses import dataclass
import datetime as dt

from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2.training_load import DayLoad, build_load_series


@dataclass
class DecayAnchor:
    """Punkt odniesienia: sygnatura + poziomy TL w dniu kotwicy."""
    day: dt.date
    sig: Signature
    tl_low: float
    tl_high: float
    tl_peak: float


# ograniczniki dryfu (sygnatura nie moze odjechac za daleko od kotwicy bez przebic)
HIE_DRIFT_MIN, HIE_DRIFT_MAX = 0.80, 1.20    # +-20%
PP_DRIFT_MIN, PP_DRIFT_MAX = 0.90, 1.10      # +-10% (PP stabilniejsze)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def daily_signature(load: DayLoad, anchor: DecayAnchor,
                    tp_override: float | None = None) -> Signature:
    """Sygnatura na dany dzien z formy (Training Load) wzgledem kotwicy.
    tp_override: gdy podane (np. cp_v3 danego dnia), uzyj zamiast dryfu TP.
    """
    # HIE dryfuje za TL_high
    if anchor.tl_high > 0.01:
        hie_ratio = _clamp(load.high.tl / anchor.tl_high, HIE_DRIFT_MIN, HIE_DRIFT_MAX)
    else:
        hie_ratio = 1.0
    hie = anchor.sig.hie_j * hie_ratio

    # PP dryfuje za TL_peak
    if anchor.tl_peak > 0.0001:
        pp_ratio = _clamp(load.peak.tl / anchor.tl_peak, PP_DRIFT_MIN, PP_DRIFT_MAX)
    else:
        pp_ratio = 1.0
    pp = anchor.sig.pp_w * pp_ratio

    # TP: z override (cp_v3) lub dryf za TL_low
    if tp_override is not None:
        tp = tp_override
    else:
        if anchor.tl_low > 0.01:
            tp_ratio = _clamp(load.low.tl / anchor.tl_low, 0.90, 1.12)
        else:
            tp_ratio = 1.0
        tp = anchor.sig.tp_w * tp_ratio

    # PP musi byc > TP
    if pp <= tp:
        pp = tp * 3.5
    return Signature(tp_w=tp, hie_j=hie, pp_w=pp)


def build_signature_series(xss_by_day: dict, anchor: DecayAnchor,
                           tp_by_day: dict | None = None) -> dict:
    """Buduje dzienna sygnature dla calego okna z XSS.
    xss_by_day: {date:(low,high,peak)}; tp_by_day: opcjonalnie {date: cp_v3_tp}.
    Zwraca {date: Signature}.
    """
    loads = build_load_series(xss_by_day)
    out = {}
    for dl in loads:
        tp_ov = None
        if tp_by_day:
            # najblizszy cp_v3 <= dzien
            cand = [d for d in tp_by_day if d <= dl.day]
            if cand:
                tp_ov = tp_by_day[max(cand)]
        out[dl.day] = daily_signature(dl, anchor, tp_override=tp_ov)
    return out
