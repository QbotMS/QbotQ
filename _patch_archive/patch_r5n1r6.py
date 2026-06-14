#!/usr/bin/env python3
"""
3 bugi:
R5: etap regex nie matchuje 'etapie' — fix: etap[uie]*\s+(\d+)
N1: intake_kcal z daily_summary myli GPT — usuń z per_day
R6: shelf_clause szuka absolutnej ścieżki a file_path jest relatywna
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
fixes = []

# ── R5: trip_attractions — etapie/etapu regex ────────────────────────
TA = '/opt/qbot/app/tools/trip_attractions.py'
with open(TA, encoding='utf-8') as f:
    ta = f.read()
shutil.copy(TA, f'{TA}.bak2.{ts}')

old_stage_m = '    stage_m = re.search(r"etap\\s+(\\d+)", ql)'
new_stage_m = '    stage_m = re.search(r"etap[uie]*\\s*(\\d+)", ql)'

if old_stage_m in ta:
    ta = ta.replace(old_stage_m, new_stage_m, 1)
    fixes.append("R5: trip_attractions stage regex: etap[uie]*\\s*(\\d+)")
else:
    print("FAIL R5: stage_m line not found")

ast.parse(ta)
with open(TA, 'w', encoding='utf-8') as f:
    f.write(ta)
print("trip_attractions.py syntax OK")

# ── N1 + R6: qbot_query_handler.py ───────────────────────────────────
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.r5n1r6.{ts}')

# N1: usuń intake_kcal z per_day entry (myli GPT — to Garmin, nie nasze)
old_entry_update = (
    '        dse = ds_by_date.get(ds)\n'
    '        if dse:\n'
    '            entry.update(dse)'
)
new_entry_update = (
    '        dse = ds_by_date.get(ds)\n'
    '        if dse:\n'
    '            # Kopiuj tylko potrzebne pola — NIE intake_kcal (Garmin, myli GPT)\n'
    '            for _k in ("expenditure_total", "balance_kcal"):\n'
    '                if _k in dse:\n'
    '                    entry[_k] = dse[_k]'
)
if old_entry_update in qh:
    qh = qh.replace(old_entry_update, new_entry_update, 1)
    fixes.append("N1: per_day entry — only expenditure_total/balance_kcal from dse, no intake_kcal")
else:
    print("FAIL N1: entry.update(dse) block not found")

# R6: shelf_clause — użyj relatywnej ścieżki (bez /opt/qbot/artifacts/)
old_shelf_clause = (
    '            if _shelf_filter:\n'
    '                _shelf_clause = "  AND LOWER(file_path) LIKE %s"\n'
    '                _shelf_params = (f"/opt/qbot/artifacts/{_shelf_filter}/%",)'
)
new_shelf_clause = (
    '            if _shelf_filter:\n'
    '                # file_path w DB jest relatywna (canonical/...), nie absolutna\n'
    '                _shelf_clause = "  AND (LOWER(file_path) LIKE %s OR LOWER(file_path) LIKE %s)"\n'
    '                _shelf_params = (\n'
    '                    f"{_shelf_filter}/%",\n'
    '                    f"/opt/qbot/artifacts/{_shelf_filter}/%",\n'
    '                )'
)
if old_shelf_clause in qh:
    qh = qh.replace(old_shelf_clause, new_shelf_clause, 1)
    fixes.append("R6: shelf_clause uses both relative and absolute path patterns")
else:
    print("FAIL R6: shelf_clause block not found")

# R6: polka display — też fix dla relatywnych ścieżek
old_polka = (
    "        _fp = str(a.get('file_path', ''))\n"
    "        _shelf_display = '?'\n"
    "        for _s in ('canonical', 'export', 'wip', 'old'):\n"
    "            if f'/artifacts/{_s}/' in _fp:\n"
    "                _shelf_display = _s\n"
    "                break"
)
new_polka = (
    "        _fp = str(a.get('file_path', ''))\n"
    "        _shelf_display = '?'\n"
    "        for _s in ('canonical', 'export', 'wip', 'old'):\n"
    "            # Sprawdź zarówno relatywną jak i absolutną ścieżkę\n"
    "            if _fp.startswith(_s + '/') or f'/artifacts/{_s}/' in _fp:\n"
    "                _shelf_display = _s\n"
    "                break"
)
if old_polka in qh:
    qh = qh.replace(old_polka, new_polka, 1)
    fixes.append("R6b: shelf display recognizes relative paths")
else:
    print("FAIL R6b: polka display block not found")

ast.parse(qh)
with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)
print("qbot_query_handler.py syntax OK")

print(f"\n=== {len(fixes)} fixes ===")
for fx in fixes:
    print(f"  OK: {fx}")
