#!/usr/bin/env python3
"""Fix E3: BLOCKED -> PARTIAL żeby OpenAI renderował odpowiedź."""
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'write_delete_unsupported' in l and 'status_override="BLOCKED"' in lines[i+2] if i+2 < len(lines) else False:
        lines[i+2] = '                         status_override="PARTIAL")\n'
        print(f"OK: line {i+3} BLOCKED->PARTIAL")
        break
    if 'write_delete_unsupported' in l and i+2 < len(lines):
        # Szukaj status_override w kolejnych liniach
        for j in range(i, min(i+5, len(lines))):
            if 'status_override="BLOCKED"' in lines[j]:
                lines[j] = lines[j].replace('status_override="BLOCKED"', 'status_override="PARTIAL"')
                print(f"OK: line {j+1} BLOCKED->PARTIAL for delete")
                break

content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
