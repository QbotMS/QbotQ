#!/usr/bin/env python3
import ast
content = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').read()
old = '        "lepszy ni\u017c", "gorszy ni\u017c",\n    ]'
new = '        "lepszy ni\u017c", "gorszy ni\u017c",\n        "lepszy od", "gorszy od",\n        "czy sp\u0105", "czy m\xf3j sen",\n    ]'
if old in content:
    content = content.replace(old, new, 1)
    ast.parse(content)
    open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
    print('OK')
else:
    print('FAIL')
