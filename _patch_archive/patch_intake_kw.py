#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

for i, l in enumerate(lines):
    if '"lista posi\u0142k\u00f3w"' in l and 'nutrition_intake_logs_list' in l:
        lines[i] = (
            '    (["meal_logs", "intake_logs", "lista posi\u0142k\u00f3w", "lista wpis\u00f3w", "ca\u0142e jedzenie", "surow\u0105 list\u0119",\n'
            '      "jad\u0142em", "jad\u0142am", "co jad\u0142em", "co jad\u0142am", "co zjad\u0142em", "co zjad\u0142am",\n'
            '      "lista posilkow", "wszystkie posilki", "pelna lista jedzenia",\n'
            '      "posi\u0142ki dzi\u015b", "posi\u0142ki wczoraj", "dzisiejsze posi\u0142ki", "wczorajsze posi\u0142ki",\n'
            '      "moje posi\u0142ki", "moje jedzenie", "szczeg\u00f3\u0142y posi\u0142k\u00f3w"], "nutrition_intake_logs_list"),\n'
        )
        print(f"OK: intake_logs line {i+1} extended")
        break

for i, l in enumerate(lines):
    if '"posi\u0142ki"' in l and 'nutrition_day' in l and 'nutrition_intake' not in l:
        lines[i] = '    (["jedzenie", "jad\u0142o", "posi\u0142ek", "meal", "\u017cywno\u015b\u0107", "spo\u017cycie"], "nutrition_day"),\n'
        print(f"OK: nutrition_day line {i+1} trimmed")
        break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")

# Test
from importlib import reload
import sys
sys.path.insert(0, '/opt/qbot/app')
import qbot_query_handler
reload(qbot_query_handler)
from qbot_query_handler import _resolve_intent
tests = ['co jad\u0142em dzi\u015b', 'posi\u0142ki dzi\u015b', 'dzisiejsze posi\u0142ki', 'moje posi\u0142ki', 'jedzenie dzi\u015b']
for q in tests:
    print(f'{_resolve_intent(q):35} <- {q!r}')
