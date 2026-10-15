#!/usr/bin/env python3
"""Sprzatanie kopii .bak / _tmp_ -> archiwum (NIC nie kasuje).

Domyslnie TYLKO podglad (dry-run). --apply przenosi pliki do
/opt/qbot/_archiwum/<data>/ z zachowaniem sciezek wzgledem /opt/qbot.

Reguly:
- kandydaci: nazwa zawiera '.bak' lub zaczyna sie od 'bak_' / '_tmp_', albo konczy '.orig'
  (+ __pycache__/*.pyc od takich plikow)
- pomijane: pliki sledzone przez git, zmienione w ostatnich --keep-hours (domyslnie 48 h),
  katalogi, .venv/.git/node_modules, katalogi archiwalne (_bak_archive, docs/archive)
- data/garage.db.bak*: zostaje NAJNOWSZA kopia
- lista ruchow -> /opt/qbot/artifacts/cleanup_bak_<data>.txt
"""
import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import time

BASE = "/opt/qbot"
ROOTS = ["/opt/qbot/app", "/opt/qbot/web/public"]
SKIP_DIRS = {".venv", ".git", "node_modules", "_bak_archive", "archive"}


def is_candidate(name):
    if name.endswith(".pyc"):
        return ".bak" in name or name.startswith("_tmp_")
    return (".bak" in name or name.startswith("bak_") or name.startswith("_tmp_")
            or name.endswith(".orig"))


def git_tracked():
    try:
        out = subprocess.run(["git", "-C", "/opt/qbot/app", "-c", "safe.directory=/opt/qbot/app",
                              "ls-files"], capture_output=True, text=True, timeout=20).stdout
        return {os.path.join("/opt/qbot/app", p) for p in out.splitlines()}
    except Exception as e:  # noqa
        print("UWAGA: git ls-files nie dziala:", e)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep-hours", type=float, default=48)
    a = ap.parse_args()

    today = dt.date.today().isoformat()
    dest_root = os.path.join(BASE, "_archiwum", today)
    tracked = git_tracked()
    if tracked is None:
        sys.exit("STOP: brak listy plikow gita - nie ruszam niczego")
    now = time.time()
    cand, skip_recent, skip_git = [], [], []
    garage = []
    for root in ROOTS:
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                if not is_candidate(fn):
                    continue
                p = os.path.join(dp, fn)
                if os.path.islink(p):
                    continue
                if p in tracked:
                    skip_git.append(p)
                    continue
                if fn.startswith("garage.db.bak"):
                    garage.append(p)
                    continue
                if now - os.path.getmtime(p) < a.keep_hours * 3600:
                    skip_recent.append(p)
                    continue
                cand.append(p)
    if garage:
        garage.sort(key=os.path.getmtime)
        skip_recent.append(garage[-1] + "  (najnowsza kopia garage.db - zostaje)")
        cand.extend(garage[:-1])

    size = sum(os.path.getsize(p) for p in cand)
    lines = [f"# cleanup_bak {dt.datetime.now():%d.%m.%Y %H:%M}  tryb={'APPLY' if a.apply else 'PODGLAD'}",
             f"do archiwum: {len(cand)} plikow, {size/1e6:.1f} MB -> {dest_root}",
             f"zostaja (swieze < {a.keep_hours:g} h): {len(skip_recent)}",
             f"zostaja (sledzone przez git - do decyzji): {len(skip_git)}", ""]
    by_dir = {}
    for p in cand:
        by_dir.setdefault(os.path.dirname(p), 0)
        by_dir[os.path.dirname(p)] += 1
    lines.append("## wg katalogu")
    lines += [f"{n:5d}  {d}" for d, n in sorted(by_dir.items(), key=lambda x: -x[1])]
    lines += ["", "## sledzone przez git"] + skip_git
    lines += ["", "## swieze (zostaja)"] + skip_recent
    lines += ["", "## do archiwum"] + sorted(cand)

    moved = 0
    if a.apply:
        os.makedirs(dest_root, exist_ok=True)
        os.chmod(os.path.join(BASE, "_archiwum"), 0o700)
        for p in cand:
            rel = os.path.relpath(p, BASE)
            d = os.path.join(dest_root, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.move(p, d)
            moved += 1
        lines.insert(1, f"PRZENIESIONO: {moved}")

    os.makedirs(os.path.join(BASE, "artifacts"), exist_ok=True)
    rep = os.path.join(BASE, "artifacts", f"cleanup_bak_{today}{'' if a.apply else '_podglad'}.txt")
    with open(rep, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:6 + len(by_dir) + 2]))
    print("raport:", rep)


if __name__ == "__main__":
    main()
