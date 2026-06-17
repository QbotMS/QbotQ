#!/usr/bin/env python3
"""
Patch 4 fixable bugów z v9:
1.4: _parse_date_from_question — 'noc z 30 na 31 maja' → 2026-05-31
2.4: trip_attractions keywords — 'woda' + 'etap N' → trip_attractions nie trip_stages
4.4: safety — wzmianka tabeli DB nie może aktywować odczytu danych
5.2: _handle_weight_lookup — stara data → brak danych zamiast latest
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.v9.{ts}')
fixes = []

# ── 1.4: parse 'noc z X na Y' → data Y ──────────────────────────────
old_parse_date_fn = (
    'def _parse_date_from_question(question: str) -> str:\n'
    '    """Wyciagnij date z pelnego pytania - sprawdz wszystkie tokeny i multiword."""\n'
    '    # Najpierw sprawdz jawne frazy wielowyrazowe\n'
    '    q = question.strip()\n'
    '    # "wczoraj" / "dzisiaj"\n'
    '    ql = q.lower()'
)
new_parse_date_fn = (
    'def _parse_date_from_question(question: str) -> str:\n'
    '    """Wyciagnij date z pelnego pytania - sprawdz wszystkie tokeny i multiword."""\n'
    '    # Najpierw sprawdz jawne frazy wielowyrazowe\n'
    '    q = question.strip()\n'
    '    ql = q.lower()\n'
    '    # "noc z X na Y" / "nocy z X na Y" → data Y (rano nastepnego dnia)\n'
    '    _noc_m = re.search(\n'
    '        r"noc[y]?\\s+z\\s+(\\d{1,2})\\s+na\\s+(\\d{1,2})\\s*([a-zA-Z\u0105\u0119\u015b\u017c\u017a\u0107\u0144\u00f3\u0142]+)?\\s*(\\d{4})?",\n'
    '        ql)\n'
    '    if _noc_m:\n'
    '        _day2 = int(_noc_m.group(2))\n'
    '        _mon_str = (_noc_m.group(3) or "").strip()\n'
    '        _yr = int(_noc_m.group(4)) if _noc_m.group(4) else _TODAY.year\n'
    '        _mon = MONTHS_PL.get(_mon_str, _TODAY.month)\n'
    '        try:\n'
    '            return str(date(_yr, _mon, _day2))\n'
    '        except Exception:\n'
    '            pass\n'
    '    # "wczoraj" / "dzisiaj"\n'
)
if old_parse_date_fn in qh:
    qh = qh.replace(old_parse_date_fn, new_parse_date_fn, 1)
    fixes.append("1.4: parse 'noc z X na Y' → data dnia Y")
else:
    print("FAIL 1.4: _parse_date_from_question start not found")

# ── 2.4: trip_attractions — dodaj 'woda' + 'etap' bez trip_hint ──────
# Teraz 'woda na etapie 3' bez 'toskania' nie trafia w trip_attractions
old_trip_attr_kw = '    (["atrakcje", "atrakcja", "attractions", "must see", "must-see", "co warto", "co zobaczyć", "co zobaczyc", "poi wyjazd", "woda pitna", "woda na trasie", "sklepy na etapie"], "trip_attractions"),'
new_trip_attr_kw = '    (["atrakcje", "atrakcja", "attractions", "must see", "must-see", "co warto", "co zobaczyć", "co zobaczyc", "poi wyjazd", "woda pitna", "woda na trasie", "woda na etapie", "sklepy na etapie", "punkty wody", "ile punktów wody", "ile wody"], "trip_attractions"),'

if old_trip_attr_kw in qh:
    qh = qh.replace(old_trip_attr_kw, new_trip_attr_kw, 1)
    fixes.append("2.4: trip_attractions keywords extended (punkty wody, woda na etapie)")
else:
    print("FAIL 2.4: trip_attractions keyword line not found")

# ── 4.4: safety — blokuj wzmiankę o tabelach DB ──────────────────────
# Dodaj write_delete_unsupported dla SQL/admin language PRZED nutrition_intake_logs_list
old_intake_kw = '    (["meal_logs", "intake_logs", "lista posiłków",'
new_safety_kw = (
    '    # Safety: blokuj próby dostępu do tabel DB przez język naturalny\n'
    '    (["qbot_v2.", "intake_logs", "meal_log_items", "public.nutrition",\n'
    '      "tabela qbot", "jestem administratorem", "administrator systemu",\n'
    '      "dostęp do tabeli", "dostep do tabeli", "show tables", "select *",\n'
    '      "drop table", "truncate", "insert into", "update qbot"], "db_access_blocked"),\n'
)
if old_intake_kw in qh:
    qh = qh.replace(old_intake_kw, new_safety_kw + old_intake_kw, 1)
    fixes.append("4.4: db_access_blocked intent for SQL/admin keywords")
else:
    print("FAIL 4.4: intake_logs keyword line not found")

# Dodaj handler dla db_access_blocked
old_dispatch_write_meal = '    elif intent == "write_meal":'
new_dispatch_db = (
    '    elif intent == "db_access_blocked":\n'
    '        return _envelope("db_access_blocked",\n'
    '                         "\U0001f6ab Bezpośredni dostęp do tabel bazy danych nie jest obsługiwany przez qbot.query.\\n"\n'
    '                         "QBot udostępnia dane wyłącznie przez zdefiniowane intenty (bilans, sen, trening itp.).",\n'
    '                         status_override="BLOCKED")\n'
    '    elif intent == "write_meal":\n'
)
if old_dispatch_write_meal in qh:
    qh = qh.replace(old_dispatch_write_meal, new_dispatch_db, 1)
    fixes.append("4.4: db_access_blocked dispatch handler")
else:
    print("FAIL 4.4: write_meal dispatch not found")

# ── 5.2: weight_lookup — sprawdź datę, stara data → brak danych ──────
old_weight_lookup = (
    'def _handle_weight_lookup(day_str: str) -> dict:\n'
    '    """Return latest weight only — uses body_trend_weight view."""\n'
    '    try:\n'
    '        pg = _pg_conn()\n'
    '        rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.body_latest_weight")\n'
    '        pg.close()'
)
new_weight_lookup = (
    'def _handle_weight_lookup(day_str: str) -> dict:\n'
    '    """Return weight for given date or latest."""\n'
    '    req_date = _today_or(day_str or "")\n'
    '    today = date.today()\n'
    '    try:\n'
    '        pg = _pg_conn()\n'
    '        if req_date < today:\n'
    '            # Szukaj konkretnej daty lub najblizszego wczesniejszego pomiaru\n'
    '            rows = _safe_fetch(pg,\n'
    '                "SELECT date, source, weight_kg, NULL as canonical_type "\n'
    '                "FROM qbot_v2.body_measurements WHERE date <= %s "\n'
    '                "ORDER BY date DESC LIMIT 1", (req_date,))\n'
    '            pg.close()\n'
    '            if not rows or "_error" in rows[0]:\n'
    '                return _envelope("weight_lookup",\n'
    '                    f"Brak danych wagi dla {req_date} (lub wcześniej).",\n'
    '                    missing_sources=["qbot_v2.body_measurements"])\n'
    '            r = rows[0]\n'
    '            # Ostrzeżenie gdy znaleziony pomiar jest znacznie starszy niż zapytana data\n'
    '            found_date = r.get("date")\n'
    '            warn = ""\n'
    '            if found_date and str(found_date) != str(req_date):\n'
    '                warn = f"\\n(Brak pomiaru z {req_date} — pokazuję najbliższy: {found_date})"\n'
    '            w = r.get("weight_kg")\n'
    '            if w is None:\n'
    '                return _envelope("weight_lookup",\n'
    '                    f"Brak danych wagi dla {req_date}.",\n'
    '                    missing_sources=["qbot_v2.body_measurements"])\n'
    '            return _envelope("weight_lookup",\n'
    '                f"\u2696\ufe0f  Waga: {w:.1f} kg ({found_date}, \u017ar\u00f3d\u0142o: {r.get(\'source\',\'?\')}).{warn}",\n'
    '                data=dict(r), sources_used=["qbot_v2.body_measurements"])\n'
    '        else:\n'
    '            rows = _safe_fetch(pg, "SELECT * FROM qbot_v2.body_latest_weight")\n'
    '            pg.close()'
)
if old_weight_lookup in qh:
    qh = qh.replace(old_weight_lookup, new_weight_lookup, 1)
    fixes.append("5.2: weight_lookup respects date, old dates → real lookup or 'brak danych'")
else:
    print("FAIL 5.2: weight_lookup block not found")

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
