#!/usr/bin/env python3
"""Przenieś analytical fallback PRZED multi-intent check."""
import ast

lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

# Znajdź blok multi-intent (linia z "# ── Multi-intent")
mi_start = None
mi_end = None
for i, l in enumerate(lines):
    if '# ── Multi-intent: sprawdz czy pytanie obejmuje >1 domene ──────────' in l:
        mi_start = i
    if mi_start and 'return _handle_multi_intent(question, domains)' in l:
        mi_end = i
        break

# Znajdź blok analytical (linia z "# ── Analytical fallback")
an_start = None
an_end = None
for i, l in enumerate(lines):
    if '# ── Analytical fallback → Albert' in l:
        an_start = i
    if an_start and '_albert_enabled = __import__' in l:
        # Znajdź koniec bloku (puste linie po except pass)
        j = i + 1
        while j < len(lines) and (lines[j].strip() == '' or lines[j].startswith('    ')):
            if lines[j].strip() == '' and j > i + 3:
                an_end = j
                break
            j += 1
        if not an_end:
            an_end = j
        break

print(f"multi-intent: lines {mi_start+1}-{mi_end+1}")
print(f"analytical: lines {an_start+1}-{an_end+1}")

# Wytnij blok analytical
analytical_block = lines[an_start:an_end]

# Usuń analytical z obecnej pozycji
del lines[an_start:an_end]

# Wstaw PRZED multi-intent (mi_start mógł się przesunąć jeśli an < mi)
if an_start < mi_start:
    insert_pos = mi_start - (an_end - an_start)
else:
    insert_pos = mi_start

lines[insert_pos:insert_pos] = analytical_block
print(f"Inserted analytical at line {insert_pos+1}")

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
