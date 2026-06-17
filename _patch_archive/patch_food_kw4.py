#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

for i, l in enumerate(lines):
    if '"jedzenie"' in l and 'nutrition_day' in l:
        # Usuń "jedzenie" z nutrition_day - wystarczy posiłek/meal/jadło
        lines[i] = l.replace('"jedzenie", ', '').replace(', "jedzenie"', '')
        print(f"OK: removed 'jedzenie' from nutrition_day line {i+1}")
        break

# Dodaj 'jedzenie' + 'zaopatrzenie' do trip_attractions tuple
for i, l in enumerate(lines):
    if '"trip_attractions"' in l and 'woda pitna' in l:
        # Wstaw przed ], "trip_attractions")
        lines[i] = l.replace(
            '], "trip_attractions"),',
            ', "jedzenie na etapie", "jedzenie na trasie", "jedzenie etap",\n'
            '      "zaopatrzenie", "zaopatrzenie na etapie", "zaopatrzenie na trasie",\n'
            '      "co zjem", "gdzie zjem", "gdzie kupi\u0107"], "trip_attractions"),'
        )
        print(f"OK: added food/supply keywords to trip_attractions line {i+1}")
        break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
