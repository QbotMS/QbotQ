"""
tools/trip_attractions.py
Handler: atrakcje/POI z qbot_planning_facts (fact_type LIKE 'poi_%').
"""
from __future__ import annotations
import json, os, re
from datetime import date
from typing import Optional

def _pg():
    import psycopg
    return psycopg.connect(
        host=os.getenv("PGHOST","127.0.0.1"), port=os.getenv("PGPORT","5432"),
        dbname=os.getenv("PGDATABASE","qbot"), user=os.getenv("PGUSER","qbot"),
        password=os.getenv("PGPASSWORD",""), connect_timeout=5,
        options="-c search_path=qbot_v2",
    )

def _fetch_poi_facts(trip_hint: str = None, stage_n: int = None) -> list[dict]:
    conn = _pg()
    try:
        cur = conn.cursor()
        where = ["fact_type LIKE 'poi_%%'"]
        params = []
        if trip_hint:
            where.append("LOWER(title) LIKE %s")
            params.append("%" + trip_hint.lower() + "%")
        if stage_n is not None:
            where.append("(LOWER(title) LIKE %s OR LOWER(title) LIKE %s)")
            params += ["%" + f"stage {stage_n:02d}" + "%", "%" + f"etap {stage_n}" + "%"]
        cur.execute(
            "SELECT id, date, title, fact_type, fact_json, status FROM qbot_planning_facts "
            "WHERE " + " AND ".join(where) + " ORDER BY date, id",
            params
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        fj = row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}")
        results.append({
            "id": row[0], "date": row[1], "title": row[2],
            "fact_type": row[3], "data": fj, "status": row[5],
        })
    return results

def _readable_poi_name(item: dict) -> str:
    """Wyciągnij czytelną nazwę POI z pól name/source_tags/category."""
    name = item.get("name", "")
    # Jeśli nazwa to "Attraction <id>" lub "Water <id>" — ignoruj, użyj tagów
    if name and not name.split()[-1].isdigit() and not name.startswith("Attraction ") and not name.startswith("Water "):
        return name
    # Spróbuj wyciągnąć name= z source_tags
    tags = item.get("source_tags", "")
    for part in tags.split(";"):
        p = part.strip()
        if p.startswith("name="):
            return p[5:].strip()
        if p.startswith("tourism=") or p.startswith("historic="):
            label = p.split("=",1)[1].replace("_"," ").strip().capitalize()
            return label
    # Fallback: kategoria + km
    cat = item.get("category","poi")
    km = item.get("route_km") or item.get("km","")
    return f"{cat.capitalize()} ~km{km:.1f}" if isinstance(km,(int,float)) else f"{cat.capitalize()}"


def _format_poi_items(items: list, section_label: str, max_items: int = 10) -> list:
    """Formatuj listę POI itemów do linii tekstowych."""
    lines = []
    if not items:
        return lines
    lines.append(f"  {section_label} ({len(items)}):")
    for item in items[:max_items]:
        name = _readable_poi_name(item)
        km   = item.get("route_km") or item.get("km") or item.get("km_approx","")
        dist = item.get("distance_to_track_m") or item.get("distance_km","")
        note = item.get("note","").replace("attraction","").replace("water","").strip().strip(";").strip()
        line = "    * " + str(name)
        if km != "" and km is not None:
            line += f" (km {km:.1f})" if isinstance(km,(int,float)) else f" (km {km})"
        if dist != "" and dist is not None:
            if isinstance(dist,(int,float)):
                line += f" — {int(dist)}m od trasy"
            else:
                line += f" +{dist}km zjazd"
        if note:
            line += f" [{note}]"
        lines.append(line)
    if len(items) > max_items:
        lines.append(f"    ... i {len(items)-max_items} wiecej")
    return lines


def _format_poi_record(rec: dict) -> str:
    title = rec["title"]
    ftype = rec["fact_type"].replace("poi_","").replace("_"," ")
    data  = rec["data"]

    if not data:
        return f"[{ftype}] {title}\n  (brak danych — uzupelnij fact_json)"

    lines = [f"[{ftype}] {title}"]

    # H2/H3: obsługa struktury {attractions:[], water:[], food:[], shop:[], ...}
    if isinstance(data, dict):
        # Wyodrebnij metadata (nie-listy)
        meta_keys = ["segment", "route_id", "stage", "variant", "status"]
        for k in meta_keys:
            if k in data and not isinstance(data[k], list):
                lines.append(f"  {k}: {data[k]}")

        # Sekcje POI
        section_map = {
            "attractions": "Atrakcje",
            "water":       "Woda pitna",
            "food":        "Jedzenie/sklepy",
            "shop":        "Sklepy",
            "accommodation": "Noclegi",
            "bike_shop":   "Serwis rowerowy",
        }
        for key, label in section_map.items():
            val = data.get(key, [])
            # Scal z google odpowiednikiem jeśli istnieje
            google_key = key + '_google'
            google_val = data.get(google_key, [])
            combined = list(val) + [g for g in google_val if g not in val]
            if combined:
                lines.extend(_format_poi_items(combined, label + (' (OSM+Google)' if google_val else '')))

        # Pozostałe klucze-listy których nie ma w section_map
        for key, val in data.items():
            if key in section_map or key in meta_keys:
                continue
            if isinstance(val, list) and val:
                lines.extend(_format_poi_items(val, key.replace("_"," ").capitalize()))
            elif isinstance(val, (str,int,float)):
                lines.append(f"  {key}: {val}")

    elif isinstance(data, list):
        # Flat lista POI (stary format)
        lines.extend(_format_poi_items(data, "POI"))

    return "\n".join(lines)

