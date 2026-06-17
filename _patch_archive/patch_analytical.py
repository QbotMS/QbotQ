#!/usr/bin/env python3
"""
Analytical fallback: gdy pytanie zawiera słowa analityczne (porównaj, najlepszy,
ile łącznie, średni, delta, trend, czy X lepszy niż Y) i intent jest prostym
readerem → przekieruj do Albert (orchestrate_query).

Intenty które NIE są przekierowywane (obsługują analitykę sami):
- trip_summary, route_climbs, route_feasibility, report_diagnostic
- artifact_search, artifact_read
- write_*, db_access_blocked, unrecognized, qbot_help
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.analytical.{ts}')

old_multi_intent_end = (
    '    day_str = _parse_date_from_question(question)\n'
    '\n'
    '    # If daily_balance or nutrition_day but query has range indicators → nutrition_range'
)
new_analytical_fallback = (
    '    # ── Analytical fallback → Albert ─────────────────────────────────────\n'
    '    # Gdy pytanie zawiera słowa analityczne a intent jest prostym readerem\n'
    '    _ANALYTICAL_WORDS = [\n'
    '        "najlepszy", "najgorszy", "najwyższy", "najniższy",\n'
    '        "najdłuższy dzień", "najkrótszy dzień",\n'
    '        "porównaj", "porównanie", "compare",\n'
    '        "ile łącznie", "łącznie za", "suma za", "razem za",\n'
    '        "średni", "średnia", "average",\n'
    '        "delta", "różnica między", "zmiana od",\n'
    '        "czy byłem", "czy jestem", "czy mój",\n'
    '        "kiedy miałem", "kiedy byłem",\n'
    '        "w którym dniu", "który dzień",\n'
    '        "ile schudłem", "ile przytyłem", "ile urosłem",\n'
    '        "przed czy po", "lepszy niż", "gorszy niż",\n'
    '    ]\n'
    '    _ANALYTICAL_INTENTS_EXEMPT = {\n'
    '        # Te intenty mają własną analitykę — nie przekierowuj\n'
    '        "trip_summary", "route_climbs", "route_feasibility",\n'
    '        "report_diagnostic", "ride_report", "daily_report",\n'
    '        "artifact_search", "artifact_read",\n'
    '        "write_meal", "write_delete_unsupported", "write_planning_unsupported",\n'
    '        "write_weight_unsupported", "db_access_blocked",\n'
    '        "unrecognized", "qbot_help", "action_execute",\n'
    '        "body_measurements_range", "nutrition_range", "training_recent",\n'
    '        "weight_trend",\n'
    '    }\n'
    '    _ql_analytical = question.lower()\n'
    '    _is_analytical = any(w in _ql_analytical for w in _ANALYTICAL_WORDS)\n'
    '    _albert_enabled = __import__("os").getenv("QBOT3_ENABLED") == "1"\n'
    '    if _is_analytical and intent not in _ANALYTICAL_INTENTS_EXEMPT and _albert_enabled:\n'
    '        try:\n'
    '            from qbot3.agent_runtime import orchestrate_query\n'
    '            _albert_result = orchestrate_query(question=question)\n'
    '            _albert_result["fallback_reason"] = f"analytical_fallback (intent={intent})"\n'
    '            return _albert_result\n'
    '        except Exception as _exc:\n'
    '            # Albert niedostępny — kontynuuj deterministycznie\n'
    '            pass\n'
    '\n'
    '    day_str = _parse_date_from_question(question)\n'
    '\n'
    '    # If daily_balance or nutrition_day but query has range indicators → nutrition_range'
)
if old_multi_intent_end in qh:
    qh = qh.replace(old_multi_intent_end, new_analytical_fallback, 1)
    print("OK: analytical fallback inserted")
else:
    print("FAIL: block not found")
    import sys; sys.exit(1)

ast.parse(qh)
with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)
print("syntax OK")
