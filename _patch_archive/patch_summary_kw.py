#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'longest stage' in l:
        lines[i] = l.rstrip() + '\n      "kt\u00f3ry etap jest najd\u0142u\u017cszy", "ktory etap jest najdluzszy",\n      "kt\u00f3ry etap jest najkr\u00f3tszy", "kt\u00f3ry etap jest najtrudniejszy",\n'
        print(f"OK: line {i+1} extended")
        break
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
