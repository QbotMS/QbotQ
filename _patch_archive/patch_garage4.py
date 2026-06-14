#!/usr/bin/env python3
"""Ostateczna naprawa garage routing — garaż nie może być substring garażu."""
import ast

QH = '/opt/qbot/app/qbot_query_handler.py'
lines = open(QH, encoding='utf-8').readlines()

# Linia 238 (0-indexed 237): garage_status
# "garaż" matchuje w "garażu" przez 'kw in ql'
# Rozwiązanie: zastąp "garaż" przez frazy z terminatorem (spacja lub koniec)
# i dodaj "mój garaż", "garaż qbot" etc.
# Alternatywa: sprawdzaj word-boundary w resolve_intent — ale to duża zmiana
# Najprostsze: usuń "garaż" i "garage" z garage_status,
# zostaw "sprzęt"/"rower"/"wyposażenie" jako wystarczające triggery dla statusu

old237 = lines[237]
lines[237] = (
    '    (["sprz\u0119t", "sprzet", "rower", "rowery", "wyposa\u017cenie", '
    '"status gara\u017cu", "co mam w gara\u017cu", "gara\u017c qbot", "m\u00f3j gara\u017c"], "garage_status"),\n'
)
print(f"Old: {old237.strip()[:80]}")
print(f"New: {lines[237].strip()[:80]}")

# Linia 239 (0-indexed 238): garage_search — dodaj z powrotem "garaż"/"garage"
old238 = lines[238]
lines[238] = (
    '    (["gara\u017c", "garage", "gara\u017cu", "w gara\u017cu", "w garazu", '
    '"kask", "kasku", "kask\u00f3w", "kaskem", "kaskow", "buty", "but", "butach", '
    '"r\u0119kawiczki", "r\u0119kawiczek", "rekawiczki", "rekawiczek", "r\u0119kawiczkach", '
    '"kurtka", "kurtki", "jersey", "koszulka", "spodenki", "szukaj", "opony", '
    '"ko\u0142a", "kola", "komponenty", "base layer", "rafa", "rapha", "pedaled", '
    '"kaski", "but\u00f3w", "kurtek", "skarpety", "torby", "namiot", "kamizelka", '
    '"spodnie", "kierownica", "sio\u0142o", "siodlo", "lancuch", "\u0142a\u0144cuch", '
    '"kaseta", "komin", "czapka", "chusta"], "garage_search"),\n'
)

content = ''.join(lines)
ast.parse(content)
open(QH, 'w', encoding='utf-8').write(content)
print("OK: garage routing final fix, syntax OK")
print("garage_status: sprzęt/rower/wyposażenie/status garażu")
print("garage_search: garaż/garage/kasków/rękawiczek/...")
