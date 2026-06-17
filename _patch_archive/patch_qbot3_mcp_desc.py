#!/usr/bin/env python3
"""
Patch: qbot3/adapters/mcp_adapter.py — wzmocnienie opisu qbot.query
"""
import ast
import shutil
from datetime import datetime

TARGET = "/opt/qbot/app/qbot3/adapters/mcp_adapter.py"
BACKUP = f"{TARGET}.bak.querydesc.{datetime.now().strftime('%Y%m%d_%H%M%S')}"

shutil.copy2(TARGET, BACKUP)
print(f"Backup: {BACKUP}")

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

OLD_DESC = (
    '"JEDYNE wejście do QBot3. Przekaż oryginalne pytanie użytkownika bez modyfikacji'
    ' — dokładnie tak jak napisał użytkownik, bez przetwarzania.'
    ' Albert sam rozpoznaje intent, wybiera narzędzia, wykonuje odczyty i zapisy.'
    ' Obsługuje żywienie, trening, trasy, zdrowie, kalendarz, przypomnienia."'
)

NEW_DESC = (
    '"[OBOWIĄZKOWE] Wywołaj to narzędzie PRZED każdą odpowiedzią na pytanie użytkownika.'
    ' NIE odpowiadaj z własnej wiedzy — ZAWSZE najpierw wywołaj qbot.query i użyj zwróconych danych.'
    ' Jeśli narzędzie zwróci błąd lub pusty wynik, poinformuj użytkownika że dane są niedostępne — NIE generuj odpowiedzi z pamięci.'
    ' Przekaż oryginalne pytanie użytkownika bez modyfikacji — dokładnie tak jak napisał użytkownik, bez przetwarzania.'
    ' Albert sam rozpoznaje intent, wybiera narzędzia, wykonuje odczyty i zapisy.'
    ' Obsługuje żywienie, trening, trasy, zdrowie, kalendarz, przypomnienia."'
)

if OLD_DESC not in src:
    print(f"BŁĄD: Nie znaleziono starego opisu.")
    print(f"Szukam: {repr(OLD_DESC[:80])}")
    # Pokaż aktualny opis
    import re
    m = re.search(r'"description": "([^"]+)"', src)
    if m:
        print(f"Znaleziono: {repr(m.group(1)[:80])}")
    exit(1)

new_src = src.replace(OLD_DESC, NEW_DESC, 1)

try:
    ast.parse(new_src)
    print("AST OK")
except SyntaxError as e:
    print(f"BŁĄD SKŁADNI: {e}")
    exit(1)

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(new_src)

print("Patch zapisany.")

# Weryfikacja
with open(TARGET, "r", encoding="utf-8") as f:
    check = f.read()
if "OBOWIĄZKOWE" in check:
    print("Weryfikacja OK — nowy opis w pliku.")
else:
    print("UWAGA: Nowy opis nie znaleziony po zapisie!")
