#!/usr/bin/env python3
"""Jednorazowa latka 2026-10-06: suwak startu w Planie dnia 08:00-12:00 -> 06:00-20:00.
Pogoda raportu (route_meteo_engine) liczy z calej doby, wiec dziala dla kazdej godziny.
Pakiet dnia AI dalej ma warianty 08-12 (poza zakresem: komunikat 'uzyty najblizszy wariant')."""
import shutil, sys, time

P = "/opt/qbot/web/public/raport-trasy2-plan.js"
REPL = [
    ('min="480" max="720" step="15"', 'min="360" max="1200" step="15"'),
    ("Math.max(480,Math.min(720,m))", "Math.max(360,Math.min(1200,m))"),
]
src = open(P, encoding="utf-8").read()
for old, new in REPL:
    n = src.count(old)
    if n != 1:
        sys.exit(f"STOP: '{old}' wystepuje {n} razy (oczekiwane 1) - nic nie zmieniono")
bak = P + ".bak." + time.strftime("%Y%m%d%H%M%S")
shutil.copy2(P, bak)
for old, new in REPL:
    src = src.replace(old, new)
open(P, "w", encoding="utf-8").write(src)
print("OK, kopia:", bak)