# Mapowanie słów kluczowych na sekcje POI
_SECTION_KW = {
    "water":       ["woda", "water", "wodę", "wody", "picia", "pitna", "picie", "fonte", "kranowa", "kran"],
    "food":        ["jedzenie", "food", "sklep", "shop", "restauracja", "bar", "cafe", "kawiarnia"],
    "attractions": ["atrakcj", "attraction", "zabytek", "zabytkow", "muzeum", "kościół", "zamek", "villa", "must see"],
    "accommodation": ["nocleg", "hotel", "camping", "hostel"],
    "bike_shop":   ["serwis", "bike shop", "mechanik"],
}

def _detect_section_filter(ql: str) -> str | None:
    """Wykryj czy pytanie dotyczy konkretnej sekcji POI."""
    for section, keywords in _SECTION_KW.items():
        for kw in keywords:
            if kw in ql:
                return section
    return None


def handle_trip_attractions(question: str) -> dict:
    ql = question.lower()

    # Wykryj filtr sekcji (woda, jedzenie, atrakcje...)
    section_filter = _detect_section_filter(ql)

    # Mapowanie PL→EN dla trip_hint (musi matchować tytuły w DB)
    _TRIP_HINT_MAP = {
        "toskani": "tuscany", "toskania": "tuscany", "toskanii": "tuscany",
        "tuscany": "tuscany", "tour": "tour",
        "wyprawa": "wyprawa", "alps": "alps", "dolomit": "dolomit",
    }
    trip_hint = None
    for kw, mapped in _TRIP_HINT_MAP.items():
        if kw in ql:
            trip_hint = mapped
            break

    stage_m = re.search(r"etap[uie]*\s*(\d+)", ql)
    stage_n = int(stage_m.group(1)) if stage_m else None

    km_m = re.search(r"km\s*(\d+)[-]\s*(\d+)", ql)

    # Brak kontekstu — pytaj zamiast zgadywać
    _context_words = ["tam", "ten etap", "tego etapu", "na nim", "na niej",
                      "na tym etapie", "tutaj", "ten"]
    _has_context_ref = any(w in ql for w in _context_words)
    if stage_n is None and trip_hint is None and _has_context_ref:
        return {
            "answer": (
                "Nie mam kontekstu poprzedniego zapytania — każde wywołanie jest niezależne.\n"
                "Podaj pełne pytanie, np. 'atrakcje etap 3 toskania' lub 'woda etap 1 toskania'."
            ),
            "data": {"requires_context": True}, "sources": []
        }

    records = _fetch_poi_facts(trip_hint, stage_n)
    if not records:
        records = _fetch_poi_facts()

    if not records:
        return {
            "answer": "Brak danych POI/atrakcji w bazie. Dodaj fakty fact_type='poi_*' przez qbot.action_execute.",
            "data": {}, "sources": ["qbot_planning_facts"]
        }

    stale_stage = None
    for rec in records:
        data = rec.get("data")
        if isinstance(data, dict) and data.get("poi_stale"):
            stale_stage = data.get("stage") or stage_n
            break
    if stale_stage is not None:
        return {
            "answer": f"POI etapu {stale_stage} wymaga odświeżenia po zmianie trasy",
            "data": {
                "count": 0,
                "records": [],
                "section_filter": section_filter,
                "stage": stale_stage,
                "poi_stale": True,
            },
            "sources": ["qbot_planning_facts"],
        }

    if km_m:
        km_from, km_to = int(km_m.group(1)), int(km_m.group(2))
        filtered = []
        for rec in records:
            data = rec["data"]
            if isinstance(data, list):
                items_in_range = [
                    i for i in data
                    if km_from <= float(i.get("km") or i.get("km_approx") or 0) <= km_to
                ]
                if items_in_range:
                    filtered.append({**rec, "data": items_in_range})
            else:
                filtered.append(rec)
        records = filtered or records

    # Zastosuj section_filter — ogranicz każdy rekord do wybranej sekcji
    if section_filter:
        filtered_records = []
        for rec in records:
            data = rec["data"]
            if isinstance(data, dict) and section_filter in data:
                section_data = data[section_filter]
                if section_data:
                    filtered_records.append({**rec, "data": {section_filter: section_data,
                                                              "segment": data.get("segment",""),
                                                              "stage": data.get("stage",""),
                                                              "route_id": data.get("route_id","")}})
            elif isinstance(data, list):
                filtered_records.append(rec)
        if filtered_records:
            records = filtered_records

    parts = [_format_poi_record(r) for r in records]
    answer = "\n\n".join(parts)
    return {
        "answer": answer,
        "data": {"count": len(records), "records": [r["id"] for r in records],
                 "section_filter": section_filter},
        "sources": ["qbot_planning_facts"]
    }


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "atrakcje toskania"
    r = handle_trip_attractions(q)
    print(r["answer"])
