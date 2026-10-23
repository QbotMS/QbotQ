#!/usr/bin/env python3
"""Zapis powiazan cwiczen Trenera z katalogiem Garmina (sql/trainer_garmin_map_v1.csv).

- trainer_exercise.garmin_kod = kod Garmina (jakosc 1 = dokladny, 2 = bliski)
- cwiczenia bez odpowiednika (jakosc 3): ocena uzytkownika tier X (silnik nie wybiera),
  tylko gdy uzytkownik nie ocenil ich wczesniej inaczej; note = "brak w Garmin".
Idempotentny. Uzycie: .venv/bin/python3 scripts/trener_garmin_apply_map.py [--user admin] [--dry-run]
"""
import csv, os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel.api import _db_connect

APP = "/opt/qbot/app"
DRY = "--dry-run" in sys.argv
USER = sys.argv[sys.argv.index("--user") + 1] if "--user" in sys.argv else "admin"
NOTE = "brak w Garmin"


def main():
    rows = list(csv.DictReader(open(f"{APP}/sql/trainer_garmin_map_v1.csv", encoding="utf-8"), delimiter=";"))
    con = _db_connect()
    try:
        cur = con.cursor()
        cur.execute("SELECT kod FROM qbot_v2.garmin_exercise")
        kody = {r[0] for r in cur.fetchall()}
        bad = [r["garmin_kod"] for r in rows if r["garmin_kod"] and r["garmin_kod"] not in kody]
        assert not bad, f"kody spoza katalogu: {bad}"
        n_map = n_x = 0
        for r in rows:
            kod = r["garmin_kod"] or None
            cur.execute("UPDATE qbot_v2.trainer_exercise SET garmin_kod=%s WHERE key=%s", (kod, r["key"]))
            n_map += cur.rowcount
            if not kod:
                cur.execute("SELECT tier FROM qbot_v2.trainer_exercise_user WHERE username=%s AND key=%s", (USER, r["key"]))
                ex = cur.fetchone()
                if ex and ex[0] not in (None, "X"):
                    print("pomijam (ocena uzytkownika):", r["key"], ex[0])
                    continue
                cur.execute(
                    """INSERT INTO qbot_v2.trainer_exercise_user (username, key, tier, note, updated_at)
                       VALUES (%s,%s,'X',%s, now())
                       ON CONFLICT (username, key) DO UPDATE SET tier='X',
                         note=CASE WHEN coalesce(qbot_v2.trainer_exercise_user.note,'')='' THEN EXCLUDED.note
                                   ELSE qbot_v2.trainer_exercise_user.note END,
                         updated_at=now()""",
                    (USER, r["key"], NOTE),
                )
                n_x += 1
        print("zmapowane wiersze:", n_map, "wylaczone (X):", n_x)
        if DRY:
            con.rollback(); print("DRY-RUN: wycofano")
        else:
            con.commit()
    finally:
        con.close()


if __name__ == "__main__":
    main()
