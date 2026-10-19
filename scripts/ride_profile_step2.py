# -*- coding: utf-8 -*-
"""Profile jazd -- krok 2 (2026-10-19): tempo i postoje per profil + walidacja LOO. NIC nie zmienia w modelu.
Wejscie: data/ride_features.json (krok 1). Wyjscie: data/ride_profiles_step2.json + raport na stdout.
Uruchom: .venv/bin/python3 scripts/ride_profile_step2.py [--limit N]
Klasy (decyzje Michala 19.10): bikepacking = ciag dni A->B (meta dnia N = start dnia N+1, poza domem);
miasto = jazda po Warszawie (dojazdy i petle przez centrum); dluga = czas ruchu >= p75 jazd z tej pory roku (min 2 h);
poza domem bez bagazu: tylko dlugosc (dzien tygodnia bez znaczenia); reszta: pn-pt trening, sb-nd krotka."""
import json, math, os, sys, time
from collections import defaultdict
from datetime import date, timedelta
sys.path.insert(0, "/opt/qbot/app"); sys.path.insert(0, "/opt/qbot/app/scripts")
os.environ.setdefault("QBOT3_ENABLED", "1")
import speed_model_review_v2 as V2
import speed_table_review as STR
from fitmodel.ftp_resolver import _db_connect

ACT = json.load(open("/opt/qbot/app/config/speed_model.json"))
TAB = ACT["table"]["normalny"]
F = json.load(open("/opt/qbot/app/data/ride_features.json"))
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None


def dk(a, b):
    la = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(la))


t0 = time.time()
conn = _db_connect(); cur = conn.cursor()
for f in F:
    cur.execute("SELECT (SELECT ARRAY[lat,lon] FROM qbot_v2.activity_record WHERE external_id=%s AND lat IS NOT NULL ORDER BY sec LIMIT 1), "
                "(SELECT ARRAY[lat,lon] FROM qbot_v2.activity_record WHERE external_id=%s AND lat IS NOT NULL ORDER BY sec DESC LIMIT 1)",
                (f["id"], f["id"]))
    f["s"], f["e"] = cur.fetchone()

# --- bikepacking: ciagi dni A->B
by = defaultdict(list)
for f in F:
    by[f["date"]].append(f)
stage = lambda f: f["s"] and f.get("a_to_b", 0) > 10 and min(f.get("start_home", 0), f.get("end_home", 0)) > 30
bp_ids, cur_seq = set(), []
def close(seq):
    if len(seq) >= 2:
        bp_ids.update(x["id"] for x in seq)
for d in sorted(by):
    st = [x for x in by[d] if stage(x)]
    if not st:
        close(cur_seq); cur_seq = []; continue
    x = st[0]
    if cur_seq and date.fromisoformat(d) - date.fromisoformat(cur_seq[-1]["date"]) == timedelta(days=1) and dk(cur_seq[-1]["e"], x["s"]) < 5:
        cur_seq.append(x)
    else:
        close(cur_seq); cur_seq = [x]
close(cur_seq)

for f in F:
    if f["id"] in bp_ids:
        f["cls"] = "bikepacking"
    elif f["cls"] == "commuting":
        f["cls"] = "miasto"
    elif f["cls"] in ("trening", "krotka_weekend") and f.get("away"):
        f["cls"] = "krotka_weekend"      # wyjazd bez bagazu: liczy sie tylko dlugosc
    elif f["cls"] == "bikepacking":    # stara lista dat, ale nie ciag A->B
        f["cls"] = "dluga" if f["mov_h"] >= 2 else "krotka_weekend"

# --- tempo: przewidziany czas ruchu (aktywna tabela) vs rzeczywisty; postoje
rows = []
todo = [f for f in F if f["km"] >= 10]
if LIMIT:
    todo = todo[:LIMIT]
for f in todo:
    try:
        res = STR.process_ride(cur, f["id"])
    except Exception:
        conn.rollback(); res = None
    if not res or len(res[0]) < 600:
        continue
    smp = res[0]
    s = V2.stops(cur, f["id"])
    rows.append(dict(id=f["id"], date=f["date"], cls=f["cls"], km=f["km"], temp=f.get("temp"),
                     act_s=len(smp), pred_s=V2.pred_s(smp, TAB), samp_km=sum(x[2] for x in smp) / 3600.0,
                     mov_h=s[0] if s else None, mikro=(s[1].get("mikro", 0.0) if s else None),
                     krotkie=(s[1].get("krotkie", 0.0) if s else None)))
conn.close()

CL = ("bikepacking", "miasto", "dluga", "krotka_weekend", "trening")
def factor(rs):   # przewidziany/rzeczywisty (czasowo wazony); >1 = szybciej niz tabela
    a = sum(r["act_s"] for r in rs)
    return sum(r["pred_s"] for r in rs) / a if a else 1.0

print("jazd z analiza 1 Hz: %d / %d, %.0f s" % (len(rows), len(todo), time.time() - t0))
out = {"version": "step2-" + date.today().isoformat(), "profiles": {}}
FREE = {"bikepacking": 0.0}
avg = lambda xs: sum(xs) / len(xs)
for k in CL:
    rs = [r for r in rows if r["cls"] == k]
    if not rs:
        continue
    fac = factor(rs)
    st = [r for r in rs if r["mov_h"]]
    h0 = FREE.get(k, ACT["stops"]["normal"]["free_h"])
    den = sum(max(0.0, r["mov_h"] - h0) for r in st)
    short = round(sum(r["krotkie"] for r in st) / den, 1) if den else None
    micro = round(sum(r["mikro"] for r in st) / sum(r["km"] for r in st), 2) if st else None
    old_e, new_e = [], []
    for r in rs:
        f_loo = factor([x for x in rs if x is not r]) if len(rs) > 1 else 1.0
        old_e.append((r["pred_s"] - r["act_s"]) / r["act_s"] * 100)
        new_e.append((r["pred_s"] / f_loo - r["act_s"]) / r["act_s"] * 100)
    p = dict(rides=len(rs), hours=round(sum(r["act_s"] for r in rs) / 3600, 1), speed_factor=round(fac, 3),
             short_min_per_h=short, micro_min_per_km=micro, free_h=h0,
             err_old=round(avg(old_e), 1), err_new=round(avg(new_e), 1),
             abs_old=round(avg([abs(x) for x in old_e]), 1), abs_new=round(avg([abs(x) for x in new_e]), 1))
    out["profiles"][k] = p
    print("%-15s n=%3d %5.0f h  tempo x%.3f  postoje krotkie %s min/h, mikro %s min/km | blad: %+.1f%% -> %+.1f%%, typowy %.1f%% -> %.1f%%" % (
        k, p["rides"], p["hours"], fac, short, micro, p["err_old"], p["err_new"], p["abs_old"], p["abs_new"]))
tb = defaultdict(list)
for r in rows:
    if r["temp"] is None or r["cls"] == "bikepacking":
        continue
    fp = out["profiles"][r["cls"]]["speed_factor"]
    tb["<5" if r["temp"] < 5 else "5-12" if r["temp"] < 12 else "12-20" if r["temp"] < 20 else ">=20"].append(r["pred_s"] / fp / r["act_s"])
for k in ("<5", "5-12", "12-20", ">=20"):
    if tb[k]:
        print("temp %-6s n=%3d  po profilu: tempo x%.3f" % (k, len(tb[k]), avg(tb[k])))
json.dump({"out": out, "rides": rows}, open("/opt/qbot/app/data/ride_profiles_step2.json", "w"), ensure_ascii=False, indent=0)
