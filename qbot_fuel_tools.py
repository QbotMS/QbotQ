#!/usr/bin/env python3
"""B2/B3 — kalkulatory zywienia na trase (QBot). Mirror 1:1 z QExt2 StatsCalculator.kt.

ZRODLO WZOROW (NIE zmieniac — mirror 1:1):
  github.com/QbotMS/QExt2 -> app/src/main/kotlin/com/qext2/primary/engine/StatsCalculator.kt
  - B3 carbsGPerH(IF, movingSec, VI, tempC, bodyKg) -> g/h (Int)
  - B2 fluidLPerH(IF, tempC) + humidityPercent + bodyWeightKg -> L/h (Float)
  Wzory wyciagniete 1:1 do dev_exchange/CURRENT.md (TASK 5, 2026-06-22). Stale, progi,
  mnozniki, zaokraglenia i clampy odwzorowane co do liczby.

WAZNE — wejscia RIDE-TIME vs PLAN:
  QExt2 liczy NA ZYWO (realny NP -> IF/VI, czas jazdy, temp/wilgotnosc z czujnika).
  W raporcie TRASY (planowanie PRZED jazda) tych wartosci NIE ma — kalkulator jest karmiony
  ESTYMATAMI planu. Wzor 1:1 zachowany; zmienia sie tylko ZRODLO wejsc:
    - IF      : target IF z trudnosci trasy / zakladanego wysilku (param if_target)
    - VI      : ~1.05-1.10 dla gravelu falistego (param vi)
    - tempC   : z prognozy pogody trasy (A5) — param temp_c; brak A5 -> None (mnoznik 1.00 jak null w QExt2)
    - humidity: z prognozy (A5) — param humidity_pct; brak A5 -> None (zalozenie neutralne 1.00 = pasmo <60%)
    - duration: z B4 (zakres czasu) — param duration_h; brak B4 -> domyslny, ZAZNACZONA zaleznosc
    - bodyKg  : qbot_v2.body_measurements (najnowszy weight_kg) lub param body_kg
  ZALEZNOSCI: A5 (pogoda) i B4 (czas) jeszcze niegotowe -> wejscia jako parametry z udokumentowanym
  domyslnym; kazda estymata jawnie opisana w wyniku. B1 (strefy %FTP) pominiete decyzja.
"""
from __future__ import annotations

import math
from typing import Any

# domyslne ESTYMATY planu (udokumentowane; NIE sa pomiarem live)
_DEFAULT_IF = 0.70         # endurance gravel target (placeholder do mapowania trudnosc trasy -> IF)
_DEFAULT_VI = 1.05         # gravel falisty ~1.05-1.10
_DEFAULT_DURATION_H = 3.0  # placeholder do czasu z B4 (ZALEZNOSC: B4 niegotowe)
_DEFAULT_BODY_KG = 75.0    # awaryjny placeholder gdy brak body_measurements i parametru


def _round_half_up(x: float) -> int:
    """Odpowiednik Kotlin Double.roundToInt() dla wartosci dodatnich (polowki w gore)."""
    return int(math.floor(x + 0.5))


def carbs_g_per_h(if_value: float, moving_sec: float, vi: float,
                  temp_c: float | None, body_kg: float) -> int:
    """B3 — mirror 1:1 StatsCalculator.carbsGPerH -> g/h (Int)."""
    if_clamp = max(0.4, min(1.1, if_value))
    base = 25.0 + ((if_clamp - 0.4) / 0.7) * 65.0
    hours = moving_sec / 3600.0
    if hours < 1:
        dur = 1.00
    elif hours < 2:
        dur = 1.08
    elif hours < 3:
        dur = 1.15
    else:
        dur = 1.22
    if vi <= 1.05:
        vim = 1.00
    elif vi <= 1.12:
        vim = 1.05
    else:
        vim = 1.10
    weight = max(0.85, min(1.20, body_kg / 75.0))
    if temp_c is None:
        tempm = 1.00
    elif temp_c < 5:
        tempm = 0.95
    elif temp_c < 25:
        tempm = 1.00
    elif temp_c < 32:
        tempm = 1.05
    else:
        tempm = 1.08
    result = base * dur * vim * weight * tempm
    g = _round_half_up(result / 5.0) * 5
    return int(max(20, min(110, g)))


