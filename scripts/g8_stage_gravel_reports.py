#!/usr/bin/env python3
"""g8_stage_gravel_reports.py — G8 Stage Gravel Reports dla Gravel Intelligence.

Generuje per-etap raporty użytkowe tłumaczące G1/G2/G3 na ocenę trasy.
Wymaga artifacts: surface_{id}.json, risk_segments_{id}.json,
                   gravel_import_{id}_summary.json.

Usage:
    python scripts/g8_stage_gravel_reports.py --routes 55395119,55401067
    python scripts/g8_stage_gravel_reports.py --route-id 55395119
    python scripts/g8_stage_gravel_reports.py --batch-json /opt/qbot/artifacts/gravel/batch_*.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
SURFACE_DIR = ARTIFACTS_DIR / "surface"
GRAVEL_DIR = ARTIFACTS_DIR / "gravel"
REPORTS_DIR = GRAVEL_DIR / "reports"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="G8 Stage Gravel Reports")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--routes", help="Comma-separated route_ids")
    g.add_argument("--route-id", help="Single route_id")
    g.add_argument("--batch-json", help="Path to G7B batch JSON to extract routes")
    p.add_argument("--project-id", default="")
    return p.parse_args()


def _read_json(path: Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_routes(args: argparse.Namespace) -> list[str]:
    if args.route_id:
        return [args.route_id.strip()]
    if args.routes:
        return [r.strip() for r in args.routes.split(",") if r.strip()]
    if args.batch_json:
        batch = _read_json(Path(args.batch_json))
        if batch and "routes" in batch:
            return [r["route_id"] for r in batch["routes"]]
        print(f"ERROR: cannot read batch JSON {args.batch_json}")
        sys.exit(1)
    return []


def _load_surface(route_id: str) -> dict | None:
    return _read_json(SURFACE_DIR / f"surface_{route_id}.json")


def _load_risk(route_id: str) -> dict | None:
    return _read_json(SURFACE_DIR / f"risk_segments_{route_id}.json")


def _load_summary(route_id: str) -> dict | None:
    return _read_json(GRAVEL_DIR / f"gravel_import_{route_id}_summary.json")


def _has_high_sand_grass(risk: dict | None) -> bool:
    if not risk:
        return False
    for seg in risk.get("segments", []):
        rt = seg.get("risk_type", "")
        sev = seg.get("severity", "")
        if rt in ("sand", "grass") and sev == "high":
            return True
    return False


def _rate_difficulty(surface: dict | None, risk: dict | None) -> str:
    if not surface or not risk:
        return "N/A"
    confidence = surface.get("confidence", "low")
    unknown_pct = surface.get("unknown_pct", 0) or 0
    high_risk_km = risk.get("high_risk_km", 0) or 0
    total_risk_km = risk.get("total_risk_km", 0) or 0
    has_sand_grass = _has_high_sand_grass(risk)

    # Data-risk high if unknown > 35%
    data_risk = unknown_pct > 35

    # Base rating on high_risk_km
    if high_risk_km > 30:
        base = "trudny gravel / ostrożnie"
    elif high_risk_km > 15:
        base = "wymagający gravel"
    elif high_risk_km > 5:
        base = "normalny gravel"
    else:
        base = "łatwy gravel"

    # Boost for sand/grass
    if has_sand_grass:
        if "normalny" in base or "łatwy" in base:
            base = "wymagający gravel"
        elif "wymagający" in base:
            base = "trudny gravel / ostrożnie"

    if data_risk:
        return f"{base} — DATA-RISK WYSOKI ({unknown_pct:.0f}% unknown)"
    return base


def _recommend_gear(surface: dict | None, risk: dict | None, rating: str) -> str:
    if not surface or not risk:
        return "Brak danych do rekomendacji."

    unknown_pct = surface.get("unknown_pct", 0) or 0
    high_risk_km = risk.get("high_risk_km", 0) or 0
    has_sand_grass = _has_high_sand_grass(risk)
    is_data_risk = unknown_pct > 35
    is_hard = high_risk_km > 30 or "trudny" in rating

    lines = ["### Rekomendacja sprzętowa"]

    if is_data_risk or is_hard or has_sand_grass:
        lines.append("")
        lines.append("**Rower:** Gravel (zalecany)")
        lines.append("**Opony:** 50 mm gravel (np. Panaracer GravelKing SK, Schwalbe G-One Bite)")
        lines.append("**Ciśnienie orientacyjne:**")
        lines.append("- Przód: ~1.8–2.2 bar (26–32 psi)")
        lines.append("- Tył: ~2.0–2.4 bar (29–35 psi)")
        lines.append("**Uwagi:** Niższe ciśnienie dla lepszej trakcji na nieznanej nawierzchni.")
    elif "łatwy" in rating:
        lines.append("")
        lines.append("**Rower:** Gravel")
        lines.append("**Opony:** 45 mm semi-slick (np. Panaracer GravelKing SS, Schwalbe G-One Allround)")
        lines.append("**Ciśnienie orientacyjne:**")
        lines.append("- Przód: ~2.2–2.5 bar (32–36 psi)")
        lines.append("- Tył: ~2.4–2.7 bar (35–39 psi)")
        lines.append("**Uwagi:** Asfalt + utwardzone drogi — semi-slick wystarczy.")
    else:
        lines.append("")
        lines.append("**Rower:** Gravel")
        lines.append("**Opony:** 45–50 mm gravel (np. Panaracer GravelKing SK, Schwalbe G-One Bite)")
        lines.append("**Ciśnienie orientacyjne:**")
        lines.append("- Przód: ~2.0–2.3 bar (29–33 psi)")
        lines.append("- Tył: ~2.2–2.5 bar (32–36 psi)")
        lines.append("**Uwagi:** Przy 50 mm możesz zjechać ciśnienie o ~0.2 bar dla lepszego komfortu.")

    lines.append("")
    lines.append("**Uwagi dla Karoo 2:**")
    lines.append("- Warningi w GPX będą widoczne jako punkty ostrzegawcze na mapie.")
    lines.append("- Wysokie ryzyka (Alert) pojawią się na ekranie podczas jazdy.")
    lines.append("- Włącz powiadomienia o punktach na trasie (Proximity Alerts).")
    lines.append("- Nie importuj automatycznie — użyj Hammerhead Dashboard lub uploadu ręcznego.")

    return "\n".join(lines)


def _pct_str(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "-"
    return f"{val:.{decimals}f}%"


def _km_str(val: float | None, decimals: int = 1) -> str:
    if val is None:
        return "-"
    return f"{val:.{decimals}f} km"


def _interpret_unknown(pct: float | None) -> str:
    if pct is None:
        return "Brak danych."
    if pct > 50:
        return f"Bardzo wysoki ({pct:.0f}%) — znaczna część trasy nie ma danych OSM. Ryzyko danych."
    if pct > 35:
        return f"Wysoki ({pct:.0f}%) — spory odcinek bez pokrycia OSM. Warto sprawdzić trasę na mapie."
    if pct > 20:
        return f"Podwyższony ({pct:.0f}%) — część trasy wymaga weryfikacji."
    if pct > 5:
        return f"Niski ({pct:.0f}%) — większość nawierzchni znana."
    return f"Bardzo niski ({pct:.0f}%) — nawierzchnia dobrze udokumentowana."


def _generate_report_md(
    route_id: str,
    surface: dict | None,
    risk: dict | None,
    summary: dict | None,
    rating: str,
    gear: str,
) -> str:
    route_name = "—"
    distance_km = 0
    trkpt_count = 0

    if surface:
        route_name = surface.get("route_name") or route_name
        distance_km = surface.get("distance_km", 0)
        trkpt_count = surface.get("point_count", 0)
    if summary and summary.get("route_name"):
        route_name = summary["route_name"]

    confidence = surface.get("confidence", "N/A") if surface else "N/A"
    unknown_pct = surface.get("unknown_pct") if surface else None
    sb = (surface.get("surface_breakdown") or {}) if surface else {}
    skm = (surface.get("surface_km") or {}) if surface else {}

    risk_segments_count = risk.get("num_segments", 0) if risk else 0
    total_risk_km = risk.get("total_risk_km") if risk else None
    high_risk_km = risk.get("high_risk_km") if risk else None
    medium_risk_km = risk.get("medium_risk_km") if risk else None
    unknown_risk_km = risk.get("unknown_risk_km") if risk else None
    segments = risk.get("segments", []) if risk else []

    warnings_in_gpx = summary.get("warnings_in_gpx", 0) if summary else 0
    wpt_count = summary.get("wpt_count", 0) if summary else 0
    warnings_list = (summary.get("warnings_in_gpx_list") or []) if summary else []
    gpx_path = summary.get("output_gpx_path", "") if summary else ""

    lines = [
        f"# Stage Gravel Report",
        f"",
        f"**Trasa:** {route_name}",
        f"**Route ID:** {route_id}",
        f"**Dystans:** {distance_km:.1f} km",
        f"**Track points:** {trkpt_count}",
        f"**Ocena:** {rating}",
        f"",
        f"---",
        f"",
        f"## 1. Confidence i pokrycie danych",
        f"",
        f"| Metryka | Wartość |",
        f"|---|---|",
        f"| Confidence | {confidence} |",
        f"| Unknown surface | {_pct_str(unknown_pct)} |",
        f"| Interpretacja | {_interpret_unknown(unknown_pct)} |",
        f"",
        f"---",
        f"",
        f"## 2. Breakdown nawierzchni",
        f"",
        f"| Nawierzchnia | % | km |",
        f"|---|---|---|",
    ]

    surface_order = ["asphalt", "gravel", "compacted", "dirt", "sand", "grass", "unpaved_track", "unknown"]
    surface_labels = {
        "asphalt": "Asfalt / utwardzona",
        "gravel": "Gravel / szuter",
        "compacted": "Compacted / utwardzony żwir",
        "dirt": "Grunt / ziemia",
        "sand": "Piasek",
        "grass": "Trawa",
        "unpaved_track": "Nieutwardzona / track",
        "unknown": "Nieznana (brak tagu OSM)",
    }
    for key in surface_order:
        pct = sb.get(key, 0)
        km = skm.get(key, 0)
        label = surface_labels.get(key, key)
        if pct is not None and pct > 0:
            lines.append(f"| {label} | {pct:.1f}% | {km:.2f} km |")
        else:
            lines.append(f"| {label} | — | — |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Risk summary",
        "",
        "| Metryka | Wartość |",
        "|---|---|",
        f"| Liczba segmentów ryzyka | {risk_segments_count} |",
        f"| Total risk km | {_km_str(total_risk_km)} |",
        f"| High risk km | {_km_str(high_risk_km)} |",
        f"| Medium risk km | {_km_str(medium_risk_km)} |",
        f"| Unknown risk km | {_km_str(unknown_risk_km)} |",
        "",
    ])

    # Top 5 risk segments
    top5 = segments[:5]
    if top5:
        lines.extend([
            "### Top 5 segmentów ryzyka",
            "",
            "| Lp. | km | długość | typ ryzyka | severity | opis |",
            "|---|---|---|---|---|---|",
        ])
        for i, seg in enumerate(top5, 1):
            start = seg.get("start_km", 0)
            end = seg.get("end_km", 0)
            length = seg.get("length_km", 0)
            rtype = seg.get("risk_type", "?")
            severity = seg.get("severity", "?")
            reason = seg.get("reason", "")[:80]
            lines.append(f"| {i} | {start:.1f}–{end:.1f} | {length:.1f} km | {rtype} | {severity} | {reason} |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Warningi w GPX",
        "",
        f"Liczba warningów w GPX: **{warnings_in_gpx}** (waypoints: {wpt_count})",
        "",
    ])

    if warnings_list:
        lines.extend([
            "| Nazwa <wpt> | km | długość | opis human-readable |",
            "|---|---|---|---|",
        ])
        for w in warnings_list:
            wname = w.get("name", "?")
            start = w.get("start_km", 0)
            end = w.get("end_km", 0)
            length = w.get("length_km", 0)
            desc = w.get("desc_human", w.get("desc_technical", ""))[:100]
            lines.append(f"| {wname} | {start:.1f}–{end:.1f} | {length:.1f} km | {desc} |")

    lines.extend([
        "",
        "---",
        "",
        "## 5. Ocena użytkowa",
        "",
        f"**{rating}**",
        "",
    ])

    # Detailed explanation
    if surface and risk:
        reasons = []
        hk = high_risk_km or 0
        uk = unknown_pct or 0
        if hk > 30:
            reasons.append(f"Bardzo dużo wysokiego ryzyka ({hk:.1f} km > 30 km).")
        elif hk > 15:
            reasons.append(f"Znaczący dystans wysokiego ryzyka ({hk:.1f} km).")
        elif hk > 5:
            reasons.append(f"Umiarkowany dystans wysokiego ryzyka ({hk:.1f} km).")
        else:
            reasons.append(f"Niski dystans wysokiego ryzyka ({hk:.1f} km).")
        if uk > 35:
            reasons.append(f"Wysoki % unknown ({uk:.0f}%) — ryzyko danych.")
        if _has_high_sand_grass(risk):
            reasons.append("Występują odcinki piasku/trawy wysokiego ryzyka.")
        lines.append("**Uzasadnienie:**")
        for r in reasons:
            lines.append(f"- {r}")

    lines.extend([
        "",
        "---",
        "",
        gear,
        "",
        "---",
        "",
        "## 6. Ostrzeżenia",
        "",
    ])

    alerts = []

    if unknown_pct is not None and unknown_pct > 35:
        alerts.append(f"- ⚠️ **Dużo unknown ({unknown_pct:.0f}%)** — dane OSM nie pokrywają znacznej części trasy. "
                       "Rzeczywista nawierzchnia może się różnić. Weryfikacja na mapie satelitarnej zalecana.")
    elif unknown_pct is not None and unknown_pct > 20:
        alerts.append(f"- ℹ️ **Podwyższony unknown ({unknown_pct:.0f}%)** — część trasy bez danych OSM. "
                       "Warto sprawdzić na mapie.")

    if high_risk_km is not None and high_risk_km > 20:
        alerts.append(f"- ⚠️ **Długie odcinki high-risk ({high_risk_km:.1f} km)** — "
                       "przygotuj się na wolniejszą jazdę i większe zmęczenie.")

    if unknown_pct is not None and unknown_pct > 20:
        alerts.append("- ℹ️ **Możliwe błędy OSM** — nieoznaczone drogi leśne/rolne mogą być "
                       "przejezdne lub nie. Nie zakładaj, że brak tagu = nieprzejezdne.")

    if confidence == "low":
        alerts.append("- ℹ️ **Niski confidence** — mała liczba próbek OSM. Wyniki orientacyjne.")

    if not summary or not summary.get("ok"):
        alerts.append("- ⚠️ **Brak danych G3** — nie wygenerowano GPX z warningami.")

    if not alerts:
        alerts.append("- Brak istotnych ostrzeżeń dla tej trasy.")

    lines.extend(alerts)
    lines.extend([
        "",
        "---",
        "",
        "## Ścieżki artefaktów",
        "",
        f"- **GPX importowy:** `{gpx_path}`",
        f"- **Surface JSON:** `{SURFACE_DIR / f'surface_{route_id}.json'}`",
        f"- **Risk segments JSON:** `{SURFACE_DIR / f'risk_segments_{route_id}.json'}`",
        f"- **G3 summary JSON:** `{GRAVEL_DIR / f'gravel_import_{route_id}_summary.json'}`",
        "",
        "---",
        f"*Raport wygenerowany przez g8_stage_gravel_reports.py — {_iso_now()}*",
        "",
    ])

    return "\n".join(lines)


def _generate_report_json(
    route_id: str,
    surface: dict | None,
    risk: dict | None,
    summary: dict | None,
    rating: str,
) -> dict:
    route_name = "—"
    distance_km = 0
    trkpt_count = 0
    if surface:
        route_name = surface.get("route_name") or route_name
        distance_km = surface.get("distance_km", 0)
        trkpt_count = surface.get("point_count", 0)
    if summary and summary.get("route_name"):
        route_name = summary["route_name"]

    sb = (surface.get("surface_breakdown") or {}) if surface else {}
    skm = (surface.get("surface_km") or {}) if surface else {}
    segments = risk.get("segments", []) if risk else []
    warnings_list = (summary.get("warnings_in_gpx_list") or []) if summary else []

    surface_order = ["asphalt", "gravel", "compacted", "dirt", "sand", "grass", "unpaved_track", "unknown"]
    surface_breakdown_list = []
    for key in surface_order:
        pct = sb.get(key, 0)
        km = skm.get(key, 0)
        if pct is not None and pct > 0:
            surface_breakdown_list.append({
                "surface": key, "label": _surface_label(key),
                "pct": round(pct, 2), "km": round(km, 2),
            })

    top5 = []
    for seg in segments[:5]:
        top5.append({
            "start_km": seg.get("start_km"),
            "end_km": seg.get("end_km"),
            "length_km": seg.get("length_km"),
            "risk_type": seg.get("risk_type"),
            "severity": seg.get("severity"),
            "reason": seg.get("reason"),
            "dominant_surface": seg.get("dominant_surface"),
        })

    warnings_out = []
    for w in warnings_list:
        warnings_out.append({
            "name": w.get("name"),
            "start_km": w.get("start_km"),
            "end_km": w.get("end_km"),
            "length_km": w.get("length_km"),
            "risk_type": w.get("risk_type"),
            "severity": w.get("severity"),
            "desc_human": w.get("desc_human"),
            "desc_technical": w.get("desc_technical"),
        })

    has_sand_grass = _has_high_sand_grass(risk)

    return {
        "route_id": route_id,
        "route_name": route_name,
        "distance_km": round(distance_km, 2) if distance_km else None,
        "trkpt_count": trkpt_count,
        "rating": rating,
        "confidence": surface.get("confidence") if surface else None,
        "unknown_pct": surface.get("unknown_pct") if surface else None,
        "surface_breakdown": surface_breakdown_list,
        "risk_summary": {
            "num_segments": risk.get("num_segments", 0) if risk else 0,
            "total_risk_km": round(risk.get("total_risk_km", 0), 2) if risk else None,
            "high_risk_km": round(risk.get("high_risk_km", 0), 2) if risk else None,
            "medium_risk_km": round(risk.get("medium_risk_km", 0), 2) if risk else None,
            "unknown_risk_km": round(risk.get("unknown_risk_km", 0), 2) if risk else None,
        },
        "top5_segments": top5,
        "warnings_in_gpx": {
            "count": len(warnings_out),
            "wpt_count": summary.get("wpt_count", 0) if summary else 0,
            "list": warnings_out,
        },
        "has_sand_grass_high": has_sand_grass,
        "gpx_path": summary.get("output_gpx_path", "") if summary else "",
        "generated_at": _iso_now(),
        "generator": "g8_stage_gravel_reports.py",
    }


def _surface_label(key: str) -> str:
    labels = {
        "asphalt": "Asfalt / utwardzona",
        "gravel": "Gravel / szuter",
        "compacted": "Compacted / utwardzony żwir",
        "dirt": "Grunt / ziemia",
        "sand": "Piasek",
        "grass": "Trawa",
        "unpaved_track": "Nieutwardzona / track",
        "unknown": "Nieznana",
    }
    return labels.get(key, key)


def _generate_index_md(reports: list[dict], project_id: str) -> str:
    ts = _ts()

    lines = [
        f"# Stage Gravel Reports — Index",
        f"",
        f"**Generated:** {_iso_now()}",
        f"**Project:** {project_id or '(none)'}",
        f"**Total reports:** {len(reports)}",
        f"",
        f"---",
        f"",
        f"## Porównanie etapów",
        f"",
        f"| # | route_id | nazwa | km | ocena | confidence | unknown % | high risk km | warningi |",
        f"|---|---|---|---|---|---|---|---|---|",
    ]

    for i, r in enumerate(reports, 1):
        rid = r.get("route_id", "?")
        name = (r.get("route_name") or "?")[:45]
        km = f"{r.get('distance_km', 0):.1f}" if r.get("distance_km") else "?"
        rating = r.get("rating", "?")
        conf = r.get("confidence") or "-"
        unk = f"{r.get('unknown_pct', 0):.1f}" if isinstance(r.get("unknown_pct"), (int, float)) else "-"
        hrisk = f"{r.get('risk_summary', {}).get('high_risk_km', 0):.1f}" if r.get("risk_summary") else "-"
        wcnt = r.get("warnings_in_gpx", {}).get("count", 0)
        lines.append(f"| {i} | {rid} | {name} | {km} | {rating} | {conf} | {unk} | {hrisk} | {wcnt} |")

    lines.extend([
        "",
        "---",
        "",
        "## Ranking: najbardziej ryzykowny etap",
        "",
    ])

    sorted_by_risk = sorted(reports, key=lambda r: (r.get("risk_summary") or {}).get("high_risk_km", 0) or 0, reverse=True)
    if sorted_by_risk:
        worst = sorted_by_risk[0]
        lines.append(f"- **#{worst.get('route_id')}** — {worst.get('route_name')} — "
                      f"{worst.get('risk_summary', {}).get('high_risk_km', 0):.1f} km high risk — "
                      f"{worst.get('rating')}")

    lines.extend([
        "",
        "## Ranking: największy unknown %",
        "",
    ])

    sorted_by_unknown = sorted(reports, key=lambda r: r.get("unknown_pct", 0) or 0, reverse=True)
    if sorted_by_unknown:
        worst_u = sorted_by_unknown[0]
        lines.append(f"- **#{worst_u.get('route_id')}** — {worst_u.get('route_name')} — "
                      f"{worst_u.get('unknown_pct', 0):.1f}% unknown — "
                      f"{worst_u.get('rating')}")

    lines.extend([
        "",
        "## Ranking: najłatwiejszy etap",
        "",
    ])

    sorted_easiest = sorted(reports, key=lambda r: (r.get("risk_summary") or {}).get("high_risk_km", 0) or 0)
    if sorted_easiest:
        easiest = sorted_easiest[0]
        lines.append(f"- **#{easiest.get('route_id')}** — {easiest.get('route_name')} — "
                      f"{easiest.get('risk_summary', {}).get('high_risk_km', 0):.1f} km high risk — "
                      f"{easiest.get('rating')}")

    lines.extend([
        "",
        "---",
        "",
        "## Lista raportów",
        "",
    ])

    for r in reports:
        rid = r.get("route_id", "?")
        lines.append(f"- `reports/stage_gravel_report_{rid}.md`")
        lines.append(f"  `reports/stage_gravel_report_{rid}.json`")

    lines.extend([
        "",
        "---",
        f"*Index wygenerowany przez g8_stage_gravel_reports.py — {_iso_now()}*",
    ])

    return "\n".join(lines)


def _generate_index_json(reports: list[dict], project_id: str) -> dict:
    ts = _ts()
    return {
        "meta": {
            "generated_at": _iso_now(),
            "project_id": project_id,
            "total_reports": len(reports),
            "generator": "g8_stage_gravel_reports.py",
        },
        "reports": reports,
        "ranking": {
            "most_risky": max(reports, key=lambda r: (r.get("risk_summary") or {}).get("high_risk_km", 0) or 0)
            if reports else None,
            "highest_unknown": max(reports, key=lambda r: r.get("unknown_pct", 0) or 0)
            if reports else None,
            "easiest": min(reports, key=lambda r: (r.get("risk_summary") or {}).get("high_risk_km", 0) or 0)
            if reports else None,
        },
    }


def process_route(route_id: str) -> dict | None:
    surface = _load_surface(route_id)
    risk = _load_risk(route_id)
    summary = _load_summary(route_id)

    if not surface and not risk and not summary:
        print(f"  ✗ {route_id} — brak danych (surface/risk/summary)")
        return None

    if not surface:
        print(f"  ⚠ {route_id} — brak G1 surface (kontynuuję)")
    if not risk:
        print(f"  ⚠ {route_id} — brak G2 risk (kontynuuję)")

    rating = _rate_difficulty(surface, risk)
    gear = _recommend_gear(surface, risk, rating)

    md_content = _generate_report_md(route_id, surface, risk, summary, rating, gear)
    json_data = _generate_report_json(route_id, surface, risk, summary, rating)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    md_path = REPORTS_DIR / f"stage_gravel_report_{route_id}.md"
    json_path = REPORTS_DIR / f"stage_gravel_report_{route_id}.json"

    with open(md_path, "w") as f:
        f.write(md_content)
    with open(json_path, "w") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"  ✓ {route_id} — {json_data.get('route_name', '?')[:55]} — {rating}")

    return json_data


def main():
    args = _parse_args()
    route_ids = _resolve_routes(args)

    if not route_ids:
        print("ERROR: no route_ids resolved")
        sys.exit(1)

    print("=" * 70)
    print("G8 Stage Gravel Reports")
    print("=" * 70)
    print(f"Routes: {len(route_ids)} — {', '.join(route_ids)}")
    print()

    reports = []
    for rid in route_ids:
        rep = process_route(rid)
        if rep:
            reports.append(rep)

    if not reports:
        print("\nNo reports generated.")
        sys.exit(1)

    # Index
    index_md = _generate_index_md(reports, args.project_id)
    index_json = _generate_index_json(reports, args.project_id)

    ts = _ts()
    index_md_path = REPORTS_DIR / f"stage_gravel_reports_index_{ts}.md"
    index_json_path = REPORTS_DIR / f"stage_gravel_reports_index_{ts}.json"

    with open(index_md_path, "w") as f:
        f.write(index_md)
    with open(index_json_path, "w") as f:
        json.dump(index_json, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"G8 COMPLETE — {len(reports)} reports, {len(route_ids) - len(reports)} skipped")
    print(f"{'='*70}")
    print(f"Reports dir: {REPORTS_DIR}")
    print(f"Index MD:    {index_md_path}")
    print(f"Index JSON:  {index_json_path}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
