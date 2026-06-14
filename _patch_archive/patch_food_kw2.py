#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'trip_attractions' in l and 'woda na etapie' in l:
        # Znajdź zamkniecie nawiasu w tej linii
        lines[i] = (
            '      "woda pitna", "woda na trasie", "woda na etapie", "sklepy na etapie",\n'
            '      "jedzenie na etapie", "jedzenie na trasie", "sklep na etapie",\n'
            '      "restauracja na etapie", "bar na etapie", "kawiarnia na etapie",\n'
            '      "zaopatrzenie na etapie", "zaopatrzenie na trasie",\n'
            '      "co zjem", "gdzie zjem", "gdzie kupi\u0107",\n'
            '      "sklepy etap", "restauracje etap", "jedzenie etap"], "trip_attractions"),\n'
        )
        print(f"OK: line {i+1} replaced")
        break
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
