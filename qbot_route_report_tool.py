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

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from qbot3.routes.route_canonical_read import read_canonical_route

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


def _read_route_source(route_id: str | None) -> dict[str, Any] | None:
    if not route_id:
        return None
    try:
        data = read_canonical_route(route_id=route_id)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _route_shade_section_lines(route_source: dict[str, Any] | None) -> list[str]:
    if not isinstance(route_source, dict):
        return []
    if str(route_source.get("land_cover_preferred_source") or "").strip() != "worldcover_shade":
        return []
    try:
        shade_count = int(route_source.get("route_shade_layer_count") or 0)
    except (TypeError, ValueError):
        shade_count = 0
    if shade_count <= 0:
        return []

    try:
        shade_coverage_pct = float(route_source.get("shade_coverage_pct") or 0.0)
    except (TypeError, ValueError):
        shade_coverage_pct = 0.0
    layer_counts = route_source.get("layer_counts") or {}
    route_base_id = route_source.get("route_base_id")
    route_version_key = route_source.get("route_version_key")
    return [
        "## A0B - OTOCZENIE TRASY (WorldCover / route_shade_layer)",
        "- źródło: WorldCover v200 przez route_shade_layer",
        f"- route_shade_layer: {shade_count} próbek/przekrojów",
        f"- pokrycie: {shade_coverage_pct:.1f}%",
        "- opis: przekrój otoczenia lewo / środek / prawo względem osi trasy; warstwa jest czytana addytywnie i nie udaje starego landcover",
        "- termin produktu: otoczenie trasy",
        *(
            [
                f"- route_base_id={route_base_id}",
                f"- route_version_key={route_version_key}",
            ]
            if route_base_id is not None or route_version_key is not None
            else []
        ),
        *(
            [
                "- layer_counts: "
                + ", ".join(
                    f"{key}={layer_counts.get(key)}"
                    for key in ("route_shade_layer",)
                    if layer_counts.get(key) is not None
                )
            ]
            if isinstance(layer_counts, dict)
            else []
        ),
        "",
    ]


def _route_elevation_section_lines(route_source: dict[str, Any] | None) -> list[str]:
    if not isinstance(route_source, dict):
        return []
    layer_counts = route_source.get("layer_counts") or {}
    if not isinstance(layer_counts, dict):
        layer_counts = {}

    def _layer_count(key: str) -> int:
        raw = route_source.get(key)
        if raw is None:
            raw = layer_counts.get(key)
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    elevation_samples = _layer_count("route_elevation_samples")
    climb_events = _layer_count("route_climb_events")
    if elevation_samples <= 0 and climb_events <= 0:
        return []

    summary = route_source.get("canonical_elevation_summary")
    if not isinstance(summary, dict):
        summary = {}

    def _fmt_m(value: Any) -> str:
        try:
            return f"{float(value):.1f} m"
        except (TypeError, ValueError):
            return "brak"

    def _fmt_pct(value: Any) -> str:
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return "brak"

    def _fmt_km(value: Any) -> str:
        try:
            return f"{float(value):.3f}"
        except (TypeError, ValueError):
            return "brak"

    route_base_id = route_source.get("route_base_id")
    route_version_key = route_source.get("route_version_key")
    lines = [
        "## A0C - PROFIL WYSOKOŚCI / PODJAZDY (canonical route_elevation_samples / route_climb_events)",
        "- źródło: canonical route_elevation_samples + route_climb_events",
        f"- profil wysokości: sample_count={int(summary.get('sample_count') or elevation_samples)} | climb_event_count={int(summary.get('climb_event_count') or climb_events)}",
        "- opis: to warstwa canonical, a nie legacy profil raportowy; służy do pokazywania sygnatury przewyższeń i podjazdów",
        *(
            [
                f"- route_base_id={route_base_id}",
                f"- route_version_key={route_version_key}",
            ]
            if route_base_id is not None or route_version_key is not None
            else []
        ),
    ]
    if summary:
        min_elevation = summary.get("min_elevation_m")
        max_elevation = summary.get("max_elevation_m")
        elevation_range = summary.get("elevation_range_m")
        ascent_smoothed = summary.get("ascent_smoothed_m")
        descent_smoothed = summary.get("descent_smoothed_m")
        smoothing_version = summary.get("smoothing_version")
        smoothing_method = summary.get("smoothing_method")
        max_climb_event_gradient = summary.get("max_climb_event_gradient_pct")
        raw_sample_max_grade = summary.get("raw_sample_max_grade_pct")
        lines.extend(
            [
                "- elevation: "
                f"min={_fmt_m(min_elevation)} | max={_fmt_m(max_elevation)} | range={_fmt_m(elevation_range)}",
                "- smoothing: "
                f"ascent_smoothed={_fmt_m(ascent_smoothed)} | "
                f"descent_smoothed={_fmt_m(descent_smoothed)} | "
                f"smoothing_version={smoothing_version or 'brak'} | "
                f"smoothing_method={smoothing_method or 'brak'}",
            ]
        )
        if max_climb_event_gradient is not None:
            lines.append(f"- climb_events: max_gradient={_fmt_pct(max_climb_event_gradient)}")
        if raw_sample_max_grade is not None:
            lines.append(
                "- raw sample diagnostics: "
                f"max_grade={_fmt_pct(raw_sample_max_grade)} "
                "(diagnostyka próbek, nie oficjalna ścianka)"
            )
        top_events = summary.get("top_climb_events") if isinstance(summary.get("top_climb_events"), list) else []
        if top_events:
            lines.append("- top climb_events:")
            for idx, event in enumerate(top_events[:3], start=1):
                if not isinstance(event, dict):
                    continue
                km_from = _fmt_km(event.get("km_from"))
                km_to = _fmt_km(event.get("km_to"))
                length_m = _fmt_m(event.get("length_m"))
                gain_m = _fmt_m(event.get("elevation_gain_m"))
                avg_gradient_pct = _fmt_pct(event.get("avg_gradient_pct"))
                max_gradient_pct = _fmt_pct(event.get("max_gradient_pct"))
                severity = str(event.get("severity") or "brak").strip() or "brak"
                lines.append(
                    f"  {idx}. km {km_from}–{km_to} | length={length_m} | gain={gain_m} | "
                    f"avg={avg_gradient_pct} | max={max_gradient_pct} | severity={severity}"
                )
        note = summary.get("short_wall_detection_note")
        if note:
            lines.append(f"- limitation: {note}")
    else:
        lines.append(
            "- limitation: profil 50 m / climb events mogą pokazywać sygnaturę podjazdów, "
            "ale bardzo krótkie strome rampy mogą umknąć"
        )
    lines.append("")
    return lines


def _route_surface_summary_lines(summary: dict[str, Any] | None) -> list[str]:
    if not isinstance(summary, dict):
        return []

    try:
        segment_count = int(summary.get("segment_count") or 0)
    except (TypeError, ValueError):
        segment_count = 0
    if segment_count <= 0:
        return []

    total_distance_m = summary.get("total_distance_m")
    coverage_pct = summary.get("coverage_pct")
    tagged_surface_pct = summary.get("tagged_surface_pct")
    inferred_surface_pct = summary.get("inferred_surface_pct")
    tagged_surface_segment_count = summary.get("tagged_surface_segment_count")
    inferred_surface_segment_count = summary.get("inferred_surface_segment_count")
    by_surface = summary.get("by_surface") if isinstance(summary.get("by_surface"), dict) else {}
    by_confidence = summary.get("by_confidence") if isinstance(summary.get("by_confidence"), dict) else {}
    problem_segments = summary.get("problem_segments") if isinstance(summary.get("problem_segments"), list) else []
    overpass_bits = []
    for key, label in (
        ("overpass_chunks_total", "chunks_total"),
        ("overpass_chunks_ok", "chunks_ok"),
        ("overpass_chunks_failed", "chunks_failed"),
        ("overpass_timeout_count", "timeout_count"),
        ("overpass_http_error_count", "http_error_count"),
    ):
        value = summary.get(key)
        if value is not None:
            overpass_bits.append(f"{label}={value}")
    lines = [
        "Źródło nawierzchni: canonical_surface_summary / route_surface_layer",
        f"segment_count={segment_count}",
        (
            f"total_distance_m={float(total_distance_m or 0.0) / 1000.0:.1f} km"
            if total_distance_m is not None
            else "total_distance_m=brak"
        ),
        (
            f"coverage_pct={float(coverage_pct or 0.0):.1f}%"
            if coverage_pct is not None
            else "coverage_pct=brak"
        ),
        (
            "tagged_surface_pct="
            f"{float(tagged_surface_pct or 0.0):.1f}% | "
            f"inferred_surface_pct={float(inferred_surface_pct or 0.0):.1f}%"
            if tagged_surface_pct is not None and inferred_surface_pct is not None
            else "tagged_surface_pct=brak | inferred_surface_pct=brak"
        ),
        (
            "tagged_surface_segments="
            f"{int(tagged_surface_segment_count or 0)} | "
            f"inferred_surface_segments={int(inferred_surface_segment_count or 0)}"
            if tagged_surface_segment_count is not None and inferred_surface_segment_count is not None
            else "tagged_surface_segments=brak | inferred_surface_segments=brak"
        ),
        "coverage_pct nie oznacza 100% tagów surface=* w OSM",
        "by_surface:",
    ]
    for surface, payload in sorted(by_surface.items()):
        if not isinstance(payload, dict):
            continue
        distance_m = payload.get("distance_m")
        pct = payload.get("pct")
        segment_ct = payload.get("segment_count")
        lines.append(
            f"- {surface}: {float(distance_m or 0.0) / 1000.0:.1f} km | "
            f"{float(pct or 0.0):.1f}% | segments={int(segment_ct or 0)}"
        )
    if by_confidence:
        conf_bits = []
        for key, payload in sorted(by_confidence.items()):
            if isinstance(payload, dict):
                conf_bits.append(f"{key}={int(payload.get('segment_count') or 0)}")
        if conf_bits:
            lines.append("by_confidence: " + ", ".join(conf_bits))
    if overpass_bits:
        lines.append("overpass: " + ", ".join(overpass_bits))
    lines.append(f"problem_segments_count={len(problem_segments)}")
    return lines


def _route_surface_section_lines(route_source: dict[str, Any] | None) -> list[str]:
    if not isinstance(route_source, dict):
        return []
    return _route_surface_summary_lines(route_source.get("canonical_surface_summary"))


