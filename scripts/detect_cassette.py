#!/usr/bin/env python3
"""Wykrywanie kasety per jazda z FIZYKI (rozwiniecie), nie z heurystyki.

Zasada
------
Dla kazdej pozycji przerzutki (activity_record.gear_rear_num -- KANON;
gear_rear_t = zeby z konfiguracji AXS BYWA NIEAKTUALNY i NIE jest uzywany)
liczymy mediane rozwiniecia:

    mpr = predkosc[m/s] * 60 / kadencja[rpm]   -> metry na obrot korby

mpr = przelozenie * obwod_kola = (zeby_przod / zeby_tyl) * C.

Ksztalt krzywej mpr(pozycja) jednoznacznie wskazuje kasete BEZ znajomosci
obwodu kola i zebatki z przodu -- obie te wielkosci sa wspolnym mnoznikiem,
ktory dopasowujemy jako skale. Rozstrzyga wzajemny stosunek zebatek.

Filtry probek: kadencja 60-100 rpm, predkosc > 2.5 m/s, moc > 60 W,
min. 25 sekund na pozycji, min. 5 pozycji na jazde.

Pewnosc: blad dopasowania (mediana bledu wzglednego) + margines nad drugim
kandydatem. Jazdy bez rozstrzygniecia dostaja kasete z najblizszej w czasie
jazdy pewnej (kaset nie zmienia sie z dnia na dzien) -- source='physics_fill'.

Wpisy source='manual' NIGDY nie sa nadpisywane.

Uzycie:
    .venv/bin/python3 scripts/detect_cassette.py --dry-run
    .venv/bin/python3 scripts/detect_cassette.py --apply
    .venv/bin/python3 scripts/detect_cassette.py --ride 23932728831 --apply
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from fitmodel.api import _db_connect  # noqa: E402

CHAINRING_ASSUMED = 36.0   # tylko skala; nie wplywa na wybor kasety
MIN_SAMPLES_PER_POS = 25
MIN_POSITIONS = 5
CONF_ERR_HIGH = 1.0        # % -- prog bledu dla pewnosci "wysoka"
CONF_MARGIN_HIGH = 3.0     # x  -- przewaga nad drugim kandydatem
CONF_MARGIN_MID = 2.0

SQL_MPR = """
select gear_rear_num,
       count(*) as n,
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

SQL_RIDES = """
select external_id, min(ts)::date as day
from qbot_v2.activity_record
where gear_rear_num is not null
group by 1
order by 2
"""


def load_cassettes(conn):
    cur = conn.cursor()
    cur.execute("select code, cogs from qbot_v2.gear_cassette")
    return {code: list(cogs) for code, cogs in cur.fetchall()}


def cog_at(cogs, pos):
    """pozycja 1 = najlzejszy bieg = najwieksza zebatka."""
    if 1 <= pos <= len(cogs):
        return cogs[len(cogs) - pos]
    return None


def measure(conn, external_id):
    cur = conn.cursor()
    cur.execute(SQL_MPR, (external_id, MIN_SAMPLES_PER_POS))
    return {int(p): float(v) for p, _n, v in cur.fetchall() if v}


def detect(mpr, cassettes):
    """Zwraca dict z wynikiem albo None gdy za malo danych."""
    if len(mpr) < MIN_POSITIONS:
        return None
    scored = []
    for code, cogs in cassettes.items():
        pairs = [(cog_at(cogs, p), v) for p, v in mpr.items() if cog_at(cogs, p)]
        if len(pairs) < MIN_POSITIONS:
            continue
        circ = statistics.median(v * t / CHAINRING_ASSUMED for t, v in pairs)
        err = statistics.median(
            abs(v - CHAINRING_ASSUMED * circ / t) / v * 100.0 for t, v in pairs)
        scored.append((err, code, circ))
    if not scored:
        return None
    scored.sort()
    err, code, circ = scored[0]
    second = scored[1][0] if len(scored) > 1 else float("inf")
    margin = (second / err) if err > 0 else float("inf")
    if err <= CONF_ERR_HIGH and margin >= CONF_MARGIN_HIGH:
        conf = "wysoka"
    elif margin >= CONF_MARGIN_MID:
        conf = "srednia"
    else:
        conf = "niska"
    return {"code": code, "err_pct": err, "margin": margin,
            "circumference_m": circ, "positions": len(mpr), "confidence": conf}


def note_text(res):
    return ("fizyka rozwiniecia: blad %.2f%%, margines x%.1f, "
            "pozycji %d, obwod ~%.3f m, pewnosc %s"
            % (res["err_pct"], res["margin"], res["positions"],
               res["circumference_m"], res["confidence"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ride", help="pojedyncza jazda (external_id)")
    ap.add_argument("--apply", action="store_true", help="zapisz do ride_cassette")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = _db_connect()
    cassettes = load_cassettes(conn)
    cur = conn.cursor()

    if args.ride:
        rides = [(args.ride, None)]
    else:
        cur.execute(SQL_RIDES)
        rides = [(r[0], r[1]) for r in cur.fetchall()]

    cur.execute("select external_id, cassette_code, source from qbot_v2.ride_cassette")
    existing = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    results = {}
    for rid, day in rides:
        results[rid] = (day, detect(measure(conn, rid), cassettes))

    # uzupelnienie niepewnych z najblizszej pewnej jazdy w czasie
    anchors = [(day, r["code"]) for _rid, (day, r) in results.items()
               if r and day and r["confidence"] in ("wysoka", "srednia")]
    anchors.sort()

    plan = []
    for rid, (day, res) in results.items():
        old_code, old_src = existing.get(rid, (None, None))
        if old_src == "manual":
            plan.append((rid, day, old_code, "manual", "pominiete (wpis reczny)", res))
            continue
        if res and res["confidence"] in ("wysoka", "srednia"):
            plan.append((rid, day, res["code"], "physics", note_text(res), res))
        elif anchors and day:
            near = min(anchors, key=lambda a: abs((a[0] - day).days))
            plan.append((rid, day, near[1], "physics_fill",
                         "za malo danych; z najblizszej pewnej jazdy %s" % near[0], res))
        else:
            plan.append((rid, day, None, None, "brak rozstrzygniecia", res))

    zmiany = 0
    for rid, day, code, src, note, res in sorted(plan, key=lambda x: (x[1] or "")):
        old_code = existing.get(rid, (None, None))[0]
        mark = ""
        if code and code != old_code:
            mark = "  <<< ZMIANA (bylo %s)" % (old_code or "brak")
            zmiany += 1
        print("%s %s -> %-6s [%s] %s%s" % (rid, day, code, src or "-", note, mark))

    print("\nrazem jazd: %d, zmian: %d" % (len(plan), zmiany))

    if args.apply:
        n = 0
        for rid, _day, code, src, note, _res in plan:
            if not code or src == "manual":
                continue
            cur.execute(
                "insert into qbot_v2.ride_cassette (external_id, cassette_code, source, note) "
                "values (%s, %s, %s, %s) "
                "on conflict (external_id) do update set cassette_code = excluded.cassette_code, "
                "source = excluded.source, note = excluded.note",
                (rid, code, src, note))
            n += 1
        conn.commit()
        print("zapisano wierszy: %d" % n)
    else:
        print("(dry-run -- nic nie zapisano; uzyj --apply)")
    conn.close()


if __name__ == "__main__":
    main()
