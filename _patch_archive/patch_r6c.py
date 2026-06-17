#!/usr/bin/env python3
import ast

QH = '/opt/qbot/app/qbot_query_handler.py'
lines = open(QH, encoding='utf-8').readlines()

# Linia 2615 (0-indexed 2614): store_unavailable = False
# Zmień na: store_unavailable = bool(_shelf_filter)
for i, l in enumerate(lines):
    if 'store_unavailable = False' in l and i > 2610:
        lines[i] = '    store_unavailable = bool(_shelf_filter)  # skip Method 1 when shelf filter set\n'
        print(f"OK: line {i+1} changed")
        break

content = ''.join(lines)
ast.parse(content)
open(QH, 'w', encoding='utf-8').write(content)
print("syntax OK")