def fluid_l_per_h(if_value: float, temp_c: float | None,
                  humidity_pct: float | None, body_kg: float) -> float:
    """B2 — mirror 1:1 StatsCalculator.fluidLPerH -> L/h (Float)."""
    if if_value < 0.55:
        base = 0.40
    elif if_value < 0.75:
        base = 0.50
    elif if_value < 0.87:
        base = 0.60
    else:
        base = 0.70
    if temp_c is None:
        tempm = 1.00
    elif temp_c < 5:
        tempm = 0.75
    elif temp_c < 12:
        tempm = 0.85
    elif temp_c < 18:
        tempm = 0.95
    elif temp_c < 24:
        tempm = 1.10
    elif temp_c < 30:
        tempm = 1.30
    elif temp_c < 35:
        tempm = 1.50
    else:
        tempm = 1.70
    # humidityMult — QExt2 nie ma galezi null; w planie brak A5 -> zalozenie neutralne 1.00 (pasmo <60%)
    if humidity_pct is None:
        hum = 1.00
    elif humidity_pct < 40:
        hum = 0.90
    elif humidity_pct < 60:
        hum = 1.00
    elif humidity_pct < 75:
        hum = 1.10
    elif humidity_pct < 85:
        hum = 1.20
    else:
        hum = 1.30
    result = base * tempm * hum * (body_kg / 70.0)
    val = _round_half_up(result / 0.05) * 0.05
    return round(max(0.30, min(1.50, val)), 2)


def _athlete_weight_safe():
    """Najnowsza waga z qbot_v2.body_measurements (reuzywa czytnik z B5). (kg, data) lub (None, None)."""
    try:
        from qbot_pressure_tools import _athlete_weight
        return _athlete_weight()
    except Exception:
        return None, None


