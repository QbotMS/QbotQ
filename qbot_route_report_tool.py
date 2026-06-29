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

import json
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


def _surface_profile_render_line(profile: dict[str, Any]) -> str:
    refined = profile.get("surface_percentages_refined") if isinstance(profile, dict) else {}
    if not isinstance(refined, dict):
        refined = {}
    aggregated: dict[str, float] = {}
    try:
        from qbot_route_tools import _surface_profile_label as _label, _surface_profile_float as _float
    except Exception:  # pragma: no cover - local fallback
        def _label(value: Any) -> str:
            return str(value or "").strip().replace("_", " ")
        def _float(value: Any) -> float | None:
            try:
                return float(value)
            except Exception:
                return None
    for key, value in refined.items():
        label = _label(key)
        if label == "nieznana":
            continue
        pct = _float(value)
        if pct is None:
            continue
        aggregated[label] = aggregated.get(label, 0.0) + pct
    items = sorted(aggregated.items(), key=lambda item: (-item[1], item[0]))
    if items:
        return ", ".join(f"{label} {pct:.1f}%" for label, pct in items[:5])
    return "brak danych"


def _read_poi_analysis_cache(route_id: str | None) -> dict[str, Any] | None:
    if not route_id:
        return None
    try:
        from pathlib import Path as _P
        import json as _json

        files = sorted(
            _P("/opt/qbot/artifacts/reports").glob(f"poi_analysis_{route_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in files:
            try:
                obj = _json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            counts = {
                "water": len(obj.get("water") or []),
                "food": len(obj.get("soft_food_stop") or []) + len(obj.get("hard_resupply") or []),
                "attractions": len(obj.get("attractions") or []),
            }
            report_md = path.with_suffix(".md")
            return {
                "status": obj.get("status") or obj.get("analysis_status") or "OK",
                "data": {
                    "counts": counts,
                    "report_path": str(report_md) if report_md.exists() else None,
                    "report_json_path": str(path),
                },
                "cache_path": str(path),
                "analysis_status": obj.get("analysis_status"),
            }
    except Exception:
        return None
    return None


def _surface_quality_lines(surface_profile: dict[str, Any] | None) -> list[str]:
    if not isinstance(surface_profile, dict):
        return [
            "Źródło nawierzchni: legacy surface path (route_frames / route_surface_segments)",
            "Profil jakości: brak danych z surface_summary_json",
            "Ostrzeżenie: legacy fallback bez dobrego profilu surface_summary_json",
        ]
    quality_status = str(surface_profile.get("quality_status") or "UNKNOWN").strip().upper()
    coverage_pct = surface_profile.get("coverage_pct")
    tagged_surface_pct = surface_profile.get("tagged_surface_pct")
    inferred_surface_pct = surface_profile.get("inferred_surface_pct")
    unknown_surface_pct = surface_profile.get("unknown_surface_pct")
    source = "surface_summary_json" if surface_profile.get("good_profile") else "legacy fallback"
    lines = [
        f"Źródło nawierzchni: {source}",
        (
            "Profil jakości: "
            f"{quality_status} | coverage {coverage_pct:.0f}% | "
            f"tagged {tagged_surface_pct:.1f}% | inferred {inferred_surface_pct:.1f}% | "
            f"unknown {unknown_surface_pct:.1f}%"
            if all(v is not None for v in (coverage_pct, tagged_surface_pct, inferred_surface_pct, unknown_surface_pct))
            else f"Profil jakości: {quality_status}"
        ),
    ]
    if not surface_profile.get("good_profile") or quality_status == "LOW_CONFIDENCE":
        lines.append("Ostrzeżenie: legacy fallback albo LOW_CONFIDENCE — interpretacja nawierzchni wymaga ostrożności")
    return lines


def _geology_lines(surface_profile: dict[str, Any] | None) -> list[str]:
    if not isinstance(surface_profile, dict):
        return ["Geologia: brak danych w profilu, nie użyto do oceny nawierzchni"]
    summary = surface_profile.get("surface_summary_json")
    if not isinstance(summary, dict):
        return ["Geologia: brak danych w profilu, nie użyto do oceny nawierzchni"]
    geo = summary.get("geology_context")
    if not isinstance(geo, dict) or not geo:
        return ["Geologia: brak danych w profilu, nie użyto do oceny nawierzchni"]

    provider = str(geo.get("provider") or "unknown").strip()
    status = str(geo.get("status") or "UNKNOWN").strip().upper()
    material_hint = str(geo.get("material_hint") or geo.get("dominant_material") or "—").strip()
    dominant_region = str(geo.get("dominant_region") or "—").strip()
    dominant_unit = str(geo.get("dominant_unit") or "—").strip()
    confidence = str(geo.get("confidence") or "—").strip()
    warnings = geo.get("warnings") if isinstance(geo.get("warnings"), list) else []
    risk_flags = geo.get("risk_flags")
    if isinstance(risk_flags, dict):
        risk_flags_text = ", ".join(f"{k}={v}" for k, v in risk_flags.items()) or "brak"
    elif isinstance(risk_flags, list):
        risk_flags_text = ", ".join(str(v) for v in risk_flags if str(v).strip()) or "brak"
    elif risk_flags:
        risk_flags_text = str(risk_flags)
    else:
        risk_flags_text = "brak"

    explanation = str(geo.get("explanation") or "").strip()
    interpretation = "brak jednoznacznej interpretacji"
    hint = material_hint.lower()
    if any(token in hint for token in ("sand", "piasek", "loose")):
        interpretation = "większe ryzyko piachu i luźnego podłoża na odcinkach inferred"
    elif any(token in hint for token in ("gravel", "zwir", "szuter")):
        interpretation = "luźny żwir / szuter może podbijać koszt i obniżać przyczepność"
    elif any(token in hint for token in ("ground", "grunt", "earth", "dirt")):
        interpretation = "grunt i ziemia mogą być bardziej wrażliwe na wilgoć i koleiny"
    elif any(token in hint for token in ("rock", "stone", "kamien", "hardpack", "compact")):
        interpretation = "twardsze podłoże zwykle daje stabilniejszą trakcję"

    lines = [
        f"Geologia / podłoże (geology_context): provider={provider} | status={status} | confidence={confidence}",
        f"- dominant_region: {dominant_region}",
        f"- dominant_unit: {dominant_unit}",
        f"- material_hint: {material_hint}",
        f"- risk_flags: {risk_flags_text}",
        f"- interpretacja: {interpretation}",
    ]
    if explanation:
        lines.append(f"- explain: {explanation}")
    if warnings:
        lines.append(f"- warnings: {', '.join(str(w) for w in warnings if str(w).strip())}")
    return lines


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


_PAVED_SURF = ("asfalt", "asphalt", "beton", "concrete", "paved", "kostka", "paving_stones")


def _parse_ftp_w(text: str | None) -> int | None:
    r"""FTP z analizy planu (A6). Regex r'FTP\s+(\d+)\s*W'."""
    if not text:
        return None
    m = re.search(r"FTP\s+(\d+)\s*W", text)
    return int(m.group(1)) if m else None


def _power_zone(ftp: int, lo_pct: int, hi_pct: int) -> tuple[int, int]:
    return round(ftp * lo_pct / 100.0), round(ftp * hi_pct / 100.0)


def _parse_surface_segments(text: str | None) -> list[tuple[float, float, float, str]]:
    """Odcinki nawierzchni >1 km, NIE-utwardzone (grunt/trawa/zwir/szuter/gravel itp.),
    sortowane malejaco wg dlugosci -> top 5. Zwraca [(km_from, km_to, dlugosc, surf), ...].
    Format wejscia (route_profile_detail): 'km 5.0-12.0 (7.0): szuter' lub 'km 5-12 szuter'."""
    if not text:
        return []
    segs: list[tuple[float, float, float, str]] = []
    for m in re.finditer(r"km\s*([\d.]+)\s*[-–]\s*([\d.]+)(?:\s*\(([\d.]+)\))?\s*:?\s*([^\n]+)", text):
        try:
            x = float(m.group(1))
            y = float(m.group(2))
        except (TypeError, ValueError):
            continue
        length = float(m.group(3)) if m.group(3) else (y - x)
        surf = (m.group(4) or "").strip()
        low = surf.lower()
        if not surf or "nieznana" in low or "unknown" in low:
            continue
        if any(p in low for p in _PAVED_SURF):
            continue
        if length > 1.0:
            segs.append((x, y, length, surf))
    segs.sort(key=lambda s: s[2], reverse=True)
    return segs[:5]


def _extract_wind(text: str | None) -> list[str]:
    """Bloki pod wiatr / w plecy z analizy planu (A4) - linie zawierajace 'wiatr'."""
    if not text:
        return []
    return [ln.strip() for ln in text.splitlines() if "wiatr" in ln.lower()]


def _parse_fuel_rates(text: str | None) -> tuple[str | None, str | None]:
    """Zywienie g/h i L/h z B2/B3. Zwraca (np. '60 g/h', '0.85 L/h')."""
    if not text:
        return None, None
    g = re.search(r"(\d+(?:\.\d+)?)\s*g/h", text)
    l = re.search(r"(\d+(?:\.\d+)?)\s*[lL]/h", text)
    return (g.group(0) if g else None, l.group(0) if l else None)


def _parse_wind_speed_kmh(text):
    """Wyciaga linie 'Sila wiatru: sr. X km/h, maks Y km/h' z tekstu briefu."""
    if not text:
        return None
    for ln in text.splitlines():
        ls = ln.strip()
        if ls.lower().startswith("sila wiatru:"):
            return ls
    return None


# ── TASK 12:
def _parse_precip_mm(text: str | None) -> float | None:
    """Opady mm z analizy planu (A5)."""
    if not text:
        return None
    m = re.search(r"opady\s*~?\s*([\d.]+)\s*mm", text)
    return float(m.group(1)) if m else None


def _parse_surf_segments_doc(text: str | None) -> list[tuple[float, float, str]]:
    """Odcinki nawierzchni z route_profile_detail — TYLKO z bloku 'Nawierzchnia (odcinki ...)'.
    Format realny: '  km 5.0-12.0 (7.0): szuter'. Akceptuje '-' i en-dash. Wymaga nawiasu (len),
    co odcina linie wysokosci ('km 10-11: +6 m') i podjazdow ('... (0.3 km): +16 m')."""
    if not text:
        return []
    seg_lines: list[str] = []
    capture = False
    for ln in text.splitlines():
        if "Nawierzchnia (odcinki" in ln:
            capture = True
            continue
        if capture:
            if ln.strip() == "" or "Wysokosci" in ln or "Podjazdy" in ln:
                break
            seg_lines.append(ln)
    scan = "\n".join(seg_lines) if seg_lines else text
    out: list[tuple[float, float, str]] = []
    for m in re.finditer(r"km\s+([\d.]+)\s*[-–]\s*([\d.]+)\s*\([\d.]+\)\s*:\s*([^\n]+)", scan):
        try:
            x = float(m.group(1)); y = float(m.group(2))
        except (TypeError, ValueError):
            continue
        surf = (m.group(3) or "").strip()
        if surf and y > x:
            out.append((x, y, surf))
    return out

def _merge_surface_segments(segs: list[tuple[float, float, str]], min_km: float = 0.5) -> list[tuple[float, float, str]]:
    """Scal sasiednie odcinki tej samej nawierzchni; zostaw scalone >= min_km (>500 m)."""
    if not segs:
        return []
    ordered = sorted(segs, key=lambda s: s[0])
    merged: list[list] = [list(ordered[0])]
    for x, y, s in ordered[1:]:
        if s == merged[-1][2] and abs(x - merged[-1][1]) < 1e-6:
            merged[-1][1] = y
        else:
            merged.append([x, y, s])
    return [(a, b, s) for a, b, s in merged if (b - a) >= min_km]


def _merge_surface_text(prof_txt: str | None, min_km: float = 0.3) -> str | None:
    """Zamienia blok 'Nawierzchnia (odcinki ...)' (ramki 80 m) na SCALONE zmiany >= min_km.
    Reszta profilu (naglowek, Wysokosci, Podjazdy) bez zmian. None -> None."""
    if not prof_txt:
        return prof_txt
    lines = prof_txt.splitlines()
    start = None
    end = None
    for i, ln in enumerate(lines):
        if "Nawierzchnia (odcinki" in ln:
            start = i
            continue
        if start is not None and (ln.strip() == "" or "Wysokosci" in ln or "Podjazdy" in ln):
            end = i
            break
    if start is None:
        return prof_txt
    if end is None:
        end = len(lines)
    merged = _merge_surface_segments(_parse_surf_segments_doc(prof_txt), min_km=min_km)
    new_block = [f"Nawierzchnia (zmiany nawierzchni, scalone >= {min_km * 1000:.0f} m):"]
    if merged:
        for a, b, s in merged:
            new_block.append(f"  km {a:g}-{b:g} ({b - a:g}): {s}")
    else:
        new_block.append("  brak odcinkow >= progu po scaleniu / dane niedostepne")
    return "\n".join(lines[:start] + new_block + lines[end:])


def _parse_wind_head_blocks(plan_txt: str | None) -> list[tuple[float, float]]:
    """Bloki pod wiatr z analizy planu (A4): linia '... Pod wiatr ...: km 10-20; km 35-40'."""
    if not plan_txt:
        return []
    blocks: list[tuple[float, float]] = []
    for line in plan_txt.splitlines():
        if "Pod wiatr" not in line:
            continue
        after = line.split(":", 1)[1] if ":" in line else line
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", after):
            blocks.append((float(m.group(1)), float(m.group(2))))
    return blocks


def _read_poi_positions_cache(route_id, start=None):
    """Czyta cache poi_positions_{route_id}.json (TASK 15 FAZA C). Zwraca [] gdy brak."""
    if not route_id:
        return []
    import json as _json
    from pathlib import Path as _P
    cache = _P(f"/opt/qbot/artifacts/reports/poi_positions_{route_id}.json")
    if not cache.exists():
        return []
    try:
        obj = _json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return []
    label_map = {"water": "woda", "hard_resupply": "sklep",
                 "soft_food_stop": "jedzenie", "attractions": "atrakcja"}
    out = []
    for key, label in label_map.items():
        v = obj.get(key)
        if not isinstance(v, list):
            continue
        for it in v:
            if not isinstance(it, dict):
                continue
            km = it.get("route_km")
            if km is None:
                continue
            name = it.get("name") or ""
            hours = it.get("open_hours") or it.get("hours") or ""
            desc = f"{label} ({name})" if name else label
            if hours and start:
                desc = f"{desc}, {hours}"
            try:
                out.append((float(km), desc))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda p: p[0])
    return out


def _parse_poi_km(poi_result: Any, route_id=None, start=None) -> list[tuple[float, str]]:
    """Punkty uzupelnienia jako [(km, typ), ...]. 16.f: najpierw cache poi_positions_{route_id}.json,
    potem _analysis(poi), potem report_json_path."""
    cached = _read_poi_positions_cache(route_id, start)
    if cached:
        return cached
    out: list[tuple[float, str]] = []
    txt = _analysis(poi_result)
    if txt:
        for m in re.finditer(r"km\s+([\d.]+)\s*[:\-]?\s*([^;,\n]*)", txt):
            try:
                out.append((float(m.group(1)), (m.group(2) or "").strip() or "punkt"))
            except (TypeError, ValueError):
                continue
    if not out and isinstance(poi_result, dict):
        data = poi_result.get("data") if isinstance(poi_result.get("data"), dict) else poi_result
        rjp = (data or {}).get("report_json_path")
        if rjp:
            try:
                import json as _json
                from pathlib import Path as _P
                obj = _json.loads(_P(rjp).read_text(encoding="utf-8"))
                label_map = {"water": "woda", "hard_resupply": "sklep",
                             "soft_food_stop": "jedzenie", "attractions": "atrakcja"}
                for key, label in label_map.items():
                    v = obj.get(key)
                    if isinstance(v, list):
                        for it in v:
                            if isinstance(it, dict) and it.get("route_km") is not None:
                                try:
                                    out.append((float(it["route_km"]), label))
                                except (TypeError, ValueError):
                                    continue
            except Exception:
                pass
    out.sort(key=lambda p: p[0])
    return out


def _infer_unknown_surface(plan_txt: str | None, temp_c: float | None, precip_mm: float | None) -> str:
    """Wnioskowanie o nawierzchni 'nieznana' z temp/opadow."""
    if temp_c is None:
        return "brak danych pogodowych do wnioskowania"
    if temp_c > 25 and (precip_mm is not None and precip_mm < 1):
        return (f"przy {temp_c:.0f}°C i braku opadów drogi leśne/polne prawdopodobnie "
                "przesuszone — ryzyko piachu")
    if temp_c > 25 and precip_mm is None:
        return (f"przy {temp_c:.0f}°C (brak danych o opadach) drogi nieutwardzone mogą być "
                "przesuszone — możliwy piach")
    return "warunki (wilgotno/chłodno) nie wskazują na istotne ryzyko piachu na nawierzchni nieznanej"


def _build_risk_combinations(surf_segments, wind_blocks_head, poi_list, dist_km):
    """Deterministyczne kombinacje ryzyk. surf_segments: [(from,to,surf)],
    wind_blocks_head: [(a,b)], poi_list: [km float], dist_km: float|None.
    Format: 'X. km A-B: [opis] -> [skutek]'."""
    def _offroad(s: str) -> bool:
        low = s.lower()
        return (not any(p in low for p in _PAVED_SURF)
                and "nieznana" not in low and "unknown" not in low)
    combos: list[str] = []
    n = 1
    for wa, wb in wind_blocks_head:
        parts: list[str] = []
        seg = next((s for s in surf_segments
                    if _offroad(s[2]) and s[0] < wb and s[1] > (wa - 5.0)), None)
        if seg:
            parts.append(f"nawierzchnia {seg[2].strip()} (km {seg[0]:g}–{seg[1]:g}) tuz przed/na odcinku pod wiatr")
        if dist_km:
            frac = wa / dist_km * 100.0
            if frac >= 50:
                parts.append(f"zmeczenie ~{frac:.0f}% trasy")
        near = any((wa - 5.0) <= p <= (wb + 2.0) for p in poi_list)
        if not near:
            parts.append("brak punktu uzupelnienia w poblizu")
        if parts:
            combos.append(f"{n}. km {wa:g}–{wb:g}: pod wiatr + " + " + ".join(parts)
                          + " → wieksze ryzyko utraty tempa i odwodnienia")
            n += 1
    for x, y, surf in surf_segments:
        if not _offroad(surf):
            continue
        ln = y - x
        if ln > 2.0 and dist_km and x >= dist_km / 2.0:
            frac = x / dist_km * 100.0
            combos.append(f"{n}. km {x:g}–{y:g}: {surf.strip()} ({ln:g} km) w drugiej polowie trasy "
                          f"+ zmeczenie ~{frac:.0f}% → wolniejsze tempo, wyzszy koszt energetyczny")
            n += 1
    return combos


# ── TASK 17: detekcja blokow, fazy, tabela ryzyk ──────────────────

def _parse_climbs_from_text(prof_txt):
    """Podjazdy z bloku 'Podjazdy ...' -> [(km_start, km_end, max_grade%), ...].
    Filtruje: dlugosc >= 0.2 km i max_grade >= 5.0%."""
    if not prof_txt:
        return []
    climbs = []
    in_block = False
    for line in prof_txt.splitlines():
        if "Podjazdy" in line and "%" in line:
            in_block = True
            continue
        if in_block:
            if not line.strip():
                break
            m = re.match(
                r"\s*km\s+([0-9.]+)\s*[-–]\s*([0-9.]+)\s*\([0-9.]+ km\).*?max\s+([0-9.]+)%",
                line,
            )
            if m:
                a, b, grade = float(m.group(1)), float(m.group(2)), float(m.group(3))
                if (b - a) >= 0.2 and grade >= 5.0:
                    climbs.append((a, b, grade))
    return climbs


def _parse_wind_blocks_with_kmh(plan_txt):
    """Bloki pod wiatr z analizy planu z km/h -> [(km_start, km_end, kmh), ...].
    Filtruje: dlugosc >= 3 km."""
    if not plan_txt:
        return []
    result = []
    for line in plan_txt.splitlines():
        if "Pod wiatr" not in line:
            continue
        after = line.split(":", 1)[1] if ":" in line else line
        kmh_m = re.search(r"\(~?([0-9.]+)\s*km/h\)", after)
        kmh = float(kmh_m.group(1)) if kmh_m else None
        for m in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)", after):
            a, b = float(m.group(1)), float(m.group(2))
            if (b - a) >= 3.0:
                result.append((a, b, kmh))
    return result


