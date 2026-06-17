#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot3/adapters/mcp_adapter.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'rel_dir = f' in l and 'shelf' in l and 'project_id' in l and 'subdir' in l:
        lines[i] = (
            '    _eff_sub = subdir if (subdir and subdir != shelf) else "files"\n'
            '    rel_dir = f"{shelf}/{project_id}/{_eff_sub}"\n'
        )
        print(f"OK: line {i+1} fixed -> {lines[i].strip()}")
        break
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot3/adapters/mcp_adapter.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
