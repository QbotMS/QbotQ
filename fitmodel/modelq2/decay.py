"""Filar 3+6 -- Signature Decay: dzienna sygnatura podazajaca za forma.

Sygnatura danego dnia NIE jest stala -- oddycha z Training Load (dowod na 272 dniach vs Xert):
  TP  ~ TL_low  r=0.77
  HIE ~ TL_high r=0.50
  PP  ~ HIE_xert r=0.75 (silniejsze niz ~TL_peak 0.65!) i PP bardzo STABILNE (984-1043, +-3%).
Zima TL_low=29 -> TP=238; lato TL_low=80 -> TP=262.

Model dziennej sygnatury:
  TP_day  = z cp_v3 (juz dryfuje z forma) -- override.
  HIE_day = HIE_anchor * clamp(TL_high_day / TL_high_anchor, +-20%)
  PP_day  = PP_anchor  * clamp(HIE_ratio, +-4%)  -- PP idzie za HIE (nie TL_peak), waski clamp,
            bo PP Xerta prawie stale. To naprawia glowny blad walidacji (PP 83W -> male).

Kotwica = punkt odniesienia (dzien z wiarygodna sygnatura). Dryf LAGODNY (TL zmienia sie wolno).
decay bez przebic = ostrozne oszacowanie z formy. HIE/TP zwalidowane (~2.4kJ / ~10W na 272 dniach).
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
HIE_DRIFT_MIN, HIE_DRIFT_MAX = 0.80, 1.20    # +-20% (HIE oddycha z forma)
PP_DRIFT_MIN, PP_DRIFT_MAX = 0.96, 1.04      # +-4% (PP Xerta prawie stale, 984-1043)
TP_DRIFT_MIN, TP_DRIFT_MAX = 0.90, 1.12


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

    # PP idzie za HIE (korelacja 0.75 > TL_peak 0.65), waski clamp bo PP prawie stale
    pp_ratio = _clamp(hie_ratio, PP_DRIFT_MIN, PP_DRIFT_MAX)
    pp = anchor.sig.pp_w * pp_ratio

    # TP: z override (cp_v3) lub dryf za TL_low
    if tp_override is not None:
        tp = tp_override
    else:
        if anchor.tl_low > 0.01:
            tp_ratio = _clamp(load.low.tl / anchor.tl_low, TP_DRIFT_MIN, TP_DRIFT_MAX)
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
            cand = [d for d in tp_by_day if d <= dl.day]
            if cand:
                tp_ov = tp_by_day[max(cand)]
        out[dl.day] = daily_signature(dl, anchor, tp_override=tp_ov)
    return out
