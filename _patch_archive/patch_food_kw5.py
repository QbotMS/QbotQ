#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

# 1. Przywróć 'jedzenie' do nutrition_day
for i, l in enumerate(lines):
    if '"jadło"' in l and 'nutrition_day' in l and '"jedzenie"' not in l:
        lines[i] = l.replace('"jadło"', '"jedzenie", "jadło"')
        print(f"OK: restored 'jedzenie' to nutrition_day line {i+1}")
        break

# 2. Dodaj multi-word trip_attractions keywords PRZED nutrition_day
for i, l in enumerate(lines):
    if '"jedzenie"' in l and 'nutrition_day' in l:
        inject = (
            '    # Multi-word trip keywords muszą być przed nutrition_day\n'
            '    (["jedzenie etap", "jedzenie na etapie", "jedzenie na trasie",\n'
            '      "zaopatrzenie etap", "zaopatrzenie na etapie", "zaopatrzenie na trasie",\n'
            '      "co zjem na etapie", "gdzie zjem na etapie", "gdzie kupi\u0107 na etapie",\n'
            '      "sklepy na etapie", "sklep na etapie", "bar na etapie",\n'
            '      "kawiarnia na etapie", "restauracja na etapie"], "trip_attractions"),\n'
        )
        lines.insert(i, inject)
        print(f"OK: inserted trip_attractions multi-word before nutrition_day line {i+1}")
        break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
