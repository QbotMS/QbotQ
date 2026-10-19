# -*- coding: utf-8 -*-
"""Profile jazd -- analiza na PELNYCH jazdach (2026-10-19): czas ruchu = rekordy > 0,5 m/s (jak raport z jazdy),
model = tabela przeskalowana na caly dystans; postoje = mikro + krotkie (dlugie >= 20 min poza modelem, jak w Analizie trasy).
Brutto = ruch + mikro + krotkie. Walidacja LOO: obecny model vs profile (z calej historii / z 365 dni)."""
import json, os
from collections import defaultdict
from datetime import date, timedelta
R = [r for r in json.load(open("/opt/qbot/app/data/ride_profiles_step2.json"))["rides"] if r.get("mov_h") and r.get("samp_km")]
S = json.load(open("/opt/qbot/app/config/speed_model.json"))["stops"]
avg = lambda xs: sum(xs) / len(xs) if xs else 0
for r in R:
    r["pf_h"] = r["pred_s"] / 3600 * r["km"] / r["samp_km"]          # model ruchu na caly dystans
    r["st"] = r["mikro"] + r["krotkie"]                              # postoje bez dlugich [min]
    r["br"] = r["mov_h"] + r["st"] / 60                              # brutto fakt [h]
def cur_model(r):
    p = S["bikepacking" if r["cls"] == "bikepacking" else "normal"]
    f = 0.92 if r["cls"] == "bikepacking" else 1.0
    mv = r["pf_h"] / f
    return mv, p["micro_min_per_km"] * r["km"] + p["short_min_per_h"] * max(0, mv - p["free_h"])
def fit(pool):
    if len(pool) < 5:
        return None
    nf = sum(x["pf_h"] for x in pool) / sum(x["mov_h"] for x in pool)            # mnoznik tempa netto
    mic = sum(x["mikro"] for x in pool) / sum(x["km"] for x in pool)
    sh = sum(x["krotkie"] for x in pool) / sum(x["mov_h"] for x in pool)
    return nf, mic, sh
def prof_model(r, pool):
    p = fit(pool)
    if not p:
        return cur_model(r)
    nf, mic, sh = p
    if os.environ.get("ONLY_STOPS"):
        nf = 0.92 if r["cls"] == "bikepacking" else 1.0   # tempo z tabeli (poziom 120 dni), profil tylko postoje
    mv = r["pf_h"] / nf
    return mv, mic * r["km"] + sh * mv
last = date.fromisoformat(max(r["date"] for r in R))
def run(test, window):
    e = defaultdict(lambda: {"cn": [], "pn": [], "cb": [], "pb": []})
    for r in test:
        d0 = date.fromisoformat(r["date"])
        pool = [x for x in R if x is not r and x["cls"] == r["cls"] and (window is None or 0 <= (d0 - date.fromisoformat(x["date"])).days <= window)]
        cm, cs = cur_model(r); pm, ps = prof_model(r, pool)
        for k in (r["cls"], "WSZYSTKIE"):
            e[k]["cn"].append((cm / r["mov_h"] - 1) * 100); e[k]["pn"].append((pm / r["mov_h"] - 1) * 100)
            e[k]["cb"].append(((cm + cs / 60) / r["br"] - 1) * 100); e[k]["pb"].append(((pm + ps / 60) / r["br"] - 1) * 100)
    return e
CL = ("WSZYSTKIE", "trening", "krotka_weekend", "dluga", "miasto", "bikepacking")
print("jazd: %d   (bledy: + = model za wolny, - = model za szybki/optymistyczny)" % len(R))
print("\nPROFIL (cala historia): tempo netto vs tabela, postoje")
for k in CL[1:]:
    p = fit([x for x in R if x["cls"] == k])
    if p:
        print("  %-15s n=%3d  tempo x%.3f  mikro %.2f min/km  krotkie %.1f min/h" % (k, sum(1 for x in R if x["cls"] == k), p[0], p[1], p[2]))
for lab, test, W in (("CALA HISTORIA, profil z calej historii", R, None),
                     ("OSTATNIE 120 DNI, profil z calej historii", [r for r in R if (last - date.fromisoformat(r["date"])).days <= 120], None),
                     ("OSTATNIE 120 DNI, profil z 365 dni", [r for r in R if (last - date.fromisoformat(r["date"])).days <= 120], 365)):
    e = run(test, W)
    print("\n" + lab)
    print("  %-15s %4s | %-26s | %-26s" % ("", "n", "NETTO sredni/typowy  obecny->profil", "BRUTTO sredni/typowy obecny->profil"))
    for k in CL:
        if not e[k]["cn"]:
            continue
        x = e[k]
        print("  %-15s %4d | %+5.1f/%4.1f%% -> %+5.1f/%4.1f%% | %+5.1f/%4.1f%% -> %+5.1f/%4.1f%%" % (
            k, len(x["cn"]), avg(x["cn"]), avg([abs(v) for v in x["cn"]]), avg(x["pn"]), avg([abs(v) for v in x["pn"]]),
            avg(x["cb"]), avg([abs(v) for v in x["cb"]]), avg(x["pb"]), avg([abs(v) for v in x["pb"]])))
