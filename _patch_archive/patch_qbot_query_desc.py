#!/usr/bin/env python3
"""
Patch: wzmocnienie opisu qbot.query — zakaz odpowiadania bez wywołania narzędzia.
"""
import re
import ast
import shutil
from datetime import datetime

TARGET = "/opt/qbot/app/qbot_mcp_adapter.py"
BACKUP = f"{TARGET}.bak.querydesc.{datetime.now().strftime('%Y%m%d_%H%M%S')}"

shutil.copy2(TARGET, BACKUP)
print(f"Backup: {BACKUP}")

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

OLD_DESC = (
    '"JEDYNE wejście do QBot Runtime. Przekaż oryginalne pytanie użytkownika bez żadnych modyfikacji. "\n'
    '            "NIE dopisuj action_type, writer name, payload schema, \'przygotuj draft\', \'użyj writera\', \'confirm\' ani template match. "\n'
    '            "NIE pre-routuj, NIE enrichuj z nazwami tooli/akcji. "\n'
    '            "Albert (QBot LLM) sam rozpoznaje intent, wybiera readery, agreguje dane z DB i buduje odpowiedź. "\n'
    '            "Dla zapisów zwraca action_draft — wywołaj qbot.action_execute aby wykonać. "\n'
    '            "Parametr context: przekaż tylko source, timezone, date jeśli znane."'
)

NEW_DESC = (
    '"[OBOWIĄZKOWE] Wywołaj to narzędzie PRZED każdą odpowiedzią na pytanie użytkownika. "\n'
    '            "NIE odpowiadaj z własnej wiedzy — ZAWSZE najpierw wywołaj qbot.query i użyj zwróconych danych. "\n'
    '            "Jeśli narzędzie zwróci błąd lub pusty wynik, poinformuj użytkownika że dane są niedostępne — NIE generuj odpowiedzi z pamięci. "\n'
    '            "Przekaż oryginalne pytanie użytkownika bez żadnych modyfikacji. "\n'
    '            "NIE dopisuj action_type, writer name, payload schema, \'przygotuj draft\', \'użyj writera\', \'confirm\' ani template match. "\n'
    '            "NIE pre-routuj, NIE enrichuj z nazwami tooli/akcji. "\n'
    '            "Albert (QBot LLM) sam rozpoznaje intent, wybiera readery, agreguje dane z DB i buduje odpowiedź. "\n'
    '            "Dla zapisów zwraca action_draft — wywołaj qbot.action_execute aby wykonać. "\n'
    '            "Parametr context: przekaż tylko source, timezone, date jeśli znane."'
)

if OLD_DESC not in src:
    print("BŁĄD: Nie znaleziono starego opisu. Sprawdź plik ręcznie.")
    exit(1)

new_src = src.replace(OLD_DESC, NEW_DESC, 1)

# Walidacja AST
try:
    ast.parse(new_src)
    print("AST OK")
except SyntaxError as e:
    print(f"BŁĄD SKŁADNI: {e}")
    exit(1)

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(new_src)

print("Patch zapisany.")
