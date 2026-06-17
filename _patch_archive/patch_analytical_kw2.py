#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if '"lepszy ni\u017c", "gorszy ni\u017c",' in l:
        lines[i] = l.rstrip() + '\n        "lepszy od", "gorszy od", "czy m\u00f3j sen", "czy spa\u0142em lepiej",\n'
        print(f"OK line {i+1}")
        break
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
