"""Parametry gornych warstw (2026-09-25): gear.g_layer (warstwowanie: chetnie / potrzeba / nie) i gear.g_style
(kolarski / outdoor). Domyslne wg kategorii + wyjatki per ID. Kopia bazy. Dry-run bez --apply."""
import shutil, sqlite3, sys, time
sys.path.insert(0, "/opt/qbot/app")
import qbot_garage_taxonomy as T

DB = "/opt/qbot/app/data/garage.db"
LAYER_OVR = {218: "chetnie", 132: "nie"}                       # Alpenglow: tez warstwa posrednia; cropped mesh: tylko sam
STYLE_OVR = {217: "outdoor", 218: "outdoor", 33: "outdoor", 34: "outdoor", 36: "outdoor",
             35: "outdoor", 38: "outdoor", 54: "outdoor"}


def main(apply):
    g = sqlite3.connect(DB); g.row_factory = sqlite3.Row
    have = {r["name"] for r in g.execute("PRAGMA table_info(gear)")}
    rows = g.execute("SELECT id, category, brand, model FROM gear WHERE category IN (?,?,?,?)",
                     (T.KOSZ_KOL, T.KOSZ_TECH, T.KURTKI, T.DESZCZ)).fetchall()
    plan = []
    for r in rows:
        c = r["category"]
        lay = {T.KOSZ_KOL: "chetnie", T.KOSZ_TECH: "potrzeba"}.get(c)
        lay = LAYER_OVR.get(r["id"], lay)
        sty = "kolarski" if c in (T.KOSZ_KOL, T.KURTKI, T.DESZCZ) else None
        sty = STYLE_OVR.get(r["id"], sty)
        plan.append((r["id"], c, "%s %s" % (r["brand"], r["model"]), lay, sty))
    for p in plan:
        print("%4d | %-28s | %-50s | warstwowanie=%-8s | styl=%s" % (p[0], p[1][:28], p[2][:50], p[3], p[4]))
    if not apply:
        print("DRY-RUN"); return
    g.close(); shutil.copy2(DB, DB + ".bak_layer_" + time.strftime("%Y%m%d_%H%M%S"))
    g = sqlite3.connect(DB)
    with g:
        for c in ("g_layer", "g_style"):
            if c not in have:
                g.execute("ALTER TABLE gear ADD COLUMN %s TEXT" % c)
        for i, _c, _n, lay, sty in plan:
            g.execute("UPDATE gear SET g_layer=?, g_style=? WHERE id=?", (lay, sty, i))
    print("zapisano:", len(plan))


if __name__ == "__main__":
    main("--apply" in sys.argv)
