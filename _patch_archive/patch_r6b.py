#!/usr/bin/env python3
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
QH = '/opt/qbot/app/qbot_query_handler.py'
with open(QH, encoding='utf-8') as f:
    qh = f.read()
shutil.copy(QH, f'{QH}.bak.r6.{ts}')

old = (
    '    # \u2500\u2500 Method 1: Try search_artifacts() from artifact store module \u2500\u2500\n'
    '    all_artifacts = []\n'
    '    store_unavailable = False\n'
    '    try:\n'
    '        from qbot3.artifacts.store import search_artifacts\n'
    '        all_artifacts = search_artifacts(query=search_term, limit=50)\n'
    '    except ImportError:\n'
    '        store_unavailable = True\n'
)
new = (
    '    # \u2500\u2500 Method 1: Try search_artifacts() from artifact store module \u2500\u2500\n'
    '    # Gdy shelf_filter ustawiony: pomi\u0144 Method 1 \u2014 nie obs\u0142uguje shelf filter\n'
    '    all_artifacts = []\n'
    '    store_unavailable = bool(_shelf_filter)\n'
    '    if not store_unavailable:\n'
    '        try:\n'
    '            from qbot3.artifacts.store import search_artifacts\n'
    '            all_artifacts = search_artifacts(query=search_term, limit=50)\n'
    '        except ImportError:\n'
    '            store_unavailable = True\n'
)

if old in qh:
    qh = qh.replace(old, new, 1)
    ast.parse(qh)
    with open(QH, 'w', encoding='utf-8') as f:
        f.write(qh)
    print('OK: Method 1 skipped when shelf_filter set, syntax OK')
else:
    print('FAIL: Method 1 block not found')
    # debug
    idx = qh.find('Method 1: Try search_artifacts')
    print('idx:', idx)
    print('context:', repr(qh[idx-5:idx+200]))
