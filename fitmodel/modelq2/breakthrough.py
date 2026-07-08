"""Filar 2 -- wykrywanie przebic (breakthrough) ze serii MPA.

Przebicie = moment gdzie realna moc dotyka/przekracza MPA (SPEC Filar 2).
Ale NIE kazde dotkniecie to przebicie:
  - odfiltruj szum (male przekroczenie, np. <10 W) i artefakty (1-2s skoki miernika),
  - grupuj ciagle fragmenty w ZDARZENIA,
  - prawdziwe przebicie = najsilniejsze zdarzenie (najglebsze wyczerpanie wbal).

Xert bierze zwykl. JEDEN punkt na jazde (green diamond = najlepszy wysilek). Gdy sygnatura
za niska, przebic-kandydatow jest duzo i wbal dobija do 0 (MPA=TP) -> sygnal "podnies sygnature"
(to konsumuje extract.py w kroku 3).
"""
from __future__ import annotations
from dataclasses import dataclass

# progi filtra (dobrane na 6.07: szum ~4W, artefakty 1s; realne ataki 132-296W exceed)
MIN_EXCEED_W = 10.0     # ponizej -> szum, nie przebicie
MIN_DURATION_S = 3.0    # krotsze -> artefakt miernika (skok 1-2s)


@dataclass
class BreakthroughEvent:
    start_ts: object
    duration_s: float
    max_exceed_w: float      # najwieksze przekroczenie MPA [W]
    mean_power_w: float
    min_mpa_w: float         # najnizsze MPA w zdarzeniu (=TP gdy wbal dobil do 0)
    depleted: bool           # czy wbal dobil do zera (MPA doszlo do TP)

    def to_dict(self) -> dict:
        return {"start": str(self.start_ts), "dur_s": round(self.duration_s, 0),
                "max_exceed_w": round(self.max_exceed_w, 0),
                "mean_power_w": round(self.mean_power_w, 0),
                "min_mpa_w": round(self.min_mpa_w, 0), "depleted": self.depleted}


def find_events(series: list, min_exceed_w: float = MIN_EXCEED_W,
                min_duration_s: float = MIN_DURATION_S) -> list:
    """Grupuje ciagle fragmenty exceed>=min_exceed_w w zdarzenia, filtruje krotkie."""
    events = []
    cur = None
    for t in series:
        if t["exceed"] >= min_exceed_w:
            if cur is None:
                cur = {"start": t["ts"], "ticks": 0, "max_ex": 0.0,
                       "psum": 0.0, "mpa_min": 1e9}
            cur["ticks"] += 1
            cur["max_ex"] = max(cur["max_ex"], t["exceed"])
            cur["psum"] += t["power"]
            cur["mpa_min"] = min(cur["mpa_min"], t["mpa"])
        else:
            if cur is not None:
                events.append(cur); cur = None
    if cur is not None:
        events.append(cur)

    out = []
    for e in events:
        if e["ticks"] < min_duration_s:
            continue
        # depleted: MPA min bardzo blisko TP (wbal ~0). TP = mpa gdy wbal=0.
        out.append(BreakthroughEvent(
            start_ts=e["start"], duration_s=float(e["ticks"]),
            max_exceed_w=e["max_ex"], mean_power_w=e["psum"] / e["ticks"],
            min_mpa_w=e["mpa_min"], depleted=False,  # depleted ustawi caller (zna TP)
        ))
    return out


def strongest(events: list) -> BreakthroughEvent | None:
    """Najsilniejsze zdarzenie = kandydat na przebicie (green diamond).
    Kryterium: najwieksze max_exceed (najglebsze wejscie w MPA)."""
    if not events:
        return None
    return max(events, key=lambda e: e.max_exceed_w)


def analyze_ride(series: list, tp_w: float,
                 min_exceed_w: float = MIN_EXCEED_W,
                 min_duration_s: float = MIN_DURATION_S) -> dict:
    """Pelna analiza przebic jazdy. Zwraca liczbe zdarzen, najsilniejsze,
    czy wbal dobil do 0 (sygnal 'sygnatura za niska')."""
    events = find_events(series, min_exceed_w, min_duration_s)
    for e in events:
        e.depleted = e.min_mpa_w <= tp_w + 1.0
    top = strongest(events)
    any_depleted = any(e.depleted for e in events)
    return {
        "n_events": len(events),
        "strongest": top.to_dict() if top else None,
        "any_depleted": any_depleted,   # True -> sygnatura prawdopodobnie za niska
        "events": [e.to_dict() for e in events],
    }
