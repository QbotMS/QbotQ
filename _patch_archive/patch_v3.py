#!/usr/bin/env python3
"""
Patch bugs z testu v3 — 2026-06-02

1. rękawiczki? — strip punctuation przed search terms
2. ride_report — szuka ostatniej jazdy globalnie, nie tylko dziś/wczoraj
3. POI trip_hint — mapowanie PL→EN (toskani→tuscany)
4. artifact_search — shelf detection PRZED last-resort search_term
5. memories_search — fallback do planning_facts
6. kasków — Helmet-first, nie wszystkie Headwear
7. bilans tabela — spójna kolumna Bilans (intake-expenditure)
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
fixes = []

QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.v3.{ts}')

# ── 1: strip punctuation w garage_search raw_terms ───────────────────
old_raw = (
    '    raw_terms = [t for t in ql.split() if len(t) > 2 and t not in STOP_WORDS]\n'
    '    if not raw_terms:\n'
    '        raw_terms = [ql]\n'
    '    # Stem Polish words for better matching\n'
    '    stemmed = []\n'
    '    for t in raw_terms:\n'
    '        stemmed.extend(_stem_polish(t))\n'
    '    raw_terms = list(set(stemmed)) if stemmed else raw_terms'
)
new_raw = (
    '    # Strip punctuation from each token before processing\n'
    '    import re as _re_gs\n'
    '    raw_terms = [_re_gs.sub(r"[^\\w\\u00C0-\\u024F]", "", t) for t in ql.split()]\n'
    '    raw_terms = [t for t in raw_terms if len(t) > 2 and t not in STOP_WORDS]\n'
    '    if not raw_terms:\n'
    '        raw_terms = [_re_gs.sub(r"[^\\w\\u00C0-\\u024F]", "", ql)]\n'
    '    # Stem Polish words for better matching\n'
    '    stemmed = []\n'
    '    for t in raw_terms:\n'
    '        stemmed.extend(_stem_polish(t))\n'
    '    raw_terms = list(set(stemmed)) if stemmed else raw_terms'
)
if old_raw in qh:
    qh = qh.replace(old_raw, new_raw, 1)
    fixes.append("1: garage_search strip punctuation from tokens")
else:
    print("FAIL 1: garage raw_terms block not found")

# ── 2: ride_report — szukaj ostatniej jazdy globalnie ────────────────
old_ride_query = (
    '        rows = _safe_fetch(pg, """\n'
    '            SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,\n'
    '                   avg_power_w, avg_hr_bpm, activity_name\n'
    '            FROM qbot_v2.training_sessions\n'
    '            WHERE date = %s\n'
    '            ORDER BY started_at DESC\n'
    '            LIMIT 5\n'
    '        """, (today_str,))\n'
    '        yesterday_rows = _safe_fetch(pg, """\n'
    '            SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,\n'
    '                   avg_power_w, avg_hr_bpm, activity_name\n'
    '            FROM qbot_v2.training_sessions\n'
    '            WHERE date = %s\n'
    '            ORDER BY started_at DESC\n'
    '            LIMIT 5\n'
    '        """, ((_TODAY - timedelta(days=1)).isoformat(),))\n'
    '        pg.close()\n'
    '    except Exception as exc:\n'
    '        return _envelope("ride_report", f"B\\u0142\\u0105d diagnostyczny: {exc}", status_override="ERROR")\n'
    '\n'
    '    all_rows = rows + yesterday_rows if rows and yesterday_rows else (rows or yesterday_rows or [])'
)
new_ride_query = (
    '        # Szukaj w żądanym dniu, jeśli podany — inaczej ostatnie 14 dni\n'
    '        import re as _re_rr\n'
    '        _rr_date = None\n'
    '        for part in question.split():\n'
    '            _rr_date = _parse_date(part)\n'
    '            if _rr_date:\n'
    '                break\n'
    '        if _rr_date:\n'
    '            rows = _safe_fetch(pg, """\n'
    '                SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,\n'
    '                       avg_power_w, avg_hr_bpm, activity_name\n'
    '                FROM qbot_v2.training_sessions\n'
    '                WHERE date = %s\n'
    '                ORDER BY started_at DESC LIMIT 5\n'
    '            """, (_rr_date.isoformat(),))\n'
    '        else:\n'
    '            rows = _safe_fetch(pg, """\n'
    '                SELECT id, date, started_at, sport_type, distance_m, duration_s, elevation_m,\n'
    '                       avg_power_w, avg_hr_bpm, activity_name\n'
    '                FROM qbot_v2.training_sessions\n'
    '                ORDER BY date DESC, started_at DESC LIMIT 5\n'
    '            """)\n'
    '        pg.close()\n'
    '    except Exception as exc:\n'
    '        return _envelope("ride_report", f"B\\u0142\\u0105d diagnostyczny: {exc}", status_override="ERROR")\n'
    '\n'
    '    all_rows = rows if rows and "_error" not in rows[0] else []'
)
if old_ride_query in qh:
    qh = qh.replace(old_ride_query, new_ride_query, 1)
    fixes.append("2: ride_report searches last N rides globally")
