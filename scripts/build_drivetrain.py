#!/usr/bin/env python3
"""qbot_v2.ride_drivetrain -- naped per jazda: przod, kaseta, obwod kola.

Jedno zrodlo prawdy o przelozeniach dla calego systemu. Zamiast kazdy modul
zgadywal osobno (raport trasy po odleglosci od Wwy, ocena podjazdow na sztywno
36T), wszyscy czytaja stad.

Sklad wiersza
-------------
chainring_t     -- EFEKTYWNA liczba zebow z przodu, wprost z AXS (gear_front_t).
                   Do LICZENIA. Owal 40T raportuje sie jako 41 i tak ma zostac.
chainring_label -- do POKAZANIA czlowiekowi ("owal 40T", "36T").
cassette_code   -- z qbot_v2.ride_cassette (scripts/detect_cassette.py, pomiar
                   rozwiniecia; wpisy manual maja pierwszenstwo).
circumference_m -- obwod kola wyliczony z rozwiniecia przy znanym przodzie
                   i znanej kasecie. Rozroznia zestawy kol (TB 2.1 na 303 S XPLR
                   ~2.25-2.29 m; G-One Pro RS na 303 S ~2.14-2.17 m).
flag            -- 'ok' albo powod watpliwosci.

DLACZEGO przod z AXS, a tyl z pomiaru: przednia zebatka i obwod kola wystepuja
w danych WYLACZNIE jako iloczyn (rozwiniecie = przod/tyl * obwod), wiec przodu
nie da sie zmierzyc niezaleznie od kola. Za to konfiguracja AXS z przodu jest
wiarygodna (jedna zebatka, zmieniana przy serwisie), w odroznieniu od tylnej,
ktora rozjezdza sie przy przekladaniu kaset miedzy bebenkami.

Uzycie:
    .venv/bin/python3 scripts/build_drivetrain.py --dry-run
    .venv/bin/python3 scripts/build_drivetrain.py --apply
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel.api import _db_connect  # noqa: E402

CIRC_MIN, CIRC_MAX = 2.05, 2.40      # sensowny obwod kola 700c gravel [m]
MIN_SAMPLES_PER_POS = 25
MIN_POSITIONS = 4

# efektywne zeby z AXS -> jak to nazwac czlowiekowi
CHAINRING_LABELS = {41: "owal 40T (41 efekt.)", 40: "40T", 36: "36T"}

DDL = """
create table if not exists qbot_v2.ride_drivetrain (
    external_id     text primary key,
    day             date,
    chainring_t     smallint,
    chainring_label text,
    cassette_code   text,
    cassette_source text,
    circumference_m real,
    positions       smallint,
    flag            text,
    note            text,
    computed_at     timestamptz not null default now()
)
"""

SQL_RIDES = """
select a.external_id,
       min(a.ts)::date as day,
       mode() within group (order by a.gear_front_t) as front_t,
       rc.cassette_code, rc.source
from qbot_v2.activity_record a
left join qbot_v2.ride_cassette rc on rc.external_id = a.external_id
where a.gear_rear_num is not null
group by a.external_id, rc.cassette_code, rc.source
order by 2
"""

SQL_MPR = """
select gear_rear_num,
       percentile_cont(0.5) within group (order by speed_mps * 60.0 / cadence_rpm)
from qbot_v2.activity_record
where external_id = %s
  and gear_rear_num is not null
  and cadence_rpm between 60 and 100
  and speed_mps > 2.5
  and power_w > 60
group by 1
having count(*) >= %s
"""


def cog_at(cogs, pos):
    return cogs[len(cogs) - pos] if 1 <= pos <= len(cogs) else None


def build_row(conn, cassettes, external_id, day, front_t, cass_code, cass_src):
    flags = []
    if not front_t:
        flags.append("brak przedniej zebatki z AXS")
    if not cass_code:
        flags.append("brak kasety")

    circ = None
    npos = 0
    if front_t and cass_code and cass_code in cassettes:
        cur = conn.cursor()
        cur.execute(SQL_MPR, (external_id, MIN_SAMPLES_PER_POS))
        cogs = cassettes[cass_code]
        vals = []
        for pos, mpr in cur.fetchall():
            t = cog_at(cogs, int(pos))
            if t and mpr:
                vals.append(float(mpr) * t / float(front_t))
        npos = len(vals)
        if npos >= MIN_POSITIONS:
            circ = statistics.median(vals)
            if not (CIRC_MIN <= circ <= CIRC_MAX):
                flags.append("obwod %.3f m poza zakresem -- sprawdz przod albo kola"
                             % circ)
        else:
            flags.append("za malo danych na obwod (%d poz.)" % npos)

    return {
        "external_id": external_id,
        "day": day,
        "chainring_t": front_t,
        "chainring_label": CHAINRING_LABELS.get(front_t,
                                                ("%dT" % front_t) if front_t else None),
        "cassette_code": cass_code,
        "cassette_source": cass_src,
        "circumference_m": circ,
        "positions": npos,
        "flag": "ok" if not flags else "uwaga",
        "note": "; ".join(flags) if flags else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = _db_connect()
    cur = conn.cursor()
    if args.apply:
        cur.execute(DDL)
        conn.commit()

    cur.execute("select code, cogs from qbot_v2.gear_cassette")
    cassettes = {c: list(g) for c, g in cur.fetchall()}

    cur.execute(SQL_RIDES)
    rides = cur.fetchall()

    rows = [build_row(conn, cassettes, *r) for r in rides]

    for r in rows:
        print("%s %s  %-20s %-6s obwod=%-7s poz=%2d  %s%s" % (
            r["external_id"], r["day"], r["chainring_label"] or "-",
            r["cassette_code"] or "-",
            ("%.3f" % r["circumference_m"]) if r["circumference_m"] else "-",
            r["positions"], r["flag"],
            (" -- " + r["note"]) if r["note"] else ""))
    nok = sum(1 for r in rows if r["flag"] == "ok")
    print("\njazd: %d, ok: %d, z uwaga: %d" % (len(rows), nok, len(rows) - nok))

    if args.apply:
        for r in rows:
            cur.execute(
                "insert into qbot_v2.ride_drivetrain (external_id, day, chainring_t, "
                "chainring_label, cassette_code, cassette_source, circumference_m, "
                "positions, flag, note, computed_at) "
                "values (%(external_id)s, %(day)s, %(chainring_t)s, %(chainring_label)s, "
                "%(cassette_code)s, %(cassette_source)s, %(circumference_m)s, "
                "%(positions)s, %(flag)s, %(note)s, now()) "
                "on conflict (external_id) do update set "
                "day=excluded.day, chainring_t=excluded.chainring_t, "
                "chainring_label=excluded.chainring_label, "
                "cassette_code=excluded.cassette_code, "
                "cassette_source=excluded.cassette_source, "
                "circumference_m=excluded.circumference_m, "
                "positions=excluded.positions, flag=excluded.flag, "
                "note=excluded.note, computed_at=now()", r)
        conn.commit()
        print("zapisano wierszy: %d" % len(rows))
    else:
        print("(dry-run -- nic nie zapisano; uzyj --apply)")
    conn.close()


if __name__ == "__main__":
    main()