def _detect_blocks(surf_segments, climbs, wind_blocks, dist_km):
    """Wykrywa istotne bloki trasy (TASK 17).
    surf_segments: [(km_from, km_to, surf)], climbs: [(a, b, grade%)],
    wind_blocks: [(a, b, kmh|None)], dist_km: float.
    Zwraca list[dict] z km_start, km_end, factors, detail.
    Progi: podjazd >=5%/>=200m; pod wiatr >=3km (juz odfiltrowane);
    nieasfalt >2km (2.pol >1.5km); START 0-6km; KONIEC ostatnie ~10%."""
    def _offroad(s):
        low = s.lower()
        return not any(p in low for p in _PAVED_SURF) and "nieznana" not in low and "unknown" not in low

    raw = []
    start_end = min(6.0, dist_km * 0.08)
    raw.append({"km_start": 0.0, "km_end": start_end, "factors": ["start"],
                 "detail": {"start": f"km 0–{start_end:.0f}: zachowawcze tempo"}})

    for a, b, grade in climbs:
        raw.append({"km_start": a, "km_end": b, "factors": ["podjazd"],
                     "detail": {"podjazd": f"max {grade:.0f}%, {(b-a)*1000:.0f} m"}})

    for a, b, kmh in wind_blocks:
        kmh_str = f"~{kmh:.0f} km/h" if kmh is not None else ""
        raw.append({"km_start": a, "km_end": b, "factors": ["pod wiatr"],
                     "detail": {"pod wiatr": kmh_str}})

    half = dist_km / 2.0
    for x, y, surf in surf_segments:
        if not _offroad(surf):
            continue
        threshold = 1.5 if x >= half else 2.0
        if (y - x) > threshold:
            raw.append({"km_start": x, "km_end": y, "factors": ["nawierzchnia"],
                         "detail": {"nawierzchnia": surf.strip()}})

    endcap_start = dist_km * 0.90
    raw.append({"km_start": endcap_start, "km_end": dist_km, "factors": ["koncowka"],
                 "detail": {"koncowka": f"ostatnie 10% (km {endcap_start:.0f}–{dist_km:.0f}), jedz wg RPE"}})

    raw.sort(key=lambda blk: blk["km_start"])

    merged = []
    for blk in raw:
        if not merged or blk["km_start"] >= merged[-1]["km_end"]:
            merged.append({"km_start": blk["km_start"], "km_end": blk["km_end"],
                            "factors": list(blk["factors"]), "detail": dict(blk["detail"])})
        else:
            prev = merged[-1]
            prev["km_end"] = max(prev["km_end"], blk["km_end"])
            for f in blk["factors"]:
                if f not in prev["factors"]:
                    prev["factors"].append(f)
                    prev["detail"][f] = blk["detail"][f]
    return merged


