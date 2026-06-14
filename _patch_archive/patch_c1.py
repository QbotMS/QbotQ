#!/usr/bin/env python3
"""C1: dodaj _normalize_question i wywołanie w handle_query."""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.c1.{ts}')

# Wstaw normalizer przed handle_query
old_def = 'def handle_query(question: str, context: dict | None = None) -> dict:\n    ql = question.lower().strip()\n    intent = _resolve_intent(question)'
new_def = (
    'def _normalize_question(q: str) -> str:\n'
    '    """Normalizuj wejscie: etap4->etap 4, stage3->stage 3, 30d->30 dni."""\n'
    '    import re as _re_n\n'
    '    q = _re_n.sub(r"etap([0-9]+)", r"etap \\1", q)\n'
    '    q = _re_n.sub(r"\\bstage([0-9]+)\\b", r"stage \\1", q)\n'
    '    q = _re_n.sub(r"\\b([0-9]+)d\\b", r"\\1 dni", q)\n'
    '    return q\n'
    '\n'
    '\n'
    'def handle_query(question: str, context: dict | None = None) -> dict:\n'
    '    question = _normalize_question(question)\n'
    '    ql = question.lower().strip()\n'
    '    intent = _resolve_intent(question)'
)

if old_def in qh:
    qh = qh.replace(old_def, new_def, 1)
    ast.parse(qh)
    with open(QH, 'w', encoding='utf-8') as f:
        f.write(qh)
    print("OK C1: _normalize_question added, syntax OK")
else:
    print("FAIL: exact block not found")
    idx = qh.find('def handle_query')
    print("Context:", repr(qh[idx:idx+120]))
