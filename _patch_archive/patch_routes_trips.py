#!/usr/bin/env python3
"""
Fix G1/G2/G3 (routes) + H2/H3 (trip stages/attractions) — 2026-06-02.

G1: route_workflow_list nie pokazuje route_id w tekście odpowiedzi
G2/G3: hardcoded route_id "55257604" (Tuscany Trail full) zamiast etapów 55395117-55395129
H2: trip_attractions._format_poi_record nie obsługuje struktury {water,food,attractions,shop}
H3: atrakcje mają nazwę "Attraction <osm_id>" — brak czytelnej nazwy (fallback na OSM tags)
"""
import ast, shutil, datetime

# ══════════════════════════════════════════════════════════
# Patch 1: qbot_query_handler.py
# ══════════════════════════════════════════════════════════
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH) as f:
    qh = f.read()

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy(QH, f'{QH}.bak.routes.{ts}')
fixes_qh = []

# ──────────────────────────────────────────────────────────
# G1: route_workflow_list — dodaj route_id do linii tekstu
# ──────────────────────────────────────────────────────────
old_list_fmt = '''            lines = ["Przetworzone trasy:"]
            for r in routes:
                lines.append("  {} | {} | {} km | {}".format(
                    r.get("date"), r.get("name"), r.get("distance_km"), r.get("status")))'''

new_list_fmt = '''            lines = ["Przetworzone trasy:"]
            for r in routes:
                lines.append("  {} | [{}] {} | {} km | {}".format(
                    r.get("date"), r.get("route_id", "—"), r.get("name"),
                    r.get("distance_km"), r.get("status")))'''

if old_list_fmt in qh:
    qh = qh.replace(old_list_fmt, new_list_fmt, 1)
    fixes_qh.append("G1: route_workflow_list shows route_id in text")
else:
    print("FAIL G1: exact match not found")

# ──────────────────────────────────────────────────────────
# G2/G3: hardcoded "55257604" → lookup from qbot_planning_facts
# Replace ALL occurrences of the hardcoded tuscany resolution block in _handle_route_climbs
# and _handle_rwgps_poi_push
# ──────────────────────────────────────────────────────────

# Helper function to add before _handle_route_climbs
helper_fn = '''
def _resolve_tuscany_route_id(stage_hint: str = None) -> str | None:
    """
    Wyszukaj route_id dla etapu Toskanii z qbot_planning_facts.
    Jeśli stage_hint podany (np. "etap 3") — zwraca route_id tego etapu.
    Bez hintu — zwraca route_id etapu 1 (lub pierwszego dostępnego).
    Fallback: None.
    """
    try:
        import os, psycopg, json, re as _re
        conn = psycopg.connect(
            host=os.getenv("PGHOST","127.0.0.1"), port=os.getenv("PGPORT","5432"),
            dbname=os.getenv("PGDATABASE","qbot"), user=os.getenv("PGUSER","qbot"),
            password=os.getenv("PGPASSWORD",""), connect_timeout=5,
            options="-c search_path=qbot_v2",
        )
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT fact_json FROM qbot_planning_facts "
                "WHERE fact_type='route_stages' AND LOWER(title) LIKE %s "
                "ORDER BY date DESC LIMIT 1",
                ("%toskani%",)
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        fj = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        stages = fj.get("stages", [])
        if not stages:
            return None
        # Wyodrębnij numer etapu z hintu
        stage_n = None
        if stage_hint:
            m = _re.search(r"etap\s*(\d+)", stage_hint.lower())
            if m:
                stage_n = int(m.group(1))
        if stage_n:
            for s in stages:
                if s.get("stage") == stage_n:
                    return str(s.get("route_id",""))
        # Bez hintu — etap 1
        for s in stages:
            if s.get("stage") == 1:
                return str(s.get("route_id",""))
        return str(stages[0].get("route_id",""))
    except Exception:
        return None


'''

# Insert helper before _handle_route_climbs
old_climbs_def = 'def _handle_route_climbs(question: str) -> dict:'
if old_climbs_def in qh and '_resolve_tuscany_route_id' not in qh:
    qh = qh.replace(old_climbs_def, helper_fn + old_climbs_def, 1)
    fixes_qh.append("G2/G3: _resolve_tuscany_route_id helper added")
elif '_resolve_tuscany_route_id' in qh:
    fixes_qh.append("G2/G3: helper already present — skip insert")
else:
    print("FAIL G2/G3: _handle_route_climbs not found")

# Now replace hardcoded tuscany lookup in _handle_route_climbs
old_tuscany_climbs = '''    if not route_id:
        for name, rid in [("toskania","55257604"),("tuscany","55257604")]:
            if name in ql: route_id = rid; break'''

new_tuscany_climbs = '''    if not route_id:
        for kw in ["toskani", "tuscany"]:
            if kw in ql:
                route_id = _resolve_tuscany_route_id(question)
                break'''

if old_tuscany_climbs in qh:
    qh = qh.replace(old_tuscany_climbs, new_tuscany_climbs, 1)
    fixes_qh.append("G2: route_climbs tuscany lookup from DB")