def _build_phase_plan(blocks, ftp, dist_km, has_wavy=False):
    """Plan jazdy po fazach (wzorzec 2). Kazdy blok = faza z taktykami per factor
    i watami z FTP. Przerwy = faza toczna (tag 'falista' gdy has_wavy)."""
    ftp = ftp or 250

    def _w(lo, hi):
        a, b = _power_zone(ftp, lo, hi)
        return f"{a}–{b} W"

    lines = ["### PLAN JAZDY PO FAZACH", ""]
    prev_km = 0.0

    def _rolling(km_a, km_b):
        label = "FAZA TOCZNA"
        if has_wavy:
            label += " (falista, faldy 3–5%)"
        z2 = _w(60, 75)
        lines.append(f"**km {km_a:.0f}–{km_b:.0f}: {label}**")
        note = " Faldy — nie forsuj, kontroluj kadencje." if has_wavy else ""
        lines.append(f"  Jedz swobodnie Z2 {z2}.{note}")
        lines.append("")

    for blk in blocks:
        a, b = blk["km_start"], blk["km_end"]
        if a > prev_km + 0.5:
            _rolling(prev_km, a)
        parts = []
        for f in blk["factors"]:
            d = blk["detail"].get(f, "")
            parts.append(f.upper() + (f" ({d})" if d else ""))
        lines.append(f"**km {a:.0f}–{b:.0f}: {' + '.join(parts)}**")
        for factor in blk["factors"]:
            if factor == "start":
                lines.append(f"  START: zachowaj sie, nie wchodz powyzej Z2. Moc: {_w(60,75)}.")
            elif factor == "podjazd":
                lines.append(f"  PODJAZD: trzymaj Z3/Z4 chwilowo ({_w(76,90)} / {_w(91,100)}), jedz pod moc i tetno.")
            elif factor == "pod wiatr":
                lines.append(f"  POD WIATR: aero, Z2 srodek ({_w(65,75)}). Nie scigaj sie ze stadem.")
            elif factor == "nawierzchnia":
                lines.append(f"  NAWIERZCHNIA: obniz moc do Z2 dol ({_w(60,70)}), kontroluj linie jazdy.")
            elif factor == "koncowka":
                lines.append(f"  KONCOWKA: jedz wg RPE, nie wg predkosci. Moc: {_w(55,70)} lub nizej.")
        lines.append("")
        prev_km = b

    if dist_km > prev_km + 0.5:
        _rolling(prev_km, dist_km)

    lines.append("_Zasada: jedz pod koszt fizjologiczny (moc+tetno+RPE+temp), nie pod stala predkosc._")
    return "\n".join(lines)


