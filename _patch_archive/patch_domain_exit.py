#!/usr/bin/env python3
"""Dodaj early-exit w _detect_domains gdy pytanie to jednoznaczny trip query."""
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

for i, l in enumerate(lines):
    if 'def _detect_domains(question: str) -> list[str]:' in l:
        # Wstaw early-exit po def
        j = i + 1
        while j < len(lines) and lines[j].strip().startswith('#'):
            j += 1
        inject = (
            '    # Early exit: pytania o POI na etapie to single-domain trip, nie multi\n'
            '    _ql_dd = question.lower()\n'
            '    _TRIP_POI_PHRASES = ["jedzenie etap", "jedzenie na etapie", "zaopatrzenie etap",\n'
            '                         "zaopatrzenie na etapie", "co zjem na etapie",\n'
            '                         "sklepy etap", "sklep na etapie", "woda etap",\n'
            '                         "woda na etapie", "atrakcje etap", "poi etap"]\n'
            '    if any(p in _ql_dd for p in _TRIP_POI_PHRASES):\n'
            '        return ["trip"]\n'
        )
        lines.insert(j, inject)
        print(f"OK: early-exit inserted at line {j+1}")
        break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
