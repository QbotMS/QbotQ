#!/usr/bin/env python3
"""
Bug 4: artifact_search — canonical/wip/export w noise words extractora
Bug 5: memories — search_term z pytajnikiem, fallback nie szuka 'toscana'
"""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.v3b.{ts}')

# ── 4: dodaj shelf words do noise w extractor ─────────────────────────
old_noise = (
    '                        noise = {"store", "w", "na", "z", "po", "do", "QBot", "qbot", "i", "oraz", "the"}'
)
new_noise = (
    '                        noise = {"store", "w", "na", "z", "po", "do", "QBot", "qbot", "i", "oraz", "the",\n'
    '                                 "canonical", "kanoniczne", "export", "eksport", "wip", "robocze",\n'
    '                                 "artefakty", "artefakt", "p\\u00f3\\u0142ka", "shelf"}'
)
if old_noise in qh:
    qh = qh.replace(old_noise, new_noise, 1)
    print("OK 4a: shelf words in artifact extractor noise")
else:
    print("FAIL 4a: noise line not found")

# ── 5: memories — strip punctuation z search_term, lepszy fallback ────
# Problem: "toskanii?" → search ma "?", planning_facts szuka "%toskanii?%"
old_mem_fallback = (
    '        try:\n'
    '            _pg2 = _pg_conn()\n'
    '            _pf_like = f"%{search_term}%" if search_term else "%tuscany%"'
)
new_mem_fallback = (
    '        try:\n'
    '            _pg2 = _pg_conn()\n'
    '            import re as _re_mem\n'
    '            _st_clean = _re_mem.sub(r"[^\\w\\u00C0-\\u024F]", " ", search_term or "toskania").strip()\n'
    '            # Mapuj PL→EN dla tytułów w DB\n'
    '            _PL_EN = {"toskania": "tuscany", "toskanii": "tuscany", "toskani": "tuscany",\n'
    '                      "florencja": "florence"}\n'
    '            for _pl, _en in _PL_EN.items():\n'
    '                if _pl in _st_clean.lower():\n'
    '                    _st_clean = _en\n'
    '                    break\n'
    '            _pf_like = f"%{_st_clean}%" if _st_clean else "%tuscany%"'
)
if old_mem_fallback in qh:
    qh = qh.replace(old_mem_fallback, new_mem_fallback, 1)
    print("OK 5: memories fallback PL→EN + strip punct")
else:
    print("FAIL 5: memories fallback block not found")

ast.parse(qh)
with open(QH, 'w', encoding='utf-8') as f:
    f.write(qh)
print("syntax OK")
