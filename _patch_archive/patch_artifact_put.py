#!/usr/bin/env python3
"""Fix qbot_artifact_put — przyjmuj content (plain text) obok content_base64."""
import ast, shutil, datetime

ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
MA = '/opt/qbot/app/qbot3/adapters/mcp_adapter.py'
with open(MA, encoding='utf-8') as f:
    ma = f.read()
shutil.copy(MA, f'{MA}.bak.artput.{ts}')

old = (
    '    filename = str(payload.get("filename", "")).strip()\n'
    '    mime_type = str(payload.get("mime_type", "")).strip()\n'
    '    content_b64 = payload.get("content_base64", "")\n'
)
new = (
    '    filename = str(payload.get("filename", "")).strip()\n'
    '    mime_type = str(payload.get("mime_type", "")).strip()\n'
    '    # Akceptuj content (plain text) i sam koduj do base64\n'
    '    content_b64 = payload.get("content_base64", "")\n'
    '    if not content_b64 and payload.get("content"):\n'
    '        import base64 as _b64\n'
    '        content_b64 = _b64.b64encode(str(payload["content"]).encode("utf-8")).decode("ascii")\n'
    '        if not mime_type:\n'
    '            mime_type = "text/markdown"\n'
)
if old in ma:
    ma = ma.replace(old, new, 1)
    print("OK: content plain text support added")
else:
    print("FAIL: block not found")
    import sys; sys.exit(1)

# Też usuń wymóg mime_type jeśli filename kończy się na .md
old_check = '    if not project_id or not filename or not mime_type or not content_b64:'
new_check = (
    '    # Zgadnij mime_type z rozszerzenia jeśli nie podany\n'
    '    if not mime_type:\n'
    '        _ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""\n'
    '        mime_type = {"md": "text/markdown", "txt": "text/plain",\n'
    '                     "json": "application/json", "gpx": "application/gpx+xml",\n'
    '                     "html": "text/html"}.get(_ext, "text/plain")\n'
    '    if not project_id or not filename or not content_b64:\n'
)
if old_check in ma:
    ma = ma.replace(old_check, new_check, 1)
    print("OK: mime_type auto-detect from extension")
else:
    print("FAIL: check block not found")

ast.parse(ma)
with open(MA, 'w', encoding='utf-8') as f:
    f.write(ma)
print("syntax OK")