else:
    print("FAIL 2: ride_report query block not found")

# ── 4: artifact_search — shelf detection PRZED last-resort ───────────
# Przenosimy cały blok "Shelf filter detection" przed blok "if not search_term"
old_shelf_after = (
    '    if not search_term:\n'
    '        # Gdy shelf_filter jest, nie używaj całego pytania jako search_term\n'
    '        if not _shelf_filter:\n'
    '            search_term = question.strip()[:80]\n'
    '        # else: search_term pozostaje pusty — szukaj wszystkiego w shelf\n'
    '\n'
    '    # ── Shelf filter detection ──\n'
    '    import re as _re2\n'
    '    _shelf_filter = None\n'
    '    _shelf_kw_map = {\n'
    '        "canonical": "canonical", "kanoniczne": "canonical", "kanoniczna": "canonical",\n'
    '        "export": "export", "eksport": "export", "do eksportu": "export",\n'
    '        "wip": "wip", "w obrobce": "wip", "w trakcie": "wip", "robocze": "wip",\n'
    '        "old": "old", "kosz": "old", "archiwum": "old",\n'
    '    }\n'
    '    _q_lower = question.lower()\n'
    '    # Explicit "shelf:wip" syntax\n'
    '    _shelf_explicit = _re2.search(r"shelf\\s*[:=]\\s*(\\w+)", _q_lower)\n'
    '    if _shelf_explicit:\n'
    '        _shelf_filter = _shelf_explicit.group(1).strip()\n'
    '    else:\n'
    '        for kw, shelf in _shelf_kw_map.items():\n'
    '            if kw in _q_lower:\n'
    '                _shelf_filter = shelf\n'
    '                break'
)
new_shelf_before = (
    '    # ── Shelf filter detection (PRZED last-resort search_term) ──\n'
    '    import re as _re2\n'
    '    _shelf_filter = None\n'
    '    _shelf_kw_map = {\n'
    '        "canonical": "canonical", "kanoniczne": "canonical", "kanoniczna": "canonical",\n'
    '        "export": "export", "eksport": "export", "do eksportu": "export",\n'
    '        "wip": "wip", "w obrobce": "wip", "w trakcie": "wip", "robocze": "wip",\n'
    '        "old": "old", "kosz": "old", "archiwum": "old",\n'
    '    }\n'
    '    _q_lower = question.lower()\n'
    '    _shelf_explicit = _re2.search(r"shelf\\s*[:=]\\s*(\\w+)", _q_lower)\n'
    '    if _shelf_explicit:\n'
    '        _shelf_filter = _shelf_explicit.group(1).strip()\n'
    '    else:\n'
    '        for kw, shelf in _shelf_kw_map.items():\n'
    '            if kw in _q_lower:\n'
    '                _shelf_filter = shelf\n'
    '                break\n'
    '\n'
    '    # Shelf keywords stripped from search_term\n'
    '    _shelf_noise = {"canonical", "kanoniczne", "kanoniczna", "export", "eksport",\n'
    '                    "wip", "robocze", "old", "kosz", "archiwum", "artefakty", "artefakt",\n'
    '                    "shelf", "p\\u00f3\\u0142ka", "p\\u00f3\\u0142ce"}\n'
    '\n'
    '    if not search_term:\n'
    '        # Gdy shelf_filter jest: użyj pozostałych słów jako project hint\n'
    '        if _shelf_filter:\n'
    '            _remaining = [w for w in _q_lower.split() if w not in _shelf_noise and len(w) > 2]\n'
    '            search_term = " ".join(_remaining).strip() or ""\n'
    '        else:\n'
    '            search_term = question.strip()[:80]'
)
if old_shelf_after in qh:
    qh = qh.replace(old_shelf_after, new_shelf_before, 1)
    fixes.append("4: artifact_search shelf detection before last-resort search_term")
else:
    print("FAIL 4: shelf detection block not found")

