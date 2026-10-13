#!/usr/bin/env python3
"""Jednorazowo 2026-10-13: cala historia wagi z Garmina do QBota.
1) kopia qbot_v2.body_measurements -> qbot_v2.body_measurements_backup_20261013
2) qbot3/connectors/rebuild_garmin_body_measurements.py --from-date 2015-01-01 --apply (379 dni zamiast 51)
3) fitmodel_daily.weight_kg: TYLKO puste dni wypelnione ostatnim pomiarem z maks. 14 dni wstecz
   (istniejace wartosci od 2026-06-05 NIETKNIETE) + w_per_kg dla tych dni (progi ModelQ nietkniete).
Uruchomienie (root, z .env): set -a; . .env; set +a; .venv/bin/python3 scripts/waga_backfill_20261013.py
"""
import os
import subprocess
import sys

sys.path.insert(0, "/opt/qbot/app")
import psycopg

MAX_GAP = 14


def conn():
    return psycopg.connect(host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                           dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                           password=os.getenv("PGPASSWORD", ""))


with conn() as c:
    c.execute("DROP TABLE IF EXISTS qbot_v2.body_measurements_backup_20261013")
    c.execute("CREATE TABLE qbot_v2.body_measurements_backup_20261013 AS SELECT * FROM qbot_v2.body_measurements")
    n = c.execute("SELECT count(*) FROM qbot_v2.body_measurements_backup_20261013").fetchone()[0]
    print("kopia body_measurements:", n, flush=True)

r = subprocess.run([sys.executable, "qbot3/connectors/rebuild_garmin_body_measurements.py",
                    "--from-date", "2015-01-01", "--to-date", "2026-10-13", "--apply"],
                   cwd="/opt/qbot/app", capture_output=True, text=True, timeout=900)
print(r.stdout[-2500:], r.stderr[-1500:], flush=True)
if r.returncode != 0:
    sys.exit("rebuild nieudany - fitmodel_daily nietkniete")

with conn() as c:
    n, a, b = c.execute("SELECT count(*), min(date), max(date) FROM qbot_v2.body_measurements").fetchone()
    print("body_measurements po:", n, a, b, flush=True)
    upd = c.execute(f"""
        UPDATE qbot_v2.fitmodel_daily f SET weight_kg = s.w
        FROM (
          SELECT f2.day, (SELECT b.weight_kg FROM qbot_v2.body_measurements b
                          WHERE b.weight_kg IS NOT NULL AND b.date <= f2.day AND b.date > f2.day - {MAX_GAP}
                          ORDER BY b.date DESC LIMIT 1) AS w
          FROM qbot_v2.fitmodel_daily f2 WHERE f2.weight_kg IS NULL
        ) s
        WHERE f.day = s.day AND s.w IS NOT NULL AND f.weight_kg IS NULL
    """).rowcount
    print("fitmodel_daily: uzupelnione dni wagi:", upd, flush=True)
    wk = c.execute("UPDATE qbot_v2.fitmodel_daily SET w_per_kg = ftp_est_w / weight_kg "
                   "WHERE w_per_kg IS NULL AND weight_kg > 0 AND ftp_est_w IS NOT NULL").rowcount
    print("w_per_kg uzupelnione:", wk, flush=True)
    for row in c.execute("SELECT extract(year from day)::int, count(weight_kg) FROM qbot_v2.fitmodel_daily GROUP BY 1 ORDER BY 1"):
        print("  rok", row[0], "dni z waga", row[1])
