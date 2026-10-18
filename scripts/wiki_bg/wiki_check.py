#!/usr/bin/env python3
"""Ktore hasla wiki opisuja zmieniony kod (pole zrodla_kodu w metaznacznikach -> docs/wiki/_indeks.json).

  wiki_check.py --staged           (hook pre-commit) ostrzega: zmieniasz plik opisany w hasle X, a hasla nie poprawiasz
  wiki_check.py --date RRRR-MM-DD  lista hasel do aktualizacji po zmianach kodu z danego dnia (commity + niezapisane), JSON
2026-10-18, decyzja Michala: wiki ma sie aktualizowac przy kazdej pracy nad serwisem."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from datetime import date, datetime

APP = "/opt/qbot/app"
IDX = f"{APP}/docs/wiki/_indeks.json"
G = ["git", "-c", f"safe.directory={APP}", "-C", APP]
KOD = (".py", ".js", ".html", ".css", ".sql", ".kt", ".service", ".timer")


def _code(paths):
    return [p for p in paths if p.endswith(KOD) and not p.startswith(("docs/", "tests/", "archive/", "scripts/wiki_bg/", "web_public/wiki-")) and ".bak" not in p and "/_tmp" not in p and not os.path.basename(p).startswith("_tmp")]


def _idx():
    try:
        return json.load(open(IDX, encoding="utf-8")).get("hasla", [])
    except Exception:
        return []


def entries_for(code_files):
    """{haslo_path: [pliki kodu]} -- dopasowanie po nazwie pliku w zrodla_kodu (np. 'fitmodel/load_guard.py' albo 'load_guard.py:funkcja')."""
    out = {}
    names = {p: os.path.basename(p) for p in code_files}
    for h in _idx():
        src = " ".join(h.get("zrodla_kodu") or [])
        for p, n in names.items():
            stem = n.rsplit(".", 1)[0]
            if p in src or re.search(r"(^|[\s/`'\"(\[])" + re.escape(n) + r"($|[\s:`'\")\],])", src) or (len(stem) > 6 and stem in src):
                out.setdefault("docs/wiki/" + h["p"], []).append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--date")
    a = ap.parse_args()
    if a.staged:
        staged = [p for p in subprocess.run(G + ["diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.splitlines() if p]
        hit = entries_for(_code(staged))
        brak = {h: f for h, f in hit.items() if h not in staged}
        if brak:
            print("\n[WIKI] Zmieniasz kod opisany w wiki, a hasla nie sa w tym commicie (popraw je albo zrobi to nocna aktualizacja 23:50):", file=sys.stderr)
            for h, f in sorted(brak.items())[:15]:
                print(f"  - {h}  <- {', '.join(sorted(set(f)))}", file=sys.stderr)
        return
    d = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else date.today()
    raw = subprocess.run(G + ["log", f"--since={d:%Y-%m-%d} 00:00", f"--until={d:%Y-%m-%d} 23:59:59", "--name-only", "--format="], capture_output=True, text=True).stdout
    changed = {p for p in raw.splitlines() if p}
    for ln in subprocess.run(G + ["status", "--porcelain"], capture_output=True, text=True).stdout.splitlines():
        p = ln[3:].strip(); fp = os.path.join(APP, p)
        if os.path.isfile(fp) and datetime.fromtimestamp(os.path.getmtime(fp)).date() == d:
            changed.add(p)
    code = _code(sorted(changed))
    wiki_changed = {p for p in changed if p.startswith("docs/wiki/")}
    hit = entries_for(code)
    todo = {h: sorted(set(f)) for h, f in hit.items() if h not in wiki_changed}
    nowe = [p for p in code if not any(p in fs for fs in hit.values())]
    print(json.dumps({"data": f"{d:%Y-%m-%d}", "kod_zmieniony": code, "hasla_do_aktualizacji": todo, "kod_bez_hasla": nowe}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
