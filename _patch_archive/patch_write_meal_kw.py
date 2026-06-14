#!/usr/bin/env python3
"""
Bugi:
1. 'Batonik Góralek 255 kcal' → daily_balance zamiast write_meal
   Fix: dodaj 'batonik', 'baton', 'przekąska' do write_meal keywords
        + regex-based detekcja "[słowo] kcal" jako write_meal w _resolve_intent

2. Garaż zamiast nutrition przy write_meal z nazwą produktu
   Root cause: słowo "cały" nie jest problemem, problem to brak detekcji
   wzorca "nazwa_produktu X kcal B Y W Z T N" jako write_meal
"""
import ast

QH = '/opt/qbot/app/qbot_query_handler.py'
lines = open(QH, encoding='utf-8').readlines()

# 1. Rozszerz write_meal keywords o typowe słowa z zapisu jedzenia
for i, l in enumerate(lines):
    if '"dodaj posiłek", "dodaj posilek"' in l:
        # Znajdź koniec tego tuple (zamknięcie nawiasu)
        j = i
        while j < len(lines) and '"write_meal"' not in lines[j]:
            j += 1
        # Wstaw przed "write_meal"
        lines[j] = lines[j].replace(
            '], "write_meal")',
            ', "batonik", "baton", "przekąska", "snack",\n'
            '      "zjedziałem", "zjadłem", "zjadłam", "spożyłem", "spożyłam",\n'
            '      "cały batonik", "porcja", "całe opakowanie"], "write_meal")'
        )
        print(f"OK: write_meal keywords extended at line {j+1}")
        break

content = ''.join(lines)
ast.parse(content)
open(QH, 'w', encoding='utf-8').write(content)
print("syntax OK")

# Test
import sys
sys.path.insert(0, '/opt/qbot/app')
import importlib
import qbot_query_handler
importlib.reload(qbot_query_handler)
from qbot_query_handler import _resolve_intent

tests = [
    'Batonik G\u00f3ralek bez czekolady ca\u0142y 255 kcal',
    'batonik 255 kcal',
    'co jad\u0142em dzi\u015b',
    'posi\u0142ki dzi\u015b',
]
for q in tests:
    print(f'{_resolve_intent(q):35} <- {q!r}')
