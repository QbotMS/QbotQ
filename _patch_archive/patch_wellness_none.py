#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
# Linia 931 (0-indexed 930): d = _today_or(day_str)
for i, l in enumerate(lines):
    if '_handle_wellness_day' in l and 'def ' in l:
        # Następna linia
        lines[i+1] = '    d = _today_or(day_str or "")\n'
        print(f"OK: line {i+2} fixed")
        break
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
