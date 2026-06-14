#!/usr/bin/env python3
"""
Patch 7 bugów z testu v7:
C1: etap4 (bez spacji) → normalizacja wejścia przed routingiem
C4: stage 3 climbs tuscany → angielski stage N w _resolve_tuscany_route_id
C5: 30d / 7d / 90d → parser dni w weight_trend i body_measurements_range
E1: dodaj posiłek → action_draft zamiast daily_balance
E3: skasuj/usuń → jawny BLOCKED unsupported
E4: dodaj etap → BLOCKED
D: unrecognized short questions → prośba o doprecyzowanie kontekstu
"""
import ast, shutil, datetime, re

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.v7.{ts}')
fixes = []

# ── C1: normalizacja wejścia — etap4→etap 4, stage3→stage 3 ────────
# Wstaw normalizer na początku handle_query
old_handle_query_start = 'def handle_query(question: str) -> dict:\n'
new_handle_query_start = (
    'def _normalize_question(q: str) -> str:\n'
    '    """Normalizuj wejście: etap4→etap 4, stage3→stage 3, 30d→30 dni."""\n'
    '    import re as _re_n\n'
    '    # etap4 → etap 4, etap4toskania → etap 4 toskania\n'
    '    q = _re_n.sub(r"etap([0-9]+)", r"etap \\1", q)\n'
    '    # stage3 → stage 3\n'
    '    q = _re_n.sub(r"\\bstage([0-9]+)\\b", r"stage \\1", q)\n'
    '    # 30d → 30 dni, 7d → 7 dni\n'
    '    q = _re_n.sub(r"\\b([0-9]+)d\\b", r"\\1 dni", q)\n'
    '    return q\n'
    '\n'
    '\n'
    'def handle_query(question: str) -> dict:\n'
    '    question = _normalize_question(question)\n'
)
if old_handle_query_start in qh:
    qh = qh.replace(old_handle_query_start, new_handle_query_start, 1)
    fixes.append("C1/C5: _normalize_question (etap4→etap 4, 30d→30 dni)")
else:
    print("FAIL C1: handle_query def not found")

# ── C4: _resolve_tuscany_route_id — obsługa angielskiego "stage N" ──
old_stage_regex = (
    '        if stage_hint:\n'
    '            m = _re.search(r"etap\\s*(\\d+)", stage_hint.lower())\n'
    '            if m:\n'
    '                stage_n = int(m.group(1))'
)
new_stage_regex = (
    '        if stage_hint:\n'
    '            m = _re.search(r"(?:etap|stage)\\s*(\\d+)", stage_hint.lower())\n'
    '            if m:\n'
    '                stage_n = int(m.group(1))'
)
if old_stage_regex in qh:
    qh = qh.replace(old_stage_regex, new_stage_regex, 1)
    fixes.append("C4: _resolve_tuscany_route_id handles 'stage N' (EN)")
else:
    print("FAIL C4: stage_regex block not found")

# ── C5: weight_trend — dodaj Nd pattern ─────────────────────────────
old_wt_days = (
    '    else:\n'
    '        m = re.search(r"(\\d+)\\s*dni", _ql_wt)\n'
    '        days = min(int(m.group(1)), 90) if m else 30'
)
new_wt_days = (
    '    else:\n'
    '        m = re.search(r"(\\d+)\\s*(?:dni|d\\b)", _ql_wt)\n'
    '        days = min(int(m.group(1)), 90) if m else 30'
)
if old_wt_days in qh:
    qh = qh.replace(old_wt_days, new_wt_days, 1)
    fixes.append("C5: weight_trend parses Nd pattern")
else:
    print("FAIL C5: weight_trend days block not found")

# ── E1: write-intent keywords → action_draft ────────────────────────
# Dodaj nowy intent "write_intent" z explicit keywords PRZED nutrition
old_first_intent = (
    '    (["bilans", "balance", "kalorii", "kalorie", "kcal"], "daily_balance"),'
)
write_intent_kw = (
    '    # Write-intenty — muszą byc przed nutrition żeby nie wpaść w daily_balance\n'
    '    (["dodaj posiłek", "dodaj posilek", "zapisz posiłek", "zapisz posilek",\n'
    '      "dodaj jedzenie", "loguj posiłek", "wpisz posiłek"], "write_meal"),\n'
    '    (["skasuj wpis", "usuń wpis", "skasuj posiłek", "usuń posiłek",\n'
    '      "skasuj ostatni", "usuń ostatni", "delete", "kasuj"], "write_delete_unsupported"),\n'
    '    (["dodaj etap", "dodaj trasę", "dodaj trasę", "utwórz etap",\n'
    '      "zapisz etap", "nowy etap"], "write_planning_unsupported"),\n'
    '    (["ustaw wagę", "ustaw wage", "zmień wagę", "set weight",\n'
    '      "wpisz wagę", "wpisz wage"], "write_weight_unsupported"),\n'
)
if old_first_intent in qh:
    qh = qh.replace(old_first_intent, write_intent_kw + old_first_intent, 1)
    fixes.append("E1/E3/E4: write-intent keywords added")
