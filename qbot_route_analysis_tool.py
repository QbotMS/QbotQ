#!/usr/bin/env python3
"""TASK 11 - route_analysis: jednowarstwowa analiza LLM zaplanowanej trasy.

route_analysis buduje JEDEN duzy kontekst (trasa + zawodnik + sprzet + POI z km +
zywienie + czas) i wysyla go do LLM z pytaniami A-F. LLM robi jedna spojna analize.
Stary route_report zostaje jako fallback. POI: kazdy punkt z route_km (nie agregat).
Nawierzchnia: PELNA lista do LLM. Wiatr: wind_speed_ms*3.6. max_tokens=1200.
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

_VARIANT_TITLE = {"skrocony": "SKRÓCONY", "pelny": "PEŁNY", "grupa": "DLA GRUPY"}

_VARIANT_SECTIONS = {
    "skrocony": ("A", "C", "F"),
    "pelny": ("A", "B", "C", "D", "E", "F"),
    "grupa": ("A", "B", "D", "F"),
}

_RWGPS_URL = "https://ridewithgps.com/routes/{rid}"

_MAX_TOKENS = 1200


def _norm_variant(value: Any) -> str | None:
    if value is None:
        return None
    return _VARIANT_ALIASES.get(str(value).strip().lower())


def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
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


def _ok(result: dict[str, Any]) -> bool:
    return isinstance(result, dict) and result.get("status") in ("OK", "ok", "READY_WITH_WARNINGS")


def _analysis(result: dict[str, Any]) -> str | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if isinstance(data, dict) and data.get("analysis"):
        return str(data["analysis"])
    if result.get("analysis"):
        return str(result["analysis"])
    return None


def _resolve_distance_km(route_id: str | None) -> float | None:
    if not route_id:
        return None
    try:
        from qbot_route_time_tools import _route_distance_km
        dist, _src = _route_distance_km(route_id)
        return dist
    except Exception:
        return None


def _strip_forma(text: str | None) -> str:
    if not text:
        return text or ""
    out: list[str] = []
    for line in text.splitlines():
        low = line.strip().lower()
        if "\U0001f4aa" in line or low.startswith("forma") or "forma (fitmodel" in low:
            break
        out.append(line)
    return "\n".join(out).rstrip()


def _parse_ftp_w(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"FTP\s+(\d+)\s*W", text)
    return int(m.group(1)) if m else None


def _power_zones_block(ftp: int) -> str:
    def z(lo: int, hi: int) -> tuple[int, int]:
        return round(ftp * lo / 100.0), round(ftp * hi / 100.0)
    e_lo, e_hi = z(55, 75)
    t_lo, t_hi = z(76, 90)
    p_lo, p_hi = z(91, 105)
    return (
        f"Strefy mocy (z FTP {ftp} W): endurance {e_lo}–{e_hi} W, "
        f"tempo {t_lo}–{t_hi} W, prog {p_lo}–{p_hi} W."
    )


def _parse_temp_c(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+)(?:–(\d+))?°C", text)
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else None
    return (lo + hi) / 2.0 if hi is not None else float(lo)


def _parse_duration_h(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+):(\d{2})", text)
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2)) / 60.0


def _wind_speed_kmh(route_id: str | None) -> tuple[float | None, float | None]:
    if not route_id:
        return None, None
    try:
        from tools.rwgps.route_brief import _db_connect
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT w.wind_speed_ms FROM qbot_v2.route_frame_weather w "
            "JOIN qbot_v2.route_frames f "
            "  ON w.route_artifact_id = f.route_artifact_id "
            "     AND w.frame_size_m = f.frame_size_m "
            "     AND w.frame_index = f.frame_index "
            "WHERE f.route_id::text = ANY(%s) AND f.frame_size_m = 80 "
            "      AND w.kind = 'forecast' AND w.wind_speed_ms IS NOT NULL",
            ([str(route_id)],),
        )
        vals = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
        try:
            conn.close()
        except Exception:
            pass
        if not vals:
            return None, None
        avg_kmh = sum(vals) / len(vals) * 3.6
        max_kmh = max(vals) * 3.6
        return round(avg_kmh, 1), round(max_kmh, 1)
    except Exception:
        return None, None


def _poi_points(route_id: str | None, dist_km: float | None, start: Any) -> list[tuple[float, str, str]]:
    if not route_id or not dist_km:
        return []
    try:
        from qbot_route_tools import _tool_qbot_route_poi_analyze
        res = _tool_qbot_route_poi_analyze({
            "route_id": str(route_id),
            "km_from": 0.0,
            "km_to": float(dist_km),
            "open_window": True,
            "ride_start": start,
            "google_hours": True,
            "confirm": True,
        })
    except Exception:
        return []
    if not isinstance(res, dict):
        return []
    analysis = res.get("analysis")
    if not isinstance(analysis, dict):
        data = res.get("data")
        analysis = data.get("analysis") if isinstance(data, dict) else None
    if not isinstance(analysis, dict):
        return []
    labels = {
        "water": "woda",
        "hard_resupply": "sklep",
        "soft_food_stop": "jedzenie",
        "attractions": "atrakcja",
    }
    points: list[tuple[float, str, str]] = []
    for key, kind in labels.items():
        items = analysis.get(key)
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            km = it.get("route_km")
            if km is None:
                continue
            try:
                kmf = float(km)
            except (TypeError, ValueError):
                continue
            name = str(it.get("name") or "").strip()
            points.append((kmf, kind, name))
    points.sort(key=lambda p: p[0])
    return points


_INTRO = (
    "Masz pełne dane trasy, zawodnika i sprzętu. Odpowiedz na każde pytanie konkretnie "
    "— z kilometrami, watami, litrami. Bez ogólników. Korzystaj WYŁĄCZNIE z liczb podanych "
    "w danych wejściowych; nie wymyślaj nowych faktów."
)

_CLOSING = "Pisz po polsku. Każda sekcja 3-6 zdań z liczbami. Oznaczaj wnioski jako (ocena)."
_SECTION_TEXT = {
    "A": (
        "## A — CHARAKTERYSTYKA TRASY\n"
        "Opisz charakter trasy w 3-4 zdaniach: co dominuje, co bedzie wymagajace, czym sie "
        "rozni od typowej jazdy."
    ),
    "B": (
        "## B — NAWIERZCHNIA (analiza, nie wypisanie)\n"
        "- Jakie sa KLUCZOWE odcinki nawierzchniowe? (tylko te ktore wplyna na jazde, z km i uzasadnieniem)\n"
        "- Co prawdopodobnie kryje sie pod nawierzchnia nieznana w tym rejonie/terenie? "
        "(wnioskuj z kontekstu: teren wiejski/lesny/miejski, okoliczne typy drog)\n"
        "- Gdzie nawierzchnia + wiatr tworza kombinacje ryzyka?"
    ),
    "C": (
        "## C — STRATEGIA MOCY\n"
        "- Docelowe zakresy mocy per typ odcinka (plasko/podjazd/pod wiatr) w W\n"
        "- Ktory odcinek wymaga najwiekszej dyscypliny i dlaczego (km + powod)\n"
        "- Jedna zasada taktyczna na te trase"
    ),
    "D": (
        "## D — ZYWIENIE I NAWODNIENIE\n"
        "- Ile wegli i plynow lacznie\n"
        "- Kiedy i gdzie uzupelnic? Podaj konkretne km ze sklepow/wody z listy POI (nie 'jest 15 sklepow')\n"
        "- Czy zapas bidonow/plecaka wystarczy do pierwszego punktu uzupelnienia?"
    ),
    "E": (
        "## E — SPRZET\n"
        "- Ktory zestaw kol lepiej pasuje do tej trasy i dlaczego (nawierzchnia + %)\n"
        "- Zalecane cisnienie startowe (konkretne wartosci dla dominujacej nawierzchni)"
    ),
    "F": (
        "## F — RYZYKA (ranking)\n"
        "- Top 3 ryzyka z km X-Y i uzasadnieniem (nawierzchnia / wiatr / fizjologia)\n"
        "- Najwieksze zagrozenie (jedno zdanie)"
    ),
}


def _build_context(route_id, plan_txt, prof_txt, poi_points, fuel_txt,
                   time_txt, tp_txt, wind_avg, wind_max, variant) -> str:
    secs = _VARIANT_SECTIONS[variant]
    out: list[str] = ["# DANE WEJSCIOWE (fakty z narzedzi QBot)", ""]
    if route_id:
        out.append(f"Trasa: {route_id} - {_RWGPS_URL.format(rid=route_id)}")
        out.append("")

    out.append("## Plan trasy (route_plan_analysis)")
    out.append(plan_txt or "_brak danych planu_")
    out.append("")

    if wind_avg is not None or wind_max is not None:
        seg = []
        if wind_avg is not None:
            seg.append(f"sr. {wind_avg:g} km/h")
        if wind_max is not None:
            seg.append(f"max {wind_max:g} km/h")
        out.append("## Sila wiatru (prognoza ramek)")
        out.append("Predkosc wiatru: " + ", ".join(seg) + ".")
        out.append("")

    if "B" in secs:
        out.append("## Nawierzchnia i podjazdy odcinkami (route_profile_detail - PELNA lista)")
        out.append(prof_txt or "_brak szczegolowego profilu_")
        out.append("")

    if "D" in secs:
        out.append("## Punkty POI z kilometrazem (kazdy punkt z km - nie zagregowane)")
        if poi_points:
            for kmf, kind, name in poi_points:
                nm = f" {name}" if name else ""
                out.append(f"- {kind}{nm}: km {kmf:.1f}")
        else:
            out.append("_brak punktow POI / niedostepne_")
        out.append("")
        out.append("## Zywienie i nawodnienie (route_fuel_plan)")
        out.append(fuel_txt or "_brak planu zywienia_")
        out.append("")

    out.append("## Szacowany czas (route_time_estimate)")
    out.append(time_txt or "_brak szacunku czasu_")
    out.append("")

    if "C" in secs or "E" in secs:
        out.append("## Zawodnik i sprzet")
        ftp = _parse_ftp_w(plan_txt)
        if "C" in secs and ftp:
            out.append(_power_zones_block(ftp))
        if "E" in secs:
            out.append(tp_txt or "_brak danych o cisnieniach/sprzecie_")
        out.append("")

    return "\n".join(out).rstrip()


def _build_questions(variant: str) -> str:
    secs = _VARIANT_SECTIONS[variant]
    blocks = [_SECTION_TEXT[s] for s in ("A", "B", "C", "D", "E", "F") if s in secs]
    return "\n\n".join(blocks)


def _build_prompt(context: str, variant: str) -> str:
    return (
        f"{_INTRO}\n\n"
        f"{context}\n\n"
        f"=== PYTANIA (odpowiedz w tej strukturze) ===\n\n"
        f"{_build_questions(variant)}\n\n"
        f"{_CLOSING}"
    )


_SYSTEM_PROMPT = (
    "Jestes Albert - analityk tras rowerowych QBot. Robisz JEDNA spojna analize "
    "zaplanowanej trasy na podstawie podanych faktow. Nie wymyslaj liczb ani faktow "
    "spoza danych wejsciowych. Badz konkretny: kilometry, waty, litry."
)


def _tool_route_analysis(args: dict[str, Any] | None = None) -> dict[str, Any]:
    a = dict(args or {})

    variant = _norm_variant(a.get("variant"))
    if variant is None:
        return {
            "status": "OK",
            "variant": None,
            "analysis": (
                "Ktory wariant analizy trasy?\n"
                "  - skrocony: A charakterystyka + C strategia mocy + F ryzyka\n"
                "  - pelny: pelna analiza A-F (nawierzchnia, POI z km, zywienie, sprzet)\n"
                "  - dla grupy: A + B + D + F bez danych osobistych (watow, sprzetu)\n"
                "Odpowiedz: skrocony / pelny / dla grupy"
            ),
        }

    route_id = a.get("route_id") or a.get("route") or a.get("route_ref")
    if route_id is not None:
        route_id = str(route_id).strip().split("/")[-1].split("?")[0] or None
    start = a.get("start")
    secs = _VARIANT_SECTIONS[variant]

    base_args: dict[str, Any] = {}
    if route_id:
        base_args["route_id"] = route_id

    plan_args = dict(base_args)
    if start:
        plan_args["start"] = start
    plan = _call_tool("route_plan_analysis", plan_args)
    plan_txt = _analysis(plan) if _ok(plan) else None
    if variant == "grupa":
        plan_txt = _strip_forma(plan_txt)

    prof_txt = None
    if "B" in secs:
        prof = _call_tool("route_profile_detail", dict(base_args))
        prof_txt = _analysis(prof) if _ok(prof) else None

    t = _call_tool("route_time_estimate", dict(base_args))
    time_txt = _analysis(t) if _ok(t) else None

    poi_points: list[tuple[float, str, str]] = []
    fuel_txt = None
    if "D" in secs:
        dist = _resolve_distance_km(route_id)
        poi_points = _poi_points(route_id, dist, start)
        temp_c = _parse_temp_c(plan_txt)
        duration_h = _parse_duration_h(time_txt)
        fuel_args: dict[str, Any] = {}
        if temp_c is not None:
            fuel_args["temp_c"] = temp_c
        if duration_h is not None:
            fuel_args["duration_h"] = duration_h
        fuel = _call_tool("route_fuel_plan", fuel_args)
        fuel_txt = _analysis(fuel) if _ok(fuel) else None

    tp_txt = None
    if "E" in secs:
        tp = _call_tool("tire_pressure", {})
        tp_txt = _analysis(tp) if _ok(tp) else None

    wind_avg, wind_max = _wind_speed_kmh(route_id)

    context = _build_context(route_id, plan_txt, prof_txt, poi_points, fuel_txt,
                             time_txt, tp_txt, wind_avg, wind_max, variant)
    prompt = _build_prompt(context, variant)

    try:
        from qgpt_client import qgpt_text
        text = (qgpt_text(prompt, system=_SYSTEM_PROMPT, max_tokens=_MAX_TOKENS, temperature=0) or "").strip()
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "ERROR",
            "variant": variant,
            "route_id": route_id,
            "error": f"LLM niedostepny: {str(exc)[:200]}",
        }

    if not text:
        text = "(analiza niedostepna - LLM zwrocil pusta odpowiedz)"

    header = f"# ANALIZA TRASY - wariant {_VARIANT_TITLE[variant]}"
    if route_id:
        header += f"\nTrasa: {route_id} - {_RWGPS_URL.format(rid=route_id)}"
    analysis_text = f"{header}\n\n{text}\n"

    return {
        "status": "OK",
        "variant": variant,
        "route_id": route_id,
        "analysis": analysis_text,
        "notes": (
            "Jedna spojna analiza LLM (sekcje wg wariantu). Pokaz pole analysis w calosci 1:1. "
            "NIE dorabiaj wlasnych ocen - analiza jest kompletna."
        ),
    }
