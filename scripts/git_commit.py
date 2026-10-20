#!/usr/bin/env python3
"""Commit wskazanych plikow do repo QBota jako biezacy uzytkownik (qbot).

Od 2026-10-20 kanal DEV MCP dziala jako qbot, wiec commit nie wymaga juz
runuser/roota. Skrypt NIGDY nie robi push (push robi Michal jako root).

Uzycie (jedna linia, bez znakow nowej linii):
  .venv/bin/python3 scripts/git_commit.py --sesja <nazwa> --msg "<opis>" <plik> [<plik> ...]
  --all  zamiast listy plikow: commit wszystkich zmian (git add -A)

Opis dostaje automatycznie ostatnia linie "Sesja: <nazwa>" (regula 18.10.2026).
"""
from __future__ import annotations

import argparse
import subprocess
import sys

REPO = "/opt/qbot/app"
GIT = ["git", "-C", REPO, "-c", "user.name=qbot",
       "-c", "user.email=qbot@olga181.mikrus.xyz"]


def run(args):
    p = subprocess.run(GIT + args, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sesja", required=True)
    ap.add_argument("--msg", required=True)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    if not a.all and not a.files:
        print("BLAD: podaj pliki albo --all")
        return 2
    rc, out = run(["add", "-A"] if a.all else ["add", "--"] + a.files)
    if rc:
        print("BLAD git add:\n" + out)
        return rc
    rc, _ = run(["diff", "--cached", "--quiet"])
    if rc == 0:
        print("Brak zmian do commita.")
        return 0
    msg = a.msg.strip() + "\n\nSesja: " + a.sesja.strip()
    rc, out = run(["commit", "-m", msg])
    print(out)
    if rc == 0:
        _, head = run(["log", "--oneline", "-1"])
        print("OK: " + head + "  (push: Michal, recznie)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
