"""Audyt stref czasowych QBota: gdzie czas moze byc pokazany w UTC zamiast Europe/Warsaw.
Wynik: docs/audit/tz_audit.md. Tylko odczyt."""
import os, re, sys, sqlite3, collections
sys.path.insert(0, "/opt/qbot/app"); os.environ["QBOT3_ENABLED"] = "1"
ROOTS = ["/opt/qbot/app", "/opt/qbot/web/public"]
SKIP = {".venv", "archive", "_bak_archive", ".ms-playwright", ".git", "node_modules", "tests", "vendor", "data", "__pycache__"}
PY = [
    ("utcnow", re.compile(r"utcnow\(\)")),
    ("now_utc", re.compile(r"now\((?:tz=)?(?:timezone\.utc|UTC|dt\.timezone\.utc|_dt\.timezone\.utc)\)")),
    ("gmtime", re.compile(r"time\.gmtime\(")),
    ("sqlite_now", re.compile(r"datetime\('now'\)|CURRENT_TIMESTAMP", re.I)),
    ("fmt_Z", re.compile(r"strftime\([^)]*Z['\"]")),
    ("pg_utc", re.compile(r"AT TIME ZONE 'UTC'|timezone\('UTC'", re.I)),
]
JS = [
    ("toISOString", re.compile(r"toISOString\(\)")),
    ("getUTC", re.compile(r"getUTC(Hours|Minutes|Date|Day)")),
    ("iso_slice", re.compile(r"\.(slice|substr|substring)\(\s*11\s*,")),
    ("tz_utc", re.compile(r"timeZone\s*:\s*['\"]UTC")),
]
hits = collections.defaultdict(list)
for root in ROOTS:
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP]
        for fn in fns:
            if ".bak" in fn or fn.startswith("_tmp_"):
                continue
            ext = os.path.splitext(fn)[1]
            pats = PY if ext == ".py" else JS if ext in (".js", ".html") else None
            if not pats:
                continue
            p = os.path.join(dp, fn)
            try:
                lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
            except Exception:
                continue
            for i, ln in enumerate(lines, 1):
                for tag, rx in pats:
                    if rx.search(ln):
                        hits[p].append((i, tag, ln.strip()[:150]))
out = ["# Audyt stref czasowych (auto)", ""]
cnt = collections.Counter(t for v in hits.values() for _, t, _ in v)
out.append("Podsumowanie wzorcow: " + ", ".join("%s=%d" % kv for kv in cnt.most_common()))
out.append("")
# Postgres: kolumny timestamp BEZ strefy (ryzyko: zapisany UTC, pokazany jako lokalny)
try:
    from fitmodel.api import _db_connect
    c = _db_connect(); cur = c.cursor()
    cur.execute("""select table_schema, table_name, column_name, column_default from information_schema.columns
                   where data_type='timestamp without time zone' and table_schema not in ('pg_catalog','information_schema')
                   order by 1,2,3""")
    rows = cur.fetchall()
    out.append("## Postgres: kolumny timestamp BEZ strefy (%d)" % len(rows))
    for r in rows:
        out.append("- %s.%s.%s default=%s" % r)
    out.append("")
except Exception as e:
    out.append("Postgres blad: %s" % e)
# SQLite garage.db: domyslne czasy (datetime('now') = UTC)
try:
    g = sqlite3.connect("/opt/qbot/app/data/garage.db")
    out.append("## garage.db: kolumny z domyslnym czasem")
    for (t,) in g.execute("select name from sqlite_master where type='table'"):
        for col in g.execute("pragma table_info(%s)" % t):
            if col[4] and re.search(r"now|CURRENT", str(col[4]), re.I):
                out.append("- %s.%s default=%s" % (t, col[1], col[4]))
    out.append("")
except Exception as e:
    out.append("garage.db blad: %s" % e)
out.append("## Kod (plik: linia [wzorzec] tresc)")
for p in sorted(hits, key=lambda k: -len(hits[k])):
    out.append("### %s (%d)" % (p.replace("/opt/qbot/", ""), len(hits[p])))
    for i, t, s in hits[p]:
        out.append("- %d [%s] `%s`" % (i, t, s.replace("`", "'")))
os.makedirs("/opt/qbot/app/docs/audit", exist_ok=True)
open("/opt/qbot/app/docs/audit/tz_audit.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("\n".join(out[:4]))
print("pliki z trafieniami:", len(hits), "| trafien:", sum(len(v) for v in hits.values()))
