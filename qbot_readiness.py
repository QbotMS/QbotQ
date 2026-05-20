#!/usr/bin/env python3
"""Shared readiness rules for QBot reports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Readiness:
    color: str
    verdict: str
    short: str
    note: str
    score: int
    hrv_delta: float | None


def _num(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_readiness(
    *,
    hrv=None,
    hrv_norm=None,
    body_battery=None,
    sleep_hours=None,
    form=None,
    illness_context: bool = False,
    resting_hr=None,
) -> Readiness:
    """Evaluate training readiness from the same rules in every report."""
    hrv_v = _num(hrv)
    norm_v = _num(hrv_norm)
    bb_v = _num(body_battery)
    sleep_v = _num(sleep_hours)
    form_v = _num(form)
    resting_v = _num(resting_hr)
    hrv_delta = round(hrv_v - norm_v, 1) if hrv_v is not None and norm_v is not None else None

    if illness_context and hrv_delta is not None and hrv_delta < -5:
        return Readiness(
            color="czerwona",
            verdict="ODPUSC",
            short="dziś bez mocnej pracy",
            note="HRV jest ponad 5 pkt poniżej normy przy kontekście choroby lub zmęczenia: trening byłby nadmiernym ryzykiem.",
            score=-4,
            hrv_delta=hrv_delta,
        )

    if bb_v is not None and bb_v < 30:
        return Readiness(
            color="czerwona",
            verdict="ODPUSC",
            short="dziś bez mocnej pracy",
            note="Body Battery rano poniżej 30: priorytetem jest regeneracja, nie dokładanie obciążenia.",
            score=-3,
            hrv_delta=hrv_delta,
        )

    score = 0
    if sleep_v is not None:
        score += 1 if sleep_v >= 7 else (-1 if sleep_v < 6 else 0)
    if hrv_delta is not None:
        score += 1 if hrv_delta >= 0 else (-2 if hrv_delta < -5 else -1)
    if bb_v is not None:
        score += 1 if bb_v >= 70 else (-1 if bb_v < 45 else 0)
    if form_v is not None:
        score += 1 if form_v >= 0 else (-1 if form_v < -15 else 0)
    if illness_context:
        score -= 1
    if resting_v is not None and illness_context:
        score -= 1

    if score >= 2:
        return Readiness(
            color="zielona",
            verdict="TAK",
            short="normalny trening",
            note="Brak twardej czerwonej flagi w dostępnych danych; normalny trening jest dopuszczalny.",
            score=score,
            hrv_delta=hrv_delta,
        )
    if score <= -2:
        return Readiness(
            color="czerwona" if score <= -3 else "żółta",
            verdict="ODPUSC" if score <= -3 else "OGRANICZ",
            short="dziś bez mocnej pracy" if score <= -3 else "lekko i krótko",
            note="Gotowość jest obniżona; ogranicz intensywność i traktuj regenerację jako główny cel.",
            score=score,
            hrv_delta=hrv_delta,
        )
    return Readiness(
        color="żółta",
        verdict="OGRANICZ",
        short="lekko i krótko",
        note="Gotowość jest mieszana; można trenować, ale bez mocnego akcentu.",
        score=score,
        hrv_delta=hrv_delta,
    )
