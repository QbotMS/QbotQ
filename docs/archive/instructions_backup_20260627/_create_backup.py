#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/opt/qbot/app')
ARCHIVE = ROOT / 'docs/archive/instructions_backup_20260627'
FILES = [
    'AGENTS.md',
    'QBOT_INSTRUCTIONS.md',
    'PROJECT_STATE.md',
    'QBOT_CURRENT_STATE.md',
    'docs/CONTEXT.md',
    'scripts/build_context.py',
    'docs/architecture/QBOT_ARCHITEKTURA_V2.md',
]

created = []
missing = []
for rel in FILES:
    src = ROOT / rel
    dst = ARCHIVE / rel
    if not src.exists():
        missing.append(rel)
        continue
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    created.append(rel)

manifest = ARCHIVE / 'MANIFEST.txt'
manifest.write_text(
    'QBot instruction backup 2026-06-27\n'
    'Source root: /opt/qbot/app\n\n'
    'Created files:\n'
    + ''.join(f'- {p}\n' for p in created)
    + ('\nMissing files:\n' + ''.join(f'- {p}\n' for p in missing) if missing else '\nMissing files: none\n'),
    encoding='utf-8',
)

print('CREATED')
for p in created:
    print(p)
if missing:
    print('MISSING')
    for p in missing:
        print(p)
