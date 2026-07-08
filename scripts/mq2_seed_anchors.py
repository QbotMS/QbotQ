"""Seed zamrozonych kotwic ModelQ v2 -> qbot_v2.modelq2_anchor.

Kotwice przepisane RAZ z Xerta (2025-12-27, 2026-02-22, 2026-03-29, 2026-05-16, 2026-06-20) i ZAMROZONE
jako wlasny parametr MQ2. Od tego momentu MQ2 nie potrzebuje zywego Xerta do dzialania:
TP dryfuje za NASZYM CTL wokol tych kotwic, HIE/PP za wlasnym TL. Zero v1, zero zywego Xerta.

ctl_anchor = CTL (nasze, z XSS) w dniu kotwicy -- zapisane do audytu; progression i tak
przelicza je z loads (make_anchor), wiec ta kolumna sluzy tylko przejrzystosci.

Idempotentny (ON CONFLICT UPDATE). Uruchom raz przy odtwarzaniu bazy:
  /opt/qbot/app/.venv/bin/python3 scripts/mq2_seed_anchors.py
"""
import os, sys
os.environ.setdefault("QBOT3_ENABLED", "1")
sys.path.insert(0, "/opt/qbot/app")
from fitmodel.ftp_resolver import _db_connect

# ZAMROZONE wartosci (przepisane z Xerta). Nie zmieniac bez swiadomej rekalibracji.
ANCHORS = [
    # day,        tp_w, hie_kj, pp_w, ctl_anchor
    ("2025-12-27", 244, 20.6, 1002, 44.0),
    ("2026-02-22", 239, 20.2, 986, 32.6),   # luka zima-wiosna (marzec zanizal, niskie CTL)
    ("2026-03-29", 245, 22.5, 1030, 61.8),
    ("2026-05-16", 245, 21.3, 1006, 59.6),  # luka wiosna-lato (maj daleko od obu kotwic)
    ("2026-06-20", 251, 22.7, 1009, 76.1),
]


def main():
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.modelq2_anchor(
        day date PRIMARY KEY,
        tp_w real NOT NULL, hie_kj real NOT NULL, pp_w real NOT NULL,
        ctl_anchor real NOT NULL, note text, frozen_at timestamptz DEFAULT now())""")
    for day, tp, hie, pp, ctl in ANCHORS:
        cur.execute("""INSERT INTO qbot_v2.modelq2_anchor(day,tp_w,hie_kj,pp_w,ctl_anchor,note)
            VALUES(%s,%s,%s,%s,%s,'kotwica przepisana z Xert (zamrozona)')
            ON CONFLICT(day) DO UPDATE SET tp_w=EXCLUDED.tp_w,hie_kj=EXCLUDED.hie_kj,
              pp_w=EXCLUDED.pp_w,ctl_anchor=EXCLUDED.ctl_anchor""", (day, tp, hie, pp, ctl))
    conn.commit()
    cur.execute("SELECT day,tp_w,hie_kj,pp_w,ctl_anchor FROM qbot_v2.modelq2_anchor ORDER BY day")
    for r in cur.fetchall():
        print(r)
    conn.close()


if __name__ == "__main__":
    main()