def _route_surface_quality_lines_from_summary(summary: dict[str, Any] | None) -> list[str]:
    if not isinstance(summary, dict):
        return []
    by_confidence = summary.get("by_confidence") if isinstance(summary.get("by_confidence"), dict) else {}
    problem_segments = summary.get("problem_segments") if isinstance(summary.get("problem_segments"), list) else []
    coverage_pct = summary.get("coverage_pct")
    tagged_surface_pct = summary.get("tagged_surface_pct")
    inferred_surface_pct = summary.get("inferred_surface_pct")
    overpass_bits = []
    for key, label in (
        ("overpass_chunks_total", "chunks_total"),
        ("overpass_chunks_ok", "chunks_ok"),
        ("overpass_chunks_failed", "chunks_failed"),
        ("overpass_timeout_count", "timeout_count"),
        ("overpass_http_error_count", "http_error_count"),
    ):
        value = summary.get(key)
        if value is not None:
            overpass_bits.append(f"{label}={value}")
    lines = ["Źródło nawierzchni: canonical_surface_summary / route_surface_layer"]
    if coverage_pct is not None:
        lines.append(f"coverage_pct={float(coverage_pct or 0.0):.1f}%")
    if tagged_surface_pct is not None and inferred_surface_pct is not None:
        lines.append(
            f"tagged_surface_pct={float(tagged_surface_pct or 0.0):.1f}% | "
            f"inferred_surface_pct={float(inferred_surface_pct or 0.0):.1f}%"
        )
    if by_confidence:
        conf_bits = []
        for key, payload in sorted(by_confidence.items()):
            if isinstance(payload, dict):
                conf_bits.append(f"{key}={int(payload.get('segment_count') or 0)}")
        if conf_bits:
            lines.append("by_confidence: " + ", ".join(conf_bits))
    if overpass_bits:
        lines.append("overpass: " + ", ".join(overpass_bits))
    lines.append("coverage_pct nie oznacza 100% tagów surface=* w OSM")
    lines.append(f"problem_segments_count={len(problem_segments)}")
    return lines


def _route_surface_geology_lines_from_summary(summary: dict[str, Any] | None) -> list[str]:
    if not isinstance(summary, dict):
        return []
    return ["Geologia / podłoże: brak danych w canonical_surface_summary"]


def _route_surface_context_lines(route_source: dict[str, Any] | None) -> list[str]:
    """Renderuje warstwe route_surface_context: odcinki BEZ tagu -> szacunek ryzyka piachu."""
    if not isinstance(route_source, dict):
        return []
    ctx = route_source.get("canonical_surface_context")
    if not isinstance(ctx, dict) or int(ctx.get("segment_count") or 0) <= 0:
        return []
    risk_counts = ctx.get("risk_counts") if isinstance(ctx.get("risk_counts"), dict) else {}
    elevated = ctx.get("elevated") if isinstance(ctx.get("elevated"), list) else []
    sand_high = float(ctx.get("sand_km_high") or 0.0)
    sand_med = float(ctx.get("sand_km_medium") or 0.0)
    lines = [
        "Źródło: route_surface_context (odcinki BEZ tagu OSM — szacunek z otoczenia WorldCover + geologii)",
        "UWAGA: tag OSM zawsze wygrywa; poniższe odcinki nie mają tagu — to szacunek ryzyka, nie pomiar",
    ]
    order = ("WYSOKIE", "SREDNIE", "UMIARK.", "NISKO-SR", "NISKIE", "?")
    counts_bits = [f"{k}={risk_counts[k]}" for k in order if risk_counts.get(k)]
    lines.append("Odcinki bez tagu: " + str(int(ctx.get("segment_count") or 0)) +
                 " | ryzyko piachu: " + (", ".join(counts_bits) if counts_bits else "brak"))
    high_segs = [e for e in elevated if e.get("sand_risk") == "WYSOKIE"]
    if high_segs:
        ranges = ", ".join(f"km {float(e['km_from']):g}–{float(e['km_to']):g}" for e in high_segs)
        lines.append(f"⚠️ MOŻLIWY GŁĘBOKI PIACH (~{sand_high:.1f} km): {ranges} — rozważ objazd")
    if sand_med > 0:
        lines.append(f"Możliwy piach / luźna nawierzchnia (średnie, ~{sand_med:.1f} km) — patrz odcinki niżej")
    if elevated:
        lines.append("Odcinki podwyższonego ryzyka:")
        for e in elevated:
            km = f"km {float(e['km_from']):g}–{float(e['km_to']):g}"
            env = f"{e.get('dominant_pl') or '?'} {int(e.get('agreement_pct') or 0)}%"
            lines.append(f"- {km} [{e.get('sand_risk')}]: {e.get('surface_estimate')} ({env}) — {e.get('reason')}")
    return lines


