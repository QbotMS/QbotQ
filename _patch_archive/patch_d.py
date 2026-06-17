#!/usr/bin/env python3
"""D: trip_attractions — gdy brak stage_n i brak trip_hint → zapytaj o doprecyzowanie."""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
TA = '/opt/qbot/app/tools/trip_attractions.py'
with open(TA, encoding='utf-8') as f:
    ta = f.read()
shutil.copy(TA, f'{TA}.bak.d.{ts}')

old_fetch = (
    '    records = _fetch_poi_facts(trip_hint, stage_n)\n'
    '    if not records:\n'
    '        records = _fetch_poi_facts()\n'
    '\n'
    '    if not records:'
)
new_fetch = (
    '    # Brak kontekstu — pytaj zamiast zgadywać\n'
    '    _context_words = ["tam", "ten etap", "tego etapu", "na nim", "na niej",\n'
    '                      "na tym etapie", "tutaj", "ten"]\n'
    '    _has_context_ref = any(w in ql for w in _context_words)\n'
    '    if stage_n is None and trip_hint is None and _has_context_ref:\n'
    '        return {\n'
    '            "answer": (\n'
    '                "Nie mam kontekstu poprzedniego zapytania — ka\u017cde wywo\u0142anie jest niezale\u017cne.\\n"\n'
    '                "Podaj pe\u0142ne pytanie, np. \'atrakcje etap 3 toskania\' lub \'woda etap 1 toskania\'."\n'
    '            ),\n'
    '            "data": {"requires_context": True}, "sources": []\n'
    '        }\n'
    '\n'
    '    records = _fetch_poi_facts(trip_hint, stage_n)\n'
    '    if not records:\n'
    '        records = _fetch_poi_facts()\n'
    '\n'
    '    if not records:'
)

if old_fetch in ta:
    ta = ta.replace(old_fetch, new_fetch, 1)
    ast.parse(ta)
    with open(TA, 'w', encoding='utf-8') as f:
        f.write(ta)
    print("OK D: trip_attractions context clarification, syntax OK")
else:
    print("FAIL: fetch block not found")
