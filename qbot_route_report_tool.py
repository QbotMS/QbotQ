#!/usr/bin/env python3
"""TASK 08 - route_report: orkiestrator znormalizowanego raportu trasy.

route_report NIE liczy niczego samodzielnie. Wywoluje gotowe narzedzia przez
ich callable z rejestru (qbot3.tool_registry):
    route_plan_analysis, route_profile_detail, route_time_estimate,
    tire_pressure, route_fuel_plan, route_poi_analyze_readonly
i sklada ich wyniki w sekcje A/B raportu wg wybranego wariantu. Sekcje C
(ocena) dopisuje model (Albert) na podstawie zebranych danych A/B.

Warianty:
  - skrocony (domyslny): A (plan bez formy) + B4 czas + B5 cisnienia
  - pelny: A1-A8 + B2/B3/B4/B5 + C1-C4
  - grupa: A1-A5 (bez formy) + A8 + B4 + C1/C2/C4 - BEZ danych osobistych
"""
from __future__ import annotations

import re
from typing import Any

_VARIANT_ALIASES = {
    "skrocony": "skrocony", "skrócony": "skrocony", "krotki": "skrocony",
    "krótki": "skrocony", "short": "skrocony", "default": "skrocony",
    "pelny": "pelny", "pełny": "pelny", "pelna": "pelny", "pełna": "pelny",
    "full": "pelny",
    "grupa": "grupa", "dla grupy": "grupa", "grupowy": "grupa",
    "group": "grupa", "znajomi": "grupa", "dla znajomych": "grupa",
}

_RWGPS_URL = "https://ridewithgps.com/routes/{rid}"

_VARIANT_TITLE = {"skrocony": "SKRÓCONY", "pelny": "PEŁNY", "grupa": "DLA GRUPY"}


def _norm_variant(value: Any) -> str | None:
    if value is None:
        return None
    return _VARIANT_ALIASES.get(str(value).strip().lower())


