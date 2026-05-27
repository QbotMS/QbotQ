#!/usr/bin/env python3
"""QBot Context Resolver — raw query → canonical_query_object.

Central date/time/language/negation resolution.
Planner consumes the canonical object — no inline date parsing in planner.
"""

from __future__ import annotations

import json, re
from datetime import date, timedelta
from typing import Any

TZ = "Europe/Warsaw"

# ── Polish month names ──

_MONTHS = {
    "stycznia":1,"lutego":2,"marca":3,"kwietnia":4,"maja":5,"czerwca":6,
    "lipca":7,"sierpnia":8,"września":9,"października":10,"listopada":11,"grudnia":12,
    "styczeń":1,"luty":2,"marzec":3,"kwiecień":4,"maj":5,"czerwiec":6,
    "lipiec":7,"sierpień":8,"wrzesień":9,"październik":10,"listopad":11,"grudzień":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

# ── Domain keywords ──

_DOMAIN_KW = {
    "nutrition": ["kalorii","kcal","zjedzone","jedzenie","żywieni","dieta","spozycie",
                  "spożycie","intake","zjadł","jadł","zjedzone","makro","białko","carbs",
                  "carbo","węgle","węglowodan","protein","płyny","nawodnieni","posiłk",
                   "bilans kalor","cronometer","karmieni","bilans odżyw","przyjęte kalorie",
                   "kalorie z dnia","kcal out","kcal_in","wydatek"],
    "training":  ["spalone","spalanie","trening","aktywność","activity","jazda","kolarstwo",
                   "cycling","dystans","przewyższenie","elevation","training load","tss",
                   "garmin activity","przebieg","kcal spalone","spalon","przejechane",
                  "jak mi poszła jazda","jak poszedł trening","oceń jazdę","jak wyszła jazda",
                  "ostatnia jazda","ostatni trening","jak mi poszło","dzisiejsza aktywność",
                  "oceń ostatnią jazdę","oceń jazdę"],
    "weight":    ["waga","wagę","ważę","ważył","weight","kilogramy","kg ","masa ciała","masę ciała"],
    "body_comp": ["body fat","body_fat","bmi","body composition","skład ciała",
                  "masa mięśniowa","muscle","bone","tkanka tłuszczowa","bf "],
    "sleep":     ["sen","sleep","spał","spanie","głęboki sen","rem"],
    "recovery":  ["hrv","tętno spoczynkowe","resting hr","rhr","regeneracja","recovery"],
    "xert":      ["xert","ftp","threshold","freshness","fatigue","fitness","strain"],
    "health_events": ["chorob","przezięb","infekcj","gorączk","katar","kaszel","wellbeing"],
    "supplements": ["suplement","omega","kreatyn","witamin","ashwagandha","melatonin"],
    "routes":    ["rwgps","trasy","route","gpx ","tcx","fit "],
    "food_catalog": ["produkty z bazy","katalog produktów","baza produktów","wszystkie produkty",
                     "lista produktów","pokaż produkty","jakie produkty"],
    "meal_templates": ["zdefiniowane posiłki","moje posiłki","templates","standardowe posiłki",
                       "szablony posiłków","cronometer","crono","manual_cronometer"],
    "meal_logs":    ["wpisy posiłków","logi posiłków","historia posiłków","posiłki przeniesione",
                     "cronometer","import z crono","chrono posiłki"],
    "data_quality": ["bez food_item_id","niepołączone produkty","kandydatów","kandydaci",
                     "bez produktu","audyt produktów","uporządkuj produkty","dodać do katalogu",
                     "nie jest podpięte","niepodpięte"],
}

# ── Task type keywords ──

_TASK_KW = [
    ("route_list",       ["najnowsze trasy","wypisz trasy","lista tras","wypisz.*trasy"]),
    ("calendar_day_context",["pokaż wszystko.*co.*qbot","pokaż wszystko.*co.*wie","co qbot wie o","co wiesz o dniu"]),
    ("missing_data_check",["które dni","brakuje","missing","bez.*nie mają","nie mają"]),
    ("comparison",       ["porównaj","porównanie","czy w dni","różnica","vs","kontra","wobec"]),
    ("trend",            ["trend","zmiana","spadek","wzrost"]),
    ("range_analysis",   ["od ","zakres","od pocz","ostatni","tygodnia","dni","miesiąc","maja","lipca","czerwca"]),
    ("lookup",           ["pokaż","wypisz","lista","znajdź","daj"]),
]

# ── Negative constraints ──

_NEGATION_PATTERNS = [
    (r"bez\s+eksportu|bez\s+exportu|nie\s+eksportuj", "no_export"),
    (r"bez\s+gpx|bez\s+plików\s+gpx|nie\s+analizuj\s+gpx", "no_gpx"),
    (r"bez\s+analizy\s+artefakt|bez\s+artefakt", "no_artifact"),
    (r"bez\s+tcx|bez\s+fit\b", "no_export"),
    (r"tylko\s+lista|tylko\s+podstawowe|bez\s+szczegół", "list_only"),
    (r"nie\s+zapisuj|tylko\s+odczyt|read.only", "read_only_enforce"),
    (r"bez\s+wzbogac|bez\s+surface|bez\s+nawierzchni", "no_enrich"),
]


def resolve(query: str, context: str = "") -> dict[str, Any]:
    """Resolve raw query + context into canonical query object."""
    q = query
    ql = q.lower()
    ctx = _parse_context(context)

    # ── Time ──
    today = date.today()
    if ctx.get("date") and re.match(r"\d{4}-\d{2}-\d{2}", str(ctx.get("date",""))):
        try: today = date.fromisoformat(str(ctx["date"])[:10])
        except: pass

    df, dt, single, grain, rel, assumptions, tconf = _resolve_time(ql, ctx, today)
    if ctx.get("date_from") and re.match(r"\d{4}-\d{2}-\d{2}", str(ctx.get("date_from",""))):
        df = str(ctx["date_from"]); dt = str(ctx.get("date_to", today.isoformat())); tconf = "high"

    # ── Task type ──
    task_type = "lookup"
    for tname, kws in _TASK_KW:
        for kw in kws:
            if re.search(kw, ql):
                task_type = tname; break
        if task_type != "lookup": break

    # ── Output format ──
    output = "table"
    if re.search(r"podsumowa|średni|avg|mean|ogólnie|generalnie", ql): output = "summary"
    if re.search(r"lista|wypisz|najnowsze", ql) and task_type != "range_analysis": output = "list"

    # ── Domains ──
    domains = []
    for dname, kws in _DOMAIN_KW.items():
        for kw in kws:
            if kw in ql:
                if dname not in domains: domains.append(dname)
                break
    if task_type == "calendar_day_context" and not domains:
        domains = ["calendar"]

    # ── Negative constraints ──
    negations = []
    for pat, tag in _NEGATION_PATTERNS:
        if re.search(pat, ql): negations.append(tag)

    # ── Metrics ──
    metrics = []
    if re.search(r"kcal\b|kalori", ql): metrics.append("kcal")
    if re.search(r"białko|protein", ql): metrics.append("protein")
    if re.search(r"węgle|węglowod|carbs|carbo", ql): metrics.append("carbs")
    if re.search(r"tłuszcz|fat\b|tłuszczu", ql): metrics.append("fat")
    if re.search(r"dystans|km\b|kilometr", ql): metrics.append("distance")

    # ── Filters ──
    filters = []
    if re.search(r"z\s+treningiem|dni\s+treningowe", ql): filters.append("has_training")
    if re.search(r"bez\s+żywienia|bez\s+jedzenia|brak\s+nutrition", ql): filters.append("no_nutrition")

    # ── Safety ──
    safety = {"read_only": True, "allow_write": False}

    return {
        "raw_query": query.strip(),
        "language": "pl",
        "timezone": TZ,
        "resolved_time": {
            "date_from": df,
            "date_to": dt,
            "single_date": single,
            "grain": grain,
            "relative_expression": rel,
            "assumptions": assumptions,
            "confidence": tconf,
        },
        "task": {"type": task_type, "output": output},
        "domains": domains,
        "metrics": metrics,
        "filters": filters,
        "negative_constraints": negations,
        "safety": safety,
    }


def _parse_context(ctx_raw: str) -> dict:
    if not ctx_raw: return {}
    try: return json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
    except: return {}


def _resolve_time(ql: str, ctx: dict, today: date) -> tuple:
    """Returns (date_from, date_to, single_date, grain, relative_expr, assumptions, confidence)."""
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", ql)
    iso_date = iso.group(1) if iso else None

    # Explicit ISO range
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:do|–|to|-)\s*(\d{4}-\d{2}-\d{2}|today|dziś|dzisiaj)", ql)
    if m:
        d2 = today.isoformat() if m.group(2) in ("today","dziś","dzisiaj") else m.group(2)
        return m.group(1), d2, None, "day", None, {}, "high"

    # "od 1 maja", "od początku maja"
    for name, num in _MONTHS.items():
        m = re.search(rf"od\s+(\d{{1,2}})\s+{name}", ql)
        if m:
            d = int(m.group(1))
            return f"{today.year}-{num:02d}-{d:02d}", today.isoformat(), None, "day", None, {}, "high"
        m = re.search(rf"od\s+(?:początku\s+)?{name}", ql)
        if m:
            return f"{today.year}-{num:02d}-01", today.isoformat(), None, "day", f"początek {name}", {}, "high"

    # "od 2026-05-01"
    m = re.search(r"od\s+(\d{4}-\d{2}-\d{2})", ql)
    if m: return m.group(1), today.isoformat(), None, "day", None, {}, "high"

    # "od 1.05" / "od 01.05"
    m = re.search(r"od\s+(\d{1,2})[\.\-/](\d{1,2})", ql)
    if m:
        return f"{today.year}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", today.isoformat(), None, "day", None, {}, "high"

    # "ostatnie X dni" / "ostatniego tygodnia"
    m = re.search(r"ostatni(?:ch|e|ego)?\s+(\d+)\s*(?:dni|day)", ql)
    if m:
        days = int(m.group(1))
        return (today - timedelta(days=days-1)).isoformat(), today.isoformat(), None, "day", f"ostatnie {days} dni", {}, "high"
    if re.search(r"ostatni(?:ego|ch|e)?\s+tygodni", ql):
        return (today - timedelta(days=6)).isoformat(), today.isoformat(), None, "day", "ostatni tydzień", {}, "high"

    # "wczoraj" / "przedwczoraj"
    if re.search(r"\bwczoraj\b", ql):
        d = (today - timedelta(days=1)).isoformat()
        return d, d, d, "day", "wczoraj", {}, "high"
    if re.search(r"\bprzedwczoraj\b", ql):
        d = (today - timedelta(days=2)).isoformat()
        return d, d, d, "day", "przedwczoraj", {}, "high"

    # "dziś" / "dzisiaj"
    if re.search(r"\bdziś\b|\bdzisiaj\b|\bdziś\b", ql):
        d = today.isoformat()
        return d, d, d, "day", "dziś", {}, "high"

    # Single ISO date embedded in query
    if iso_date:
        return iso_date, iso_date, iso_date, "day", None, {}, "high"

    # Fallback: default 30 days for range queries, today for lookups
    if any(w in ql for w in ["od ","zakres","ostatni","porównaj"]):
        return (today - timedelta(days=29)).isoformat(), today.isoformat(), None, "day", "default 30d", {}, "low"
    d = today.isoformat()
    return d, d, d, "day", "default today", {}, "medium"
