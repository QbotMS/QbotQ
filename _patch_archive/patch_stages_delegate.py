#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
# Znajdź def _handle_trip_stages
for i, l in enumerate(lines):
    if 'def _handle_trip_stages(text: str) -> dict:' in l:
        # Wstaw delegację po docstringu (linia i+2 to pierwsza linia ciała)
        inject = (
            '    # Deleguj zapytania agreguj\u0105ce do trip_summary\n'
            '    _ql_ts = text.lower()\n'
            '    if any(w in _ql_ts for w in ["najd\u0142u\u017cszy", "najdluzszy", "najkr\u00f3tszy",\n'
            '                                  "najkrotszy", "suma", "\u0142\u0105cznie", "lacznie",\n'
            '                                  "ile km razem", "razem"]):\n'
            '        return _handle_trip_summary(text)\n'
        )
        # Wstaw po linii def i docstringu
        # Znajdź koniec docstringu
        j = i + 1
        while j < len(lines) and '"""' not in lines[j]:
            j += 1
        j += 1  # po zamknięciu """
        lines.insert(j, inject)
        print(f"OK: delegacja wstawiona po linii {j}")
        break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
