#!/usr/bin/env python3
"""Import wynikow audytu garderoby do garage.db (tabela gear, kolumny a_*).

Audyt = plik JSON w docs/audit/ (np. garderoba_2026-09-24.json). Kolejny audyt = nowy plik, ten sam skrypt.
Kolumny a_* sa WYLACZNIE wynikiem audytu; notatki, ocena i reszta rekordu gear NIE sa zmieniane.

Uzycie:
  .venv/bin/python3 scripts/garage_audit_import.py docs/audit/garderoba_2026-09-24.json           # podglad (dry-run)
  .venv/bin/python3 scripts/garage_audit_import.py docs/audit/garderoba_2026-09-24.json --apply   # zapis (+ kopia bazy)
  --reset-all   przed zapisem czysci a_* we WSZYSTKICH rekordach (pelny nowy audyt zastepuje stary)
"""
import argparse
import datetime as dt
import json
import shutil
import sqlite3
import sys

GARAGE_DB = "/opt/qbot/app/data/garage.db"
COLS = [  # (kolumna, typ, klucz w JSON)
    ("a_status", "TEXT", "st"), ("a_fit", "TEXT", "fit"), ("a_use", "TEXT", "use"),
    ("a_temp_min", "INTEGER", None), ("a_temp_max", "INTEGER", None),
    ("a_effort", "TEXT", "eff"), ("a_rain", "TEXT", "rain"), ("a_wind", "TEXT", "wind"),
    ("a_wet_cold", "INTEGER", "wet"), ("a_pad_h", "TEXT", "pad"), ("a_carry", "TEXT", "carry"),
    ("a_role", "TEXT", "role"), ("a_pairs", "TEXT", "pairs"), ("a_note", "TEXT", "note"),
    ("a_out", "INTEGER", "out"), ("a_src", "TEXT", "src"), ("a_date", "TEXT", None),
]
ST = {"CORE", "ROTATION", "SPECIAL", "BACKUP", "RETIRE_CANDIDATE", "FIT_BLOCKED", "OFF_BIKE", "NEW"}
FIT = {"OK", "LEKKO_CIASNA", "ZA_LUZNA", "BLOKUJE"}
USE = {"CZESTO", "SPORADYCZNIE", "RZADKO", "NIGDY"}
RAIN = {"brak_oczekiwan", "nietestowany", "mzawka_przemaka", "mzawka_sucho", "umiarkowany_przemaka_po_czasie",
        "umiarkowany_sucho", "ulewa_sucho"}
WIND = {"mocna", "umiarkowana", "czesciowa", "mala"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reset-all", action="store_true")
    a = ap.parse_args()
    doc = json.load(open(a.file, encoding="utf-8"))
    date, dsrc = doc["date"], doc.get("default_src") or "audyt"
    g = sqlite3.connect(GARAGE_DB)
    g.row_factory = sqlite3.Row
    have = {r["name"] for r in g.execute("PRAGMA table_info(gear)")}
    errs, rows = [], []
    seen = set()
    for it in doc["items"]:
        i = int(it["id"])
        if i in seen:
            errs.append("id %s dwa razy" % i)
        seen.add(i)
        r = g.execute("SELECT id, brand, model, active FROM gear WHERE id=?", (i,)).fetchone()
        if not r:
            errs.append("id %s nie istnieje" % i); continue
        name = ("%s %s" % (r["brand"] or "", r["model"] or "")).lower()
        if it["chk"].lower() not in name:
            errs.append("id %s: '%s' nie pasuje do '%s'" % (i, it["chk"], name)); continue
        for k, allowed in (("st", ST), ("fit", FIT), ("use", USE), ("rain", RAIN), ("wind", WIND)):
            if it.get(k) is not None and it[k] not in allowed:
                errs.append("id %s: zla wartosc %s=%s" % (i, k, it[k]))
        t = it.get("t")
        if t is not None and not (len(t) == 2 and t[0] <= t[1]):
            errs.append("id %s: zly zakres t=%s" % (i, t))
        v = {c: (it.get(k) if k else None) for c, _, k in COLS}
        v["a_temp_min"], v["a_temp_max"] = (t[0], t[1]) if t else (None, None)
        v["a_src"] = it.get("src") or dsrc
        v["a_date"] = date
        v["a_out"] = int(it.get("out") or 0)
        v["a_wet_cold"] = int(it.get("wet") or 0)
        rows.append((i, name, r["active"], v))
    print("pozycji w pliku: %d, bledow: %d" % (len(rows), len(errs)))
    for e in errs:
        print("  BLAD:", e)
    inact = [x for x in rows if not x[2]]
    for x in inact:
        print("  UWAGA: id %s nieaktywne (%s)" % (x[0], x[1]))
    miss = [c for c, _, _ in COLS if c not in have]
    print("nowe kolumny:", ", ".join(miss) or "brak")
    by = {}
    for x in rows:
        by[x[3]["a_status"] or "-"] = by.get(x[3]["a_status"] or "-", 0) + 1
    print("statusy:", by, "| a_out=1:", sum(1 for x in rows if x[3]["a_out"]))
    if errs:
        sys.exit(2)
    if not a.apply:
        print("DRY-RUN - nic nie zapisano (dodaj --apply)")
        return
    bak = "%s.bak_audit_%s" % (GARAGE_DB, dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    g.close()
    shutil.copy2(GARAGE_DB, bak)
    print("kopia bazy:", bak)
    g = sqlite3.connect(GARAGE_DB)
    with g:
        for c, typ, _ in COLS:
            if c in miss:
                g.execute("ALTER TABLE gear ADD COLUMN %s %s" % (c, typ))
        if a.reset_all:
            g.execute("UPDATE gear SET " + ", ".join("%s=NULL" % c for c, _, _ in COLS))
        cols = [c for c, _, _ in COLS]
        for i, _, _, v in rows:
            g.execute("UPDATE gear SET " + ", ".join("%s=?" % c for c in cols) + " WHERE id=?", [v[c] for c in cols] + [i])
    n = g.execute("SELECT count(*) FROM gear WHERE a_date=?", (date,)).fetchone()[0]
    print("ZAPISANO: rekordow z a_date=%s: %d" % (date, n))


if __name__ == "__main__":
    main()