else:
    print("FAIL G2: tuscany lookup block in climbs not found")

# Replace hardcoded tuscany lookup in _handle_rwgps_poi_push
old_tuscany_poi = '''    if not route_id:
        for name, rid in [("toskania", "55257604"), ("tuscany", "55257604")]:
            if name in ql:
                route_id = rid
                break'''

new_tuscany_poi = '''    if not route_id:
        for kw in ["toskani", "tuscany"]:
            if kw in ql:
                route_id = _resolve_tuscany_route_id(question)
                break'''

if old_tuscany_poi in qh:
    qh = qh.replace(old_tuscany_poi, new_tuscany_poi, 1)
    fixes_qh.append("G3: rwgps_poi_push tuscany lookup from DB")
else:
    print("FAIL G3: tuscany lookup block in poi_push not found")

# Also fix the km_to fallback that used hardcoded route_id check
old_km_check1 = '        km_to = 530.0 if route_id == "55257604" else 100.0'
new_km_check1 = '        km_to = 530.0 if (route_id and route_id.startswith("5539")) else 100.0'

count_km1 = qh.count(old_km_check1)
if count_km1 > 0:
    qh = qh.replace(old_km_check1, new_km_check1)
    fixes_qh.append(f"G2/G3: km_to fallback — {count_km1} occurrences fixed")

old_km_total = '            "km_total": 530.0 if route_id == "55257604" else 0.0,'
new_km_total = '            "km_total": 530.0 if (route_id and route_id.startswith("5539")) else 0.0,'

if old_km_total in qh:
    qh = qh.replace(old_km_total, new_km_total, 1)
    fixes_qh.append("G3: km_total fallback fixed")

# Validate and write
try:
    ast.parse(qh)
    print("qbot_query_handler.py syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR in qh: {e}")
    import sys; sys.exit(1)

with open(QH, 'w') as f:
    f.write(qh)

for fix in fixes_qh:
    print(f"  OK: {fix}")


# ══════════════════════════════════════════════════════════
# Patch 2: tools/trip_attractions.py
# H2: _format_poi_record nie obsługuje struktury {water,food,attractions,shop}
# H3: nazwa "Attraction <osm_id>" — wyciągnij z source_tags lub użyj kategorii+km
# ══════════════════════════════════════════════════════════
TA = '/opt/qbot/app/tools/trip_attractions.py'
with open(TA) as f:
    ta = f.read()

shutil.copy(TA, f'{TA}.bak.{ts}')
fixes_ta = []

old_format_fn = '''def _format_poi_record(rec: dict) -> str:
    title = rec["title"]
    ftype = rec["fact_type"].replace("poi_","").replace("_"," ")
    data  = rec["data"]

    if not data:
        return f"[{ftype}] {title}\\n  (brak danych — uzupelnij fact_json)"

    lines = [f"[{ftype}] {title}"]
    if isinstance(data, list):
        for item in data[:10]:
            name = item.get("name") or item.get("title","?")
            dist = item.get("distance_km") or item.get("detour_km","")
            km   = item.get("km") or item.get("km_approx","")
            note = item.get("note") or item.get("notes","")
            line = "  * " + str(name)
            if km: line += " (km~" + str(km) + ")"
            if dist: line += " +" + str(dist) + "km zjazd"
            if note: line += " — " + str(note)
            lines.append(line)
        if len(data) > 10:
            lines.append("  ... i " + str(len(data)-10) + " wiecej")
    elif isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                lines.append("  " + key + ":")
                for item in val[:5]:
                    if isinstance(item, dict):
                        lines.append("    * " + item.get("name","?"))
                    else:
                        lines.append("    * " + str(item))
            elif isinstance(val, (str,int,float)):
                lines.append("  " + str(key) + ": " + str(val))

    return "\\n".join(lines)'''

new_format_fn = '''def _readable_poi_name(item: dict) -> str:
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
        return f"[{ftype}] {title}\\n  (brak danych — uzupelnij fact_json)"

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
            val = data.get(key)
            if isinstance(val, list) and val:
                lines.extend(_format_poi_items(val, label))

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

    return "\\n".join(lines)'''

if old_format_fn in ta:
    ta = ta.replace(old_format_fn, new_format_fn, 1)
    fixes_ta.append("H2: _format_poi_record handles {water,food,attractions,shop} structure")
    fixes_ta.append("H3: _readable_poi_name extracts name from source_tags for 'Attraction <id>'")
else:
    print("FAIL H2/H3: _format_poi_record exact match not found")

try:
    ast.parse(ta)
    print("trip_attractions.py syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR in ta: {e}")
    import sys; sys.exit(1)

with open(TA, 'w') as f:
    f.write(ta)

for fix in fixes_ta:
    print(f"  OK: {fix}")

# ══════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════
all_fixes = fixes_qh + fixes_ta
print(f"\\n=== {len(all_fixes)} fixes applied ===")
