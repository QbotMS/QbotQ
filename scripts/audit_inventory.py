#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inwentaryzacja bazowa QBota (rdzen: qbot-api/mcp/dev-mcp/qlab).
Zbiera DOWODY do jednego raportu markdown. NIE ocenia - ocena rano w sesji.
Kazda sekcja w try/except: jedna awaria nie kladzie calego raportu.
Uruchom: /opt/qbot/app/.venv/bin/python3 scripts/audit_inventory.py [YYYY-MM-DD]
"""
import os, sys, re, ast, subprocess, datetime, glob, traceback

APP = "/opt/qbot/app"
sys.path.insert(0, APP)
os.environ["QBOT3_ENABLED"] = "1"

RUN_DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
AUDIT_DIR = os.path.join(APP, "docs", "audit")
os.makedirs(AUDIT_DIR, exist_ok=True)
OUT = os.path.join(AUDIT_DIR, "inventory_%s.md" % RUN_DATE)

buf = []
def w(s=""):
    buf.append(s)

def section(title):
    w("\n## " + title + "\n")

def run(cmd, timeout=60):
    """Uruchom komende (lista), zwroc (rc, out)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, "ERR: %s" % e

def all_py():
    out = []
    for root, dirs, files in os.walk(APP):
        # pomin smieci i venv/archiwum przy analizie glownego kodu
        if "/.venv" in root or "/node_modules" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.join(root, f))
    return out

# ---------- naglowek ----------
w("# QBot — inwentaryzacja bazowa (%s)" % RUN_DATE)
w("_Auto-zebrane przez scripts/audit_inventory.py. To DOWODY, nie werdykt — ocena w sesji porannej._")
w("_Wygenerowano: %s_" % datetime.datetime.now().isoformat(timespec="seconds"))

# ---------- 1. USLUGI ----------
try:
    section("1. Uslugi i timery systemd")
    rc, out = run(["systemctl", "--no-pager", "-l", "list-units", "qbot*"])
    w("### Jednostki qbot*\n```\n" + out.strip() + "\n```")
    rc, out = run(["systemctl", "--no-pager", "-l", "list-timers", "--all"])
    w("### Wszystkie timery (szukaj nieudokumentowanych)\n```\n" + out.strip()[:6000] + "\n```")
