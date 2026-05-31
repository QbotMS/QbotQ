#!/usr/bin/env python3
"""g9_surface_quality_review.py — G9 Surface Data Quality / Multi-source Validation.

Wykrywa odcinki wymagające walidacji nawierzchni, klasyfikuje je priorytetowo
i przygotowuje strukturę pod manual overrides.

Usage:
    python scripts/g9_surface_quality_review.py --routes 55395119,55401067
    python scripts/g9_surface_quality_review.py --route-id 55395119
    python scripts/g9_surface_quality_review.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_DIR = Path("/opt/qbot/artifacts")
SURFACE_DIR = ARTIFACTS_DIR / "surface"
GRAVEL_DIR = ARTIFACTS_DIR / "gravel"
REPORTS_DIR = GRAVEL_DIR / "reports"
QUALITY_DIR = ARTIFACTS_DIR / "surface_quality"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="G9 Surface Data Quality Review")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--routes", help="Comma-separated route_ids")
    g.add_argument("--route-id", help="Single route_id")
    g.add_argument("--all", action="store_true", help="All routes with G1 data")
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
    if args.all:
        paths = sorted(SURFACE_DIR.glob("surface_*.json"))
        ids = []
        for p in paths:
            rid = p.stem.replace("surface_", "")
            if rid.isdigit():
                ids.append(rid)
        return ids
    return []


def _load_surface(route_id: str) -> dict | None:
    return _read_json(SURFACE_DIR / f"surface_{route_id}.json")


def _load_risk(route_id: str) -> dict | None:
    return _read_json(SURFACE_DIR / f"risk_segments_{route_id}.json")


def _load_g8_report(route_id: str) -> dict | None:
    return _read_json(REPORTS_DIR / f"stage_gravel_report_{route_id}.json")


def _assign_priority(seg: dict) -> str:
    risk_type = seg.get("risk_type", "")
    severity = seg.get("severity", "")
    confidence = seg.get("confidence", "low")
    length_km = seg.get("length_km", 0) or 0
    dominant_surface = seg.get("dominant_surface", "")

    # High priority
    if risk_type == "unknown_long" and severity == "high" and length_km > 3:
        return "high"
    if (risk_type == "unknown_long" or dominant_surface == "unknown") and length_km > 5:
        return "high"
    if risk_type == "mixed_bad" and length_km > 2:
        return "high"
    if confidence == "low" and length_km > 3:
        return "high"

    # Medium priority
    if risk_type == "unknown_long" and length_km > 1:
        return "medium"
    if dominant_surface == "unknown" and length_km > 1:
        return "medium"
    if confidence == "low" and length_km > 1:
        return "medium"
    if severity == "high" and length_km > 3:
        return "medium"
    if dominant_surface in ("dirt", "sand", "grass") and length_km > 3:
        return "medium"

    # Low priority
    if length_km > 0.5:
        return "low"

    return "low"


def _suggest_validation_source(seg: dict, priority: str) -> str:
    risk_type = seg.get("risk_type", "")
    confidence = seg.get("confidence", "")

    if priority == "high":
        if risk_type == "unknown_long":
            return "satellite/orthophoto check"
        if confidence == "low":
            return "OSM edit/manual review"
        return "satellite/orthophoto check"

    if priority == "medium":
        if risk_type == "unknown_long":
            return "Mapillary/photo check"
        if confidence == "low":
            return "user memory/manual override"
        return "manual ride note"

    return "user memory/manual override"


def _review_route(route_id: str) -> dict | None:
    surface = _load_surface(route_id)
    risk = _load_risk(route_id)
    g8 = _load_g8_report(route_id)

    if not surface and not risk:
        return None

    route_name = "—"
    if surface:
        route_name = surface.get("route_name") or route_name
    if not route_name or route_name == "—":
        if g8:
            route_name = g8.get("route_name") or route_name

    confidence = surface.get("confidence", "N/A") if surface else "N/A"
    unknown_pct = surface.get("unknown_pct", 0) or 0 if surface else 0
    distance_km = surface.get("distance_km", 0) or 0 if surface else 0
    segments = risk.get("segments", []) if risk else []

    review_items = []
    used_types = set()

    for seg in segments:
        priority = _assign_priority(seg)
        length_km = seg.get("length_km", 0) or 0

        if priority == "low" and length_km < 1:
            continue

        source = _suggest_validation_source(seg, priority)
        risk_type = seg.get("risk_type", "")
        used_types.add(risk_type)

        item = {
            "route_id": route_id,
            "start_km": round(seg.get("start_km", 0), 2),
            "end_km": round(seg.get("end_km", 0), 2),
            "length_km": round(length_km, 2),
            "representative_lat": seg.get("representative_lat"),
            "representative_lon": seg.get("representative_lon"),
            "current_surface": seg.get("dominant_surface", "unknown"),
            "risk_type": risk_type,
            "severity": seg.get("severity", ""),
            "segment_confidence": seg.get("confidence", "low"),
            "reason_for_review": seg.get("reason", "")[:200],
            "priority": priority,
            "suggested_validation_source": source,
        }
        review_items.append(item)

    # Also add a summary-level quality note based on overall unknown %
    high_count = sum(1 for it in review_items if it["priority"] == "high")
    medium_count = sum(1 for it in review_items if it["priority"] == "medium")
    low_count = sum(1 for it in review_items if it["priority"] == "low")
    total_review_km = round(sum(it["length_km"] for it in review_items), 2)

    result = {
        "route_id": route_id,
        "route_name": route_name,
        "distance_km": round(distance_km, 2) if distance_km else None,
        "surface_confidence": confidence,
        "unknown_pct": round(unknown_pct, 1) if unknown_pct else 0,
        "review_summary": {
            "total_segments_for_review": len(review_items),
            "high_priority": high_count,
            "medium_priority": medium_count,
            "low_priority": low_count,
            "total_km_requiring_review": total_review_km,
            "pct_of_route": round(total_review_km / distance_km * 100, 1) if distance_km and distance_km > 0 else 0,
        },
        "review_items": review_items,
        "generated_at": _iso_now(),
        "generator": "g9_surface_quality_review.py",
    }

    if surface and surface.get("unknown_pct", 0) > 35:
        result["data_quality_flag"] = "DATA-RISK HIGH — unknown >35%"

    return result


def _generate_md(result: dict) -> str:
    rid = result["route_id"]
    name = result.get("route_name", "—")
    summary = result.get("review_summary", {})
    items = result.get("review_items", [])
    dq_flag = result.get("data_quality_flag")

    lines = [
        f"# Surface Quality Review — {name}",
        f"",
        f"**Route ID:** {rid}",
        f"**Dystans:** {result.get('distance_km', '?')} km",
        f"**Confidence:** {result.get('surface_confidence', 'N/A')}",
        f"**Unknown:** {result.get('unknown_pct', '?')}%",
    ]

    if dq_flag:
        lines.append(f"**⚠️ {dq_flag}**")

    lines.extend([
        "",
        "---",
        "",
        "## Podsumowanie walidacji",
        "",
        f"| Metryka | Wartość |",
        f"|---|---|",
        f"| Segmenty do walidacji | {summary.get('total_segments_for_review', 0)} |",
        f"| High priority | {summary.get('high_priority', 0)} |",
        f"| Medium priority | {summary.get('medium_priority', 0)} |",
        f"| Low priority | {summary.get('low_priority', 0)} |",
        f"| km do review | {summary.get('total_km_requiring_review', 0)} km |",
        f"| % trasy do review | {summary.get('pct_of_route', 0)}% |",
        "",
        "---",
        "",
        "## Segmenty wymagające walidacji",
        "",
    ])

    if not items:
        lines.append("Brak segmentów wymagających walidacji.")
    else:
        lines.extend([
            "| # | km | długość | surface | typ ryzyka | severity | confidence | priorytet | źródło walidacji |",
            "|---|---|---|---|---|---|---|---|---|",
        ])
        for i, it in enumerate(items, 1):
            start = it.get("start_km", 0)
            end = it.get("end_km", 0)
            length = it.get("length_km", 0)
            surface_cur = it.get("current_surface", "?")
            rtype = it.get("risk_type", "?")
            sev = it.get("severity", "?")
            conf = it.get("segment_confidence", "?")
            prio = it.get("priority", "?")
            src = it.get("suggested_validation_source", "?")
            lines.append(f"| {i} | {start:.1f}–{end:.1f} | {length:.1f} km | {surface_cur} | {rtype} | {sev} | {conf} | {prio} | {src} |")

    lines.extend([
        "",
        "---",
        "",
        "## Szczegóły segmentów",
        "",
    ])

    for i, it in enumerate(items, 1):
        lines.extend([
            f"### #{i} — km {it['start_km']:.1f}–{it['end_km']:.1f} ({it['length_km']:.1f} km)",
            f"",
            f"- **Priorytet:** {it['priority']}",
            f"- **Obecna nawierzchnia:** {it['current_surface']}",
            f"- **Typ ryzyka:** {it['risk_type']} ({it['severity']})",
            f"- **Confidence segmentu:** {it['segment_confidence']}",
            f"- **Powód:** {it['reason_for_review']}",
            f"- **Sugerowane źródło walidacji:** {it['suggested_validation_source']}",
            f"- **Lokalizacja:** {it.get('representative_lat','?')}, {it.get('representative_lon','?')}",
            "",
        ])

    lines.extend([
        "---",
        f"*Raport wygenerowany przez g9_surface_quality_review.py — {_iso_now()}*",
    ])

    return "\n".join(lines)


def _generate_index_md(results: list[dict]) -> str:
    ts = _ts()

    lines = [
        f"# Surface Quality Review — Index",
        f"",
        f"**Generated:** {_iso_now()}",
        f"**Total routes:** {len(results)}",
        f"",
        f"---",
        f"",
        f"## Porównanie",
        f"",
        f"| # | route_id | nazwa | km | conf | unknown % | review km | review % | high | med | low | flag |",
        f"|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    total_review_km = 0
    total_high = 0
    total_segments = 0

    for i, r in enumerate(results, 1):
        rid = r["route_id"]
        name = (r.get("route_name") or "?")[:40]
        km = f"{r.get('distance_km', 0):.1f}" if r.get("distance_km") else "?"
        conf = r.get("surface_confidence", "?")
        unk = f"{r.get('unknown_pct', 0):.1f}" if isinstance(r.get("unknown_pct"), (int, float)) else "?"
        s = r.get("review_summary", {})
        rkm = f"{s.get('total_km_requiring_review', 0):.1f}"
        rpct = f"{s.get('pct_of_route', 0):.1f}"
        hi = s.get("high_priority", 0)
        med = s.get("medium_priority", 0)
        lo = s.get("low_priority", 0)
        flag = "⚠️" if r.get("data_quality_flag") else "✓"
        total_review_km += s.get("total_km_requiring_review", 0) or 0
        total_high += hi
        total_segments += s.get("total_segments_for_review", 0) or 0
        lines.append(f"| {i} | {rid} | {name} | {km} | {conf} | {unk} | {rkm} | {rpct}% | {hi} | {med} | {lo} | {flag} |")

    lines.extend([
        "",
        "---",
        "",
        "## Zbiorcze podsumowanie",
        "",
        f"- **Łączna liczba tras:** {len(results)}",
        f"- **Łączna liczba segmentów do walidacji:** {total_segments}",
        f"- **Łączne km do review:** {total_review_km:.1f} km",
        f"- **Łączna liczba high priority:** {total_high}",
        "",
    ])

    # Top 10 segments across all routes
    all_items = []
    for r in results:
        for it in r.get("review_items", []):
            all_items.append(it)

    sorted_items = sorted(all_items, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "low"), 3))
    top10 = sorted_items[:10]

    if top10:
        lines.extend([
            "---",
            "",
            "## Top 10 najpilniejszych segmentów",
            "",
            "| # | route_id | km | długość | surface | typ | priorytet | źródło |",
            "|---|---|---|---|---|---|---|---|",
        ])
        for i, it in enumerate(top10, 1):
            rid = it.get("route_id", "?")
            start = it.get("start_km", 0)
            end = it.get("end_km", 0)
            length = it.get("length_km", 0)
            surf = it.get("current_surface", "?")
            rtype = it.get("risk_type", "?")
            prio = it.get("priority", "?")
            src = it.get("suggested_validation_source", "?")
            lines.append(f"| {i} | {rid} | {start:.1f}–{end:.1f} | {length:.1f} km | {surf} | {rtype} | {prio} | {src} |")

    lines.extend([
        "",
        "---",
        "",
        "## Największe problemy danych",
        "",
    ])

    data_risk_routes = [r for r in results if r.get("data_quality_flag")]
    if data_risk_routes:
        lines.append("**Trasy DATA-RISK (unknown >35%):**")
        for r in data_risk_routes:
            pct = r.get("unknown_pct", 0)
            lines.append(f"- {r['route_id']} — {r.get('route_name','?')} — {pct:.0f}% unknown")
    else:
        lines.append("Brak tras z DATA-RISK wysokim unknown.")

    lines.extend([
        "",
        "**Trasy z największą liczbą segmentów do walidacji:**",
        "",
    ])
    sorted_by_segments = sorted(results, key=lambda r: (r.get("review_summary") or {}).get("total_segments_for_review", 0), reverse=True)
    for r in sorted_by_segments[:3]:
        s = r.get("review_summary", {})
        lines.append(f"- {r['route_id']} — {r.get('route_name','?')} — {s.get('total_segments_for_review',0)} segmentów, {s.get('total_km_requiring_review',0):.1f} km")

    lines.extend([
        "",
        "---",
        f"*Index wygenerowany przez g9_surface_quality_review.py — {_iso_now()}*",
    ])

    return "\n".join(lines)


def _generate_index_json(results: list[dict]) -> dict:
    all_items = []
    for r in results:
        for it in r.get("review_items", []):
            all_items.append(it)

    sorted_items = sorted(all_items, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "low"), 3))
    top10 = sorted_items[:10]

    total_review_km = sum((r.get("review_summary") or {}).get("total_km_requiring_review", 0) or 0 for r in results)
    total_segments = sum((r.get("review_summary") or {}).get("total_segments_for_review", 0) or 0 for r in results)
    total_high = sum((r.get("review_summary") or {}).get("high_priority", 0) or 0 for r in results)

    data_risk_ids = [r["route_id"] for r in results if r.get("data_quality_flag")]

    return {
        "meta": {
            "generated_at": _iso_now(),
            "total_routes": len(results),
            "total_segments_for_review": total_segments,
            "total_km_requiring_review": round(total_review_km, 2),
            "total_high_priority": total_high,
            "data_risk_routes": data_risk_ids,
            "generator": "g9_surface_quality_review.py",
        },
        "routes": results,
        "top_10_segments": top10,
    }


def _create_override_template() -> dict:
    return {
        "$schema": "manual_surface_override_v1",
        "description": "Szablon nadpisania nawierzchni dla segmentu trasy.",
        "fields": {
            "route_id": {
                "type": "integer",
                "description": "RWGPS route_id",
                "example": 55401067,
            },
            "segment_id": {
                "type": "string",
                "description": "Unikalne ID segmentu (np. unknown_55401067_28.6)",
                "example": "unknown_55401067_28.6",
            },
            "start_km": {
                "type": "number",
                "description": "Początek segmentu w km",
                "example": 28.6,
            },
            "end_km": {
                "type": "number",
                "description": "Koniec segmentu w km",
                "example": 40.9,
            },
            "override_surface": {
                "type": "string",
                "enum": ["asphalt", "gravel", "dirt", "sand", "grass", "unknown", "mixed"],
                "description": "Rzeczywista nawierzchnia po weryfikacji",
                "example": "gravel",
            },
            "rideability": {
                "type": "string",
                "enum": ["easy", "normal", "hard", "hike_a_bike"],
                "description": "Ocena przejezdności",
                "example": "normal",
            },
            "confidence": {
                "type": "string",
                "enum": ["user_confirmed", "photo_confirmed", "low"],
                "description": "Poziom ufności override",
                "example": "photo_confirmed",
            },
            "note": {
                "type": "string",
                "description": "Notatka uzasadniająca override",
                "example": "Potwierdzone na zdjęciach Mapillary — dobrze utrzymana droga szutrowa.",
            },
            "source": {
                "type": "string",
                "enum": ["user_manual", "ride_after_action", "mapillary", "satellite", "osm_edit"],
                "description": "Źródło override",
                "example": "mapillary",
            },
            "created_at": {
                "type": "string",
                "description": "Data utworzenia override (ISO 8601)",
                "example": "2026-05-31T12:00:00+00:00",
            },
        },
        "example": {
            "route_id": 55401067,
            "segment_id": "unknown_55401067_28.6",
            "start_km": 28.6,
            "end_km": 40.9,
            "override_surface": "gravel",
            "rideability": "normal",
            "confidence": "photo_confirmed",
            "note": "Potwierdzone na zdjęciach satelitarnych — droga szutrowa, przejezdna.",
            "source": "satellite",
            "created_at": "2026-05-31T12:00:00+00:00",
        },
        "override_history": [],
    }


def main():
    args = _parse_args()
    route_ids = _resolve_routes(args)

    if not route_ids:
        print("ERROR: no route_ids resolved")
        sys.exit(1)

    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("G9 Surface Data Quality / Multi-source Validation")
    print("=" * 70)
    print(f"Routes: {len(route_ids)} — {', '.join(route_ids)}")
    print()

    results = []
    for rid in route_ids:
        result = _review_route(rid)
        if not result:
            print(f"  ✗ {rid} — brak danych G1/G2")
            continue

        s = result.get("review_summary", {})
        flag = " ⚠️" if result.get("data_quality_flag") else ""
        print(f"  ✓ {rid} — {s.get('total_segments_for_review', 0)} segments, "
              f"{s.get('high_priority', 0)} high, "
              f"{s.get('total_km_requiring_review', 0):.1f} km{flag}")

        # Write per-route files
        md = _generate_md(result)
        md_path = QUALITY_DIR / f"surface_quality_{rid}.md"
        json_path = QUALITY_DIR / f"surface_quality_{rid}.json"
        with open(md_path, "w") as f:
            f.write(md)
        with open(json_path, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        results.append(result)

    if not results:
        print("\nNo results generated.")
        sys.exit(1)

    # Index
    index_md = _generate_index_md(results)
    index_json = _generate_index_json(results)

    ts = _ts()
    index_md_path = QUALITY_DIR / f"surface_quality_index_{ts}.md"
    index_json_path = QUALITY_DIR / f"surface_quality_index_{ts}.json"

    with open(index_md_path, "w") as f:
        f.write(index_md)
    with open(index_json_path, "w") as f:
        json.dump(index_json, f, ensure_ascii=False, indent=2, default=str)

    # Manual overrides template
    template = _create_override_template()
    template_path = QUALITY_DIR / "manual_surface_overrides_template.json"
    with open(template_path, "w") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    total_seg = sum((r.get("review_summary") or {}).get("total_segments_for_review", 0) or 0 for r in results)
    total_km = sum((r.get("review_summary") or {}).get("total_km_requiring_review", 0) or 0 for r in results)
    total_high = sum((r.get("review_summary") or {}).get("high_priority", 0) or 0 for r in results)

    print(f"\n{'='*70}")
    print(f"G9 COMPLETE")
    print(f"{'='*70}")
    print(f"  Routes reviewed: {len(results)}")
    print(f"  Segments needing review: {total_seg}")
    print(f"  Total km requiring review: {total_km:.1f} km")
    print(f"  High priority: {total_high}")
    print(f"  Reports: {QUALITY_DIR}")
    print(f"  Index MD: {index_md_path}")
    print(f"  Template: {template_path}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
