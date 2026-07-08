"""Filar 3+6 -- Signature Decay: dzienna sygnatura podazajaca za forma.

Sygnatura danego dnia NIE jest stala -- oddycha z Training Load (dowod na 272 dniach vs Xert):
  TP  ~ TL_low  r=0.77
  HIE ~ TL_high r=0.50
  PP  ~ HIE_xert r=0.75 (silniejsze niz ~TL_peak 0.65!) i PP bardzo STABILNE (984-1043, +-3%).
Zima TL_low=29 -> TP=238; lato TL_low=80 -> TP=262.

Model dziennej sygnatury:
  TP_day  = TP_anchor - 0.15*age + 0.66*(CTL_day - CTL_anchor)  -- dryf za NASZYM CTL (bez v1).
  HIE_day = HIE_anchor * clamp(TL_high_day / TL_high_anchor, +-20%)
  PP_day  = PP_anchor  * clamp(HIE_ratio, +-4%)  -- PP idzie za HIE (nie TL_peak), waski clamp,
            bo PP Xerta prawie stale. To naprawia glowny blad walidacji (PP 83W -> male).

Kotwica = punkt odniesienia (dzien z wiarygodna sygnatura). Dryf LAGODNY (TL zmienia sie wolno).
WIELE KOTWIC: dla kazdego dnia wybieramy najblizsza czasowo kotwice -> mniejszy dryf, mniejszy blad
na duzych dystansach (styczen 2025 z jedna letnia kotwica miel 5.9kJ bledu HIE).
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
    ctl: float = 0.0


# ograniczniki dryfu (sygnatura nie moze odjechac za daleko od kotwicy bez przebic)
HIE_DRIFT_MIN, HIE_DRIFT_MAX = 0.80, 1.20    # +-20% (HIE oddycha z forma)
PP_DRIFT_MIN, PP_DRIFT_MAX = 0.93, 1.07      # miekki bezpiecznik (PP Xerta 984-1043)
PP_K = 0.10                                   # tlumienie: PP dryfuje 10% amplitudy HIE (PP prawie stale, jak Xert sd~15)
TP_DRIFT_MIN, TP_DRIFT_MAX = 0.90, 1.12
TP_K_DRIFT = 0.66                             # W na 1 pkt CTL (dryf TP miedzy kotwicami, jak cp_v3)
TP_DECAY_W_PER_DAY = 0.15                     # zanik kotwicy bez treningu (jak cp_v3)


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

    # PP dryfuje LAGODNIE za HIE (tlumiona amplituda), symetrycznie wokol kotwicy -- BEZ podlogi.
    # HIE waha ~+-12%, PP Xerta ~+-2-3% -> tlumienie PP_K=0.2. Wczesniej twardy clamp 0.96
    # przycinal wiekszosc dni do dolnej krawedzi (efekt "podloga + szpilki") -- poprawione.
    pp_drift = 1.0 + PP_K * (hie_ratio - 1.0)
    pp_ratio = _clamp(pp_drift, PP_DRIFT_MIN, PP_DRIFT_MAX)
    pp = anchor.sig.pp_w * pp_ratio

    # TP dryfuje za NASZYM CTL wokol kotwicy (odtworzenie cp_v3, ale BEZ v1 -- CTL z wlasnego XSS).
    # tp_override zostaje tylko dla wstecznej kompatybilnosci; produkcja MQ2 go NIE podaje.
    if tp_override is not None:
        tp = tp_override
    else:
        ctl_day = load.low.tl + load.high.tl + load.peak.tl
        age = abs((load.day - anchor.day).days)
        tp = anchor.sig.tp_w - TP_DECAY_W_PER_DAY * age + TP_K_DRIFT * (ctl_day - anchor.ctl)
        tp = _clamp(tp, anchor.sig.tp_w * TP_DRIFT_MIN, anchor.sig.tp_w * TP_DRIFT_MAX)

    # PP musi byc > TP
    if pp <= tp:
        pp = tp * 3.5
    return Signature(tp_w=tp, hie_j=hie, pp_w=pp)


def build_signature_series(xss_by_day: dict, anchor: DecayAnchor,
                           tp_by_day: dict | None = None) -> dict:
    """Buduje dzienna sygnature dla calego okna z JEDNA kotwica.
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


def make_anchor(day: dt.date, sig: Signature, loads_by_day: dict) -> DecayAnchor:
    """Tworzy kotwice z dnia + poziomow TL tego dnia (z gotowej mapy loads)."""
    dl = loads_by_day[day]
    return DecayAnchor(day=day, sig=sig, tl_low=dl.low.tl, tl_high=dl.high.tl,
                       tl_peak=dl.peak.tl, ctl=dl.low.tl + dl.high.tl + dl.peak.tl)


def build_signature_series_multi(xss_by_day: dict, anchors: list,
                                 tp_by_day: dict | None = None) -> dict:
    """Buduje dzienna sygnature z WIELOMA kotwicami. Dla kazdego dnia uzywa
    kotwicy NAJBLIZSZEJ czasowo (min |dzien - kotwica|). Zmniejsza dryf na duzych
    dystansach. anchors: lista DecayAnchor.
    """
    if not anchors:
        return {}
    loads = build_load_series(xss_by_day)
    anchor_days = [a.day for a in anchors]
    out = {}
    for dl in loads:
        # najblizsza kotwica w czasie
        best_i = min(range(len(anchors)), key=lambda i: abs((dl.day - anchor_days[i]).days))
        anchor = anchors[best_i]
        tp_ov = None
        if tp_by_day:
            cand = [d for d in tp_by_day if d <= dl.day]
            if cand:
                tp_ov = tp_by_day[max(cand)]
        out[dl.day] = daily_signature(dl, anchor, tp_override=tp_ov)
    return out