except Exception:
    w("BLAD sekcji uslug:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 2. CRON / zaplanowane ----------
try:
    section("2. Cron i harmonogramy")
    for path in ["/etc/crontab"]:
        if os.path.exists(path):
            try:
                w("### %s\n```\n%s\n```" % (path, open(path).read()[:3000]))
            except Exception as e:
                w("### %s — brak dostepu: %s" % (path, e))
    for d in ["/etc/cron.d"]:
        if os.path.isdir(d):
            try:
                w("### %s: %s" % (d, ", ".join(os.listdir(d)) or "(pusto)"))
            except Exception as e:
                w("### %s — brak dostepu: %s" % (d, e))
    # harmonogramy w kodzie (APScheduler / petle / godziny)
    hits = []
    pat = re.compile(r"(apscheduler|BackgroundScheduler|add_job|on-calendar|OnCalendar|04:45|every\s+15|asyncio\.sleep|schedule\.)", re.I)
    for f in all_py():
        try:
            for i, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
                if pat.search(line):
                    hits.append("%s:%d  %s" % (f.replace(APP + "/", ""), i, line.strip()[:120]))
        except Exception:
            pass
    w("### Harmonogramy/petle w kodzie (%d trafien)\n```\n%s\n```" % (len(hits), "\n".join(hits[:200])))
except Exception:
    w("BLAD sekcji cron:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 3. ZLOGI: pliki-smieci ----------
try:
    section("3. Zlogi — pliki tymczasowe / kopie / archiwum")
    clutter = []
    for pat in ["scripts/_tmp_*.py", "scripts/_tmp_*", "**/*.bak", "**/*.bak.*"]:
        clutter += glob.glob(os.path.join(APP, pat), recursive=True)
    clutter = sorted(set(clutter))
    w("### Kandydaci do kasacji (%d)\n```\n%s\n```" % (len(clutter),
        "\n".join(c.replace(APP + "/", "") for c in clutter) or "(brak)"))
    arch = os.path.join(APP, "archive")
    if os.path.isdir(arch):
        n = sum(len(fs) for _, _, fs in os.walk(arch))
        w("### archive/ obecny — %d plikow (przejrzec czy potrzebne)" % n)
except Exception:
    w("BLAD sekcji smieci:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 4. ZLOGI: moduly-sieroty (nikt nie importuje) ----------
try:
    section("4. Zlogi — moduly nieimportowane (kandydaci na martwy kod)")
    pyfiles = [f for f in all_py() if "/scripts/" not in f and "/tests/" not in f and "/archive/" not in f]
    modnames = {}
    for f in pyfiles:
        base = os.path.splitext(os.path.basename(f))[0]
        if base != "__init__":
            modnames[base] = f
    # zbuduj korpus importow
    corpus = ""
    for f in pyfiles:
        try:
            corpus += open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            pass
    orphans = []
    for base, f in sorted(modnames.items()):
        # czy ktokolwiek importuje ten modul (import X / from ... import X / .X)
        if not re.search(r"(import\s+\w*%s\b|from[\w. ]+import[\w, ]*\b%s\b|\.%s\b|import\s+%s\b)" % (base, base, base, base), corpus):
            orphans.append(f.replace(APP + "/", ""))
    w("Heurystyka: modul, ktorego nazwa nie pada nigdzie poza wlasnym plikiem. Szum mozliwy (entrypointy, dynamiczne importy) — WYMAGA oceny.")
    w("```\n%s\n```" % ("\n".join(orphans) or "(brak oczywistych sierot)"))
except Exception:
    w("BLAD sekcji sieroty:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 5. NARZEDZIA vs PROMPT ALBERTA ----------
try:
    section("5. Spojnosc: narzedzia (tool_registry) vs prompt Alberta (_SYSTEM)")
    reg = open(os.path.join(APP, "qbot3/tool_registry.py"), encoding="utf-8", errors="ignore").read()
    alb = open(os.path.join(APP, "qbot3/llm/albert.py"), encoding="utf-8", errors="ignore").read()
    # nazwy narzedzi: "name": "..." oraz name=  (heurystyka)
    tools = sorted(set(re.findall(r'["\']name["\']\s*:\s*["\']([a-z0-9_\.]+)["\']', reg) +
                       re.findall(r'\bname\s*=\s*["\']([a-z0-9_\.]+)["\']', reg)))
    missing = [t for t in tools if t not in alb]
    w("### Narzedzia wykryte w rejestrze (%d)\n```\n%s\n```" % (len(tools), ", ".join(tools) or "(0 — sprawdz wzorzec)"))
    w("### NIE wspomniane w prompcie Alberta (potencjalne narzedzia-widma)\n```\n%s\n```" % ("\n".join(missing) or "(wszystkie obecne)"))
    # opisy > 500 znakow (build_tools_spec obcina)
    longd = []
    for m in re.finditer(r'["\']description["\']\s*:\s*["\'](.+?)["\']\s*[,}]', reg, re.S):
        if len(m.group(1)) > 500:
            longd.append(m.group(1)[:60] + "...")
    w("### Opisy narzedzi > 500 znakow (zostana obciete): %d\n```\n%s\n```" % (len(longd), "\n".join(longd) or "(brak)"))
except Exception:
    w("BLAD sekcji narzedzia/prompt:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 6. ENDPOINTY WEB vs DOKI ----------
try:
    section("6. Endpointy web vs dokumentacja")
    web = open(os.path.join(APP, "qbot_web.py"), encoding="utf-8", errors="ignore").read()
    eps = sorted(set(re.findall(r'@app\.(?:get|post|put|delete)\(\s*["\']([^"\']+)["\']', web)))
    docs_text = ""
    for dn in ["RAPORT_WEB.md", "FORMA_UI_LAYOUT.md", "CONTEXT.md"]:
        p = os.path.join(APP, "docs", dn)
        if os.path.exists(p):
            docs_text += open(p, encoding="utf-8", errors="ignore").read()
    undoc = [e for e in eps if e not in docs_text]
    w("### Endpointy w qbot_web.py (%d)\n```\n%s\n```" % (len(eps), "\n".join(eps)))
    w("### Nieudokumentowane (brak w RAPORT_WEB/FORMA/CONTEXT)\n```\n%s\n```" % ("\n".join(undoc) or "(wszystkie wspomniane)"))
except Exception:
    w("BLAD sekcji endpointy:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 7. TABELE: kod vs baza ----------
try:
    section("7. Tabele — kod vs schemat bazy")
    used = set()
    for f in all_py():
        try:
            for line in open(f, encoding="utf-8", errors="ignore"):
                for t in re.findall(r"qbot_v2\.([a-z_][a-z0-9_]+)", line):
                    used.add(t)
        except Exception:
            pass
    w("### Tabele qbot_v2.* uzywane w kodzie (%d)\n```\n%s\n```" % (len(used), ", ".join(sorted(used))))
    try:
        from fitmodel.api import _db_connect
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute("select table_name from information_schema.tables where table_schema='qbot_v2'")
        real = set(r[0] for r in cur.fetchall())
        cur.close(); conn.close()
        code_missing = sorted(used - real)   # kod odwoluje sie do NIEISTNIEJACEJ tabeli — POWAZNE
        db_unused = sorted(real - used)       # tabela istnieje, kod jej nie dotyka (slabszy sygnal)
        w("### Kod odwoluje sie do tabel NIEISTNIEJACYCH w bazie (POWAZNE)\n```\n%s\n```" % ("\n".join(code_missing) or "(brak — dobrze)"))
        w("### Tabele w bazie nieuzywane w kodzie (%d — moga byc sieroty lub uzywane z SQL/dashboardow)\n```\n%s\n```" % (len(db_unused), ", ".join(db_unused)))
    except Exception as e:
        w("### Polaczenie z baza nieudane: %s" % e)
except Exception:
    w("BLAD sekcji tabele:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 8. WLASCIWE DANE: inwarianty kanonu (z CONTEXT.md) ----------
try:
    section("8. Wlasciwe zrodla danych — inwarianty kanonu")
    findings = []
    # 8a. CP/W'bal maja liczyc z activity_record, NIE z plikow FIT
    fit_reads = []
    for f in all_py():
        if "/fitmodel/" not in f:
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
            if re.search(r"(\.fit\b|fitparse|FitFile|hammerhead_originals|garmin_proxy)", txt) and \
               re.search(r"(cp_|wprime|wbal|w_prime)", txt, re.I):
                fit_reads.append(f.replace(APP + "/", ""))
        except Exception:
            pass
    findings.append(("CP/W' liczone z plikow FIT zamiast activity_record (nie powinno)",
                     fit_reads or ["(brak — dobrze)"]))
    # 8b. slad 'zamrozenia 2026-06-28' (bledny mit — nie powinno byc w kodzie)
    frozen = []
    for f in all_py():
        try:
            for i, line in enumerate(open(f, encoding="utf-8", errors="ignore"), 1):
                if "2026-06-28" in line and re.search(r"(frozen|zamro|freeze|ingest)", line, re.I):
                    frozen.append("%s:%d %s" % (f.replace(APP+"/",""), i, line.strip()[:100]))
        except Exception:
            pass
    findings.append(("Slad mitu 'zamrozenie ingestu 2026-06-28'", frozen or ["(brak — dobrze)"]))
    # 8c. FTP kanoniczny = fitmodel_daily.ftp_est_w; Xert tylko benchmark
    xert_as_input = []
    for f in all_py():
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
            if re.search(r"xert", txt, re.I) and re.search(r"(ftp|cp_|wprime)", txt, re.I) \
               and "bench" not in os.path.basename(f).lower():
                xert_as_input.append(f.replace(APP + "/", ""))
        except Exception:
            pass
    findings.append(("Pliki mieszajace Xert z FTP/CP/W' (sprawdz czy tylko benchmark, nie input)",
                     xert_as_input or ["(brak)"]))
    for title, items in findings:
        w("### %s\n```\n%s\n```" % (title, "\n".join(items)))
except Exception:
    w("BLAD sekcji inwarianty:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 9. TESTY ----------
try:
    section("9. Testy jednostkowe")
    rc, out = run([os.path.join(APP, ".venv/bin/python3"), "-m", "pytest", "-q", "--no-header"], timeout=300)
    if rc == -1 or "No module named pytest" in out or "usage:" in out[:80]:
        rc, out = run([os.path.join(APP, ".venv/bin/python3"), "-m", "unittest", "discover", "-s", "tests"], timeout=300)
    tail = out.strip().splitlines()[-40:]
    w("rc=%d\n```\n%s\n```" % (rc, "\n".join(tail)))
except Exception:
    w("BLAD sekcji testy:\n```\n" + traceback.format_exc() + "\n```")

# ---------- 10. GIT ----------
try:
    section("10. Git — stan i tydzien commitow")
    rc, out = run(["git", "-C", APP, "status", "--short"])
    w("### git status --short\n```\n%s\n```" % (out.strip() or "(czysto)"))
    rc, out = run(["git", "-C", APP, "log", "--oneline", "--since=7.days"])
    w("### Commity z 7 dni\n```\n%s\n```" % out.strip())
except Exception:
    w("BLAD sekcji git:\n```\n" + traceback.format_exc() + "\n```")

# ---------- zapis ----------
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(buf) + "\n")
print("RAPORT:", OUT)
print("sekcji:", buf.count("") )
