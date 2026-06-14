#!/usr/bin/env python3
"""Popraw delegację — wstaw do właściwej funkcji _handle_trip_stages."""
import ast

lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()

# Najpierw usuń błędnie wstawioną delegację z _diagnose_source_status (linie 2268-2273)
# Znajdź gdzie jest i usuń
bad_lines = []
for i, l in enumerate(lines):
    if '_ql_ts = text.lower()' in l and i > 2260 and i < 2280:
        bad_lines = [i, i+1, i+2, i+3, i+4]
        print(f"Found bad injection at lines {[x+1 for x in bad_lines]}")
        break

if bad_lines:
    for idx in sorted(bad_lines, reverse=True):
        del lines[idx]
    print("Removed bad injection")

# Teraz znajdź _handle_trip_stages (linia 2157, po usunięciu ~2152)
for i, l in enumerate(lines):
    if 'def _handle_trip_stages(text: str) -> dict:' in l:
        # Wstaw delegację jako pierwsza linia ciała funkcji
        inject = (
            '    # Deleguj agregacje do trip_summary\n'
            '    if any(w in text.lower() for w in ["najd\u0142u\u017cszy", "najdluzszy",\n'
            '                                        "najkr\u00f3tszy", "najkrotszy",\n'
            '                                        "\u0142\u0105cznie", "lacznie", "razem", "suma"]):\n'
            '        return _handle_trip_summary(text)\n'
        )
        lines.insert(i + 1, inject)
        print(f"OK: delegation inserted at line {i+2}")
        break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
