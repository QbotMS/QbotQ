#!/usr/bin/env python3
"""
Patch keyword router — rzeczy które DA SIĘ zrobić deterministycznie:
2.1: suma etapów toskanii → nowy handler _handle_trip_summary
2.2: najdłuższy etap → w trip_summary
2.3: feasibility etap N toskania → _resolve_tuscany_route_id zamiast hardcoded 55257604
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.router.{ts}')
fixes = []

# ── 2.1/2.2: nowy intent trip_summary ────────────────────────────────
# Keywords PRZED trip_stages żeby nie wpaść w etap-today
old_trip_stages_kw = '    (["etap", "etapy", "stage", "stages", "dzisiejszy etap",'
new_trip_summary_kw = (
    '    (["suma etapów", "suma kilometrów", "łącznie etapy", "lacznie etapy",\n'
    '      "ile łącznie", "ile lacznie", "ile km toskania", "ile km tuscany",\n'
    '      "najdłuższy etap", "najdluzszy etap", "longest stage",\n'
    '      "najtrudniejszy etap", "najkrótszy etap", "najkrotszy etap",\n'
    '      "statystyki etapów", "statystyki etapow", "podsumowanie etapów",\n'
    '      "podsumowanie trasy", "overview etapów"], "trip_summary"),\n'
    '    (["etap", "etapy", "stage", "stages", "dzisiejszy etap",'
)
if old_trip_stages_kw in qh:
    qh = qh.replace(old_trip_stages_kw, new_trip_summary_kw, 1)
    fixes.append("2.1/2.2: trip_summary intent added")
else:
    print("FAIL 2.1/2.2: trip_stages keyword line not found")

# Dodaj handler _handle_trip_summary i dispatch
old_trip_stages_handler = 'def _handle_trip_stages(text: str) -> dict:'
new_trip_summary_handler = (
    'def _handle_trip_summary(text: str) -> dict:\n'
    '    """Podsumowanie wszystkich etapów: suma km, D+, najdłuższy, najkrótszy."""\n'
    '    ql = text.lower()\n'
    '    try:\n'
    '        pg = _pg_conn()\n'
    '        rows = _safe_fetch(pg, """\n'
    '            SELECT fact_json->>\'stages\' as stages_json\n'
    '            FROM qbot_v2.qbot_planning_facts\n'
    '            WHERE fact_type=\'route_stages\'\n'
    '            ORDER BY date DESC LIMIT 1\n'
    '        """)\n'
    '        pg.close()\n'
    '    except Exception as exc:\n'
    '        return _envelope("trip_summary", f"Błąd: {exc}", status_override="ERROR")\n'
    '\n'
    '    if not rows or "_error" in rows[0]:\n'
    '        return _envelope("trip_summary", "Brak planów etapów w bazie.")\n'
    '\n'
    '    import json\n'
    '    stages = json.loads(rows[0]["stages_json"] or "[]")\n'
    '    if not stages:\n'
    '        return _envelope("trip_summary", "Brak etapów w planie.")\n'
    '\n'
    '    total_km = sum(float(s.get("distance_km") or 0) for s in stages)\n'
    '    longest = max(stages, key=lambda s: float(s.get("distance_km") or 0))\n'
    '    shortest = min(stages, key=lambda s: float(s.get("distance_km") or 0))\n'
    '\n'
    '    lines = [f"📊 Podsumowanie trasy ({len(stages)} etapów):",\n'
    '             f"  Łącznie: {total_km:.1f} km",\n'
    '             f"  Najdłuższy: Etap {longest.get(\'stage\')} — {longest.get(\'segment\',\'?\')} ({longest.get(\'distance_km\')} km)",\n'
    '             f"  Najkrótszy: Etap {shortest.get(\'stage\')} — {shortest.get(\'segment\',\'?\')} ({shortest.get(\'distance_km\')} km)",\n'
    '             "",\n'
    '             "  Etapy:"]\n'
    '    for s in sorted(stages, key=lambda x: x.get("stage", 0)):\n'
    '        lines.append(f"  {s.get(\'stage\',\'?\')}: {s.get(\'segment\',\'?\')} — {s.get(\'distance_km\',\'?\')} km")\n'
    '\n'
    '    return _envelope("trip_summary", "\\n".join(lines),\n'
    '                     data={"stages": stages, "total_km": total_km,\n'
    '                           "longest": longest, "shortest": shortest},\n'
    '                     sources_used=["qbot_v2.qbot_planning_facts"])\n'
    '\n'
    '\n'
    'def _handle_trip_stages(text: str) -> dict:\n'
)
if old_trip_stages_handler in qh:
    qh = qh.replace(old_trip_stages_handler, new_trip_summary_handler, 1)
    fixes.append("2.1/2.2: _handle_trip_summary function added")
else:
    print("FAIL 2.1/2.2: trip_stages handler def not found")

# Dispatch dla trip_summary
old_dispatch_trip_stages = (
    '    elif intent == "trip_stages":\n'
    '        return _handle_trip_stages(question)'
)
new_dispatch_trip = (
    '    elif intent == "trip_summary":\n'
    '        return _handle_trip_summary(question)\n'
    '    elif intent == "trip_stages":\n'
    '        return _handle_trip_stages(question)'
)
if old_dispatch_trip_stages in qh:
    qh = qh.replace(old_dispatch_trip_stages, new_dispatch_trip, 1)
    fixes.append("2.1/2.2: trip_summary dispatch")
else:
    print("FAIL 2.1/2.2: trip_stages dispatch not found")

# ── 2.3: feasibility — zastąp hardcoded 55257604 ─────────────────────
old_feasibility_hardcoded = (
    '    for name,rid in [("toskania","55257604"),("tuscany","55257604")]:\n'
    '        if name in ql and not route_id: route_id=rid; break'
)
new_feasibility_resolve = (
    '    if not route_id:\n'
    '        for kw in ["toskani", "tuscany"]:\n'
    '            if kw in ql:\n'
    '                route_id = _resolve_tuscany_route_id(question)\n'
    '                break'
)
if old_feasibility_hardcoded in qh:
    qh = qh.replace(old_feasibility_hardcoded, new_feasibility_resolve, 1)
    fixes.append("2.3: feasibility uses _resolve_tuscany_route_id (not hardcoded 55257604)")
else:
    print("FAIL 2.3: feasibility hardcoded block not found")

try:
    ast.parse(qh)
    print("qbot_query_handler.py syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    import sys; sys.exit(1)

with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)

print(f"\n=== {len(fixes)} fixes ===")
for fx in fixes:
    print(f"  OK: {fx}")
