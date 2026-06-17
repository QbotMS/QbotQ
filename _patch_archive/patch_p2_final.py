#!/usr/bin/env python3
"""
P2 fixes:
1. nutrition_range per_day: nadpisz balance_kcal obliczonym bilansem
2. energy routing: 'ile kalorii spaliłem' → energy_day, nie daily_balance
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.p2.{ts}')

# ── 1: per_day — nadpisz balance_kcal obliczonym _bal ────────────────
old_bal_append = (
    '            if _bal is not None:\n'
    '                totals["balance_kcal"] += _bal\n'
    '                totals_count["balance_kcal"] += 1\n'
    '            # If no nutrition summary but daily_summary has intake, use that\n'
    '            if not n and dse.get("intake_kcal") is not None:\n'
    '                totals["intake_kcal"] += dse["intake_kcal"]\n'
    '                totals_count["intake_kcal"] += 1\n'
    '\n'
    '        per_day.append(entry)'
)
new_bal_append = (
    '            if _bal is not None:\n'
    '                totals["balance_kcal"] += _bal\n'
    '                totals_count["balance_kcal"] += 1\n'
    '            # Nadpisz balance_kcal w entry obliczonym bilansem (nie Garmin)\n'
    '            entry["balance_kcal"] = _bal\n'
    '            # If no nutrition summary but daily_summary has intake, use that\n'
    '            if not n and dse.get("intake_kcal") is not None:\n'
    '                totals["intake_kcal"] += dse["intake_kcal"]\n'
    '                totals_count["intake_kcal"] += 1\n'
    '\n'
    '        per_day.append(entry)'
)
if old_bal_append in qh:
    qh = qh.replace(old_bal_append, new_bal_append, 1)
    print("OK 1: per_day balance_kcal overwritten with calculated value")
else:
    print("FAIL 1: bal_append block not found")

# ── 2: energy routing — dodaj 'ile kalorii spalone' przed daily_balance ──
# Problem: 'kalorii' w daily_balance matchuje przed 'spaliłem' w energy_day
# Fix: dodaj explicit frazy do energy_day keywords
old_energy_kw = '    (["energia", "energię", "energy", "spaliłem", "spaliłam", "kroki", "steps", "aktywność"], "energy_day"),'
new_energy_kw = '    (["ile kalorii", "ile spaliłem", "ile spaliłam", "kalorii spalone", "kalorii spaliłem", "energia", "energię", "energy", "spaliłem", "spaliłam", "kroki", "steps", "aktywność"], "energy_day"),'

if old_energy_kw in qh:
    qh = qh.replace(old_energy_kw, new_energy_kw, 1)
    print("OK 2: energy_day keywords extended for 'ile kalorii'")
else:
    print("FAIL 2: energy_day keyword line not found")

# energy_day musi być PRZED daily_balance w INTENT_KEYWORDS
# Sprawdź kolejność
idx_energy = qh.find('"energy_day"')
idx_balance = qh.find('"daily_balance"')
if idx_energy > idx_balance:
    # Przenieś energy_day przed daily_balance
    # Znajdź całą linię energy_day
    import re
    energy_line_m = re.search(r'    \(\[.*?"energy_day"\),\n', qh)
    balance_line_m = re.search(r'    \(\[.*?"daily_balance"\),\n', qh)
    if energy_line_m and balance_line_m:
        energy_line = energy_line_m.group(0)
        balance_line = balance_line_m.group(0)
        # Usuń energy_day z obecnej pozycji
        qh_no_energy = qh.replace(energy_line, '', 1)
        # Wstaw przed daily_balance
        qh = qh_no_energy.replace(balance_line, energy_line + balance_line, 1)
        print("OK 2b: energy_day moved before daily_balance in INTENT_KEYWORDS")
    else:
        print("WARN 2b: could not reorder (regex miss)")
else:
    print("OK 2b: energy_day already before daily_balance")

ast.parse(qh)
with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)
print("syntax OK")
