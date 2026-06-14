#!/usr/bin/env python3
import ast
lines = open('/opt/qbot/app/qbot_query_handler.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if '"podjazdy"' in l and 'route_climbs' in l:
        inject = (
            '    (["trasy rwgps", "moje trasy rwgps", "ostatnie trasy", "nowe trasy rwgps",\n'
            '      "trasy z ostatniego", "trasy u\u0142o\u017cone", "historia tras", "trasy w rwgps",\n'
            '      "co uk\u0142ada\u0142em", "co tworzy\u0142em w rwgps"], "rwgps_recent_routes"),\n'
        )
        lines.insert(i, inject)
        print(f"OK: keyword inserted before line {i+1}")
        break
content = ''.join(lines)
ast.parse(content)
open('/opt/qbot/app/qbot_query_handler.py', 'w', encoding='utf-8').write(content)
print("syntax OK")
