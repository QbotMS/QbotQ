#!/usr/bin/env python3
from qbot_query_handler import _handle_nutrition_range
r = _handle_nutrition_range('makro za ostatni tydzien')
pd = r['data']['per_day']
print("N1: per_day balance_kcal spójność:")
for e in pd:
    kcal = e.get('kcal_total')
    exp = e.get('expenditure_total')
    bal_entry = e.get('balance_kcal')
    bal_calc = round(kcal - exp, 0) if (kcal is not None and exp is not None) else None
    match = 'OK' if bal_entry == bal_calc else f'DIFF entry={bal_entry} calc={bal_calc}'
    print(f"  {e['date']}: kcal={kcal} exp={exp} bal_entry={bal_entry} calc={bal_calc} -> {match}")

print()
print("Tabela z odpowiedzi:")
for line in r['answer'].split('\n'):
    if '202' in line or 'Bilans' in line or '---' in line:
        print(' ', line)
