#!/usr/bin/env python3
"""Audyt etap 3: graf importow -> moduly rdzenia nieosiagalne z punktow startowych (kandydaci na martwy kod).
Tylko odczyt. Wynik: docs/audit/martwy_kod_<data>.md
Punkty startowe: ExecStart uslug qbot*, pliki wykonywalne w katalogu glownym (cron root), wszystkie scripts/*.py i tests/*.py
(narzedzia/testy traktujemy jako zywe korzenie -- osobna lista skryptow nieuzywanych).
Import = AST (import/from) + napisy w kodzie rowne nazwie modulu (importlib, uvicorn "mod:app")."""
import ast, datetime, os, re, subprocess, sys

APP = "/opt/qbot/app"
SKIP = {".venv", ".git", "_bak_archive", "archive", "node_modules", "__pycache__", "web_public", "web_landing",
        ".ms-playwright", ".aider.tags.cache.v4", "data", "logs", "outgoing", "state", "artifacts"}
UNITS = ["qbot-api", "qbot-web", "qbot-mcp-bridge", "qbot-dev-mcp", "qbot-qlab-server", "qbot-backup", "qbot-garmin-watch",
         "qbot-guest-forecast", "qbot-komoot-watch", "qbot-nutrition-watchdog"]

files = {}  # modname -> path
for dp, dns, fns in os.walk(APP):
    dns[:] = [d for d in dns if d not in SKIP and not d.startswith(".")]
    for fn in fns:
        if fn.endswith(".py") and ".bak" not in fn:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, APP)[:-3].replace(os.sep, ".")
            if rel.endswith(".__init__"):
                rel = rel[:-9]
            files[rel] = p
# wykonywalne bez .py w katalogu glownym (cron root): qbot-hammerhead-sync, qbot-withings-sync ...
extra = []
for fn in os.listdir(APP) + ["scripts/" + f for f in os.listdir(APP + "/scripts")]:
    p = os.path.join(APP, fn)
    if os.path.isfile(p) and "." not in fn and os.access(p, os.X_OK):
        try:
            if open(p, "rb").read(2) == b"#!":  # python LUB powloka (np. scripts/qbot -> CLI)
                extra.append(p)
        except Exception:
            pass

short = {}  # ostatni czlon -> [modname]
for m in files:
    short.setdefault(m.split(".")[-1], []).append(m)


def deps(path):
    out = set()
    try:
        src = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return out
    try:
        tree = ast.parse(src)
    except Exception:  # skrypt powloki / plik bez Pythona: same napisy (sciezki i nazwy modulow)
        for tok in re.findall(r"[A-Za-z_][\w.]*", re.sub(r"\.py\b", "", src.replace("/", "."))):
            out.add(tok)
        tree = None
    for n in (ast.walk(tree) if tree is not None else []):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:  # wzgledny
                pkg = os.path.relpath(os.path.dirname(path), APP).replace(os.sep, ".")
                parts = pkg.split(".")[: len(pkg.split(".")) - (n.level - 1)] if pkg != "." else []
                base = ".".join([p for p in parts if p] + ([base] if base else []))
            out.add(base)
            for a in n.names:
                out.add(base + "." + a.name if base else a.name)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) < 160:
            for tok in re.findall(r"[A-Za-z_][\w.]*", re.sub(r"\.py\b", "", n.value.replace("/", "."))):
                out.add(tok)
    res = set()
    for d in out:
        parts = d.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in files:
                res.add(cand)
                # pakiety nadrzedne tez zywe
                for j in range(1, i):
                    if ".".join(parts[:j]) in files:
                        res.add(".".join(parts[:j]))
                break
        else:
            if len(parts) == 1 and parts[0] in short and len(short[parts[0]]) == 1 and parts[0] not in ("api", "main", "base", "config", "utils"):
                res.add(short[parts[0]][0])
    return res


roots = set()
for u in UNITS:
    try:
        es = subprocess.run(["systemctl", "show", u + ".service", "-p", "ExecStart"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        es = ""
    for tok in re.findall(r"[\w./-]+", es):
        t = tok.replace("/opt/qbot/app/", "")
        m = t[:-3].replace("/", ".") if t.endswith(".py") else t
        for cand in (m, m.split(":")[0], m.split(".")[0]):
            if cand in files:
                roots.add(cand)
for m in files:
    if m.startswith("scripts.") or m.startswith("tests.") or m.split(".")[-1].startswith("test_"):
        roots.add(m)
extra_deps = set()
for p in extra:
    extra_deps |= deps(p)

live, stack = set(), list(roots | extra_deps)
graph_cache = {}
while stack:
    m = stack.pop()
    if m in live:
        continue
    live.add(m)
    d = graph_cache.setdefault(m, deps(files[m]))
    stack.extend(d - live)

# zywe tylko przez testy/skrypty (nie przez produkcje)
prod_roots = {r for r in roots if not (r.startswith("scripts.") or r.startswith("tests.") or r.split(".")[-1].startswith("test_"))} | extra_deps
prod_live, stack = set(), list(prod_roots)
while stack:
    m = stack.pop()
    if m in prod_live:
        continue
    prod_live.add(m)
    stack.extend(graph_cache.setdefault(m, deps(files[m])) - prod_live)


def last_commit(path):
    try:
        return subprocess.run(["git", "-C", APP, "log", "-1", "--format=%cs", "--", path], capture_output=True, text=True, timeout=5).stdout.strip() or "spoza gita"
    except Exception:
        return "?"


def lines(path):
    try:
        return sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))
    except Exception:
        return 0


core = {m for m in files if not (m.startswith("scripts.") or m.startswith("tests.") or m.split(".")[-1].startswith("test_"))}
dead = sorted(core - live)
test_only = sorted((core & live) - prod_live)
today = datetime.date.today().isoformat()
out = [f"# Martwy kod -- kandydaci ({today})",
       "_scripts/audit_deadcode.py. Graf importow (AST + napisy) od punktow startowych: uslugi qbot*, wykonywalne w katalogu glownym (cron root), scripts/, tests/._",
       "_UWAGA: crontab roota jest niewidoczny dla kanalu DEV -- skrypty odpalane tylko z crona moga byc falszywie 'nieuzywane'. Werdykt = czlowiek._",
       f"\nPunkty startowe uslug: {', '.join(sorted(prod_roots)) or '(brak)'}",
       f"Wykonywalne w katalogu glownym: {', '.join(os.path.basename(p) for p in extra)}",
       f"\nModulow rdzenia: {len(core)} | osiagalne z produkcji: {len(core & prod_live)} | tylko z testow/skryptow: {len(test_only)} | nieosiagalne: {len(dead)}\n",
       "## A. Nieosiagalne z niczego (najmocniejsi kandydaci)", "| modul | linii | ostatni commit |", "|---|---|---|"]
out += [f"| {m} | {lines(files[m])} | {last_commit(files[m])} |" for m in dead]
out += ["", "## B. Uzywane TYLKO przez testy/skrypty (produkcja ich nie laduje)", "| modul | linii | ostatni commit |", "|---|---|---|"]
out += [f"| {m} | {lines(files[m])} | {last_commit(files[m])} |" for m in test_only]
os.makedirs(APP + "/docs/audit", exist_ok=True)
rep = f"{APP}/docs/audit/martwy_kod_{today}.md"
open(rep, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("\n".join(out[:6]))
print("A:", len(dead), "| B:", len(test_only), "| raport:", rep)