def _build_risk_table(blocks):
    """Tabela ryzyk (wzorzec 3) z tych samych blokow.
    Poziom: >=2 factors lub nieasfalt+pod wiatr -> wysokie; 1 istotny -> srednie."""
    _SKIP = {"start"}
    lines = ["### TABELA RYZYK", ""]
    lines.append("| km | poziom | powod |")
    lines.append("|---|---|---|")
    has_rows = False
    for blk in blocks:
        a, b = blk["km_start"], blk["km_end"]
        factors = [f for f in blk["factors"] if f not in _SKIP]
        if not factors:
            continue
        offroad = "nawierzchnia" in factors
        wind = "pod wiatr" in factors
        n = len(factors)
        if n >= 2 or (offroad and wind):
            level = "wysokie"
        elif n == 1:
            level = "srednie" if factors[0] in ("podjazd", "pod wiatr", "nawierzchnia", "koncowka") else "niskie"
        else:
            level = "niskie"
        powod = " + ".join(factors)
        details = [blk["detail"].get(f, "") for f in factors if blk["detail"].get(f)]
        if details:
            powod += f" ({'; '.join(details)})"
        lines.append(f"| km {a:.0f}–{b:.0f} | {level} | {powod} |")
        has_rows = True
    if not has_rows:
        lines.append("| – | – | brak istotnych blokow ryzyka |")
    return "\n".join(lines)