def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Wywoluje narzedzie przez callable z rejestru (wzorzec agent_runtime)."""
    from qbot3.tool_registry import lookup
    spec = lookup(name)
    if not spec or not spec.get("callable"):
        return {"status": "error", "error": f"brak narzedzia '{name}' w rejestrze"}
    fn = spec["callable"]
    wrapped = spec.get("wrapped")
    try:
        if wrapped:
            return fn(wrapped, args)
        return fn(args)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)[:300]}


def _resolve_distance_km(route_id: str | None) -> float | None:
    """Dystans trasy do km_to dla POI (reuse istniejacego helpera B4)."""
    if not route_id:
        return None
    try:
        from qbot_route_time_tools import _route_distance_km
        dist, _src = _route_distance_km(route_id)
        return dist
    except Exception:
        return None


def _ok(result: dict[str, Any]) -> bool:
    return isinstance(result, dict) and result.get("status") in ("OK", "ok", "READY_WITH_WARNINGS")


def _analysis(result: dict[str, Any]) -> str | None:
    """Wyciaga pole analysis (success_result pakuje dane w 'data')."""
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if isinstance(data, dict) and data.get("analysis"):
        return str(data["analysis"])
    if result.get("analysis"):
        return str(result["analysis"])
    return None


def _reason(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "zly format wyniku"
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    return str(result.get("error") or result.get("warning")
               or data.get("warning") or result.get("status") or "niedostepne")


def _strip_forma(text: str | None) -> str:
    """Usuwa blok formy/FTP (A6) - zawsze ostatni blok analizy planu."""
    if not text:
        return text or ""
    out: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if "\U0001f4aa" in line or low.startswith("forma") or "forma (fitmodel" in low:
            break
        out.append(line)
    return "\n".join(out).rstrip()


def _parse_temp_c(text: str | None) -> float | None:
    """temp_c z analizy planu (A5). Regex (\\d+)(?:–(\\d+))?°C -> srednia zakresu lub pojedyncza."""
    if not text:
        return None
    m = re.search(r"(\d+)(?:–(\d+))?°C", text)
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else None
    return (lo + hi) / 2.0 if hi is not None else float(lo)


def _parse_duration_h(text: str | None) -> float | None:
    """duration_h z analizy czasu (B4). Regex (\\d+):(\\d{2}) -> h + m/60."""
    if not text:
        return None
    m = re.search(r"(\d+):(\d{2})", text)
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2)) / 60.0


def _generate_section_c(analysis_ab: str, variant: str) -> str:
    """Sekcja C (ocena) generowana przez LLM wzorcem qgpt_client.qgpt_text.
    Pelny: C1-C4; grupa: C1/C2/C4; inny: pusto. Fallback: '(ocena niedostępna)'."""
    if variant == "pelny":
        zakres = (
            "C1 Taktyka (kluczowe wyzwania trasy i sugestia tempa - z A2/A3/A4/B4); "
            "C2 Ryzyko (pogoda / nawierzchnia / wiatr - z A3/A4/A5); "
            "C3 Sprzet (czy aktywny zestaw kol/opony pasuja do nawierzchni - z A3/A7/B5); "
            "C4 Najwieksze zagrozenie (jedno zdanie)."
        )
    elif variant == "grupa":
        zakres = (
            "C1 Taktyka (kluczowe wyzwania trasy i sugestia tempa - z A2/A3/A4/B4); "
            "C2 Ryzyko (pogoda / nawierzchnia / wiatr - z A3/A4/A5); "
            "C4 Najwieksze zagrozenie (jedno zdanie). Pomin ocene sprzetu."
        )
    else:
        return ""
    prompt = (
        "Dane raportu trasy (sekcje A/B, fakty z narzedzi QBot):\n\n"
        f"{analysis_ab[:2000]}\n\n"
        "Na podstawie WYLACZNIE powyzszych danych (bez zgadywania, bez nowych liczb) "
        f"napisz sekcje oceny: {zakres} "
        "Kazdy punkt w osobnej linii zaczynajacej sie od '- ' z numerem, "
        "np. '- C1 Taktyka (ocena): ...'. Pisz krotko, po polsku."
    )
    system = (
        "Jestes Albert - analityk tras rowerowych QBot. Oceniasz ZAPLANOWANA trase "
        "wylacznie na podstawie podanych danych A/B. Nie wymyslaj liczb ani faktow spoza danych."
    )
    try:
        from qgpt_client import qgpt_text
        text = (qgpt_text(prompt, system=system, max_tokens=400, temperature=0) or "").strip()
        return text or "(ocena niedostępna)"
    except Exception:
        return "(ocena niedostępna)"


def _tool_route_report(args: dict[str, Any] | None = None) -> dict[str, Any]:
    a = dict(args or {})

    variant = _norm_variant(a.get("variant"))
    if variant is None:
        return {
            "status": "OK",
            "variant": None,
            "analysis": (
                "Który wariant raportu?\n"
                "  • skrócony — szybki przegląd (dystans, czas, nawierzchnia, pogoda, ciśnienia)\n"
                "  • pełny — wszystkie sekcje A/B/C (forma, waga, paliwo, sprzęt)\n"
                "  • dla grupy — trasa i warunki bez danych osobistych\n"
                "Odpowiedz: skrócony / pełny / dla grupy"
            ),
        }

    route_id = a.get("route_id") or a.get("route") or a.get("route_ref")
    if route_id is not None:
        route_id = str(route_id).strip().split("/")[-1].split("?")[0] or None
    start = a.get("start")

    base_args: dict[str, Any] = {}
    if route_id:
        base_args["route_id"] = route_id

    sections: list[str] = []
    H = sections.append

    H(f"# RAPORT TRASY - wariant {_VARIANT_TITLE[variant]}")
    if route_id:
        H(f"Trasa: {route_id} · {_RWGPS_URL.format(rid=route_id)}")
    H("")

    # ---- A: plan_analysis (A1 trasa, A2 profil, A3 nawierzchnia%, A4 wiatr, A5 pogoda, A6 forma) ----
    plan_args = dict(base_args)
    if start:
        plan_args["start"] = start
    plan = _call_tool("route_plan_analysis", plan_args)
    H("## A - DANE TRASY")
    if _ok(plan) and _analysis(plan):
        text = _analysis(plan)
        if variant in ("skrocony", "grupa"):
            text = _strip_forma(text)  # A6 forma/FTP tylko w wariancie pelnym
        H(text)
    else:
        H(f"_A1-A5 niedostepne: {_reason(plan)}_")
    H("")

    # ---- A2/A3 odcinkami: profile_detail (pelny + grupa) ----
    if variant in ("pelny", "grupa"):
        prof = _call_tool("route_profile_detail", dict(base_args))
        H("## A3 - NAWIERZCHNIA I PROFIL ODCINKAMI")
        if _ok(prof) and _analysis(prof):
            H(_analysis(prof))
        else:
            H(f"_Szczegolowy profil niedostepny: {_reason(prof)}_")
        H("")

    # ---- A7 sprzet (tylko pelny) ----
    if variant == "pelny":
        H("## A7 - SPRZET")
        H("_Rower, aktywny zestaw kol i opony - dane w bloku B5 (kalkulator cisnien "
          "czyta z garazu: masa roweru, zestaw, szerokosci opon)._")
        H("")

    # ---- A8 woda/sklepy/refill: poi readonly (pelny + grupa) ----
    if variant in ("pelny", "grupa"):
        H("## A8 - WODA / SKLEPY / REFILL")
        dist = _resolve_distance_km(route_id)
        if route_id and dist:
            poi = _call_tool("route_poi_analyze_readonly", {
                "route_id": route_id,
                "km_from": 0.0,
                "km_to": float(dist),
                "open_window": True,
                "ride_start": start,
            })
            if _ok(poi):
                pdata = poi.get("data") if isinstance(poi.get("data"), dict) else poi
                pdata = pdata or {}
                counts = pdata.get("counts") or {}
                H(f"Zakres: km 0-{float(dist):.0f}")
                H(f"- Woda (punkty): {counts.get('water')}")
                H(f"- Jedzenie/sklepy (punkty): {counts.get('food')}")
                H(f"- Atrakcje: {counts.get('attractions')}")
                rep = pdata.get("report_path")
                if rep:
                    H(f"- Pelny raport POI (godziny otwarcia): {rep}")
            else:
                H(f"_POI niedostepne: {_reason(poi)}_")
        else:
            H("_A8 wymaga route_id z policzonym dystansem trasy (km_to). "
              "Brak - pomijam bez zgadywania._")
        # ZMIANA 2: deterministyczna rekomendacja bidonow (temp z planu, dystans z helpera)
        temp_c = _parse_temp_c(_analysis(plan)) if _ok(plan) else None
        if temp_c is not None and temp_c >= 20 and dist and dist >= 50:
            rec = "plecak 1.5–2 l + 2 bidony"
        elif temp_c is not None and temp_c < 5:
            rec = "butelki termiczne"
        else:
            rec = "2 bidony w ramie"
        H(f"💧 Bidony: {rec}. Zakładaj możliwość refill.")
        H("")

    # ---- B: wyliczenia ----
    H("## B - WYLICZENIA")
    H("")

    # B4 czas (wszystkie warianty)
    t = _call_tool("route_time_estimate", dict(base_args))
    H("### B4 - Szacowany czas przejazdu")
    if _ok(t) and _analysis(t):
        H(_analysis(t))
    else:
        H(f"_B4 niedostepne: {_reason(t)}_")
    H("")

    # B2/B3 zywienie (tylko pelny)
    if variant == "pelny":
        # ZMIANA 1: realne wejscia z juz zebranych wynikow - temp z A5 (plan), czas z B4.
        temp_c = _parse_temp_c(_analysis(plan)) if _ok(plan) else None
        duration_h = _parse_duration_h(_analysis(t)) if _ok(t) else None
        fuel_args: dict[str, Any] = {}
        if temp_c is not None:
            fuel_args["temp_c"] = temp_c
        if duration_h is not None:
            fuel_args["duration_h"] = duration_h
        fuel = _call_tool("route_fuel_plan", fuel_args)
        H("### B2/B3 - Plyny i weglowodany")
        if _ok(fuel) and _analysis(fuel):
            H(_analysis(fuel))
        else:
            H(f"_B2/B3 niedostepne: {_reason(fuel)}_")
        temp_note = (f"{temp_c:.0f}°C z A5 planu (realne)" if temp_c is not None
                     else "domyslne (brak temp w A5 -> mnoznik 1.00)")
        dur_note = (f"{duration_h:.2f} h z B4 (realne)" if duration_h is not None
                    else "domyslne (brak B4 -> zalozenie kalkulatora)")
        H(f"_Wejscia route_fuel_plan: temperatura = {temp_note}; czas = {dur_note}._")
        H("")

    # B5 cisnienia (skrocony + pelny; NIE grupa - dane osobiste)
    if variant in ("skrocony", "pelny"):
        tp = _call_tool("tire_pressure", {})
        H("### B5 - Cisnienie opon")
        if _ok(tp) and _analysis(tp):
            H(_analysis(tp))
        else:
            H(f"_B5 niedostepne: {_reason(tp)}_")
        H("")

    # ---- C: ocena (generowana przez LLM na podstawie zebranych danych A/B) ----
    if variant in ("pelny", "grupa"):
        analysis_ab = "\n".join(sections)
        H("## C - OCENA (na podstawie danych A/B; oznaczona „(ocena)”)")
        H(_generate_section_c(analysis_ab, variant))

    analysis_text = "\n".join(sections).rstrip() + "\n"
    note = ("Raport zlozony z gotowych narzedzi (orkiestracja). Sekcje A/B pochodza 1:1 "
            "z narzedzi - pokaz je w calosci. ")
    note += ("Wariant skrocony nie ma sekcji C." if variant == "skrocony"
             else "Sekcje C (ocena) wygenerowane na podstawie danych A/B.")
    return {
        "status": "OK",
        "variant": variant,
        "route_id": route_id,
        "analysis": analysis_text,
        "notes": note,
    }
