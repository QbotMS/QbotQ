#!/usr/bin/env python3
"""Reczne wymuszenie analizy trasy Komoot - dokladnie to, co robi przycisk "Analizuj"
w Telegramie (komoot_analyze_worker.py w tle, wynik sam idzie na Telegram).

  .venv/bin/python3 scripts/komoot_analyze_bg.py <tour_id> [--atrakcje]
Wraca od razu; log: /opt/qbot/logs/komoot_analyze.log
"""
import os
import subprocess
import sys

APP = "/opt/qbot/app"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or not args[0].isdigit():
        print("Uzycie: komoot_analyze_bg.py <tour_id (cyfry)> [--atrakcje]")
        return 2
    cmd = [os.path.join(APP, ".venv/bin/python3"), os.path.join(APP, "scripts/komoot_analyze_worker.py"), args[0]]
    if "--atrakcje" in sys.argv:
        cmd.append("--atrakcje")
    with open(os.devnull, "rb") as dn, open(os.devnull, "wb") as out:
        p = subprocess.Popen(cmd, cwd=APP, stdin=dn, stdout=out, stderr=out, start_new_session=True, close_fds=True)
    print(f"analiza w tle, pid={p.pid}: {' '.join(cmd[1:])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