def _build_context_document(plan, prof, t, fuel, tp, poi, wellness, start, route_id=None) -> str:
    """TASK 12: jeden ustrukturyzowany dokument kontekstowy dla Alberta.
    Sekcje osobiste (FORMA/SPRZET/B2B3) pojawiaja sie tylko gdy podano ich dane
    (wellness/tp/fuel) - dla wariantu 'grupa' sa None i sa pomijane."""
    plan_txt = _analysis(plan) if plan else None
    prof_txt = _analysis(prof) if prof else None
    t_txt = _analysis(t) if t else None
    fuel_txt = _analysis(fuel) if fuel else None
    tp_txt = _analysis(tp) if tp else None

    dist_km = None
    out: list[str] = ["## DOKUMENT KONTEKSTOWY TRASY", ""]

    out.append("### DANE TRASY")
    if plan_txt:
        for line in plan_txt.splitlines():
            ls = line.strip()
            if ls.startswith("Dystans:") or ls.startswith("Stromizny:") or ls.startswith("Nawierzchnia:"):
                out.append(f"- {ls}")
            if ls.startswith("Dystans:"):
                md = re.search(r"([\d.]+)\s*km", ls)
                if md:
                    dist_km = float(md.group(1))
    else:
        out.append("- brak danych planu trasy")
    out.append("")

    out.append("### PROFIL WYSOKOSCIOWY")
    prof_added = False
    if prof_txt:
        capture = False
        for line in prof_txt.splitlines():
            if "Podjazdy" in line:
                capture = True
                out.append(f"- {line.strip()}")
                continue
            if capture:
                if line.strip() == "":
                    break
                out.append(f"  {line.strip()}")
                prof_added = True
    if not prof_added:
        out.append("- brak wyroznionych podjazdow / profil niedostepny")
    out.append("")

    out.append("### NAWIERZCHNIA (odcinki scalone > 500 m)")
    all_segs = _parse_surf_segments_doc(prof_txt)
    merged = _merge_surface_segments(all_segs, min_km=0.5)
    if merged:
        out.append("| km od | km do | typ | dlugosc |")
        out.append("|---|---|---|---|")
        for a, b, s in merged:
            out.append(f"| {a:g} | {b:g} | {s} | {b - a:g} km |")
    else:
        out.append("- brak odcinkow nawierzchni > 500 m / dane niedostepne")
    # 16.b: asercja kompletnosci tabeli nawierzchni
    if all_segs and dist_km is not None:
        last_end = max(seg[1] for seg in all_segs)
        if dist_km - last_end > 0.3:
            out.append(f"⚠️ UWAGA: brak danych nawierzchni km {last_end:g}–{dist_km:g} (tabela niekompletna)")
    elif not all_segs and dist_km is not None:
        out.append(f"⚠️ UWAGA: brak danych nawierzchni na całej trasie (km 0–{dist_km:g})")
    out.append("")

    temp_c = _parse_temp_c(plan_txt)
    precip_mm = _parse_precip_mm(plan_txt)
    out.append("### POGODA")
    if temp_c is not None:
        out.append(f"- Temperatura: ~{temp_c:.0f}°C")
    if precip_mm is not None:
        out.append(f"- Opady: ~{precip_mm:.1f} mm na trasie")
    wind_lines = [ln.strip() for ln in (plan_txt or "").splitlines() if "wiatr" in ln.lower()]
    for wl in wind_lines:
        out.append(f"- {wl}")
    wind_kmh = _parse_wind_speed_kmh(plan_txt)
    if wind_kmh:
        out.append(f"- {wind_kmh}")
    else:
        out.append("- Wiatr (km/h): brak danych")
    if temp_c is None and precip_mm is None and not wind_lines:
        out.append("- brak danych pogodowych")
    out.append("")

    if wellness:
        out.append("### FORMA ZAWODNIKA (FTP + strefy mocy)")
        out.append(f"- {wellness}")
        ftp = _parse_ftp_w(plan_txt)
        if ftp:
            z2 = _power_zone(ftp, 60, 75)
            z3 = _power_zone(ftp, 76, 90)
            z4 = _power_zone(ftp, 91, 100)
            out.append(f"- FTP: {ftp} W")
            out.append(f"- Z2 (60–75% FTP): {z2[0]}–{z2[1]} W")
            out.append(f"- Z3 (76–90% FTP): {z3[0]}–{z3[1]} W")
            out.append(f"- Z4 (91–100% FTP): {z4[0]}–{z4[1]} W")
        else:
            out.append("- FTP: brak danych w analizie planu")
        out.append("")

    if tp_txt:
        out.append("### SPRZET (B5 cisnienie)")
        for line in tp_txt.splitlines():
            if line.strip():
                out.append(f"- {line.strip()}")
        out.append("")

    if fuel_txt:
        out.append("### WYLICZENIA (B2/B3 zywienie, B4 czas)")
    else:
        out.append("### WYLICZENIA (B4 czas)")
    dur = _parse_duration_h(t_txt)
    if dur is not None:
        h = int(dur); mnt = int(round((dur - h) * 60))
        out.append(f"- B4 czas przejazdu: ~{h}:{mnt:02d} h")
    elif t_txt:
        out.append("- B4 czas: " + t_txt.splitlines()[0].strip())
    else:
        out.append("- B4 czas: brak danych")
    if fuel_txt:
        g, l = _parse_fuel_rates(fuel_txt)
        if g or l:
            out.append("- B2/B3 zywienie: " + ", ".join(s for s in (g, l) if s))
        else:
            out.append("- B2/B3 zywienie: brak danych")
    out.append("")

    out.append("### PUNKTY UZUPELNIENIA")
    poi_pts = _parse_poi_km(poi, route_id=route_id, start=start)
    if poi_pts:
        for km, typ in poi_pts:
            out.append(f"- km {km:g}: {typ}")
        for (k1, _), (k2, _) in zip(poi_pts, poi_pts[1:]):
            if (k2 - k1) > 20:
                out.append(f"⚠️ UWAGA: przerwa {k2 - k1:g} km bez pewnego punktu (km {k1:g}–{k2:g})")
    else:
        out.append("- brak listy punktow uzupelnienia (czytaj raport POI)")
    out.append("")

    out.append("### KOMBINACJE RYZYK")
    wind_blocks = _parse_wind_head_blocks(plan_txt)
    poi_km_list = [k for k, _ in poi_pts]
    combos = _build_risk_combinations(all_segs, wind_blocks, poi_km_list, dist_km)
    if combos:
        out.extend(combos)
    else:
        out.append("brak zidentyfikowanych kombinacji ryzyk z dostepnych danych")
    out.append("")

    out.append("### NIEZNANA NAWIERZCHNIA")
    unknown_segs = [s for s in all_segs if "nieznana" in s[2].lower() or "unknown" in s[2].lower()]
    if unknown_segs:
        km_list = "; ".join(f"km {a:g}–{b:g}" for a, b, _ in unknown_segs)
        out.append(f"- Odcinki nieznane: {km_list}")
    out.append(f"- Wnioskowanie: {_infer_unknown_surface(plan_txt, temp_c, precip_mm)}")
    out.append("")

    # ── TASK 17: PLAN JAZDY PO FAZACH + TABELA RYZYK
    _blocks17: list = []
    _ftp17 = _parse_ftp_w(plan_txt)
    _climbs17 = _parse_climbs_from_text(prof_txt)
    _wind17 = _parse_wind_blocks_with_kmh(plan_txt)
    _has_wavy17 = "Falistosc:" in (prof_txt or "") and "brak odcinkow" not in (prof_txt or "")
    if dist_km:
        _blocks17 = _detect_blocks(merged, _climbs17, _wind17, dist_km)

    if dist_km and _blocks17:
        out.append(_build_phase_plan(_blocks17, _ftp17, dist_km, has_wavy=_has_wavy17))
    else:
        out.append("### PLAN JAZDY PO FAZACH")
        out.append("- brak danych dystansu lub blokow")
    out.append("")

    if _blocks17:
        out.append(_build_risk_table(_blocks17))
    else:
        out.append("### TABELA RYZYK")
        out.append("- brak blokow ryzyka / dystans niedostepny")
    out.append("")

    return "\n".join(out).rstrip()


