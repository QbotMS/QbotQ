#!/usr/bin/env python3
"""
Dodaj keywords dla jedzenia/sklepów/zaopatrzenia → trip_attractions.
Jednocześnie upewnij się że section_filter 'food' działa.
"""
import ast

QH = '/opt/qbot/app/qbot_query_handler.py'
lines = open(QH, encoding='utf-8').readlines()

for i, l in enumerate(lines):
    if '"woda pitna", "woda na trasie", "woda na etapie"' in l and 'trip_attractions' in l:
        lines[i] = l.rstrip().rstrip('],') + (
            ',\n'
            '      "jedzenie na etapie", "jedzenie na trasie", "sklep na etapie", "sklep na trasie",\n'
            '      "restauracja na etapie", "bar na etapie", "kawiarnia na etapie",\n'
            '      "zaopatrzenie na etapie", "zaopatrzenie na trasie",\n'
            '      "co zjem", "gdzie zjem", "gdzie kupi\u0107", "gdzie kupc",\n'
            '      "sklepy etap", "restauracje etap", "jedzenie etap"], "trip_attractions"),\n'
        )
        print(f"OK: trip_attractions keywords extended at line {i+1}")
        break

content = ''.join(lines)
ast.parse(content)
open(QH, 'w', encoding='utf-8').write(content)
print("syntax OK")
