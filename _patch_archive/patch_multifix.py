import ast, shutil, sys
from datetime import datetime

TARGET = "/opt/qbot/app/qbot_query_handler.py"
BACKUP = f"{TARGET}.bak.multifix.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
shutil.copy2(TARGET, BACKUP)
print(f"Backup: {BACKUP}")

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

errors = []

# FIX 1: usun toskania/tuscany z trip_stages
OLD1 = '(["etap", "etapy", "stage", "stages", "dzisiejszy etap", "etap dzi\u015b", "etap dzis", "plan etap\u00f3w", "plan etapow", "jaki etap", "kt\u00f3ry etap", "toskania", "tuscany", "toskanii", "toskanię"], "trip_stages")'
NEW1 = '(["etap", "etapy", "stage", "stages", "dzisiejszy etap", "etap dzi\u015b", "etap dzis", "plan etap\u00f3w", "plan etapow", "jaki etap", "kt\u00f3ry etap"], "trip_stages")'
if OLD1 in src:
    src = src.replace(OLD1, NEW1, 1)
    print("Fix 1 OK")
else:
    errors.append("Fix1: nie znaleziono trip_stages kw")

# FIX 2: dodaj gotowosci intent przed trip_stages
READINESS_INTENT = '(["ocen forme", "ocen form\u0119", "gotowo\u015b\u0107 przed", "gotowosc przed", "czy jestem gotowy", "czy dam rade", "czy dam rad\u0119", "forma przed wyjazdem", "forma przed wyprawa", "readiness przed", "gotowy na wyjazd", "ocen moja forme", "ocen moj\u0105 form\u0119", "jaka mam forme", "jaka mam form\u0119"], "xert_status"),\n    ' + NEW1
if NEW1 in src:
    src = src.replace(NEW1, READINESS_INTENT, 1)
    print("Fix 2 OK")
else:
    errors.append("Fix2: nie znaleziono miejsca na readiness intent")

# FIX 3: lepszy komunikat PARTIAL w multi_intent
OLD3 = '    if not results:\n        return _envelope("multi_intent", "Brak danych dla podanych domen.", status_override="PARTIAL")'
NEW3 = ('    if not results:\n'
        '        domains_str = ", ".join(domains) if domains else "nieznane"\n'
        '        err_str = ("; ".join(str(e) for e in errors)) if errors else "brak odpowiedzi"\n'
        '        msg = (f"Nie udalo sie pobrac danych dla domen: {domains_str}.\\n"\n'
        '               f"Bledy: {err_str}\\n"\n'
        '               f"Sprobuj pytac osobno, np. \'moja forma xert\' lub \'sen dzisiaj\'.")\n'
        '        return _envelope("multi_intent", msg, status_override="PARTIAL")')
if OLD3 in src:
    src = src.replace(OLD3, NEW3, 1)
    print("Fix 3 OK")
else:
    errors.append("Fix3: nie znaleziono if not results")

if errors:
    print("BLEDY:", errors)
    sys.exit(1)

try:
    ast.parse(src)
    print("AST OK")
except SyntaxError as e:
    print(f"BLAD SKLADNI: {e}")
    sys.exit(1)

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src)
print("Patch zapisany.")