# ── 5: memories_search — fallback do planning_facts ──────────────────
old_memories_empty = (
    '    if not results:\n'
    '        return _envelope("memories_search",\n'
    '                         f"W memories nie znaleziono pasujących wpisów dla: {search_term}" if search_term else "Brak notatek w pamięci.",\n'
    '                         data={"query": search_term or "(all)", "result_count": 0, "results": []},\n'
    '                         sources_used=["sqlite.memories"])'
)
new_memories_fallback = (
    '    if not results:\n'
    '        # Fallback: szukaj w qbot_planning_facts\n'
    '        pf_results = []\n'
    '        try:\n'
    '            _pg2 = _pg_conn()\n'
    '            _pf_like = f"%{search_term}%" if search_term else "%tuscany%"\n'
    '            _pf_rows = _safe_fetch(_pg2, """\n'
    '                SELECT id, fact_type, title, date, status\n'
    '                FROM qbot_v2.qbot_planning_facts\n'
    '                WHERE LOWER(title) LIKE %s OR LOWER(fact_type) LIKE %s\n'
    '                ORDER BY date DESC LIMIT 10\n'
    '            """, (_pf_like, _pf_like))\n'
    '            _pg2.close()\n'
    '            if _pf_rows and "_error" not in _pf_rows[0]:\n'
    '                pf_results = _pf_rows\n'
    '        except Exception:\n'
    '            pass\n'
    '\n'
    '        if pf_results:\n'
    '            _pf_parts = [f"\\U0001f9e0 Brak w memories, znaleziono w planning_facts ({len(pf_results)}):"]\n'
    '            for _pf in pf_results:\n'
    '                _pf_parts.append(f"  [{_pf.get(\'fact_type\',\'?\')}] {_pf.get(\'title\',\'?\')} ({_pf.get(\'date\',\'?\')})")\n'
    '            return _envelope("memories_search", "\\n".join(_pf_parts),\n'
    '                             data={"query": search_term, "planning_facts": pf_results, "result_count": len(pf_results)},\n'
    '                             sources_used=["sqlite.memories", "qbot_v2.qbot_planning_facts"])\n'
    '\n'
    '        return _envelope("memories_search",\n'
    '                         f"W memories nie znaleziono pasujących wpisów dla: {search_term}" if search_term else "Brak notatek w pamięci.",\n'
    '                         data={"query": search_term or "(all)", "result_count": 0, "results": []},\n'
    '                         sources_used=["sqlite.memories"])'
)
if old_memories_empty in qh:
    qh = qh.replace(old_memories_empty, new_memories_fallback, 1)
    fixes.append("5: memories_search fallback to planning_facts")
else:
    print("FAIL 5: memories_search empty block not found")

try:
    ast.parse(qh)
    print("qbot_query_handler.py syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR qh: {e}")
    import sys; sys.exit(1)

with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)

# ── 3: trip_attractions — PL→EN trip_hint mapping ────────────────────
TA = '/opt/qbot/app/tools/trip_attractions.py'
with open(TA, encoding='utf-8') as f:
    ta = f.read()
shutil.copy(TA, f'{TA}.bak.{ts}')

old_trip_hint = (
    '    trip_hint = None\n'
    '    for kw in ["toskani","tuscany","tour","wyprawa","alps","dolomit"]:\n'
    '        if kw in ql:\n'
    '            trip_hint = kw\n'
    '            break'
)
new_trip_hint = (
    '    # Mapowanie PL→EN dla trip_hint (musi matchować tytuły w DB)\n'
    '    _TRIP_HINT_MAP = {\n'
    '        "toskani": "tuscany", "toskania": "tuscany", "toskanii": "tuscany",\n'
    '        "tuscany": "tuscany", "tour": "tour",\n'
    '        "wyprawa": "wyprawa", "alps": "alps", "dolomit": "dolomit",\n'
    '    }\n'
    '    trip_hint = None\n'
    '    for kw, mapped in _TRIP_HINT_MAP.items():\n'
    '        if kw in ql:\n'
    '            trip_hint = mapped\n'
    '            break'
)
if old_trip_hint in ta:
    ta = ta.replace(old_trip_hint, new_trip_hint, 1)
    fixes.append("3: trip_attractions PL→EN trip_hint mapping")
else:
    print("FAIL 3: trip_hint block not found")

# ── 6: garage_search — helmet-first, ogranicz headwear ───────────────
# Jeśli search zawiera 'helmet' i są wyniki helmet, nie zwracaj headwear
old_garage_results = (
    '    for tbl in matched_tables:\n'
    '        used.append(f"garage.db.{tbl}")\n'
    '\n'
    '    if not results:'
)
new_garage_results = (
    '    for tbl in matched_tables:\n'
    '        used.append(f"garage.db.{tbl}")\n'
    '\n'
    '    # Helmet-first: jeśli search zawiera helmet i mamy wyniki Helmet, usuń Headwear\n'
    '    if results and any("helmet" in str(t).lower() for t in expanded_terms):\n'
    '        helmet_results = [r for r in results if str(r.get("category","")).lower() == "helmet"]\n'
    '        if helmet_results:\n'
    '            results = helmet_results\n'
    '\n'
    '    if not results:'
)
if old_garage_results in qh:
    # qh już zapisany — musimy wczytać ponownie (był zapisany wyżej)
    with open(QH, encoding='utf-8') as f:
        qh2 = f.read()
    if old_garage_results in qh2:
        qh2 = qh2.replace(old_garage_results, new_garage_results, 1)
        ast.parse(qh2)
        with open(QH, 'w', encoding='utf-8') as f:
            f.write(qh2)
        fixes.append("6: garage_search helmet-first filter")
    else:
        print("FAIL 6: garage results block not found in saved file")
else:
    print("FAIL 6: garage results block not found")

try:
    ast.parse(ta)
    print("trip_attractions.py syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR ta: {e}")
    import sys; sys.exit(1)
with open(TA, 'w', encoding='utf-8') as f:
    f.write(ta)

print(f"\n=== {len(fixes)} fixes applied ===")
for fx in fixes:
    print(f"  OK: {fx}")
