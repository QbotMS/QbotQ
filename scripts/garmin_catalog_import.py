#!/usr/bin/env python3
"""Import katalogu cwiczen Garmina do qbot_v2.garmin_exercise (TRENER v12).

Zrodla (w repo):
  sql/garmin_exercises_v1.csv        - 663 cwiczenia sprawdzone (GPT x2 + walidacja Claude), separator ';'
  sql/garmin_exercises_fix_v1.csv    - reczne poprawki (25 cwiczen z hantlami/guma blednie w "sztanga" w regulach)
  sql/garmin_exercises_klasy_v1.csv  - reguly sprzetu/statusu dla calego katalogu (fallback)
  garminconnect.exercises._RAW       - pelny katalog Garmina (kody, nazwy EN)

Warianty "Weighted ..." nie sa osobnymi pozycjami merytorycznie: dostaja weighted_of = cwiczenie
bazowe i dziedzicza po nim status/partie/nazwe PL (+ hantle w sprzecie).
Idempotentny (UPSERT po kod). Uzycie: .venv/bin/python3 scripts/garmin_catalog_import.py [--dry-run]
"""
import csv, os, sys, collections
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from garminconnect.exercises import _RAW
from fitmodel.api import _db_connect

APP = "/opt/qbot/app"
DRY = "--dry-run" in sys.argv
KLASA_SPRZET = {
    "hantle": ["hantle"], "guma": ["guma"], "sztanga/gryf": ["sztanga"], "kettlebell": ["kettlebell"],
    "drazek": ["drazek"], "talerz": ["talerz"], "skrzynia": ["skrzynia"], "maszyna/wyciag": ["maszyna"],
    "pilka/bosu/rolka": ["pilka"], "TRX/kolka": ["inne"], "liny/worki/inne": ["inne"],
    "cardio/poza domem": ["inne"], "bez sprzetu/lawka/mata": ["brak"],
    "z obciazeniem (hantel/kamizelka)": ["hantle"],
}


def kod_of(cat, ex):
    return f"{cat}/{ex or cat}"


def main():
    gpt, reczne = {}, set()
    # v1 = GPT (2 rundy, walidowane); fix_v1 = reczne poprawki (nadpisuja v1 i reguly)
    for fn in ("garmin_exercises_v1.csv", "garmin_exercises_fix_v1.csv"):
        with open(f"{APP}/sql/{fn}", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f, delimiter=";"):
                gpt[r["kod"]] = r
                if fn.startswith("garmin_exercises_fix"):
                    reczne.add(r["kod"])
    klasy = {}
    with open(f"{APP}/sql/garmin_exercises_klasy_v1.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            klasy[kod_of(r["category"], r["exercise"])] = r
    cat = {kod_of(c, e): (n, c, e or c) for n, c, e in _RAW}
    assert set(gpt) <= set(cat), "kody z CSV spoza katalogu"

    def base_row(k):
        """(status, partia, sprzet, name_pl) dla kodu z GPT albo z regul."""
        if k in gpt:
            g = gpt[k]
            return g["status"], g["partia"] or None, [s for s in g["sprzet"].split("+") if s], g["nazwa_pl"] or None
        kl = klasy[k]
        return kl["status"], None, KLASA_SPRZET.get(kl["klasa"], ["inne"]), None

    rows = []
    for k, (name, c, e) in cat.items():
        weighted_of = None
        if k in gpt:
            st, pa, sp, pl = base_row(k)
            g = gpt[k]
            dup, uw = g["duplikat_kodu"] or None, g["uwagi"] or None
            src = "reczne" if k in reczne else "gpt"
        else:
            dup, uw = None, None
            base = kod_of(c, e[len("WEIGHTED_"):]) if e.startswith("WEIGHTED_") else None
            if base and base in cat:
                weighted_of = base
                st, pa, sp, pl = base_row(base)
                sp = sorted(set(sp) - {"brak"} | {"hantle"})
                pl = f"{pl} z obciążeniem" if pl else None
                src = "wariant"
            else:
                st, pa, sp, pl = base_row(k)
                src = "reguly"
        rows.append((k, c, e, name, pl, sp, st, pa, dup, weighted_of, src, uw))

    stat = collections.Counter((r[10], r[6]) for r in rows)
    print("razem", len(rows))
    for (src, st), n in sorted(stat.items()):
        print(f"  {src:8s} {st:8s} {n}")
    print("warianty bez bazy:", sum(1 for r in rows if r[3].lower().startswith("weighted ") and not r[9]))
    if DRY:
        print("DRY-RUN: nic nie zapisano")
        return
    con = _db_connect()
    try:
        cur = con.cursor()
        cur.execute(open(f"{APP}/sql/trainer_v12.sql", encoding="utf-8").read())
        for r in rows:
            cur.execute(
                """INSERT INTO qbot_v2.garmin_exercise
                   (kod, category, exercise, name_en, name_pl, sprzet, status, partia, dup_of, weighted_of, zrodlo, uwagi, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                   ON CONFLICT (kod) DO UPDATE SET
                     category=EXCLUDED.category, exercise=EXCLUDED.exercise, name_en=EXCLUDED.name_en,
                     name_pl=EXCLUDED.name_pl, sprzet=EXCLUDED.sprzet, status=EXCLUDED.status, partia=EXCLUDED.partia,
                     dup_of=EXCLUDED.dup_of, weighted_of=EXCLUDED.weighted_of, zrodlo=EXCLUDED.zrodlo,
                     uwagi=EXCLUDED.uwagi, updated_at=now()""",
                r,
            )
        con.commit()
        cur.execute("SELECT status, count(*) FROM qbot_v2.garmin_exercise GROUP BY 1 ORDER BY 1")
        print("BAZA:", cur.fetchall())
    finally:
        con.close()


if __name__ == "__main__":
    main()
