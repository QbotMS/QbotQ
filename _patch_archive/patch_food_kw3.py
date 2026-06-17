#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

# Usuń wszystkie linie które są duplikowanym fragmentem trip_attractions
new_lines = []
skip_next = False
for i, l in enumerate(lines):
    # Znajdź linię z trip_attractions keyword tuple
    if '"trip_attractions"' in l and 'woda pitna' in l:
        # Zastąp całą linię rozszerzoną wersją
        new_lines.append(
            '    (["atrakcje", "atrakcja", "attractions", "must see", "must-see",\n'
            '      "co warto", "co zobaczy\u0107", "co zobaczyc", "poi wyjazd",\n'
            '      "woda pitna", "woda na trasie", "woda na etapie",\n'
            '      "punkty wody", "ile punkt\u00f3w wody", "ile wody",\n'
            '      "jedzenie na etapie", "jedzenie na trasie", "jedzenie etap",\n'
            '      "sklep na etapie", "sklep na trasie", "sklepy etap",\n'
            '      "restauracja na etapie", "bar na etapie", "kawiarnia na etapie",\n'
            '      "zaopatrzenie na etapie", "zaopatrzenie na trasie",\n'
            '      "co zjem", "gdzie zjem", "gdzie kupi\u0107",\n'
            '      "restauracje etap"], "trip_attractions"),\n'
        )
        skip_next = True
        print(f"OK: replaced trip_attractions line {i+1}")
    elif skip_next and ('"sklepy etap"' in l or '"restauracje etap"' in l or '"jedzenie etap"' in l):
        # To jest stara duplikowana linia — pomiń
        print(f"  Skipped duplicate line {i+1}: {l.strip()[:60]}")
    else:
        skip_next = False
        new_lines.append(l)

content = ''.join(new_lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
