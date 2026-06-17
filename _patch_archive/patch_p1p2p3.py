#!/usr/bin/env python3
"""
P1: trip_attractions — filtr sekcji (woda → tylko water, atrakcje → tylko attractions)
P2: route_climbs — resolved_route_id w odpowiedzi i data
P3: wellness_day — jawny komunikat gdy HRV null a pytanie zawiera 'hrv'
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
fixes = []

# ══════════════════════════════════════════════════════════
# P1: trip_attractions — section filter
# ══════════════════════════════════════════════════════════
TA = '/opt/qbot/app/tools/trip_attractions.py'
with open(TA, encoding='utf-8') as f:
    ta = f.read()
shutil.copy(TA, f'{TA}.bak.p123.{ts}')

old_handle_start = (
    'def handle_trip_attractions(question: str) -> dict:\n'
    '    ql = question.lower()\n'
    '\n'
    '    # Mapowanie PL\u2192EN dla trip_hint (musi matchowa\u0107 tytu\u0142y w DB)\n'
)
new_handle_start = (
    '# Mapowanie s\u0142\u00f3w kluczowych na sekcje POI\n'
    '_SECTION_KW = {\n'
    '    "water":       ["woda", "water", "wod\u0119", "wody", "picia", "pitna", "picie", "fonte", "kranowa", "kran"],\n'
    '    "food":        ["jedzenie", "food", "sklep", "shop", "restauracja", "bar", "cafe", "kawiarnia"],\n'
    '    "attractions": ["atrakcj", "attraction", "zabytek", "zabytkow", "muzeum", "ko\u015bci\u00f3\u0142", "zamek", "villa", "must see"],\n'
    '    "accommodation": ["nocleg", "hotel", "camping", "hostel"],\n'
    '    "bike_shop":   ["serwis", "bike shop", "mechanik"],\n'
    '}\n'
    '\n'
    'def _detect_section_filter(ql: str) -> str | None:\n'
    '    """Wykryj czy pytanie dotyczy konkretnej sekcji POI."""\n'
    '    for section, keywords in _SECTION_KW.items():\n'
    '        for kw in keywords:\n'
    '            if kw in ql:\n'
    '                return section\n'
    '    return None\n'
    '\n'
    '\n'
    'def handle_trip_attractions(question: str) -> dict:\n'
    '    ql = question.lower()\n'
    '\n'
    '    # Wykryj filtr sekcji (woda, jedzenie, atrakcje...)\n'
    '    section_filter = _detect_section_filter(ql)\n'
    '\n'
    '    # Mapowanie PL\u2192EN dla trip_hint (musi matchowa\u0107 tytu\u0142y w DB)\n'
)
if old_handle_start in ta:
    ta = ta.replace(old_handle_start, new_handle_start, 1)
    fixes.append("P1a: section_filter detection added")
else:
    print("FAIL P1a: handle_trip_attractions start not found")

# Dodaj section_filter do formatowania odpowiedzi — po zbudowaniu records
old_format_parts = (
    '    parts = [_format_poi_record(r) for r in records]\n'
    '    answer = "\\n\\n".join(parts)\n'
    '    return {\n'
    '        "answer": answer,\n'
    '        "data": {"count": len(records), "records": [r["id"] for r in records]},\n'
    '        "sources": ["qbot_planning_facts"]\n'
    '    }'
)
new_format_parts = (
    '    # Zastosuj section_filter — ogranicz ka\u017cdy rekord do wybranej sekcji\n'
    '    if section_filter:\n'
    '        filtered_records = []\n'
    '        for rec in records:\n'
    '            data = rec["data"]\n'
    '            if isinstance(data, dict) and section_filter in data:\n'
    '                section_data = data[section_filter]\n'
    '                if section_data:\n'
    '                    filtered_records.append({**rec, "data": {section_filter: section_data,\n'
    '                                                              "segment": data.get("segment",""),\n'
    '                                                              "stage": data.get("stage",""),\n'
    '                                                              "route_id": data.get("route_id","")}})\n'
    '            elif isinstance(data, list):\n'
    '                filtered_records.append(rec)\n'
    '        if filtered_records:\n'
    '            records = filtered_records\n'
    '\n'
    '    parts = [_format_poi_record(r) for r in records]\n'
    '    answer = "\\n\\n".join(parts)\n'
    '    return {\n'
    '        "answer": answer,\n'
    '        "data": {"count": len(records), "records": [r["id"] for r in records],\n'
    '                 "section_filter": section_filter},\n'
    '        "sources": ["qbot_planning_facts"]\n'
    '    }'
)
if old_format_parts in ta:
    ta = ta.replace(old_format_parts, new_format_parts, 1)
    fixes.append("P1b: section_filter applied to records before formatting")
else:
    print("FAIL P1b: format_parts block not found")

ast.parse(ta)
with open(TA, 'w', encoding='utf-8') as f:
    f.write(ta)
print("trip_attractions.py syntax OK")

# ══════════════════════════════════════════════════════════
# P2 + P3: qbot_query_handler.py
# ══════════════════════════════════════════════════════════
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.p23.{ts}')

# P2: route_climbs — dodaj resolved_route_id do answer i data
old_climbs_return = (
    '        report = format_climbs_report(climbs)\n'
    '        return _envelope("route_climbs", report, data={"climbs": climbs, "count": len(climbs)}, sources_used=["rwgps"])'
)
new_climbs_return = (
    '        report = format_climbs_report(climbs)\n'
    '        _header = f"Trasa: {route_id}\\n"\n'
    '        return _envelope("route_climbs", _header + report,\n'
    '                         data={"climbs": climbs, "count": len(climbs),\n'
    '                               "resolved_route_id": route_id, "km_from": km_from},\n'
    '                         sources_used=["rwgps"])'
)
if old_climbs_return in qh:
    qh = qh.replace(old_climbs_return, new_climbs_return, 1)
    fixes.append("P2: route_climbs shows resolved_route_id in answer and data")
else:
    print("FAIL P2: climbs return block not found")

# P3: wellness_day — jawny komunikat gdy HRV null a pytanie zawiera 'hrv'
old_hrv_check = (
    '    parts = []\n'
    '    if r.get("hrv_ms") is not None:\n'
    '        parts.append(f"\U0001f493 HRV: {r[\'hrv_ms\']:.0f}ms")\n'
    '    if r.get("resting_hr_bpm") is not None:\n'
    '        parts.append(f"\u2764\ufe0f  T\u0119tno spoczynkowe: {r[\'resting_hr_bpm\']}bpm")'
)
new_hrv_check = (
    '    parts = []\n'
    '    if r.get("hrv_ms") is not None:\n'
    '        parts.append(f"\U0001f493 HRV: {r[\'hrv_ms\']:.0f}ms")\n'
    '    elif "hrv" in (question or "").lower():\n'
    '        parts.append(f"\U0001f493 HRV: brak danych dla {d} (null w Garmin)")\n'
    '    if r.get("resting_hr_bpm") is not None:\n'
    '        parts.append(f"\u2764\ufe0f  T\u0119tno spoczynkowe: {r[\'resting_hr_bpm\']}bpm")'
)
if old_hrv_check in qh:
    qh = qh.replace(old_hrv_check, new_hrv_check, 1)
    fixes.append("P3: wellness_day explicit HRV null message when asked")
else:
    print("FAIL P3: hrv_check block not found")

# P3: _handle_wellness_day musi przyjmować question jako drugi argument
old_wellness_def = 'def _handle_wellness_day(day_str: str) -> dict:'
new_wellness_def = 'def _handle_wellness_day(day_str: str, question: str = "") -> dict:'
if old_wellness_def in qh:
    qh = qh.replace(old_wellness_def, new_wellness_def, 1)
    fixes.append("P3b: _handle_wellness_day accepts question param")
else:
    print("FAIL P3b: wellness_day def not found")

# Zaktualizuj wywołania _handle_wellness_day żeby przekazywały question
old_wellness_call_dispatch = (
    '        return _handle_wellness_day(_parse_date_from_question(question))'
)
new_wellness_call_dispatch = (
    '        return _handle_wellness_day(_parse_date_from_question(question), question)'
)
count = qh.count(old_wellness_call_dispatch)
if count > 0:
    qh = qh.replace(old_wellness_call_dispatch, new_wellness_call_dispatch)
    fixes.append(f"P3c: wellness_day calls pass question ({count}x)")
else:
    print("WARN P3c: wellness_day dispatch call not found (may be inline)")

# Sprawdź też wywołanie w dispatch głównym
old_wellness_main = (
    '    elif intent == "wellness_day":\n'
    '        return _handle_wellness_day(day_str)'
)
new_wellness_main = (
    '    elif intent == "wellness_day":\n'
    '        return _handle_wellness_day(day_str, question)'
)
if old_wellness_main in qh:
    qh = qh.replace(old_wellness_main, new_wellness_main, 1)
    fixes.append("P3d: main dispatch passes question to wellness_day")
else:
    print("WARN P3d: main wellness dispatch not found")

ast.parse(qh)
with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)
print("qbot_query_handler.py syntax OK")

print(f"\n=== {len(fixes)} fixes ===")
for fx in fixes:
    print(f"  OK: {fx}")
