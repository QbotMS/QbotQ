"""Migracja Garazu na nowa taksonomie odziezy (2026-09-24). Dry-run domyslnie, --apply zapisuje (z kopia bazy).
- gear.category -> nowe kategorie (per ID), gear.g_body / g_len (parametry)
- gear.s_* (Ankieta ocen v2, -2..+2): przeliczone z r_* (0..5, wstepne AI) -> s_status='draft'
- ride_gear_log.slot -> nowe sloty (z rzeczy; meta '_*' bez zmian)
"""
import os, shutil, sqlite3, sys, time
sys.path.insert(0, "/opt/qbot/app")
import qbot_garage_taxonomy as T

DB = "/opt/qbot/app/data/garage.db"
K, TE, TR, KU, DE, ZW, BW, WA = T.KOSZ_KOL, T.KOSZ_TECH, T.TERMIKA, T.KURTKI, T.DESZCZ, T.Z_WKL, T.BEZ_WKL, T.WARMERS
M = {}
def put(cat, body, ln, ids):
    for i in ids:
        assert i not in M, i
        M[i] = (cat, body, ln)
# Termika
put(TR, "gora", "dlugi", [1, 2, 3, 5, 7, 8, 9, 10, 11, 234, 16])
put(TR, "gora", "bez", [4, 6, 113, 150, 152, 153])
put(TR, "gora", "krotki", [145, 146, 147, 149, 151])
put(TR, "dol", "dlugi", [12, 13, 15, 28])
put(TR, "dol", "34", [14])
# Koszulki i bluzy kolarskie
put(K, "gora", "krotki", [29, 112, 114, 117, 172, 183])
put(K, "gora", "dlugi", [17, 18, 19, 20, 25, 26, 27, 125, 128, 37])
# Koszulki i bluzy techniczne
put(TE, "gora", "krotki", [116, 118, 119, 127, 132, 140, 175, 176, 192, 220, 225, 226, 129])
put(TE, "gora", "dlugi", [126, 189, 217, 218, 221])
# Kurtki i kamizelki
put(KU, "gora", "dlugi", [21, 22, 23, 30, 33, 34, 36, 39, 131, 139])
put(KU, "gora", "bez", [24, 41, 42, 43, 177])
# Odziez deszczowa
put(DE, "gora", "dlugi", [31, 32, 35, 38, 110, 121])
put(DE, "gora", "bez", [40])
put(DE, "dol", "dlugi", [54, 122])
put(DE, "dol", "krotki", [237])
# Spodnie i spodenki z wkladka
put(ZW, "dol", "krotki", [48, 49, 50, 55, 58, 59, 120, 134, 173, 174, 193, 236, 238, 239, 179])
put(ZW, "dol", "dlugi", [44, 53])
# bez wkladki
put(BW, "dol", "dlugi", [46, 51, 52, 56, 57, 235])
# rekawki i nogawki (kategoria bez zmian, tylko parametry)
put(WA, "gora", "dlugi", [60, 144])
put(WA, "dol", "dlugi", [61])
put(WA, "dol", "34", [62, 63])

NEWCOLS = [("g_body", "TEXT"), ("g_len", "TEXT")] + [(c, "INTEGER") for c in T.SURVEY_COLS] + [("s_status", "TEXT")]
R2S = {"r_breath": "s_breath", "r_dry": "s_dry", "r_wind": "s_wind", "r_water": "s_water", "r_pack": "s_pack", "r_insul": "s_insul"}


def conv(r):
    return None if r is None else int(max(-2, min(2, round((float(r) - 2.5) * 0.8))))


def main(apply):
    g = sqlite3.connect(DB); g.row_factory = sqlite3.Row
    have = {r["name"] for r in g.execute("PRAGMA table_info(gear)")}
    old_cats = set(T.OLD2NEW) | {WA}
    rows = g.execute("SELECT * FROM gear").fetchall()
    miss = [(r["id"], r["category"], r["brand"], r["model"]) for r in rows if r["category"] in old_cats and r["id"] not in M]
    extra = [i for i in M if not any(r["id"] == i for r in rows)]
    print("rzeczy w starych kategoriach bez przypisania:", miss)
    print("przypisane ID, ktorych nie ma:", extra)
    assert not miss and not extra
    by = {}
    for i, (c, b, l) in M.items():
        by[c] = by.get(c, 0) + 1
    print("nowe kategorie:", by)
    logs = g.execute("SELECT id, slot, gear_id FROM ride_gear_log").fetchall()
    if not apply:
        print("DRY-RUN"); return
    bak = DB + ".bak_taks_" + time.strftime("%Y%m%d_%H%M%S")
    g.close(); shutil.copy2(DB, bak); print("kopia:", bak)
    g = sqlite3.connect(DB); g.row_factory = sqlite3.Row
    with g:
        for c, t in NEWCOLS:
            if c not in have:
                g.execute("ALTER TABLE gear ADD COLUMN %s %s" % (c, t))
        for i, (c, b, l) in M.items():
            g.execute("UPDATE gear SET category=?, g_body=?, g_len=? WHERE id=?", (c, b, l, i))
        # ankieta v2 z wstepnych ocen AI
        nconv = 0
        for r in g.execute("SELECT id, " + ", ".join(R2S) + ", ratings_status FROM gear").fetchall():
            vals = {R2S[k]: conv(r[k]) for k in R2S}
            if any(v is not None for v in vals.values()):
                g.execute("UPDATE gear SET " + ", ".join("%s=?" % k for k in vals) + ", s_status='draft' WHERE id=?",
                          list(vals.values()) + [r["id"]])
                nconv += 1
        print("przeliczone oceny wstepne:", nconv)
        # sloty "W czym jechalem"
        info = {r["id"]: r for r in g.execute("SELECT id, category, g_body, g_len FROM gear").fetchall()}
        nlog = 0
        for lg in logs:
            if lg["slot"].startswith("_") or lg["slot"] in ("wheels", "cassette"):
                continue
            it = info.get(lg["gear_id"])
            ns = T.slot_of(it["category"], it["g_body"], it["g_len"]) if it else T.OLD_SLOT.get(lg["slot"], lg["slot"])
            if ns and ns != lg["slot"]:
                g.execute("UPDATE ride_gear_log SET slot=? WHERE id=?", (ns, lg["id"]))
                nlog += 1
        print("zmienione sloty w 'W czym jechalem':", nlog)
    left = g.execute("SELECT category, count(*) FROM gear WHERE category IN (%s) GROUP BY 1" % ",".join("?" * len(T.OLD2NEW)),
                     list(T.OLD2NEW)).fetchall()
    print("pozostale stare kategorie:", [tuple(x) for x in left])
    g.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
