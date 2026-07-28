# -*- coding: utf-8 -*-
"""Uzupelnia color_q dla rzeczy, ktore maja kolor tekstowy, ale pusta kolumne Kolor.
Domyslnie NA SUCHO (nic nie zapisuje). Zapis dopiero z argumentem: --zapisz"""
import sys, os, sqlite3
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

ZAPIS = "--zapisz" in sys.argv
DB = "/opt/qbot/app/data/garage.db"

from qbot_web import _color_q

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id, brand, model, color FROM gear "
    "WHERE color IS NOT NULL AND color<>'' AND (color_q IS NULL OR color_q='') "
    "ORDER BY id").fetchall()

print("TRYB:", "ZAPIS" if ZAPIS else "NA SUCHO (nic nie zapisuje)")
print("rzeczy do uzupelnienia:", len(rows))
print()
ok = brak = 0
for r in rows:
    nazwa = ((r["brand"] or "") + " " + (r["model"] or "")).strip()[:36]
    try:
        q = _color_q(r["color"])
    except Exception as e:
        q = None
        print("  %4d | %-36s | %-22s -> WYJATEK %s" % (
            r["id"], nazwa, repr(r["color"])[:22], type(e).__name__))
        continue
    if q:
        ok += 1
        print("  %4d | %-36s | %-22s -> %s" % (r["id"], nazwa, repr(r["color"])[:22], q))
        if ZAPIS:
            c.execute("UPDATE gear SET color_q=? WHERE id=?", (q, r["id"]))
    else:
        brak += 1
        print("  %4d | %-36s | %-22s -> NIE ROZPOZNANO" % (
            r["id"], nazwa, repr(r["color"])[:22]))
if ZAPIS:
    c.commit()
print()
print("rozpoznano: %d | nie rozpoznano: %d" % (ok, brak))
if not ZAPIS:
    print("\nNIC NIE ZAPISANO. Aby zapisac: dopisz --zapisz")
c.close()
