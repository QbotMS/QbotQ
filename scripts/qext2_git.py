#!/usr/bin/env python3
"""Commit i push repozytorium QExt2 (/opt/qbot/qext2_deploy) jako qbot -- bez roota i bez ssh q.

Od 2026-10-20 (sesja devmcp-2010) logowanie na serwer jako root wymaga Touch ID Michala,
wiec sesje AI nie moga juz pushowac QExt2 przez `ssh q`. Ten skrypt uzywa osobnego klucza
deploy (tylko repo QbotMS/QExt2, prawo zapisu), nalezacego do uzytkownika qbot:
  /opt/qbot/.ssh-qext2/id_ed25519  (+ known_hosts z kluczem GitHuba)

Uzycie (jedna linia):
  .venv/bin/python3 scripts/qext2_git.py status
  .venv/bin/python3 scripts/qext2_git.py commit --sesja <nazwa> --msg "<opis>" <pliki...>   (albo --all)
  .venv/bin/python3 scripts/qext2_git.py push
  .venv/bin/python3 scripts/qext2_git.py commit --sesja <nazwa> --msg "<opis>" --all --push
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

REPO = "/opt/qbot/qext2_deploy"
KEY_DIR = "/opt/qbot/.ssh-qext2"
REMOTE = "git@github.com:QbotMS/QExt2.git"
BRANCH = "main"
GIT = ["git", "-C", REPO, "-c", "safe.directory=" + REPO,
       "-c", "user.name=qbot", "-c", "user.email=qbot@olga181.mikrus.xyz"]


def run(args, env=None, timeout=180):
    p = subprocess.run(GIT + args, capture_output=True, text=True, env=env, timeout=timeout)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def push() -> int:
    key = os.path.join(KEY_DIR, "id_ed25519")
    kh = os.path.join(KEY_DIR, "known_hosts")
    if not os.path.exists(key):
        print("BLAD: brak klucza deploy %s -- poproś Michala o konfiguracje (DECISIONS 2026-10-20)." % key)
        return 2
    env = dict(os.environ)
    env["GIT_SSH_COMMAND"] = ("ssh -i %s -o IdentitiesOnly=yes -o UserKnownHostsFile=%s "
                              "-o StrictHostKeyChecking=yes -o BatchMode=yes" % (key, kh))
    rc, out = run(["push", REMOTE, "HEAD:" + BRANCH], env=env)
    print(out)
    if rc == 0:
        run(["update-ref", "refs/remotes/origin/" + BRANCH, "HEAD"])
        _, head = run(["log", "--oneline", "-1"])
        print("OK push: " + head)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("push")
    c = sub.add_parser("commit")
    c.add_argument("--sesja", required=True)
    c.add_argument("--msg", required=True)
    c.add_argument("--all", action="store_true")
    c.add_argument("--push", action="store_true")
    c.add_argument("files", nargs="*")
    a = ap.parse_args()

    if a.cmd == "status":
        rc, out = run(["status", "--short", "--branch"])
        print(out)
        _, log = run(["log", "--oneline", "-5"])
        print(log)
        return rc
    if a.cmd == "push":
        return push()

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
    else:
        rc, out = run(["commit", "-m", a.msg.strip() + "\n\nSesja: " + a.sesja.strip()])
        print(out)
        if rc:
            return rc
    return push() if a.push else 0


if __name__ == "__main__":
    sys.exit(main())
