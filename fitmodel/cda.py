# -*- coding: utf-8 -*-
"""CENTRUM CdA (v1, 2026-10-18) -- opor powietrza z ZWYKLYCH jazd, bez testow. Zakladka Forma > Centrum CdA.

Na jazde (1 Hz z activity_record):
  odcinki 30 s (co 10 s): plasko (|nachylenie| <= 2 %), predkosc >= 5,5 m/s, moc >= 60 W i rowna (CV <= 25 %),
  kadencja >= 50, kierunek prosty (zmiana <= 35 st.), nawierzchnia z raportu jazdy kat. 1-2 (twarda szybka / dobry gravel).
  Moc na powietrze = moc*0,976 - m*g*v*(nachylenie + Crr) - zmiana energii kinetycznej.
  WIATR liczony Z SAMEJ JAZDY: siatka sila 0-7 m/s x kierunek co 10 st., CdA metoda najmniejszych kwadratow -> minimum bledu
  (proba 16.10, scripts/_tmp_aero_wind.py: wyjasnia 35-80 % rozrzutu). Masa = waga dnia + fitmodel.meter_physics.EXTRA_KG.
Pomijane jazdy (jedna lista prawdy o mocy -- DECISIONS 2026-10-18): kwarantanna miernika (released IS NULL),
  zly okres miernika lthr.METER_BAD, rozjazd moc/tetno load_guard (stosunek XSS poza LO-HI), < MIN_WIN odcinkow.
ZALOZENIA v1 (pokazywane na stronie): Crr kat.1 = 0,0055, kat.2 = 0,0085 (nie liczone -- to krok 3 [AERO-CDA]);
  kat. 3-5 i nieznana nawierzchnia nie wchodza do liczenia.
Rower: regula Michala -- AXS 27856 = Grail, AXS 10625 = Grizl, brak AXS przy mierniku = Monster; FIT bez czujnikow = nieznany.
Tabela qbot_v2.ride_cda (jedna jazda = jeden wiersz, takze pominieta z powodem). Krok daily_job 'cda' (7 dni),
przeliczenie wstecz: .venv/bin/python3 fitmodel/cda.py --backfill 2026-06-16 (w tle, Telegram na koniec).
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import sqlite3
import statistics as st

G, ETA, WIN, STEP = 9.81, 0.976, 30, 10
CRR = {1: 0.0055, 2: 0.0085}
MIN_WIN = 12
AXS_BIKE = {27856: "Grail", 10625: "Grizl"}
CANON_DAYS = 120
GARAGE_DB = "/opt/qbot/app/data/garage.db"
# warstwy pod spodem (termika) nie zmieniaja oporu powietrza -- nie porownujemy (inaczej wychodza pozorne roznice z pory roku)
CMP_SLOTS = ["Kurtka", "Kamizelka", "Koszulka / bluza", "Nakrycie głowy", "Komin i chusta", "Nogawki", "wheels"]
CMP_MIN = 5     # min. jazd z rzecza i bez niej, zeby podac wynik
CMP_SURE = 8    # od tylu jazd po obu stronach wynik moze byc "pewne"

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.ride_cda (
    external_id   text PRIMARY KEY,
    ride_date     date,
    bike          text,
    meter_key     text,
    n_windows     integer,
    dir_spread    real,
    wind_ms       real,
    wind_from_deg real,
    cda           real,
    cda_se        real,
    explained_pct real,
    rho           real,
    status        text,      -- OK / POMINIETA
    reason        text,
    computed_at   timestamptz NOT NULL DEFAULT now())"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


# ---------------- obliczenia na jedna jazde ----------------

def _bearing(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    return math.atan2(math.sin(dl) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))


def windows(rows, trace, mass, hpa):
    """rows: (sec, power, speed, distance, altitude, cadence, temp, lat, lon). -> [(aero_W, v, rho, heading)]"""
    kms = (trace or {}).get("km")
    cats = (trace or {}).get("surface_cat")
    out, i = [], 0
    while i + WIN < len(rows):
        w = rows[i:i + WIN + 1]
        i += STEP
        if any(x[1] is None or x[2] is None or x[3] is None or x[4] is None or x[7] is None for x in w):
            continue
        p = [x[1] for x in w[1:]]
        v = [x[2] for x in w]
        pm = st.mean(p)
        if min(p) < 60 or st.mean(v) < 5.5 or min(v) < 4.5 or st.pstdev(p) / pm > 0.25:
            continue
        cad = [x[5] for x in w if x[5] is not None]
        if not cad or min(cad) < 50:
            continue
        dist = w[-1][3] - w[0][3]
        if dist < 120:
            continue
        grade = (w[-1][4] - w[0][4]) / dist
        if abs(grade) > 0.02:
            continue
        h1 = _bearing(w[0][7], w[0][8], w[WIN // 2][7], w[WIN // 2][8])
        h2 = _bearing(w[WIN // 2][7], w[WIN // 2][8], w[-1][7], w[-1][8])
        if abs(math.atan2(math.sin(h1 - h2), math.cos(h1 - h2))) > math.radians(35):
            continue
        if not kms or not cats:
            continue
        j = max(0, min(len(kms) - 1, bisect.bisect_left(kms, w[WIN // 2][3] / 1000)))
        scat = cats[j]
        if scat not in CRR:
            continue
        vm = dist / WIN
        tc = st.mean([x[6] for x in w if x[6] is not None] or [12])
        rho = hpa * 100 / (287.05 * (tc + 273.15))
        kin = 0.5 * mass * (v[-1] ** 2 - v[0] ** 2) / WIN
        aero = pm * ETA - mass * G * vm * (grade + CRR[scat]) - kin
        hdg = _bearing(w[0][7], w[0][8], w[-1][7], w[-1][8])
        out.append((aero, vm, rho, hdg))
    return out


def fit(ws):
    """(sse, cda, wind_ms, wind_from_deg) -- siatka wiatru, CdA najmniejsze kwadraty."""
    best = None
    for s4 in range(0, 29):
        s = s4 / 4
        for d10 in range(0, 36 if s > 0 else 1):
            th = math.radians(d10 * 10)
            xs = [(a, 0.5 * r * (v + s * math.cos(th - h)) ** 2 * v) for a, v, r, h in ws]
            den = sum(x * x for _a, x in xs)
            if den <= 0:
                continue
            cda = sum(a * x for a, x in xs) / den
            sse = sum((a - cda * x) ** 2 for a, x in xs)
            if best is None or sse < best[0]:
                best = (sse, cda, s, d10 * 10, den)
    return best


def spread(ws):
    c, s = sum(math.cos(w[3]) for w in ws), sum(math.sin(w[3]) for w in ws)
    return 1 - math.hypot(c, s) / len(ws)


def bike_and_meter(cur, eid):
    cur.execute("SELECT device_type, manufacturer, ant_device_number, serial_number FROM qbot_v2.activity_device "
                "WHERE external_id=%s", (eid,))
    rows = cur.fetchall()
    axs = [r[2] for r in rows if str(r[0]) == "34" and r[1] == "sram"]
    pm = [r for r in rows if r[0] == "bike_power"]
    meter = None
    if pm:
        meter = ("ant:%s" % pm[0][2]) if pm[0][2] is not None else ("sn:%s" % pm[0][3])
    if axs:
        bike = AXS_BIKE.get(axs[0], "AXS %s" % axs[0])
    elif pm:
        bike = "Monster"
    else:
        bike = None
    return bike, meter


def _excluded(cur, eid, day):
    from fitmodel.lthr import METER_BAD
    from fitmodel.load_guard import LO, HI
    cur.execute("SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine WHERE external_id=%s AND released IS NULL", (eid,))
    if cur.fetchone():
        return "kwarantanna miernika"
    if any(a <= day <= b for a, b in METER_BAD):
        return "zły okres miernika"
    cur.execute("SELECT ratio FROM qbot_v2.load_guard WHERE external_id=%s", (eid,))
    r = cur.fetchone()
    if r and r[0] is not None and not (LO <= float(r[0]) <= HI):
        return "moc i tętno się rozjeżdżają"
    return None


def compute_ride(cur, eid, day):
    """-> dict wiersza ride_cda."""
    from fitmodel.meter_physics import EXTRA_KG
    bike, meter = bike_and_meter(cur, eid)
    row = {"external_id": eid, "ride_date": day, "bike": bike, "meter_key": meter, "n_windows": 0,
           "dir_spread": None, "wind_ms": None, "wind_from_deg": None, "cda": None, "cda_se": None,
           "explained_pct": None, "rho": None, "status": "POMINIETA", "reason": None}
    why = _excluded(cur, eid, day)
    if why:
        row["reason"] = why
        return row
    cur.execute("SELECT w1_json FROM qbot_v2.ride_report_data WHERE ride_key=%s ORDER BY schema_version DESC LIMIT 1", (eid,))
    r = cur.fetchone()
    w1 = (json.loads(r[0]) if isinstance(r[0], str) else r[0]) if r else {}
    trace = (w1 or {}).get("trace")
    if not trace:
        row["reason"] = "brak raportu jazdy (nawierzchnia)"
        return row
    hpa = (((w1.get("weather") or {}).get("pressure_hpa") or {}).get("value")) or 1013
    cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE day<=%s AND weight_kg IS NOT NULL "
                "ORDER BY day DESC LIMIT 1", (day,))
    wr = cur.fetchone()
    mass = (float(wr[0]) if wr else 100.0) + EXTRA_KG
    cur.execute("SELECT sec, power_w, speed_mps, distance_m, altitude_m, cadence_rpm, temperature_c, lat, lon "
                "FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (eid,))
    rows = [tuple(x) for x in cur.fetchall()]
    ws = windows(rows, trace, mass, float(hpa))
    row["n_windows"] = len(ws)
    if len(ws) < MIN_WIN:
        row["reason"] = "za mało płaskich, równych odcinków"
        return row
    sse, cda, s, d, den = fit(ws)
    xs0 = [(w[0], 0.5 * w[2] * w[1] ** 3) for w in ws]
    n0 = sum(a * x for a, x in xs0) / sum(x * x for _a, x in xs0)
    sse0 = sum((a - n0 * x) ** 2 for a, x in xs0)
    row.update({"dir_spread": round(spread(ws), 3), "wind_ms": s, "wind_from_deg": d, "cda": round(cda, 4),
                "cda_se": round(math.sqrt(sse / max(1, len(ws) - 1) / den), 4),
                "explained_pct": round(100 * (1 - sse / sse0), 1) if sse0 else None,
                "rho": round(st.mean(w[2] for w in ws), 4), "status": "OK"})
    if not (0.15 <= cda <= 0.9):
        row.update({"status": "POMINIETA", "reason": "wynik poza zakresem fizycznym (%.2f)" % cda})
    return row


_UPSERT = ("INSERT INTO qbot_v2.ride_cda (external_id, ride_date, bike, meter_key, n_windows, dir_spread, wind_ms, "
           "wind_from_deg, cda, cda_se, explained_pct, rho, status, reason) VALUES "
           "(%(external_id)s,%(ride_date)s,%(bike)s,%(meter_key)s,%(n_windows)s,%(dir_spread)s,%(wind_ms)s,"
           "%(wind_from_deg)s,%(cda)s,%(cda_se)s,%(explained_pct)s,%(rho)s,%(status)s,%(reason)s) "
           "ON CONFLICT (external_id) DO UPDATE SET ride_date=EXCLUDED.ride_date, bike=EXCLUDED.bike, "
           "meter_key=EXCLUDED.meter_key, n_windows=EXCLUDED.n_windows, dir_spread=EXCLUDED.dir_spread, "
           "wind_ms=EXCLUDED.wind_ms, wind_from_deg=EXCLUDED.wind_from_deg, cda=EXCLUDED.cda, cda_se=EXCLUDED.cda_se, "
           "explained_pct=EXCLUDED.explained_pct, rho=EXCLUDED.rho, status=EXCLUDED.status, reason=EXCLUDED.reason, "
           "computed_at=now()")


def run(conn, lookback_days: int = 7, since: str | None = None, recheck: bool = False) -> dict:
    """Liczy jazdy (>10 km, z moca) z okna. Bez recheck: tylko te bez wpisu."""
    ensure_table(conn)
    cur = conn.cursor()
    if since:
        cond, arg = "t.date >= %s::date", since
    else:
        cond, arg = "t.date >= CURRENT_DATE - %s * interval '1 day'", lookback_days
    cur.execute("SELECT t.external_id, t.date FROM qbot_v2.training_sessions t WHERE " + cond +
                " AND t.avg_power_w IS NOT NULL AND t.distance_m > 10000 " +
                ("" if recheck else "AND NOT EXISTS (SELECT 1 FROM qbot_v2.ride_cda c WHERE c.external_id=t.external_id) ") +
                "ORDER BY t.date", (arg,))
    out = {"ok": 0, "pominiete": 0}
    for eid, day in cur.fetchall():
        row = compute_ride(cur, str(eid), day)
        cur.execute(_UPSERT, row)
        conn.commit()
        out["ok" if row["status"] == "OK" else "pominiete"] += 1
    return out


# ---------------- podsumowanie dla strony ----------------

def _wmedian(vals):
    """mediana wazona: vals = [(x, waga)]"""
    vals = sorted(vals)
    tot = sum(w for _x, w in vals)
    acc = 0.0
    for x, w in vals:
        acc += w
        if acc >= tot / 2:
            return x
    return vals[-1][0] if vals else None


def _q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    f = math.floor(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _status(n, lo, hi, med):
    if n < 3 or med is None:
        return "za mało danych"
    if n >= 8 and (hi - lo) / med <= 0.15:
        return "pewne"
    return "niepewne"


def _gear(ride_keys):
    """{ride_key: {slot: nazwa}} z Garazu (W czym jechalem)."""
    if not ride_keys:
        return {}
    g = sqlite3.connect(GARAGE_DB)
    try:
        names = {}
        for gid, brand, model in g.execute("SELECT id, brand, model FROM gear"):
            names[str(gid)] = ((brand or "") + " " + (model or "")).strip()
        try:
            for cid, brand, model in g.execute("SELECT id, brand, model FROM components"):
                names.setdefault("c%s" % cid, ((brand or "") + " " + (model or "")).strip())
        except Exception:
            pass
        out = {}
        q = "SELECT ride_key, slot, gear_id, value FROM ride_gear_log WHERE ride_key IN (%s)" % ",".join("?" * len(ride_keys))
        for rk, slot, gid, val in g.execute(q, list(ride_keys)):
            if slot not in CMP_SLOTS:
                continue
            if slot == "wheels":
                nm = names.get("c%s" % (val or gid)) or ("koła #%s" % (val or gid))
            else:
                nm = names.get(str(gid)) or (str(val) if val else None)
            if nm:
                out.setdefault(str(rk), {})[slot] = nm
        return out
    finally:
        g.close()


def _verdict(d, a, b):
    """Roznica srednich CdA z bledem; "pewne" tylko przy CMP_SURE jazdach po obu stronach (inaczej max "mozliwe")."""
    se = math.sqrt(st.variance(a) / len(a) + st.variance(b) / len(b))
    if abs(d) > 2 * se and min(len(a), len(b)) >= CMP_SURE:
        stt = "pewne"
    elif abs(d) > se:
        stt = "możliwe"
    else:
        stt = "bez różnicy"
    return {"d_cda": round(d, 4), "se": round(se, 4), "status": stt}


def summary(conn) -> dict:
    from qbot3.routes.route_surface_category_store import LABELS
    cur = conn.cursor()
    ensure_table(conn)
    cur.execute("SELECT external_id, ride_date, bike, meter_key, n_windows, cda, cda_se, status, reason, wind_ms, "
                "dir_spread, explained_pct, computed_at FROM qbot_v2.ride_cda ORDER BY ride_date")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    ok = [r for r in rows if r["status"] == "OK"]
    today = dt.date.today()
    cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL ORDER BY day DESC LIMIT 1")
    wr = cur.fetchone()
    from fitmodel.meter_physics import EXTRA_KG
    mass = (float(wr[0]) if wr else 100.0) + EXTRA_KG

    bikes = []
    for b in sorted({r["bike"] for r in rows if r["bike"]}):
        mine = [r for r in ok if r["bike"] == b and (today - r["ride_date"]).days <= CANON_DAYS]
        allb = [r for r in rows if r["bike"] == b]
        vals = [float(r["cda"]) for r in mine]
        med = _wmedian([(float(r["cda"]), 1.0 / max(float(r["cda_se"] or 0.05), 0.01) ** 2) for r in mine]) if mine else None
        lo, hi = _q(vals, 0.25), _q(vals, 0.75)
        meters = []
        for r in sorted(allb, key=lambda r: r["ride_date"]):
            if r["meter_key"] and (not meters or meters[-1]["meter"] != r["meter_key"]):
                meters.append({"meter": r["meter_key"], "from": r["ride_date"].isoformat()})
        bikes.append({"bike": b, "cda": med, "lo": lo, "hi": hi, "n_rides": len(mine),
                      "n_windows": sum(r["n_windows"] or 0 for r in mine),
                      "status": _status(len(mine), lo or 0, hi or 0, med),
                      "last_ride": max((r["ride_date"] for r in allb), default=None),
                      "meters": meters[-3:]})
    for x in bikes:
        x["last_ride"] = x["last_ride"].isoformat() if x["last_ride"] else None

    crr = []
    for cat in (1, 2, 3, 4, 5):
        c = CRR.get(cat)
        crr.append({"cat": cat, "label": LABELS.get(cat, str(cat)), "crr": c, "assumed": c is not None,
                    "w25": round(mass * G * c * (25 / 3.6)) if c else None})

    # porownania: rzecz z "W czym jechalem" vs te same jazdy (ten sam rower) bez niej
    gear = _gear([r["external_id"] for r in ok])
    logged = [r for r in ok if r["external_id"] in gear]
    items = {}
    for r in logged:
        for slot, nm in gear[r["external_id"]].items():
            items.setdefault((slot, nm), set()).add(r["external_id"])
    compare = []
    for (slot, nm), with_ids in items.items():
        bike_counts = {}
        for r in logged:
            if r["external_id"] in with_ids:
                bike_counts[r["bike"]] = bike_counts.get(r["bike"], 0) + 1
        bk = max(bike_counts, key=bike_counts.get)
        a = [float(r["cda"]) for r in logged if r["bike"] == bk and r["external_id"] in with_ids]
        b = [float(r["cda"]) for r in logged if r["bike"] == bk and r["external_id"] not in with_ids]
        item = {"slot": "koła" if slot == "wheels" else slot, "item": nm, "bike": bk, "n_with": len(a), "n_without": len(b),
                "d_cda": None, "se": None, "status": "za mało danych"}
        if len(a) >= CMP_MIN and len(b) >= CMP_MIN:
            item.update(_verdict(st.mean(a) - st.mean(b), a, b))
        compare.append(item)
    compare.sort(key=lambda c: (c["d_cda"] is None, -(c["n_with"] + c["n_without"])))
    gb = {}
    for r in ok:
        gb.setdefault(r["bike"], []).append(float(r["cda"]))
    cmp_bikes = []
    names = sorted(b for b in gb if b)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = gb[names[i]], gb[names[j]]
            it = {"slot": "rower", "item": "%s zamiast %s" % (names[j], names[i]), "bike": None,
                  "n_with": len(b), "n_without": len(a), "d_cda": None, "se": None, "status": "za mało danych"}
            if len(a) >= CMP_MIN and len(b) >= CMP_MIN:
                it.update(_verdict(st.mean(b) - st.mean(a), a, b))
            cmp_bikes.append(it)

    points = [{"d": r["ride_date"].isoformat(), "id": r["external_id"], "bike": r["bike"] or "nieznany",
               "cda": float(r["cda"]), "se": float(r["cda_se"] or 0), "n": r["n_windows"],
               "wind": r["wind_ms"], "spread": r["dir_spread"], "gear": gear.get(r["external_id"], {})} for r in ok]
    excl = {}
    for r in rows:
        if r["status"] != "OK":
            excl[r["reason"] or "inne"] = excl.get(r["reason"] or "inne", 0) + 1
    return {
        "updated": max((r["computed_at"] for r in rows), default=None).isoformat() if rows else None,
        "mass_kg": round(mass, 1), "rho_ref": 1.2,
        "bikes": bikes, "crr": crr, "compare": cmp_bikes + compare, "points": points,
        "quality": {"rides_total": len(rows), "rides_used": len(ok),
                    "windows": sum(r["n_windows"] or 0 for r in ok),
                    "since": min((r["ride_date"] for r in rows), default=None).isoformat() if rows else None,
                    "excluded": [{"reason": k, "n": v} for k, v in sorted(excl.items(), key=lambda kv: -kv[1])],
                    "excluded_rides": [{"d": r["ride_date"].isoformat(), "id": r["external_id"], "bike": r["bike"],
                                        "reason": r["reason"]} for r in rows if r["status"] != "OK"][-60:],
                    "position": "pole AERO z Karoo nie trafia jeszcze do bazy QBota -- porównanie chwytów niemożliwe"},
        "assumptions": ["Opór toczenia założony (nie liczony): twarda szybka 0,0055, dobry gravel 0,0085.",
                        "Liczone tylko odcinki na tych dwóch nawierzchniach.",
                        "Wiatr liczony z samej jazdy (różne kierunki); jazda w jednym kierunku = mniejsza pewność.",
                        "Masa = waga dnia + %s kg (rower, sprzęt)." % str(EXTRA_KG).replace(".", ",")],
    }


def _tg(msg):
    try:
        from fitmodel.telegram_notify import send
        send(msg)
    except Exception as exc:
        print("telegram:", exc)


if __name__ == "__main__":
    #   .venv/bin/python3 fitmodel/cda.py --backfill 2026-06-16   (przelicza wszystko od daty, Telegram na koniec)
    #   .venv/bin/python3 fitmodel/cda.py                         (7 dni, tylko nowe)
    import os, sys, time
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    c = _db_connect()
    t0 = time.time()
    try:
        if len(sys.argv) > 2 and sys.argv[1] == "--backfill":
            res = run(c, since=sys.argv[2], recheck=True)
            _tg("Centrum CdA: przeliczenie od %s gotowe w %.0f s -- %s jazd policzonych, %s pominietych. Forma > Centrum CdA."
                % (sys.argv[2], time.time() - t0, res["ok"], res["pominiete"]))
        else:
            res = run(c)
        print(res)
    except Exception as exc:
        if len(sys.argv) > 2:
            _tg("Centrum CdA: przeliczenie PRZERWANE bledem: %s" % exc)
        raise
    finally:
        c.close()