def _tool_qbot_route_fuel_plan(args: dict | None = None) -> dict[str, Any]:
    a = args or {}

    if_target = a.get("if_target")
    if if_target is None:
        if_target = _DEFAULT_IF
        if_src = (f"DOMYSLNY {_DEFAULT_IF} (endurance gravel; brak mapowania trudnosc trasy->IF "
                  f"— DO POTWIERDZENIA)")
    else:
        if_src = "parametr if_target"
    if_target = float(if_target)

    vi = a.get("vi")
    if vi is None:
        vi = _DEFAULT_VI
        vi_src = f"DOMYSLNY {_DEFAULT_VI} (gravel falisty ~1.05-1.10)"
    else:
        vi_src = "parametr vi"
    vi = float(vi)

    duration_h = a.get("duration_h")
    if duration_h is None:
        duration_h = _DEFAULT_DURATION_H
        dur_src = (f"ZALOZENIE {_DEFAULT_DURATION_H} h (ZALEZNOSC: B4/czas niegotowe — "
                   f"podaj duration_h lub poczekaj na B4)")
    else:
        dur_src = "parametr duration_h (z B4/czasu)"
    duration_h = float(duration_h)
    moving_sec = duration_h * 3600.0

    temp_c = a.get("temp_c")
    if temp_c is not None:
        temp_c = float(temp_c)
        temp_src = "parametr temp_c (z prognozy A5)"
    else:
        temp_src = "BRAK (A5/pogoda niegotowe) -> mnoznik temp 1.00 (jak null w QExt2); ZALEZNOSC: A5"

    humidity_pct = a.get("humidity_pct")
    if humidity_pct is not None:
        humidity_pct = float(humidity_pct)
        hum_src = "parametr humidity_pct (z prognozy A5)"
    else:
        hum_src = "BRAK (A5/pogoda niegotowe) -> zalozenie neutralne 1.00 (pasmo <60%); ZALEZNOSC: A5"

    body_kg = a.get("body_kg")
    body_date = None
    if body_kg is None:
        body_kg, body_date = _athlete_weight_safe()
        body_src = "qbot_v2.body_measurements"
    else:
        body_src = "parametr body_kg"
    if body_kg is None:
        body_kg = _DEFAULT_BODY_KG
        body_src = f"ZALOZENIE {_DEFAULT_BODY_KG} kg (brak body_measurements i parametru) — DO POTWIERDZENIA"
    body_kg = float(body_kg)

    carbs = carbs_g_per_h(if_target, moving_sec, vi, temp_c, body_kg)
    fluid = fluid_l_per_h(if_target, temp_c, humidity_pct, body_kg)
    carbs_total = int(round(carbs * duration_h))
    fluid_total = round(fluid * duration_h, 1)

    temp_disp = f"{temp_c:.0f} C" if temp_c is not None else "brak"
    hum_disp = f"{humidity_pct:.0f} %" if humidity_pct is not None else "brak"
    body_disp = f"{body_kg:.1f} kg — {body_src}" + (f", {body_date}" if body_date else "")

    lines = [
        "## Plan zywienia na trase — B2 (plyny) + B3 (wegle)",
        "_Wzory: mirror 1:1 QExt2 StatsCalculator (carbsGPerH / fluidLPerH). W QExt2 liczone "
        "na zywo z realnego NP/IF — tu KARMIONE estymatami planu (przed jazda)._",
        "",
        "### Wejscia (zrodla)",
        f"- IF (target): {if_target:.2f} — {if_src}",
        f"- VI: {vi:.2f} — {vi_src}",
        f"- Czas jazdy: {duration_h:.2f} h — {dur_src}",
        f"- Temperatura: {temp_disp} — {temp_src}",
        f"- Wilgotnosc: {hum_disp} — {hum_src}",
        f"- Waga: {body_disp}",
        "",
        "### B3 — wegle (carbs)",
        f"- **{carbs} g/h** (zaokraglone do 5 g, clamp 20-110 g/h)",
        f"- Suma na {duration_h:.1f} h: ~{carbs_total} g (pochodna: g/h x czas)",
        "",
        "### B2 — plyny (fluids)",
        f"- **{fluid:.2f} L/h** (zaokraglone do 0.05 L, clamp 0.30-1.50 L/h)",
        f"- Suma na {duration_h:.1f} h: ~{fluid_total:.1f} L (pochodna: L/h x czas)",
        "",
        "### Zaleznosci / uwagi",
        "- A5 (prognoza pogody) niegotowe -> temp/wilgotnosc jako parametry; brak -> mnozniki neutralne "
        "(temp 1.00, wilg. 1.00). Po wpieciu A5 podac temp_c/humidity_pct z prognozy po wspolrzednych trasy.",
        "- B4 (czas z historii) niegotowe -> duration_h jako parametr/zalozenie. Po wpieciu B4 podac zakres czasu.",
        "- IF target docelowo z trudnosci trasy (route_plan_analysis); VI ~1.05-1.10 dla gravelu falistego.",
        "- B1 (strefy mocy %FTP): pominiete decyzja (malo wazne); QExt2 nie ma klasycznych stref %FTP.",
    ]
    analysis = "\n".join(lines)
    notes = ("B2/B3 mirror 1:1 QExt2 StatsCalculator. Wejscia planowe (estymaty), nie pomiar live. "
             "Zaleznosci: A5 (temp/wilgotnosc), B4 (czas). Karmic danymi trasy gdy gotowe.")
    return {
        "status": "OK",
        "analysis": analysis,
        "notes": notes,
        "data": {
            "carbs_g_per_h": carbs,
            "fluid_l_per_h": fluid,
            "carbs_total_g": carbs_total,
            "fluid_total_l": fluid_total,
            "inputs": {
                "if_target": if_target, "vi": vi, "duration_h": duration_h,
                "temp_c": temp_c, "humidity_pct": humidity_pct, "body_kg": body_kg,
            },
        },
    }