def _build_forma_line(start: Any) -> str:
    """ZMIANA 2 (TASK10): forma dnia z xert_readiness + wellness_day (gdy podano date startu).
    Wyciaga TP, HIE, forma, HRV, Body Battery. Brak startu -> komunikat."""
    if not start:
        return "FORMA DNIA: nie podano daty startu"
    combined = ""
    try:
        combined += (_analysis(_call_tool("xert_readiness", {})) or "") + "\n"
    except Exception:
        pass
    try:
        combined += (_analysis(_call_tool("wellness_day", {"date": str(start)[:10]})) or "")
    except Exception:
        pass
    parts: list[str] = []
    for label, pat in (
        ("TP", r"\bTP[:\s]+(-?\d+(?:\.\d+)?)"),
        ("HIE", r"\bHIE[:\s]+(\d+(?:\.\d+)?)"),
        ("forma", r"[Ff]orma(?:/TSB)?[:\s]+(-?\d+(?:\.\d+)?)"),
        ("HRV", r"\bHRV[:\s]+(\d+(?:\.\d+)?)"),
        ("Body Battery", r"Body Battery[:\s]+(\d+)"),
    ):
        m = re.search(pat, combined)
        if m:
            parts.append(f"{label} {m.group(1)}")
    if parts:
        return "FORMA DNIA: " + ", ".join(parts)
    return f"FORMA DNIA: dane formy niedostepne (start {str(start)[:10]})"