def _route_poi_section_lines(route_source: dict[str, Any] | None) -> list[str]:
    if not isinstance(route_source, dict):
        return []
    if str(route_source.get("read_path") or "").strip() != "canonical":
        return []
    summary = route_source.get("canonical_poi_summary")
    if not isinstance(summary, dict):
        return []

    try:
        poi_count = int(summary.get("poi_count") or 0)
    except (TypeError, ValueError):
        poi_count = 0
    if poi_count <= 0:
        return []

    by_category = summary.get("by_category") if isinstance(summary.get("by_category"), dict) else {}
    field_counts = summary.get("field_counts") if isinstance(summary.get("field_counts"), dict) else {}
    clusters = summary.get("clusters") if isinstance(summary.get("clusters"), list) else []

    def _field_count(key: str) -> int:
        try:
            return int(field_counts.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    cat_bits = []
    for key, payload in sorted(by_category.items()):
        if isinstance(payload, dict):
            cat_bits.append(f"{key}={int(payload.get('count') or 0)}")

    lines = [
        "Źródło POI: canonical route_poi_layer",
        f"route_poi_layer_count={poi_count}",
    ]
    if cat_bits:
        lines.append("kategorie: " + ", ".join(cat_bits))
    lines.append(
        "dane dostępne: "
        f"km={_field_count('km_on_route')}/{poi_count}, "
        f"distance={_field_count('distance_from_route_m')}/{poi_count}, "
        f"opening_hours={_field_count('opening_hours')}/{poi_count}, "
        f"locality/town={_field_count('town_rows')}/{poi_count}"
    )
    if clusters:
        lines.append("Najlepsze klastry canonical POI:")
        for idx, cluster in enumerate(clusters[:3], start=1):
            if not isinstance(cluster, dict):
                continue
            locality = str(cluster.get("locality") or "brak lokalizacji").strip() or "brak lokalizacji"
            item_count = int(cluster.get("item_count") or 0)
            km_min = cluster.get("km_min")
            km_max = cluster.get("km_max")
            other_count = int(cluster.get("other_count") or 0)
            if km_min is not None and km_max is not None:
                loc = f"km {float(km_min):.1f}–{float(km_max):.1f}"
            else:
                loc = "km ?"
            lines.append(f"{idx}. {locality} | {item_count} punktów | {loc}")
            if other_count:
                lines.append(f"   +{other_count} innych punktów w pobliżu")
            for item in cluster.get("best_items") or []:
                if not isinstance(item, dict):
                    continue
                hours = item.get("opening_hours") or "brak"
                dist_m = item.get("distance_from_route_m")
                dist_s = f"{float(dist_m):.0f} m" if dist_m is not None else "brak"
                km = item.get("km_on_route")
                km_s = f"{float(km):.1f}" if km is not None else "brak"
                lines.append(
                    f"   - {item.get('name')} | {item.get('category')} | km {km_s} | "
                    f"distance_from_route_m={dist_s} | opening_hours={hours}"
                )
    lines.append(
        "Uwaga: canonical POI ma km/distance dla wszystkich punktów, ale opening_hours tylko dla części; "
        "legacy cache nadal dostarcza pełniejszą logistykę ETA i godzin."
    )
    return lines


def _parse_route_report_start(start: Any) -> tuple[str, str] | None:
    if start is None:
        return None
    text = str(start).strip()
    if not text:
        return None
    text = text.replace("T", " ")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        try:
            from zoneinfo import ZoneInfo
            parsed = parsed.astimezone(ZoneInfo("Europe/Warsaw"))
        except Exception:
            parsed = parsed.astimezone(timezone.utc)
    return parsed.date().isoformat(), parsed.strftime("%H:%M")


def _meteo_status_label(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "UNAVAILABLE"
    if result.get("status") != "OK":
        return "UNAVAILABLE"
    per_segment = result.get("per_segment") if isinstance(result.get("per_segment"), list) else []
    table = result.get("tabela_30min") if isinstance(result.get("tabela_30min"), list) else []
    peak = result.get("peak") if isinstance(result.get("peak"), dict) else None
    if not per_segment or not table or not peak:
        return "LIMITED"
    return "OK"


def _meteo_summary_bits(result: dict[str, Any]) -> list[str]:
    bits = []
    alerts = result.get("alerts") if isinstance(result.get("alerts"), list) else []
    counts: dict[str, int] = {}
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        typ = str(alert.get("typ") or "inne").strip() or "inne"
        counts[typ] = counts.get(typ, 0) + 1
    if counts:
        order = ("upał", "deszcz", "burza", "zimno")
        summary = []
        for key in order:
            if key in counts:
                summary.append(f"{key}={counts[key]}")
        for key in sorted(k for k in counts if k not in order):
            summary.append(f"{key}={counts[key]}")
        bits.append("alerty: " + ", ".join(summary))

    per_segment = result.get("per_segment") if isinstance(result.get("per_segment"), list) else []
    wind_vals = []
    for seg in per_segment:
        if not isinstance(seg, dict):
            continue
        try:
            wind_vals.append(float(seg["wind_eff_ms"]))
        except (KeyError, TypeError, ValueError):
            continue
    if wind_vals:
        bits.append(f"wiatr_eff_max={max(wind_vals):.1f} m/s")

    if not result.get("alerts"):
        bits.append("brak istotnych alertów w prognozie")
    return bits


def _load_route_meteo_engine() -> tuple[Any | None, str | None]:
    try:
        from qbot3.routes.route_meteo_engine import run_meteo_engine as _run_meteo_engine
    except Exception as exc:  # noqa: BLE001
        return None, f"meteo import failed: {str(exc)[:160]}"
    return _run_meteo_engine, None


def _meteo_section_lines(route_id: str | None, start: Any) -> list[str]:
    payload = _meteo_report_payload(route_id, start)
    return payload["lines"]


def _meteo_report_payload(route_id: str | None, start: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "UNAVAILABLE",
        "reason": None,
        "result": None,
        "date_str": None,
        "start_time": None,
        "lines": ["## A4 - METEO / route_run_context"],
    }
    lines = payload["lines"]
    parsed = _parse_route_report_start(start)
    if not route_id:
        lines.extend([
            "- status: UNAVAILABLE",
            "- powód: brak route_id",
            "",
        ])
        payload["reason"] = "brak route_id"
        return payload
    if parsed is None:
        lines.extend([
            "- status: UNAVAILABLE",
            "- powód: brak lub niepoprawny start",
            "- źródło danych: route_meteo_engine (nieuruchomiony)",
            "",
        ])
        payload["reason"] = "brak lub niepoprawny start"
        return payload

    date_str, start_time = parsed
    payload["date_str"] = date_str
    payload["start_time"] = start_time
    run_meteo_engine, load_error = _load_route_meteo_engine()
    if run_meteo_engine is None:
        lines.extend([
            "- status: UNAVAILABLE",
            f"- powód: {load_error or 'meteo import failed'}",
            "- źródło danych: route_meteo_engine (nieuruchomiony)",
            "",
        ])
        payload["reason"] = load_error or "meteo import failed"
        return payload
    try:
        meteo = run_meteo_engine(route_id=route_id, date_str=date_str, start_time=start_time, mode="normalny")
    except Exception as exc:  # noqa: BLE001
        lines.extend([
            "- status: UNAVAILABLE",
            f"- powód: meteo run failed: {str(exc)[:160]}",
            "- źródło danych: Open-Meteo + route_meteo_engine.run_meteo_engine",
            f"- start_local: {date_str} {start_time}",
            "",
        ])
        payload["reason"] = f"meteo run failed: {str(exc)[:160]}"
        return payload

    status = _meteo_status_label(meteo)
    payload["status"] = status
    payload["result"] = meteo
    lines.append(f"- status: {status}")
    lines.append("- źródło danych: Open-Meteo + route_meteo_engine.run_meteo_engine")
    lines.append(f"- start_local: {date_str} {start_time}")
    if status == "UNAVAILABLE":
        err = str((meteo or {}).get("error") or "brak danych pogodowych").strip()
        lines.append(f"- powód: {err}")
        lines.append("")
        payload["reason"] = err
        return payload

    peak = meteo.get("peak") if isinstance(meteo.get("peak"), dict) else {}
    if peak:
        lines.append(
            "- peak WBGT: "
            f"wbgt_eff={peak.get('wbgt_eff')} | km={peak.get('km')} | eta={peak.get('eta')} | "
            f"alert_level={peak.get('alert_level')} | teren={peak.get('teren')}"
        )
    n_segments = meteo.get("n_segments")
    n_windows = meteo.get("n_windows")
    if n_segments is not None or n_windows is not None:
        seg_bits = []
        if n_segments is not None:
            seg_bits.append(f"n_segments={n_segments}")
        if n_windows is not None:
            seg_bits.append(f"n_windows={n_windows}")
        lines.append("- " + " | ".join(seg_bits))
    lines.append("- temperatura powietrza: brak w obecnym kontrakcie METEO; raport pokazuje WBGT/Tmrt/UTCI")
    lines.extend(f"- {bit}" for bit in _meteo_summary_bits(meteo))

    alerts = meteo.get("alerts") if isinstance(meteo.get("alerts"), list) else []
    if alerts:
        lines.append("- najważniejsze alerty:")
        for idx, alert in enumerate(alerts[:3], start=1):
            if not isinstance(alert, dict):
                continue
            typ = alert.get("typ") or "inne"
            severity = alert.get("severity") or "brak"
            km_od = alert.get("km_od")
            km_do = alert.get("km_do")
            eta_od = alert.get("eta_od")
            eta_do = alert.get("eta_do")
            minuty = alert.get("minuty")
            extra_bits = []
            for key in ("wbgt_max", "opad_max_mm", "prawdopod", "kod_burzy", "cape_max",
                        "porywy_max_ms", "utci_min", "kategoria", "czekanie_min"):
                if alert.get(key) is not None:
                    extra_bits.append(f"{key}={alert.get(key)}")
            extra = f" | {'; '.join(extra_bits)}" if extra_bits else ""
            lines.append(
                f"  {idx}. {typ} | {severity} | km {km_od}–{km_do} | "
                f"eta {eta_od}–{eta_do} | {minuty} min{extra}"
            )
    caveats = meteo.get("caveats") if isinstance(meteo.get("caveats"), list) else []
    if caveats:
        lines.append("- caveats:")
        for caveat in caveats:
            lines.append(f"  - {caveat}")
    lines.append("")
    return payload


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "brak"


def _fmt_m(value: Any) -> str:
    try:
        return f"{float(value):.1f} m"
    except (TypeError, ValueError):
        return "brak"


def _route_verdict_section_lines(route_source: dict[str, Any] | None, meteo_payload: dict[str, Any] | None,
                                 collected: dict[str, Any]) -> list[str]:
    lines = ["## WERDYKT TRASY / DECYZJA"]
    if not isinstance(route_source, dict):
        lines.extend([
            "- decyzja: BRAK PEŁNYCH DANYCH",
            "- główny powód: brak canonical route_source",
            "",
        ])
        return lines

    surface = route_source.get("canonical_surface_summary") if isinstance(route_source.get("canonical_surface_summary"), dict) else None
    poi = route_source.get("canonical_poi_summary") if isinstance(route_source.get("canonical_poi_summary"), dict) else None
    elevation = route_source.get("canonical_elevation_summary") if isinstance(route_source.get("canonical_elevation_summary"), dict) else None
    meteo_ok = bool(isinstance(meteo_payload, dict) and meteo_payload.get("status") == "OK" and isinstance(meteo_payload.get("result"), dict))
    meteo_result = meteo_payload.get("result") if meteo_ok else None
    fuel_txt = _analysis(collected.get("fuel")) if collected.get("fuel") else None
    tp_txt = _analysis(collected.get("tp")) if collected.get("tp") else None

    missing_layers = []
    if surface is None:
        missing_layers.append("nawierzchnia")
    if elevation is None:
        missing_layers.append("przewyższenia")
    if poi is None:
        missing_layers.append("POI")
    if not meteo_ok:
        missing_layers.append("METEO")

    surface_risks: list[str] = []
    if surface:
        try:
            inferred_pct = float(surface.get("inferred_surface_pct") or 0.0)
        except (TypeError, ValueError):
            inferred_pct = 0.0
        if inferred_pct > 0:
            surface_risks.append("nawierzchnia częściowo inferowana")
        if (surface.get("unknown_provenance_count") or 0) > 0:
            surface_risks.append("nieznana proweniencja")
    ctx_v = route_source.get("canonical_surface_context") if isinstance(route_source.get("canonical_surface_context"), dict) else None
    if ctx_v:
        elev_v = ctx_v.get("elevated") if isinstance(ctx_v.get("elevated"), list) else []
        high_v = [e for e in elev_v if e.get("sand_risk") == "WYSOKIE"]
        if high_v:
            km_h = float(ctx_v.get("sand_km_high") or 0.0)
            rng = ", ".join(f"km {float(e['km_from']):g}–{float(e['km_to']):g}" for e in high_v[:4])
            more = "…" if len(high_v) > 4 else ""
            surface_risks.insert(0, f"możliwy głęboki piach ~{km_h:.1f} km ({rng}{more})")
    elevation_risks: list[str] = []
    if elevation:
        if elevation.get("short_wall_detection_note"):
            elevation_risks.append("krótkie rampy mogą umknąć")
        if elevation.get("max_climb_event_gradient_pct") is not None:
            elevation_risks.append(
                f"max_gradient={float(elevation.get('max_climb_event_gradient_pct')):.1f}%"
            )
    poi_risks: list[str] = []
    if poi:
        try:
            poi_count = int(poi.get("poi_count") or 0)
        except (TypeError, ValueError):
            poi_count = 0
        field_counts = poi.get("field_counts") if isinstance(poi.get("field_counts"), dict) else {}
        try:
            opening_hours_count = int(field_counts.get("opening_hours") or 0)
        except (TypeError, ValueError):
            opening_hours_count = 0
        if poi_count and opening_hours_count < poi_count:
            poi_risks.append("brak pełnych godzin POI")

    meteo_risks: list[str] = []
    if meteo_result:
        alerts = meteo_result.get("alerts") if isinstance(meteo_result.get("alerts"), list) else []
        alert_severities = [str(a.get("severity") or "").upper() for a in alerts if isinstance(a, dict)]
        if "NO-GO" in alert_severities:
            meteo_risks.append("burza NO-GO")
        elif "ALARM" in alert_severities:
            meteo_risks.append("METEO ALARM")
        peak = meteo_result.get("peak") if isinstance(meteo_result.get("peak"), dict) else {}
        try:
            peak_wbgt = float(peak.get("wbgt_eff")) if peak.get("wbgt_eff") is not None else None
        except (TypeError, ValueError):
            peak_wbgt = None
        try:
            peak_alert_level = int(peak.get("alert_level")) if peak.get("alert_level") is not None else None
        except (TypeError, ValueError):
            peak_alert_level = None
        if peak_wbgt is not None and peak_wbgt >= 30.0 and "upał" not in " ".join(meteo_risks):
            meteo_risks.append(f"WBGT={peak_wbgt:.1f}")
        elif peak_alert_level is not None and peak_alert_level >= 3:
            meteo_risks.append(f"alert_level={peak_alert_level}")

    if missing_layers:
        decision = "BRAK PEŁNYCH DANYCH"
        reason = "brak " + ", ".join(missing_layers)
        biggest_risk = reason
    elif "burza NO-GO" in meteo_risks:
        decision = "PRZEŁÓŻ"
        reason = "burza NO-GO"
        biggest_risk = reason
    elif surface_risks or elevation_risks or poi_risks or meteo_risks:
        decision = "JEDŹ OSTROŻNIE"
        reason = "; ".join((meteo_risks or surface_risks or elevation_risks or poi_risks)[:2])
        biggest_risk = "; ".join((meteo_risks + surface_risks + elevation_risks + poi_risks)[:3])
    else:
        decision = "JEDŹ"
        reason = "brak istotnych ryzyk w dostępnych danych"
        biggest_risk = reason

    lines.append(f"- decyzja: {decision}")
    lines.append(f"- główny powód: {reason}")
    lines.append(f"- największe ryzyko: {biggest_risk}")

    if surface:
        try:
            top_surfaces = sorted(
                (surface.get("by_surface") or {}).items(),
                key=lambda item: (-float((item[1] or {}).get("pct") or 0.0), str(item[0])),
            )[:4]
        except Exception:
            top_surfaces = []
        mix_bits = [f"{name} {_fmt_pct((payload or {}).get('pct'))}" for name, payload in top_surfaces]
        surface_bits = [
            f"coverage={_fmt_pct(surface.get('coverage_pct'))}",
            f"tagged={_fmt_pct(surface.get('tagged_surface_pct'))}",
            f"inferred={_fmt_pct(surface.get('inferred_surface_pct'))}",
        ]
        if mix_bits:
            surface_bits.append("mix: " + ", ".join(mix_bits))
        if surface.get("problem_segments") is not None:
            try:
                surface_bits.append(f"problem_segments={len(surface.get('problem_segments') or [])}")
            except Exception:
                pass
        lines.append("- nawierzchnia: " + "; ".join(surface_bits))
    else:
        lines.append("- nawierzchnia: dane ograniczone")

    if elevation:
        elev_bits = [
            f"ascent_smoothed={_fmt_m(elevation.get('ascent_smoothed_m'))}",
            f"descent_smoothed={_fmt_m(elevation.get('descent_smoothed_m'))}",
            f"climb_events={elevation.get('climb_event_count')}",
            f"max_gradient={_fmt_pct(elevation.get('max_climb_event_gradient_pct'))}",
        ]
        if elevation.get("short_wall_detection_note"):
            elev_bits.append("limit: bardzo krótkie strome rampy mogą umknąć")
        lines.append("- przewyższenia: " + "; ".join(elev_bits))
    else:
        lines.append("- przewyższenia: dane ograniczone")

    if meteo_ok and meteo_result:
        peak = meteo_result.get("peak") if isinstance(meteo_result.get("peak"), dict) else {}
        alerts = meteo_result.get("alerts") if isinstance(meteo_result.get("alerts"), list) else []
        alert_bits = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            typ = str(alert.get("typ") or "").strip()
            severity = str(alert.get("severity") or "").strip()
            if typ and severity:
                alert_bits.append(f"{typ}={severity}")
        meteo_bits = [
            f"status={meteo_payload.get('status')}",
            f"peak_WBGT={peak.get('wbgt_eff')}",
            f"alerts={', '.join(alert_bits) if alert_bits else 'brak'}",
        ]
        caveats = meteo_result.get("caveats") if isinstance(meteo_result.get("caveats"), list) else []
        if caveats:
            meteo_bits.append("caveats=obecne")
        lines.append("- meteo: " + "; ".join(meteo_bits))
    else:
        lines.append("- meteo: METEO unavailable / dane ograniczone")

    if poi:
        by_category = poi.get("by_category") if isinstance(poi.get("by_category"), dict) else {}
        cat_bits = []
        for key in ("hard_resupply", "soft_food_stop", "water", "town"):
            payload = by_category.get(key)
            if isinstance(payload, dict):
                cat_bits.append(f"{key}={int(payload.get('count') or 0)}")
        field_counts = poi.get("field_counts") if isinstance(poi.get("field_counts"), dict) else {}
        poi_bits = [
            f"poi_count={int(poi.get('poi_count') or 0)}",
            f"km={int(field_counts.get('km_on_route') or 0)}/{int(poi.get('poi_count') or 0)}",
            f"distance={int(field_counts.get('distance_from_route_m') or 0)}/{int(poi.get('poi_count') or 0)}",
            f"opening_hours={int(field_counts.get('opening_hours') or 0)}/{int(poi.get('poi_count') or 0)}",
        ]
        if cat_bits:
            poi_bits.append("kategorie: " + ", ".join(cat_bits))
        lines.append("- logistyka/POI: " + "; ".join(poi_bits))
        if poi_risks:
            lines.append("- logistyka/POI uwaga: " + "; ".join(poi_risks))
    else:
        lines.append("- logistyka/POI: dane ograniczone")

    if tp_txt:
        lines.append("- sprzęt/opony: B5 dostępne; ciśnienie policzone")
    else:
        lines.append("- sprzęt/opony: dane ograniczone")

    if fuel_txt:
        g, l = _parse_fuel_rates(fuel_txt)
        fuel_bits = [bit for bit in (g, l) if bit]
        if fuel_bits:
            lines.append("- żywienie/woda: " + ", ".join(fuel_bits))
        else:
            lines.append("- żywienie/woda: B2/B3 dostępne")
    else:
        lines.append("- żywienie/woda: dane ograniczone")
    lines.append("")
    return lines


_ROUTE_VERSION_META_KEYS = (
    "route_id",
    "route_artifact_id",
    "created_at",
    "updated_at",
    "sha256",
    "source_artifact_sha256",
    "distance_m",
    "distance_km",
    "track_points",
    "elevation_gain_m",
    "geometry_hash",
    "points_hash",
    "route_version_key",
)

_ROUTE_VERSION_EVIDENCE_KEYS = tuple(
    key for key in _ROUTE_VERSION_META_KEYS if key not in {"route_id", "route_version_key"}
)


def _route_version_scalar(value: Any, *, key: str | None = None) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if key in {"route_artifact_id", "track_points"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if key in {"distance_m", "distance_km", "elevation_gain_m"}:
        try:
            return round(float(value), 6)
        except (TypeError, ValueError):
            return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    return text or None


def _route_version_payload(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    payload: dict[str, Any] = {}
    for key in _ROUTE_VERSION_META_KEYS:
        value = _route_version_scalar(record.get(key), key=key)
        if value is not None:
            payload[key] = value
    return payload


def _route_version_fingerprint(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = _route_version_payload(record)
    has_evidence = any(payload.get(key) is not None for key in _ROUTE_VERSION_EVIDENCE_KEYS)
    if not has_evidence:
        return {"route_version_key": None, "route_version_payload": payload, "has_evidence": False}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "route_version_key": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "route_version_payload": payload,
        "has_evidence": True,
    }


def _fetch_route_version_record(*, route_id: str | None = None, route_artifact_id: str | int | None = None) -> dict[str, Any] | None:
    route_id_text = str(route_id).strip() if route_id is not None else None
    route_artifact_text = str(route_artifact_id).strip() if route_artifact_id is not None else None
    if not route_id_text and not route_artifact_text:
        return None
    try:
        import os as _os
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(
            host=_os.getenv("PGHOST", "127.0.0.1"),
            port=_os.getenv("PGPORT", "5432"),
            dbname=_os.getenv("PGDATABASE", "qbot"),
            user=_os.getenv("PGUSER", "qbot"),
            password=_os.getenv("PGPASSWORD", ""),
            row_factory=dict_row,
            connect_timeout=5,
        )
        if route_artifact_text and route_artifact_text.isdigit():
            sql = """
                SELECT
                    a.id AS route_artifact_id,
                    a.route_id::text AS route_id,
                    a.created_at,
                    a.updated_at,
                    a.sha256,
                    a.source_artifact_sha256,
                    a.metadata_json,
                    p.parsed_at,
                    p.distance_m,
                    p.distance_km,
                    p.track_points,
                    p.elevation_gain_m
                FROM qbot_v2.route_artifacts a
                LEFT JOIN LATERAL (
                    SELECT
                        pr.parsed_at,
                        pr.distance_m,
                        pr.distance_km,
                        pr.track_points,
                        pr.elevation_gain_m
                    FROM qbot_v2.route_parse_results pr
                    WHERE pr.route_artifact_id = a.id
                    ORDER BY pr.parsed_at DESC NULLS LAST, pr.id DESC
                    LIMIT 1
                ) p ON TRUE
                WHERE a.id = %s
                LIMIT 1
            """
            params = (int(route_artifact_text),)
        else:
            sql = """
                SELECT
                    a.id AS route_artifact_id,
                    a.route_id::text AS route_id,
                    a.created_at,
                    a.updated_at,
                    a.sha256,
                    a.source_artifact_sha256,
                    a.metadata_json,
                    p.parsed_at,
                    p.distance_m,
                    p.distance_km,
                    p.track_points,
                    p.elevation_gain_m
                FROM qbot_v2.route_artifacts a
                LEFT JOIN LATERAL (
                    SELECT
                        pr.parsed_at,
                        pr.distance_m,
                        pr.distance_km,
                        pr.track_points,
                        pr.elevation_gain_m
                    FROM qbot_v2.route_parse_results pr
                    WHERE pr.route_artifact_id = a.id
                    ORDER BY pr.parsed_at DESC NULLS LAST, pr.id DESC
                    LIMIT 1
                ) p ON TRUE
                WHERE a.route_id::text = %s
                ORDER BY a.updated_at DESC NULLS LAST, a.created_at DESC NULLS LAST, a.id DESC
                LIMIT 1
            """
            params = (route_id_text,)
        row = conn.execute(sql, params).fetchone()
        conn.close()
        if not row:
            return None

        metadata = row.get("metadata_json") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}

        record: dict[str, Any] = {
            "route_id": row.get("route_id"),
            "route_artifact_id": row.get("route_artifact_id"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "sha256": row.get("sha256"),
            "source_artifact_sha256": row.get("source_artifact_sha256"),
            "distance_m": row.get("distance_m") or metadata.get("distance_m"),
            "distance_km": row.get("distance_km") or metadata.get("distance_km"),
            "track_points": row.get("track_points") or metadata.get("point_count") or metadata.get("track_points"),
            "elevation_gain_m": row.get("elevation_gain_m") or metadata.get("elevation_gain_m"),
        }
        record["route_version_key"] = _route_version_fingerprint(record).get("route_version_key")
        return record
    except Exception:
        return None


def _route_version_guard(
    *,
    active_version: dict[str, Any] | None,
    block_version: dict[str, Any] | None,
    source_name: str,
) -> dict[str, Any]:
    block_payload = _route_version_payload(block_version)
    active_payload = _route_version_payload(active_version)
    block_has_evidence = any(block_payload.get(key) is not None for key in _ROUTE_VERSION_EVIDENCE_KEYS)
    active_has_evidence = any(active_payload.get(key) is not None for key in _ROUTE_VERSION_EVIDENCE_KEYS)

    if not block_has_evidence or not active_has_evidence:
        return {
            "status": "WARN",
            "code": "SOURCE_VERSION_METADATA_MISSING",
            "source": source_name,
            "message": f"{source_name}: brak wiarygodnych metadanych wersji",
        }

    mismatches: list[tuple[str, Any, Any]] = []
    compared = 0
    for key in _ROUTE_VERSION_EVIDENCE_KEYS:
        block_value = block_payload.get(key)
        if block_value is None:
            continue
        active_value = active_payload.get(key)
        compared += 1
        if active_value is None:
            continue
        if block_value != active_value:
            mismatches.append((key, active_value, block_value))

    if mismatches:
        key, active_value, block_value = mismatches[0]
        return {
            "status": "ERROR",
            "code": "ROUTE_VERSION_MISMATCH",
            "source": source_name,
            "field": key,
            "active_value": active_value,
            "block_value": block_value,
            "message": (
                f"{source_name}: {key}={block_value!r} != aktywne {active_value!r}"
            ),
        }

    if compared == 0:
        return {
            "status": "WARN",
            "code": "SOURCE_VERSION_METADATA_MISSING",
            "source": source_name,
            "message": f"{source_name}: brak porownywalnych metadanych wersji",
        }

    return {
        "status": "OK",
        "code": "OK",
        "source": source_name,
        "route_version_key": active_payload.get("route_version_key") or block_payload.get("route_version_key"),
        "message": f"{source_name}: wersja zgodna",
    }


def _open_status_rank(status: str | None) -> int:
    if status == "OPEN_AT_ETA":
        return 0
    if status in {"OPEN_AT_ETA_MARGIN_RISK", "OPEN_SOON_MARGIN_RISK", "CLOSED_AT_ETA_MARGIN_RISK"}:
        return 1
    if status == "UNKNOWN_HOURS":
        return 2
    return 3


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
    """POI dla raportu — WYLACZNIE z kanonicznej bazy (route_poi_layer + route_poi_meta)
    przez read_canonical_route. 2026-07-02: zlikwidowano czytanie starych plikow z
    /opt/qbot/artifacts/reports/ (poi_analysis_<id>_*.json) — to byl przeciek granicy:
    raport wsysal cudze artefakty po samym numerze trasy, z pominieciem bazy. Teraz raport
    czyta ta sama kanoniczna baze co reszta. Zwraca ten sam ksztalt co dawny cache dyskowy,
    wiec render POI dziala bez zmian. generated_at = route_poi_meta.fetched_at (prawdziwa
    data pobrania POI = 'dane POI z dnia'). Wersje kotwiczymy na aktywnym route_base
    (route_artifact_id + sha256), bo dane POI sa Z DEFINICJI z aktywnej wersji trasy."""
    if not route_id:
        return None
    try:
        canonical = read_canonical_route(route_id=route_id)
    except Exception:
        return None
    if not isinstance(canonical, dict):
        return None
    layers = canonical.get("layers") if isinstance(canonical.get("layers"), dict) else {}
    poi_rows = layers.get("route_poi_layer") or []
    meta = canonical.get("canonical_poi_meta") if isinstance(canonical.get("canonical_poi_meta"), dict) else {}
    if not poi_rows and not meta:
        return None

    def _open_source(provider: Any) -> str | None:
        p = str(provider or "").strip().lower()
        if "google" in p:
            return "google"
        if "osm" in p or "overpass" in p:
            return "osm"
        return p or None

    def _source_tags(row: dict[str, Any]) -> Any:
        mj = row.get("poi_meta_json")
        if isinstance(mj, str):
            try:
                mj = json.loads(mj)
            except Exception:
                mj = None
        if isinstance(mj, dict):
            return mj.get("source_tags")
        return None

    buckets: dict[str, list[dict[str, Any]]] = {
        "hard_resupply": [], "soft_food_stop": [], "water": [], "attraction": [], "town": [],
    }
    for row in poi_rows:
        cat = str(row.get("category") or "").strip()
        if cat not in buckets:
            continue
        buckets[cat].append({
            "category": cat,
            "name": row.get("name"),
            "route_km": row.get("km_on_route"),
            "distance_to_track_m": row.get("distance_from_route_m"),
            "opening_hours_osm": row.get("opening_hours"),
            "open_source": _open_source(row.get("provider")),
            "source_tags": _source_tags(row),
            "lat": row.get("lat"),
            "lon": row.get("lon"),
        })

    fetched_at = meta.get("fetched_at")
    if hasattr(fetched_at, "isoformat"):
        generated_at = fetched_at.isoformat()
    else:
        generated_at = str(fetched_at) if fetched_at else None

    buffers = meta.get("buffers_json") if isinstance(meta.get("buffers_json"), dict) else {}
    missing_chunks = meta.get("missing_chunks_json") if isinstance(meta.get("missing_chunks_json"), list) else []

    cache: dict[str, Any] = {
        "status": meta.get("analysis_status") or ("OK" if poi_rows else "UNAVAILABLE"),
        "analysis_status": meta.get("analysis_status"),
        "source": "canonical_db",
        "cache_path": "qbot_v2.route_poi_layer",
        "report_json_path": "qbot_v2.route_poi_layer + route_poi_meta",
        "report_path": None,
        "generated_at": generated_at,
        "summary": {
            "hard_resupply": len(buckets["hard_resupply"]),
            "soft_food_stop": len(buckets["soft_food_stop"]),
            "water": len(buckets["water"]),
            "attractions": len(buckets["attraction"]),
            "town": len(buckets["town"]),
        },
        "poi_source_mode": meta.get("poi_source_mode"),
        "google_supply_count": meta.get("google_supply_count"),
        "supply_status": meta.get("supply_status"),
        "technical_completeness": meta.get("technical_completeness"),
        "supply_longest_gap_km": meta.get("supply_longest_gap_km"),
        "supply_longest_gap_from_km": meta.get("supply_longest_gap_from_km"),
        "buffers": buffers,
        "hard_resupply": buckets["hard_resupply"],
        "soft_food_stop": buckets["soft_food_stop"],
        "water": buckets["water"],
        "attractions": buckets["attraction"],
        "town_fallback_check": buckets["town"],
        "missing_chunks": missing_chunks,
        "missing_chunks_count": meta.get("missing_chunks_count"),
        "markdown": None,
    }
    base = canonical.get("route_base") if isinstance(canonical.get("route_base"), dict) else {}
    if base.get("route_artifact_id") is not None:
        cache["route_artifact_id"] = base.get("route_artifact_id")
    if base.get("sha256") is not None:
        cache["sha256"] = base.get("sha256")
    if base.get("route_version_key") is not None:
        cache["route_version_key"] = base.get("route_version_key")
    cache["route_id"] = str(canonical.get("route_id") or route_id)
    return cache


def _parse_source_tags(source_tags: Any) -> dict[str, str]:
    if isinstance(source_tags, dict):
        return {str(k).strip(): str(v).strip() for k, v in source_tags.items() if str(k).strip()}
    if not isinstance(source_tags, str):
        return {}
    out: dict[str, str] = {}
    for part in source_tags.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip()
        val = val.strip()
        if key:
            out[key] = val
    return out


def _parse_avg_speed_kmh(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"v\s*([\d.]+)\s*km/h", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except (TypeError, ValueError):
            return None
    return None


def _supply_kind_from_tags(tags: dict[str, str], category: str, name: str) -> str:
    if category == "hard_resupply":
        shop = str(tags.get("shop") or "").lower()
        amenity = str(tags.get("amenity") or "").lower()
        if amenity == "fuel":
            return "stacja paliw"
        if amenity in {"restaurant", "cafe", "fast_food", "bar"}:
            return "gastronomia"
        if shop in {"supermarket", "convenience", "grocery", "general", "deli", "bakery", "greengrocer"}:
            return "sklep"
        return "zaopatrzenie"
    if category == "soft_food_stop":
        return "gastronomia"
    if category == "water":
        return "drinking_water"
    if category == "town":
        return "miejscowość"
    if category == "attraction":
        return "attraction"
    raw_name = str(name or "").strip().lower()
    if any(tok in raw_name for tok in ("zabka", "dino", "lewiatan", "delikates", "groszek", "abc", "biedronka", "lidl", "netto", "aldi", "carrefour", "kaufland")):
        return "sklep"
    return category or "poi"


def _normalize_poi_supply_item(item: dict[str, Any], *, ride_start: Any = None, avg_speed_kmh: float | None = None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    category = str(item.get("category") or "").strip()
    if category not in {"hard_resupply", "soft_food_stop", "water", "attraction", "town"}:
        return None
    if category == "town" and not (item.get("hard_resupply_found") or str(item.get("hard_resupply_names") or "").strip()):
        return None

    tags = _parse_source_tags(item.get("source_tags"))
    name = str(item.get("google_name") or item.get("name") or "").strip()
    if not name and category == "town":
        name = str(item.get("hard_resupply_names") or item.get("town_name") or item.get("name") or "").strip()
    kind = _supply_kind_from_tags(tags, category, name)
    km_on_route = item.get("route_km") if item.get("route_km") is not None else item.get("km_on_route")
    distance_from_route_m = item.get("distance_to_track_m") if item.get("distance_to_track_m") is not None else item.get("distance_from_track_m")
    opening_hours = item.get("opening_hours_osm") or item.get("opening_hours") or None
    open_source = str(item.get("open_source") or "").strip().lower() or None
    open_at_arrival = item.get("open_at_arrival")
    eta_iso = item.get("eta_iso")
    render_eta_iso = eta_iso
    open_status = None

    if ride_start is not None and km_on_route is not None:
        try:
            from datetime import datetime as _dt
            from tools.rwgps.poi_open_window import classify_osm_open_status, eta_at_km, parse_osm_opening_hours
            start_dt = _dt.fromisoformat(str(ride_start).replace("Z", "+00:00"))
            render_eta_iso = eta_at_km(float(km_on_route), start_dt, float(avg_speed_kmh or 18.0)).isoformat()
            if render_eta_iso and opening_hours:
                eta_dt = _dt.fromisoformat(str(render_eta_iso).replace("Z", "+00:00"))
                parsed = parse_osm_opening_hours(str(opening_hours))
                open_status = classify_osm_open_status(parsed, eta_dt)
        except Exception:
            render_eta_iso = eta_iso

    if open_status is None and ride_start is not None and open_at_arrival is not None and not opening_hours:
        open_status = "UNKNOWN_HOURS"

    if open_status == "OPEN_AT_ETA":
        open_at_arrival = True
    elif open_status in {"OPEN_AT_ETA_MARGIN_RISK", "OPEN_SOON_MARGIN_RISK", "CLOSED_AT_ETA", "CLOSED_AT_ETA_MARGIN_RISK"}:
        open_at_arrival = False if open_status.startswith("CLOSED") or open_status == "OPEN_SOON_MARGIN_RISK" else True
    else:
        open_at_arrival = None
        if opening_hours:
            open_status = "UNKNOWN_HOURS"

    if open_status == "OPEN_AT_ETA" and opening_hours:
        confidence = "HIGH"
    elif open_status == "OPEN_AT_ETA_MARGIN_RISK" and opening_hours:
        confidence = "MEDIUM"
    elif open_status == "OPEN_AT_ETA" and open_source == "google":
        confidence = "MEDIUM"
    elif category == "water" and not opening_hours:
        confidence = "LOW"
    else:
        confidence = "MEDIUM" if opening_hours else "LOW"

    return {
        "category": category,
        "kind": kind,
        "name": name or kind,
        "km_on_route": float(km_on_route) if km_on_route is not None else None,
        "distance_from_route_m": float(distance_from_route_m) if distance_from_route_m is not None else None,
        "opening_hours": opening_hours,
        "open_at_arrival": open_at_arrival,
        "open_status": open_status,
        "eta_iso": render_eta_iso,
        "confidence": confidence,
        "open_source": open_source,
        "note": str(item.get("note") or "").strip(),
        "source_tags": tags,
        "source_tags_raw": item.get("source_tags"),
        "town_name": str(item.get("name") or "").strip() if category == "town" else None,
        "hard_resupply_names": str(item.get("hard_resupply_names") or "").strip() if category == "town" else None,
    }


def _cluster_supply_items(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered = sorted(
        [item for item in items if item.get("km_on_route") is not None],
        key=lambda item: (float(item.get("km_on_route") or 0.0), float(item.get("distance_from_route_m") or 9999.0)),
    )
    clusters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    last_km: float | None = None
    for item in ordered:
        km = float(item["km_on_route"])
        if current and last_km is not None and (km - last_km) > 1.0:
            clusters.append(current)
            current = []
        current.append(item)
        last_km = km
    if current:
        clusters.append(current)
    return clusters


def _render_poi_supply_section(
    poi_cache: dict[str, Any] | None,
    *,
    ride_start: Any = None,
    plan_text: str | None = None,
    route_distance_km: float | None = None,
) -> list[str]:
    if not isinstance(poi_cache, dict):
        return [
            "Status zaopatrzenia: UNAVAILABLE",
            "Kompletność techniczna POI: UNAVAILABLE",
            "Źródło danych/cache: brak cache POI",
            "Jawne ostrzeżenie: brak danych POI nie oznacza braku sklepów po drodze; raport nie uruchamia ciężkiego refreshu Overpass.",
        ]

    report_json_path = str(poi_cache.get("report_json_path") or poi_cache.get("cache_path") or "").strip() or "—"
    generated_at = str(poi_cache.get("generated_at") or "—").strip()
    analysis_status = str(poi_cache.get("analysis_status") or poi_cache.get("status") or "UNKNOWN").strip().upper()
    summary = poi_cache.get("summary") if isinstance(poi_cache.get("summary"), dict) else {}
    buffers = poi_cache.get("buffers") if isinstance(poi_cache.get("buffers"), dict) else {}
    try:
        avg_speed_buf = float(buffers.get("avg_speed_kmh")) if buffers.get("avg_speed_kmh") is not None else None
    except (TypeError, ValueError):
        avg_speed_buf = None
    avg_speed_kmh = _parse_avg_speed_kmh(plan_text) or avg_speed_buf or 18.0
    temp_c = _parse_temp_c(plan_text)

    raw_items: list[dict[str, Any]] = []
    for cat in ("hard_resupply", "soft_food_stop", "water", "town_fallback_check"):
        for item in poi_cache.get(cat) or []:
            norm = _normalize_poi_supply_item(item, ride_start=ride_start, avg_speed_kmh=avg_speed_kmh)
            if norm is not None:
                raw_items.append(norm)

    def _distance_m(item: dict[str, Any]) -> float | None:
        try:
            distance = item.get("distance_from_route_m")
            return float(distance) if distance is not None else None
        except (TypeError, ValueError):
            return None

    def _within_distance(item: dict[str, Any], *, max_m: float) -> bool:
        distance = _distance_m(item)
        return distance is not None and distance <= max_m

    def _in_strategic_window(item: dict[str, Any], checkpoint_km: float) -> bool:
        km = item.get("km_on_route")
        try:
            km_val = float(km) if km is not None else None
        except (TypeError, ValueError):
            km_val = None
        if km_val is None:
            return False
        return abs(km_val - checkpoint_km) <= 5.0

    supply_items = [item for item in raw_items if item.get("category") in {"hard_resupply", "soft_food_stop", "water", "town"}]
    direct_items = [item for item in supply_items if item.get("category") != "town"]
    near_direct_items = [item for item in direct_items if _within_distance(item, max_m=500.0)]
    fallback_direct_items = []
    for item in direct_items:
        dist_m = _distance_m(item)
        if dist_m is not None and 500.0 < dist_m <= 1000.0:
            fallback_direct_items.append(item)
    water_items = [item for item in near_direct_items if item.get("category") == "water"]
    open_items = [item for item in near_direct_items if item.get("open_status") == "OPEN_AT_ETA"]
    margin_items = [item for item in near_direct_items if str(item.get("open_status") or "").endswith("_MARGIN_RISK")]
    unknown_items = [item for item in near_direct_items if item.get("open_status") == "UNKNOWN_HOURS"]
    closed_items = [item for item in near_direct_items if item.get("open_status") == "CLOSED_AT_ETA"]
    town_items = [item for item in raw_items if item.get("category") == "town" and item.get("hard_resupply_names")]

    supply_assessment: dict[str, Any] = {}
    try:
        from qbot3.artifacts.route_analyzer import _route_poi_v2_assess_supply_status as _assess_supply_status

        main_assessment_items = [item for item in near_direct_items if item.get("category") in {"hard_resupply", "soft_food_stop", "water"}]
        supply_assessment = _assess_supply_status(main_assessment_items, temp_c=temp_c)
    except Exception:
        supply_assessment = {}

    def _gap_stats(items: list[dict[str, Any]]) -> tuple[float | None, float | None]:
        kms = sorted(float(i["km_on_route"]) for i in items if i.get("km_on_route") is not None)
        if len(kms) < 2:
            return (None, None)
        gaps = [b - a for a, b in zip(kms, kms[1:])]
        if not gaps:
            return (None, None)
        idx = max(range(len(gaps)), key=lambda i: gaps[i])
        return (gaps[idx], kms[idx])

    longest_gap, gap_from_km = _gap_stats(open_items)
    technical_completeness = str(
        poi_cache.get("technical_completeness")
        or poi_cache.get("analysis_status")
        or poi_cache.get("status")
        or "UNKNOWN"
    ).strip().upper()
    status = str(supply_assessment.get("supply_status") or poi_cache.get("supply_status") or "UNAVAILABLE").strip().upper()
    if not supply_assessment and near_direct_items:
        if open_items and longest_gap is not None and longest_gap >= 25:
            status = "RISK"
        elif not open_items:
            status = "RISK"
        elif unknown_items or closed_items or (longest_gap is not None and longest_gap >= (20 if (temp_c or 0) >= 28 else 25)):
            status = "PARTIAL"
        else:
            status = "OK"

    supply_clusters = _cluster_supply_items([item for item in near_direct_items if item.get("category") in {"hard_resupply", "soft_food_stop", "water"}])
    confidence_counts = {
        "OPEN_AT_ETA": len(open_items),
        "MARGIN_RISK": len(margin_items),
        "UNKNOWN_HOURS": len(unknown_items),
        "CLOSED_AT_ETA": len(closed_items),
    }
    lines = [
        f"Status zaopatrzenia: {status}",
        f"Kompletność techniczna POI: {technical_completeness}",
        f"Źródło danych/cache: {report_json_path}",
        f"Dane POI z dnia: {(generated_at[:10] if isinstance(generated_at, str) and generated_at[:1].isdigit() else generated_at)}",
        f"Świeżość danych: {generated_at}",
    ]
    if poi_cache.get("poi_source_mode"):
        lines.append(f"Źródła kandydatów: {poi_cache.get('poi_source_mode')}")
    if poi_cache.get("google_supply_count") is not None:
        lines.append(f"Google Places kandydatów: {poi_cache.get('google_supply_count')}")
    lines += [
        f"Pewne punkty OPEN_AT_ETA do 500 m od trasy: {confidence_counts['OPEN_AT_ETA']}",
        f"Punkty blisko okna otwarcia/zamknięcia: {confidence_counts['MARGIN_RISK']}",
        f"Potencjalne UNKNOWN_HOURS do 500 m od trasy: {confidence_counts['UNKNOWN_HOURS']}",
        f"Punkty CLOSED_AT_ETA: {confidence_counts['CLOSED_AT_ETA']}",
        f"Publiczne drinking_water: {len(water_items)} (bonus, nie główne źródło zaopatrzenia w Polsce)",
    ]
    if longest_gap is not None and gap_from_km is not None:
        lines.append(f"Najdłuższy odcinek bez OPEN_AT_ETA: {longest_gap:.1f} km (od km {gap_from_km:.1f})")
        if temp_c is not None and temp_c >= 28 and longest_gap >= 15:
            lines.append("⚠️ Krytyczna luka przy upale: warto planować zakup wody wcześniej niż zwykle.")
    if poi_cache.get("missing_chunks_count"):
        lines.append(f"Braki techniczne providerów: missing_chunks={poi_cache.get('missing_chunks_count')}")
    if summary:
        parts = [f"{k}={v}" for k, v in summary.items() if v is not None]
        if parts:
            lines.append("Podsumowanie cache: " + ", ".join(parts))
    if town_items:
        lines.append(f"Fallback miejscowości z wyłapanym zaopatrzeniem: {len(town_items)}")

    route_distance_km_val: float | None
    try:
        route_distance_km_val = float(route_distance_km) if route_distance_km is not None else None
    except (TypeError, ValueError):
        route_distance_km_val = None

    fallback_sections: list[dict[str, Any]] = []
    if route_distance_km_val is not None and route_distance_km_val > 0:
        checkpoints = [
            ("25%", route_distance_km_val * 0.25),
            ("50%", route_distance_km_val * 0.50),
            ("75%", route_distance_km_val * 0.75),
        ]
        for label, checkpoint_km in checkpoints:
            nearby_open = [
                item
                for item in near_direct_items
                if item.get("open_status") == "OPEN_AT_ETA"
                and _within_distance(item, max_m=500.0)
                and _in_strategic_window(item, checkpoint_km)
            ]
            if nearby_open:
                continue
            candidates = [
                item
                for item in fallback_direct_items
                if item.get("category") in {"hard_resupply", "soft_food_stop"}
                and _in_strategic_window(item, checkpoint_km)
            ]
            if not candidates:
                continue
            best = sorted(
                candidates,
                key=lambda item: (
                    _open_status_rank(str(item.get("open_status") or "")),
                    float(item.get("distance_from_route_m") or 9999.0),
                    0 if item.get("kind") in {"stacja paliw", "sklep"} else 1,
                    0 if item.get("category") == "hard_resupply" else 1,
                ),
            )[0]
            fallback_sections.append(
                {
                    "label": label,
                    "checkpoint_km": checkpoint_km,
                    "item": best,
                }
            )

    if not supply_clusters:
        lines.append("Najważniejsze klastry zaopatrzenia blisko trasy: brak punktów <= 500 m w cache.")
    else:
        lines.append("Najważniejsze klastry zaopatrzenia blisko trasy:")
    for idx, cluster in enumerate(supply_clusters, start=1):
        cluster_open = sum(1 for item in cluster if item.get("open_status") == "OPEN_AT_ETA")
        cluster_margin = sum(1 for item in cluster if str(item.get("open_status") or "").endswith("_MARGIN_RISK"))
        cluster_unknown = sum(1 for item in cluster if item.get("open_status") == "UNKNOWN_HOURS")
        cluster_closed = sum(1 for item in cluster if item.get("open_status") == "CLOSED_AT_ETA")
        km_vals = [float(item["km_on_route"]) for item in cluster if item.get("km_on_route") is not None]
        km_min = min(km_vals) if km_vals else None
        km_max = max(km_vals) if km_vals else None
        cluster_status = "OK" if cluster_open and not cluster_unknown and not cluster_closed else ("RISK" if not cluster_open else "PARTIAL")
        best = sorted(
            cluster,
            key=lambda item: (
                _open_status_rank(str(item.get("open_status") or "")),
                float(item.get("distance_from_route_m") or 9999.0),
                0 if item.get("kind") in {"stacja paliw", "sklep"} else 1,
                0 if item.get("category") == "hard_resupply" else 1,
            ),
        )[:2]
        best_km = best[0].get("km_on_route") if best else None
        loc = ""
        if km_min is not None and km_max is not None:
            loc = f"km {km_min:.1f}–{km_max:.1f}"
        elif best_km is not None:
            loc = f"km {float(best_km):.1f}"
        town = next((item.get("town_name") for item in cluster if item.get("town_name")), None)
        town_part = f" | miejscowość: {town}" if town else ""
        other_count = max(0, len(cluster) - len(best))
        lines.append(
            f"{idx}. {loc or 'km ?'}{town_part} | status zaopatrzenia: {cluster_status} | "
            f"{len(cluster)} punktów ({cluster_open} OPEN_AT_ETA, {cluster_margin} MARGIN_RISK, {cluster_unknown} UNKNOWN_HOURS, {cluster_closed} CLOSED_AT_ETA)"
        )
        if other_count:
            lines.append(f"   +{other_count} innych punktów w pobliżu")
        for item in best:
            hours = item.get("opening_hours") or ("Google Places" if item.get("open_source") == "google" else "brak")
            eta = str(item.get("eta_iso") or "brak").replace("T", " ")
            dist_m = item.get("distance_from_route_m")
            dist_s = f"{float(dist_m):.0f} m" if dist_m is not None else "brak"
            lines.append(
                f"   - {item.get('name')} | {item.get('kind')} | km {float(item.get('km_on_route') or 0.0):.1f} | "
                f"distance_from_route_m={dist_s} | opening_hours={hours} | eta_at_poi={eta} | "
                f"status_hours={item.get('open_status')} | confidence={item.get('confidence')}"
            )
    if fallback_sections:
        lines.append("Awaryjne punkty strategiczne do 1 km:")
        for section in fallback_sections:
            item = section["item"]
            checkpoint_km = float(section["checkpoint_km"])
            lines.append(
                f"- {section['label']} checkpoint km {checkpoint_km:.1f} | AWARYJNY_FALLBACK_1KM | "
                "tylko gdy brak bliskiego OPEN_AT_ETA do 500 m"
            )
            hours = item.get("opening_hours") or ("Google Places" if item.get("open_source") == "google" else "brak")
            eta = str(item.get("eta_iso") or "brak").replace("T", " ")
            dist_m = item.get("distance_from_route_m")
            dist_s = f"{float(dist_m):.0f} m" if dist_m is not None else "brak"
            lines.append(
                f"   - {item.get('name')} | {item.get('kind')} | km {float(item.get('km_on_route') or 0.0):.1f} | "
                f"distance_from_route_m={dist_s} | opening_hours={hours} | eta_at_poi={eta} | "
                f"status_hours={item.get('open_status')} | confidence={item.get('confidence')}"
            )
    lines.append("Jawne ostrzeżenie: brak publicznego drinking_water nie oznacza braku możliwości zakupu wody.")
    return lines


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
    overpass_metrics = surface_profile.get("overpass_metrics")
    if not isinstance(overpass_metrics, dict):
        summary = surface_profile.get("surface_summary_json")
        overpass_metrics = summary.get("overpass_metrics") if isinstance(summary, dict) else None
    source = "surface_summary_json" if surface_profile.get("good_profile") else "legacy fallback"
    overpass_bits = []
    if isinstance(overpass_metrics, dict):
        for key, label in (
            ("chunks_total", "chunks_total"),
            ("chunks_ok", "chunks_ok"),
            ("chunks_failed", "chunks_failed"),
            ("timeout_count", "timeout_count"),
            ("http_error_count", "http_error_count"),
        ):
            value = overpass_metrics.get(key)
            if value is not None:
                overpass_bits.append(f"{label}={value}")
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
    if overpass_bits:
        lines.append("overpass: " + ", ".join(overpass_bits))
    lines.append("coverage_pct nie oznacza 100% tagów surface=* w OSM")
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


def _parse_fuel_rates(text: str | None) -> tuple[str | None, str | None]:
    """Zywienie g/h i L/h z B2/B3. Zwraca (np. '60 g/h', '0.85 L/h')."""
    if not text:
        return None, None
    g = re.search(r"(\d+(?:\.\d+)?)\s*g/h", text)
    l = re.search(r"(\d+(?:\.\d+)?)\s*[lL]/h", text)
    return (g.group(0) if g else None, l.group(0) if l else None)


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


def _read_poi_positions_cache(route_id, start=None):
    """Pozycje POI (km, opis) z kanonicznej bazy (route_poi_layer). 2026-07-02: bylo
    czytanie poi_positions_{route_id}.json z /artifacts/reports/ — usuniete (przeciek
    granicy). Raport czyta wylacznie z bazy."""
    if not route_id:
        return []
    try:
        canonical = read_canonical_route(route_id=route_id)
    except Exception:
        return []
    if not isinstance(canonical, dict):
        return []
    layers = canonical.get("layers") if isinstance(canonical.get("layers"), dict) else {}
    poi_rows = layers.get("route_poi_layer") or []
    label_map = {"water": "woda", "hard_resupply": "sklep",
                 "soft_food_stop": "jedzenie", "attraction": "atrakcja"}
    out = []
    for row in poi_rows:
        cat = str(row.get("category") or "").strip()
        label = label_map.get(cat)
        if not label:
            continue
        km = row.get("km_on_route")
        if km is None:
            continue
        name = str(row.get("name") or "").strip()
        hours = str(row.get("opening_hours") or "").strip()
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
    """Bloki pod wiatr z analizy planu z m/s i km/h -> [(km_start, km_end, wind_ms, wind_kmh), ...].
    Filtruje: dlugosc >= 3 km."""
    if not plan_txt:
        return []
    result = []
    for line in plan_txt.splitlines():
        if "Pod wiatr" not in line:
            continue
        after = line.split(":", 1)[1] if ":" in line else line
        ms = None
        kmh = None
        ms_m = re.search(r"\(~?([0-9.]+)\s*m/s(?:\s*/\s*([0-9.]+)\s*km/h)?\)", after)
        if ms_m:
            ms = float(ms_m.group(1))
            if ms_m.group(2):
                kmh = float(ms_m.group(2))
            else:
                kmh = ms * 3.6
        else:
            kmh_m = re.search(r"\(~?([0-9.]+)\s*km/h\)", after)
            if kmh_m:
                kmh = float(kmh_m.group(1))
                ms = kmh / 3.6
        for m in re.finditer(r"km\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)", after):
            a, b = float(m.group(1)), float(m.group(2))
            if (b - a) >= 3.0:
                result.append((a, b, ms, kmh))
    return result


def _format_wind_block_detail(wind_ms: float | None, wind_kmh: float | None) -> str:
    if wind_ms is None and wind_kmh is None:
        return ""
    if wind_ms is None and wind_kmh is not None:
        wind_ms = wind_kmh / 3.6
    if wind_ms is None:
        return ""
    if wind_kmh is None:
        wind_kmh = wind_ms * 3.6
    return f"~{wind_ms:.1f} m/s / {wind_kmh:.0f} km/h"


def _detect_blocks(surf_segments, climbs, wind_blocks, dist_km):
    """Wykrywa istotne bloki trasy (TASK 17).
    surf_segments: [(km_from, km_to, surf)], climbs: [(a, b, grade%)],
    wind_blocks: [(a, b, wind_ms|None, wind_kmh|None)], dist_km: float.
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

    for entry in wind_blocks:
        if len(entry) == 4:
            a, b, wind_ms, wind_kmh = entry
        elif len(entry) == 3:
            a, b, wind_kmh = entry
            wind_ms = wind_kmh / 3.6 if wind_kmh is not None else None
        else:
            continue
        kmh_str = _format_wind_block_detail(wind_ms, wind_kmh)
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


def _meteo_wind_blocks(meteo_result, thr: float = 1.5, min_km: float = 1.0):
    """Bloki 'pod wiatr' z wyniku METEO (per_segment.wind_tail_ms < 0 = czolo).
    JEDYNE zrodlo wiatru w raporcie (TASK 26) - zero parsowania z tekstu route_brief.
    Zwraca:
      head_km:  [(km_a, km_b), ...]                     -> _build_risk_combinations
      head_kmh: [(km_a, km_b, wind_ms, wind_kmh), ...]  -> _detect_blocks
    wind_ms = srednia sila wiatru otoczenia = hypot(tail, cross) po segmentach bloku."""
    import math
    if not isinstance(meteo_result, dict):
        return [], []
    ps = meteo_result.get("per_segment") if isinstance(meteo_result.get("per_segment"), list) else []
    segs = []
    for s in ps:
        if not isinstance(s, dict):
            continue
        tail = s.get("wind_tail_ms")
        if tail is None:
            continue
        try:
            km = float(s.get("km"))
            tail = float(tail)
        except (TypeError, ValueError):
            continue
        cross = s.get("wind_cross_ms") or 0.0
        try:
            amb = math.hypot(tail, float(cross))
        except (TypeError, ValueError):
            amb = abs(tail)
        segs.append((km, tail, amb))
    segs.sort(key=lambda x: x[0])
    runs = []
    cur = []
    for km, tail, amb in segs:
        if tail <= -thr:
            cur.append((km, tail, amb))
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    head_km, head_kmh = [], []
    for r in runs:
        a, b = r[0][0], r[-1][0]
        if (b - a) < min_km:
            continue
        amb_avg = sum(x[2] for x in r) / len(r)
        head_km.append((round(a, 1), round(b, 1)))
        head_kmh.append((round(a, 1), round(b, 1), round(amb_avg, 1), round(amb_avg * 3.6)))
    return head_km, head_kmh


def _build_context_document(plan, prof, t, fuel, tp, poi, wellness, start, route_id=None, meteo_result=None) -> str:
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

    # temp/precip zostaja tylko dla _infer_unknown_surface (heurystyka nawierzchni, nie pogoda)
    temp_c = _parse_temp_c(plan_txt)
    precip_mm = _parse_precip_mm(plan_txt)
    # POGODA i WIATR: jedyne zrodlo = silnik METEO (TASK 26). Zero parsowania z route_brief.
    _mwind_head, _mwind_kmh = _meteo_wind_blocks(meteo_result)
    out.append("### POGODA")
    if isinstance(meteo_result, dict) and meteo_result.get("status") == "OK":
        _peak = meteo_result.get("peak") if isinstance(meteo_result.get("peak"), dict) else {}
        if isinstance(_peak, dict) and _peak.get("wbgt_eff") is not None:
            out.append(f"- WBGT szczyt: {_peak.get('wbgt_eff')}°C (km {_peak.get('km')}, {_peak.get('eta')})")
        for _bit in _meteo_summary_bits(meteo_result):
            out.append(f"- {_bit}")
        if _mwind_head:
            _wtxt = "; ".join(f"km {a:g}–{b:g}" for a, b in _mwind_head)
            out.append(f"- pod wiatr: {_wtxt}")
        out.append("- źrodlo pogody: route_meteo_engine (Open-Meteo, os 50 m)")
    else:
        out.append("- brak danych pogodowych (METEO nieuruchomione)")
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
    wind_blocks = _mwind_head
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
    _wind17 = _mwind_kmh
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

    # TASK 26: wiatr z silnika METEO (sections_data["meteo"]), nie z tekstu route_brief
    _mres = (sd.get("meteo") or {}).get("result") if isinstance(sd.get("meteo"), dict) else None
    _mhead, _ = _meteo_wind_blocks(_mres)
    if _mhead:
        out.append("WIATR - pod wiatr (METEO):")
        out.extend(f"- km {a:g}–{b:g}" for a, b in _mhead)
    else:
        out.append("WIATR: brak istotnych blokow pod wiatr (METEO).")
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
    route_source = _read_route_source(route_id)
    route_read_path = str((route_source or {}).get("read_path") or "legacy_fallback")
    route_fallback_reason = (route_source or {}).get("fallback_reason")
    route_landscape_source = (route_source or {}).get("land_cover_preferred_source")

    base_args: dict[str, Any] = {}
    if route_id:
        base_args["route_id"] = route_id

    collected: dict[str, Any] = {"variant": variant}
    sections: list[str] = []
    H = sections.append
    integrity_errors: list[dict[str, Any]] = []

    H(f"# RAPORT TRASY - wariant {_VARIANT_TITLE[variant]}")
    if route_id:
        H(f"Trasa: {route_id} · {_RWGPS_URL.format(rid=route_id)}")
    H("")
    H("## A0 - ŹRÓDŁO DANYCH TRASY")
    H(f"- źródło danych trasy: {route_read_path}")
    if route_fallback_reason:
        H(f"- fallback_reason: {route_fallback_reason}")
    if route_landscape_source:
        H(f"- landscape_source: {route_landscape_source}")
    if route_source:
        layer_counts = route_source.get("layer_counts") or {}
        if isinstance(layer_counts, dict):
            summary_bits = []
            for key in ("route_surface_layer", "route_poi_layer", "route_shade_layer", "route_elevation_samples", "route_climb_events"):
                value = layer_counts.get(key)
                if value is not None:
                    summary_bits.append(f"{key}={value}")
            if summary_bits:
                H("- layer_counts: " + ", ".join(summary_bits))
        shade_count = route_source.get("route_shade_layer_count")
        shade_cov = route_source.get("shade_coverage_pct")
        if shade_count is not None or shade_cov is not None:
            shade_bits = []
            if shade_count is not None:
                shade_bits.append(f"route_shade_layer_count={shade_count}")
            if shade_cov is not None:
                shade_bits.append(f"shade_coverage_pct={float(shade_cov):.1f}%")
            H("- " + ", ".join(shade_bits))
    H("")
    for line in _route_shade_section_lines(route_source):
        H(line)
    for line in _route_elevation_section_lines(route_source):
        H(line)
    active_route_version = _fetch_route_version_record(route_id=route_id) if route_id else None

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
        surface_summary = route_source.get("canonical_surface_summary") if isinstance(route_source, dict) else None
        surface_canonical_lines = _route_surface_summary_lines(surface_summary)
        if surface_canonical_lines:
            for line in surface_canonical_lines:
                H(line)
            H("")
        if surface_canonical_lines:
            collected["surface_summary"] = surface_summary
            H("## A3B - DIAGNOSTYKA JAKOŚCI")
            for line in _route_surface_quality_lines_from_summary(surface_summary):
                H(line)
            H("")
            H("## A3C - GEOLOGIA / PODŁOŻE")
            for line in _route_surface_geology_lines_from_summary(surface_summary):
                H(line)
            H("")
            _ctx_lines = _route_surface_context_lines(route_source)
            if _ctx_lines:
                H("## A3D - RYZYKO NAWIERZCHNI (odcinki bez tagu OSM)")
                for line in _ctx_lines:
                    H(line)
                H("")
                collected["surface_context"] = route_source.get("canonical_surface_context")
        else:
            surface_profile = None
            try:
                from qbot_route_tools import _fetch_best_route_surface_profile as _fetch_surface_profile
                surface_profile = _fetch_surface_profile(route_id=route_id, route_artifact_id=base_args.get("artifact_id"))
            except Exception:
                surface_profile = None

            surface_guard = _route_version_guard(
                active_version=active_route_version,
                block_version=surface_profile,
                source_name="surface_summary_json",
            )
            if surface_guard["status"] == "ERROR":
                H(f"_DATA_INTEGRITY_ERROR: ROUTE_VERSION_MISMATCH — {surface_guard['message']}_")
                collected["surface_version_guard"] = surface_guard
                integrity_errors.append(surface_guard)
                if isinstance(surface_profile, dict):
                    surface_profile = dict(surface_profile)
                    surface_profile["good_profile"] = False
            elif surface_guard["status"] == "WARN":
                H(f"_WARN: SOURCE_VERSION_METADATA_MISSING — {surface_guard['message']}_")
                collected["surface_version_guard"] = surface_guard

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
        poi_canonical_lines = _route_poi_section_lines(route_source)
        for line in poi_canonical_lines:
            H(line)
        if poi_canonical_lines:
            H("")
        dist = _resolve_distance_km(route_id)
        poi = _read_poi_analysis_cache(route_id) if route_id else None
        if poi is None:
            poi = {
                "status": "UNAVAILABLE",
                "analysis_status": "UNAVAILABLE",
                "cache_path": None,
                "report_json_path": None,
                "report_path": None,
                "summary": {},
                "buffers": {},
                "hard_resupply": [],
                "soft_food_stop": [],
                "water": [],
                "attractions": [],
                "town_fallback_check": [],
                "missing_chunks": [],
                "missing_chunks_count": None,
                "generated_at": None,
            }
        poi_guard = _route_version_guard(
            active_version=active_route_version,
            block_version=poi,
            source_name="poi_cache",
        )
        if poi_guard["status"] == "ERROR":
            H(f"_DATA_INTEGRITY_ERROR: ROUTE_VERSION_MISMATCH — {poi_guard['message']}_")
            collected["poi_version_guard"] = poi_guard
            integrity_errors.append(poi_guard)
        elif poi_guard["status"] == "WARN":
            H(f"_WARN: SOURCE_VERSION_METADATA_MISSING — {poi_guard['message']}_")
            collected["poi_version_guard"] = poi_guard
        collected["poi"] = poi
        for line in _render_poi_supply_section(poi, ride_start=start, plan_text=_analysis(plan), route_distance_km=dist):
            H(line)
        if dist:
            H(f"Zakres trasy dla POI: km 0-{float(dist):.0f}")
        else:
            H("Zakres trasy dla POI: brak policzonego dystansu")
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

    # ---- A4 meteo / route_run_context: read-only overlay dla startu ----
    meteo_report = _meteo_report_payload(route_id, start)
    collected["meteo"] = meteo_report
    for line in meteo_report["lines"]:
        H(line)

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

    # ---- WERDYKT TRASY / DECYZJA: synthesize route layers for rider-facing summary ----
    for line in _route_verdict_section_lines(route_source, meteo_report, collected):
        H(line)

    collected["forma"] = _build_forma_line(start) if variant == "pelny" else None
    context_doc = _build_context_document(
        collected.get("plan"), collected.get("prof"), collected.get("t"),
        collected.get("fuel"), collected.get("tp"), collected.get("poi"),
        collected.get("forma"), start, route_id=route_id,
        meteo_result=(collected.get("meteo") or {}).get("result"),
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
        "status": "ERROR" if integrity_errors else "OK",
        "variant": variant,
        "route_id": route_id,
        "route_source": route_source,
        "analysis": analysis_text,
        "context_for_section_c": context_for_c,
        "notes": note,
    }
