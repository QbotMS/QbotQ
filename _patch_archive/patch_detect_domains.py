#!/usr/bin/env python3
"""
Patch: _detect_domains — wyklucz 'trip' gdy pytanie dotyczy gotowości/formy przed wyjazdem.
Problem: "czy jestem gotowy na toskanie" → trip+xert → multi_intent → PARTIAL
Fix: readiness_trip_phrases → usuń 'trip' z domains, zostaw xert/wellness/sleep
"""
import ast
import shutil
from datetime import datetime

TARGET = "/opt/qbot/app/qbot_query_handler.py"
BACKUP = f"{TARGET}.bak.multidomain.{datetime.now().strftime('%Y%m%d_%H%M%S')}"

shutil.copy2(TARGET, BACKUP)
print(f"Backup: {BACKUP}")

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

OLD = '''def _detect_domains(question: str) -> list[str]:
    # Early exit: pytania o POI na etapie to single-domain trip, nie multi
    _ql_dd = question.lower()
    _TRIP_POI_PHRASES = ["jedzenie etap", "jedzenie na etapie", "zaopatrzenie etap",
                         "zaopatrzenie na etapie", "co zjem na etapie",
                         "sklepy etap", "sklep na etapie", "woda etap",
                         "woda na etapie", "atrakcje etap", "poi etap"]
    if any(p in _ql_dd for p in _TRIP_POI_PHRASES):
        return ["trip"]
    """Wykryj domeny w pytaniu - zwroc liste gdy >1."""
    ql = question.lower()
    found = []
    for domain, signals in _DOMAIN_SIGNALS.items():
        if any(s in ql for s in signals):
            found.append(domain)
    return found'''

NEW = '''def _detect_domains(question: str) -> list[str]:
    # Early exit: pytania o POI na etapie to single-domain trip, nie multi
    _ql_dd = question.lower()
    _TRIP_POI_PHRASES = ["jedzenie etap", "jedzenie na etapie", "zaopatrzenie etap",
                         "zaopatrzenie na etapie", "co zjem na etapie",
                         "sklepy etap", "sklep na etapie", "woda etap",
                         "woda na etapie", "atrakcje etap", "poi etap"]
    if any(p in _ql_dd for p in _TRIP_POI_PHRASES):
        return ["trip"]
    # Pytania o gotowość/formę przed wyjazdem — trip to tylko kontekst, nie domena danych
    # Wykluczamy 'trip' zeby nie routowac do trip_stages ktory zwroci ERROR
    _READINESS_PHRASES = [
        "gotowy na", "gotowa na", "gotowosc na", "gotowos na",
        "czy moge jechac", "czy dam rade", "forma przed",
        "forma na toskanie", "forma przed toskania", "forma na tuscany",
        "ocen forme", "ocen moja forme", "moja forma przed",
        "readiness", "czy jestem gotowy", "czy jestem gotowa",
        "przygotowany na", "przygotowana na",
    ]
    if any(p in _ql_dd for p in _READINESS_PHRASES):
        # Wykryj domeny ale bez trip — trip to kontekst geograficzny, nie zrodlo danych
        ql = _ql_dd
        found = []
        for domain, signals in _DOMAIN_SIGNALS.items():
            if domain == "trip":
                continue
            if any(s in ql for s in signals):
                found.append(domain)
        # Jesli brak innych domen, fallback do xert (forma)
        if not found:
            found = ["xert"]
        return found
    """Wykryj domeny w pytaniu - zwroc liste gdy >1."""
    ql = question.lower()
    found = []
    for domain, signals in _DOMAIN_SIGNALS.items():
        if any(s in ql for s in signals):
            found.append(domain)
    return found'''

if OLD not in src:
    print("BLAD: Nie znaleziono starego kodu _detect_domains")
    # Pokaż co jest
    import re
    m = re.search(r'def _detect_domains.*?return found', src, re.DOTALL)
    if m:
        print("Znaleziono fragment:", m.group()[:200])
    exit(1)

new_src = src.replace(OLD, NEW, 1)

try:
    ast.parse(new_src)
    print("AST OK")
except SyntaxError as e:
    print(f"BLAD SKLADNI: {e}")
    exit(1)

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(new_src)

print("Patch zapisany.")

# Weryfikacja
with open(TARGET, "r", encoding="utf-8") as f:
    check = f.read()
if "READINESS_PHRASES" in check:
    print("Weryfikacja OK.")
else:
    print("UWAGA: Patch nie znaleziony po zapisie!")
