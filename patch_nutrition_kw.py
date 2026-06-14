#!/usr/bin/env python3
"""patch_nutrition_kw.py — guard dla 'ile kalorii zjadlem' przed energy_day."""

import ast, shutil
from datetime import datetime

TARGET = "/opt/qbot/app/qbot_query_handler.py"

src = open(TARGET, encoding="utf-8").read()

# Anchor: linia energy_day z "ile kalorii" — dodajemy guard PRZED nia
OLD = '    (["ile kalorii", "ile spaliłem", "ile spaliłam", "kalorii spalone", "kalorii spaliłem", "energia", "energię", "energy", "spaliłem", "spaliłam", "kroki", "steps", "aktywność"], "energy_day"),'

# Guard: wielowyrazowe frazy nutrition PRZED "ile kalorii" w energy_day
GUARD = '    # Guard: "ile kalorii zjadlem" musi byc PRZED energy_day ("ile kalorii" -> energy)\n    (["ïle kalorii zjadłem", "ile kalorii zjadłam", "ile kcal zjadłem", "ile kcal zjadłam",\n      "kalorii zjadłem", "kalorii zjadłam", "ile zjadłem kalorii", "ile zjadłam kalorii",\n      "ile kalorii wziąłem", "ile kalorii wzięłam", "ile kalorii spożyłem", "ile kalorii spożyłam",\n      "ile kalorii na dzień", "ile kalorii dziś", "kalorii dziś zjadlem", "kalorii wczoraj zjadłem"], "daily_balance"),\n    '

# Sprawdz ze anchor istnieje
if OLD not in src:
    # Sprobuj bez polskich znakow (fallback: szukaj po fragmencie ASCII)
    import re
    m = re.search(r'\(\["ile kalorii".*?"energy_day"\),', src)
    if m:
        OLD = m.group(0)
        print(f"  anchor znaleziony alternatywnie: {OLD[:60]}")
    else:
        raise SystemExit("BLAD: nie znaleziono anchor energy_day")

# Guard bez unicode escape - zapisujemy wprost
GUARD_CLEAN = (
    '    # Guard: "ile kalorii zjadlem" musi byc PRZED energy_day\n'
    '    (["ile kalorii zjadłem", "ile kalorii zjadłam",\n'
    '      "ile kcal zjadłem", "ile kcal zjadłam",\n'
    '      "kalorii zjadłem", "kalorii zjadłam",\n'
    '      "ile kalorii dziś", "kalorii dziś", "ile kalorii wczoraj",\n'
    '      "ile zjadłem kcal", "ile zjadłam kcal"], "daily_balance"),\n'
    '    '
)

patched = src.replace(OLD, GUARD_CLEAN + OLD, 1)

try:
    ast.parse(patched)
except SyntaxError as e:
    raise SystemExit(f"BLAD skladni: {e}")

bak = TARGET + ".bak." + datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(TARGET, bak)
open(TARGET, "w", encoding="utf-8").write(patched)
print("OK: guard nutrition dodany przed energy_day")
print(f"backup: {bak}")