def _build_section_c_brief(sections_data: dict[str, Any] | None) -> str:
    """ZMIANA 1 (TASK10): zwiezly brief z KONKRETNYMI liczbami z zebranych wynikow
    (plan, prof, t, fuel, tp, forma) zamiast surowego tekstu A/B. Trafia do LLM (sekcja C).
    sections_data: {plan, prof, t, fuel, tp, forma, variant}."""
    sd = sections_data or {}
    variant = sd.get("variant", "pelny")
    plan_txt = _analysis(sd.get("plan")) if sd.get("plan") else None
    prof_txt = _analysis(sd.get("prof")) if sd.get("prof") else None
    t_txt = _analysis(sd.get("t")) if sd.get("t") else None
    fuel_txt = _analysis(sd.get("fuel")) if sd.get("fuel") else None
    tp_txt = _analysis(sd.get("tp")) if sd.get("tp") else None

    out: list[str] = ["BRIEF DO OCENY (konkretne liczby z narzedzi QBot):", ""]

    if variant == "pelny":
        ftp = _parse_ftp_w(plan_txt)
        if ftp:
            e_lo, e_hi = _power_zone(ftp, 55, 75)
            t_lo, t_hi = _power_zone(ftp, 76, 90)
            out.append(f"MOC (FTP {ftp} W):")
            out.append(f"- endurance (55-75% FTP): {e_lo}–{e_hi} W")
            out.append(f"- tempo (76-90% FTP): {t_lo}–{t_hi} W")
        else:
            out.append("MOC: brak FTP w danych planu.")
        out.append("")

    segs = _parse_surface_segments(prof_txt)
    if segs:
        out.append("NAWIERZCHNIA (odcinki off-road >1 km, top 5 wg dlugosci):")
        for x, y, ln, surf in segs:
            out.append(f"- km {x:g}–{y:g}: {surf} ({ln:g} km)")
    else:
        out.append("NAWIERZCHNIA: brak odcinkow off-road >1 km w profilu.")
    out.append("")

    winds = _extract_wind(plan_txt)
    if winds:
        out.append("WIATR (bloki z planu):")
        out.extend(f"- {w}" for w in winds)
    else:
        out.append("WIATR: brak wyroznionych blokow wiatru w planie.")
    out.append("")

    dur = _parse_duration_h(t_txt)
    if dur is not None:
        h = int(dur)
        mnt = int(round((dur - h) * 60))
        out.append(f"CZAS (B4): ~{h}:{mnt:02d} h przejazdu.")
    elif t_txt:
        out.append("CZAS (B4): " + t_txt.splitlines()[0].strip())
    else:
        out.append("CZAS (B4): brak danych.")
    out.append("")

    if variant == "pelny":
        g, l = _parse_fuel_rates(fuel_txt)
        if g or l:
            out.append("ZYWIENIE (B2/B3): " + ", ".join(s for s in (g, l) if s) + ".")
        else:
            out.append("ZYWIENIE (B2/B3): brak danych.")
        if tp_txt:
            lines_ne = [ln.strip() for ln in tp_txt.splitlines() if ln.strip()]
            wheel = next((ln.lstrip("# ").strip() for ln in lines_ne
                          if "Zipp" in ln and ("Zestaw" in ln or "główny" in ln.lower())), None)
            if wheel is None:
                wheel = next((ln.lstrip("# ").strip() for ln in lines_ne if "Zipp" in ln), None)
            opona = next((ln for ln in lines_ne if ln.lower().startswith("opona")), None)
            gravel = next((ln for ln in lines_ne
                           if "luźny szuter" in ln.lower() or "żwir" in ln.lower()), None)
            picked = [x for x in (wheel, opona, gravel) if x]
            out.append("SPRZET/CISNIENIE (B5): " + (" | ".join(picked) if picked else lines_ne[0]))
        else:
            out.append("SPRZET/CISNIENIE (B5): brak danych.")
        out.append("")
        out.append(sd.get("forma") or "FORMA DNIA: nie podano daty startu")

    return "\n".join(out).rstrip()


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
    surface_detail = bool(a.get("surface_detail"))

    base_args: dict[str, Any] = {}
    if route_id:
        base_args["route_id"] = route_id

    collected: dict[str, Any] = {"variant": variant}
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
    collected["plan"] = plan
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
        H("## A3 - NAWIERZCHNIA I PROFIL ODCINKAMI")
        surface_profile = None
        try:
            from qbot_route_tools import _fetch_best_route_surface_profile as _fetch_surface_profile
            surface_profile = _fetch_surface_profile(route_id=route_id, route_artifact_id=base_args.get("artifact_id"))
        except Exception:
            surface_profile = None

        if surface_profile and surface_profile.get("good_profile"):
            surface_line = _surface_profile_render_line(surface_profile)
            H("SZCZEGOLOWY PROFIL TRASY (surface_summary_json)")
            H(
                "Nawierzchnia: "
                f"{surface_line} (źródło: surface_summary_json)"
            )
            H(
                "Profil jakości: "
                f"{surface_profile.get('quality_status')} | coverage {surface_profile.get('coverage_pct'):.0f}% | "
                f"tagged {surface_profile.get('tagged_surface_pct'):.1f}% | "
                f"inferred {surface_profile.get('inferred_surface_pct'):.1f}% | "
                f"unknown {surface_profile.get('unknown_surface_pct'):.1f}%"
            )
            H(
                "Źródło profilu: qbot_v2.route_surface_profiles.surface_summary_json "
                f"(route_surface_profiles.id={surface_profile.get('id')}, route_artifact_id={surface_profile.get('route_artifact_id')}, enriched_at={surface_profile.get('enriched_at')})"
            )
            collected["surface_profile"] = surface_profile
        else:
            prof = _call_tool("route_profile_detail", dict(base_args))
            collected["prof"] = prof
            if _ok(prof) and _analysis(prof):
                _prof_txt = _analysis(prof)
                H(_prof_txt if surface_detail else (_merge_surface_text(_prof_txt, 0.3) or _prof_txt))
                H("")
                H("_UWAGA: legacy surface path (route_frames / route_surface_segments) — brak dobrego profilu surface_summary_json._")
            else:
                H(f"_Szczegolowy profil niedostepny: {_reason(prof)}_")
        H("")

        H("## A3B - DIAGNOSTYKA JAKOŚCI")
        for line in _surface_quality_lines(surface_profile):
            H(line)
        H("")

        H("## A3C - GEOLOGIA / PODŁOŻE")
        for line in _geology_lines(surface_profile):
            H(line)
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
            poi = _read_poi_analysis_cache(route_id)
            if not poi:
                poi = {
                    "status": "PARTIAL",
                    "data": {
                        "counts": {"water": None, "food": None, "attractions": None},
                        "report_path": None,
                        "report_json_path": None,
                    },
                    "warning": "POI cache unavailable; legacy route_poi_analyze_readonly intentionally skipped to avoid blocking public report",
                }
            collected["poi"] = poi
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
    collected["t"] = t
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
        collected["fuel"] = fuel
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
        collected["tp"] = tp
        H("### B5 - Cisnienie opon")
        if _ok(tp) and _analysis(tp):
            H(_analysis(tp))
        else:
            H(f"_B5 niedostepne: {_reason(tp)}_")
        H("")

    collected["forma"] = _build_forma_line(start) if variant == "pelny" else None
    context_doc = _build_context_document(
        collected.get("plan"), collected.get("prof"), collected.get("t"),
        collected.get("fuel"), collected.get("tp"), collected.get("poi"),
        collected.get("forma"), start, route_id=route_id,
    )
    # DOKUMENT KONTEKSTOWY nie idzie do widocznego raportu — tylko do context_for_section_c.
    # ---- C: ocena (sam naglowek; tresc C dopisuje Albert deterministycznie w albert.py) ----
    if variant in ("pelny", "grupa"):
        H("## C - OCENA")

    prompt_C = (
        "Masz kompletne dane powyzej. Napisz TYLKO sekcję C: "
        "C1 TAKTYKA (2-3 zdania z km i watami), "
        "C2 PUNKTY RYZYKA (max 3, każdy 1 zdanie: km X–Y + powód), "
        "C3 SPRZĘT (1-2 zdania, tylko pelny), "
        "C4 NAJWIĘKSZE ZAGROŻENIE (1 zdanie: km + powód + skutek). "
        "Oznaczaj '(ocena)'. Max 8 zdań łącznie."
    )
    context_for_c = f"{context_doc}\n\n{prompt_C}" if variant in ("pelny", "grupa") else None

    analysis_text =  "\n".join(sections).rstrip() + "\n"
    note = ("Raport zlozony z gotowych narzedzi (orkiestracja). Sekcje A/B pochodza 1:1 "
            "z narzedzi - pokaz je w calosci. ")
    note += ("Wariant skrocony nie ma sekcji C." if variant == "skrocony"
             else "Sekcja C wygenerowana przez Alberta na podstawie dokumentu kontekstowego.")

    return {
        "status": "OK",
        "variant": variant,
        "route_id": route_id,
        "analysis": analysis_text,
        "context_for_section_c": context_for_c,
        "notes": note,
    }