else:
    print("FAIL E1: first intent line not found")

# Dodaj handlery dla write-intentów w dispatch
old_dispatch_end = (
    '    else:\n'
    '        return _envelope("unrecognized",\n'
    '                         "Nie rozpoznano intencji. Spróbuj: bilans, jedzenie, sen, wellness, energia, trening, xert, garaż, notatki, wyjazdy, raport dobowy, raport z jazdy.")'
)
new_dispatch_end = (
    '    elif intent == "write_meal":\n'
    '        return _envelope("write_meal",\n'
    '                         "\U0001f4dd Zapis posiłku wymaga potwierdzenia.\\n"\n'
    '                         "Użyj ChatGPT z narzędziem qbot.action_execute i confirm=true.\\n"\n'
    '                         "Przykład: qbot.action_execute z action_type=nutrition_log_add.",\n'
    '                         data={"action_type": "nutrition_log_add", "requires_confirm": True},\n'
    '                         status_override="ACTION_REQUIRED")\n'
    '    elif intent == "write_delete_unsupported":\n'
    '        return _envelope("write_delete_unsupported",\n'
    '                         "\U0001f6ab Kasowanie wpisów nie jest obsługiwane przez qbot.query.\\n"\n'
    '                         "Operacja delete nie jest na liście dozwolonych akcji.",\n'
    '                         status_override="BLOCKED")\n'
    '    elif intent == "write_planning_unsupported":\n'
    '        return _envelope("write_planning_unsupported",\n'
    '                         "\U0001f6ab Dodawanie etapów/tras przez qbot.query nie jest obsługiwane.\\n"\n'
    '                         "Użyj qbot.action_execute z action_type=planning_fact_add i confirm=true.",\n'
    '                         data={"action_type": "planning_fact_add", "requires_confirm": True},\n'
    '                         status_override="BLOCKED")\n'
    '    elif intent == "write_weight_unsupported":\n'
    '        return _envelope("write_weight_unsupported",\n'
    '                         "\U0001f6ab Waga pochodzi z Garmin Index Scale — nie można jej ustawić ręcznie.\\n"\n'
    '                         "Zważ się na wadze Garmin, dane zostaną zaimportowane automatycznie.",\n'
    '                         status_override="BLOCKED")\n'
    '    else:\n'
    '        _ql_ur = question.lower()\n'
    '        # Krótkie pytania bez kontekstu — prośba o doprecyzowanie zamiast zgadywania\n'
    '        _short_ctx = ["tam", "ten etap", "ten", "to", "tutaj", "na nim", "na niej",\n'
    '                      "tego etapu", "tej trasy", "ile to", "ile km"]\n'
    '        if any(kw in _ql_ur for kw in _short_ctx) or len(question.split()) <= 4:\n'
    '            return _envelope("unrecognized",\n'
    '                             "Nie mam kontekstu poprzedniego zapytania — każde wywołanie jest niezależne.\\n"\n'
    '                             "Podaj pełne pytanie, np. \'atrakcje etap 3 toskania\' lub \'woda etap 3 toskania\'.",\n'
    '                             status_override="PARTIAL")\n'
    '        return _envelope("unrecognized",\n'
    '                         "Nie rozpoznano intencji. Spróbuj: bilans, jedzenie, sen, wellness, energia, trening, xert, garaż, notatki, wyjazdy, raport dobowy, raport z jazdy.")'
)
if old_dispatch_end in qh:
    qh = qh.replace(old_dispatch_end, new_dispatch_end, 1)
    fixes.append("E1/E3/E4: write-intent dispatch handlers")
    fixes.append("D: unrecognized short/context queries → ask for clarification")
else:
    print("FAIL dispatch_end: block not found")

try:
    ast.parse(qh)
    print("qbot_query_handler.py syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    import sys; sys.exit(1)

with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)

print(f"\n=== {len(fixes)} fixes ===")
for fx in fixes:
    print(f"  OK: {fx}")
