# -*- coding: utf-8 -*-
"""CENTRUM CdA (v2, 2026-10-18) -- opor powietrza i opor toczenia z ZWYKLYCH jazd, bez testow. Forma > Centrum CdA.

Odcinki 30 s (co 10 s, z activity_record 1 Hz): plasko (|nachylenie| <= 2 %), predkosc >= 4 m/s, moc >= 60 W i rowna (CV <= 25 %),
kadencja >= 50, kierunek prosty (zmiana <= 35 st.), nawierzchnia z raportu jazdy kat. 1-4 (5 = ryzyko i nieznana -- pomijane).
Rownanie odcinka: P*0,976 - m*g*v*nachylenie - dEk/dt = m*g*v*Crr[kat] + 1/2*rho*CdA*(v+wiatr)^2*v.
WSPOLNE LICZENIE (v2): CdA i wiatr per jazda (wiatr z samej jazdy: siatka 0-7 m/s x co 10 st.), Crr per nawierzchnia z WSZYSTKICH jazd,
na zmiane do zbieznosci. KOTWICA: Crr asfaltu (kat. 1) STALY = CRR_ANCHOR. Bez kotwicy CdA i Crr sie nie rozdzielaja
(proba 18.10: Crr rosl, CdA malalo bez konca -- predkosci na odcinkach za malo rozne). Z kotwica stabilnie: gravel kat. 2-4
ok. +0,005 wzgledem asfaltu niezaleznie od kotwicy; od kotwicy zalezy poziom CdA (+-0,001 Crr -> -+0,03 CdA), NIE porownania.
Pomijane jazdy (jedna lista prawdy o mocy, DECISIONS 2026-10-18): kwarantanna miernika, lthr.METER_BAD, load_guard poza LO-HI,
< MIN_WIN odcinkow, CdA poza 0,15-0,9. Masa = waga dnia + meter_physics.EXTRA_KG.
Rower: AXS 27856 = Grail, AXS 10625 = Grizl, brak AXS przy mierniku = Monster, FIT bez czujnikow = nieznany (regula Michala).
Tabele: qbot_v2.ride_cda (jazda), qbot_v2.cda_crr (nawierzchnia). Krok daily_job 'cda' = pelne przeliczenie od CDA_SINCE (kilka s).
Pole AERO z Karoo: fitmodel/qext2_aero.py -- tylko sprawdzian, nie wejscie.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import sqlite3
import statistics as st

import numpy as np

G, ETA, WIN, STEP = 9.81, 0.976, 30, 10
VMIN = 4.0
CRR_ANCHOR = 0.0055                      # asfalt (kat. 1) -- zalozony, kotwica
CRR_START = {1: CRR_ANCHOR, 2: 0.0085, 3: 0.012, 4: 0.018}
CRR_MIN_WIN = 150                        # od tylu odcinkow nawierzchnia ma wlasny, liczony Crr
MIN_WIN = 12
CDA_SINCE = "2026-06-16"                 # od kiedy sa raporty jazd z nawierzchnia
AXS_BIKE = {27856: "Grail", 10625: "Grizl"}
CANON_DAYS = 120
# Mierniki pomijane TYLKO w Centrum CdA (decyzja Michala 19.10): 29525 = os Force DUB-PWR z wada zera; w czerwcu 2026
# (przed oficjalnym 'zlym okresem' 01.07-25.08) moc przy tetnie +15 %, CdA Grizla 0,51-0,62 vs 0,33-0,41 na Quarqu.
# Obciazenia i progow to nie dotyczy (tam lthr.METER_BAD).
CDA_BAD_METERS = {"ant:29525": "miernik z wadą zera (29525)"}
GARAGE_DB = "/opt/qbot/app/data/garage.db"
# warstwy pod spodem (termika) nie zmieniaja oporu powietrza -- nie porownujemy (pozorne roznice z pory roku)
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
    status        text,
    reason        text,
    computed_at   timestamptz NOT NULL DEFAULT now())"""
DDL_CRR = """CREATE TABLE IF NOT EXISTS qbot_v2.cda_crr (
    cat         integer PRIMARY KEY,
    crr         real,
    n_windows   integer,
    n_rides     integer,
    source      text,
    computed_at timestamptz NOT NULL DEFAULT now())"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(DDL_CRR)
        cur.execute("ALTER TABLE qbot_v2.ride_cda ADD COLUMN IF NOT EXISTS quality text, "
                    "ADD COLUMN IF NOT EXISTS quality_why text, ADD COLUMN IF NOT EXISTS gravel_share real")
    conn.commit()


def _bearing(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    return math.atan2(math.sin(dl) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))


LOOP_MAX_M = 150.0          # start i meta blizej niz tyle = petla -> wysokosc musi wrocic do poczatku


def detrend_altitude(rows):
    """Dryf wysokosci na PETLI (start i meta < LOOP_MAX_M): roznica wysokosci meta - start to blad (zmiana cisnienia w trakcie
    jazdy), rozkladany liniowo w CZASIE i odejmowany. Testy syntetyczne 19.10: blad nachylenia 0,1 % = CdA -8 %; na prawdziwych
    petlach dryf 0,00-0,035 % trasy (do ~3 % CdA). Nie-petla -> bez zmian. rows jak w windows(); zwraca (rows, dryf_m | None)."""
    pts = [r for r in rows if r[4] is not None and r[7] is not None and r[8] is not None]
    if len(pts) < 2:
        return rows, None
    a, b = pts[0], pts[-1]
    dx = (b[7] - a[7]) * 111320.0
    dy = (b[8] - a[8]) * 111320.0 * math.cos(math.radians(a[7]))
    if math.hypot(dx, dy) > LOOP_MAX_M:
        return rows, None
    drift = b[4] - a[4]
    t0, t1 = a[0], b[0]
    if t1 <= t0:
        return rows, None
    out = []
    for r in rows:
        if r[4] is None:
            out.append(r)
            continue
        f = min(1.0, max(0.0, (r[0] - t0) / (t1 - t0)))
        out.append(r[:4] + (r[4] - drift * f,) + r[5:])
    return out, drift


def windows(rows, trace, mass, hpa):
    """rows: (sec, power, speed, distance, altitude, cadence, temp, lat, lon, epoch_ts).
    -> np.array kolumny: 0 Pa0 (moc minus grawitacja i kinetyka), 1 m*g*v, 2 v, 3 rho, 4 kurs, 5 kat, 6 t0, 7 t1"""
    kms = (trace or {}).get("km")
    cats = (trace or {}).get("surface_cat")
    if not kms or not cats:
        return None
    out, i = [], 0
    while i + WIN < len(rows):
        w = rows[i:i + WIN + 1]
        i += STEP
        if any(x[1] is None or x[2] is None or x[3] is None or x[4] is None or x[7] is None for x in w):
            continue
        p = [x[1] for x in w[1:]]
        v = [x[2] for x in w]
        pm = st.mean(p)
        if min(p) < 60 or st.mean(v) < VMIN or min(v) < VMIN - 1 or st.pstdev(p) / pm > 0.25:
            continue
        cad = [x[5] for x in w if x[5] is not None]
        if not cad or min(cad) < 50:
            continue
        dist = w[-1][3] - w[0][3]
        if dist < 80:
            continue
        grade = (w[-1][4] - w[0][4]) / dist
        if abs(grade) > 0.02:
            continue
        h1 = _bearing(w[0][7], w[0][8], w[WIN // 2][7], w[WIN // 2][8])
        h2 = _bearing(w[WIN // 2][7], w[WIN // 2][8], w[-1][7], w[-1][8])
        if abs(math.atan2(math.sin(h1 - h2), math.cos(h1 - h2))) > math.radians(35):
            continue
        j = max(0, min(len(kms) - 1, bisect.bisect_left(kms, w[WIN // 2][3] / 1000)))
        c = cats[j]
        if c not in CRR_START:
            continue
        vm = dist / WIN
        tc = st.mean([x[6] for x in w if x[6] is not None] or [12])
        rho = hpa * 100 / (287.05 * (tc + 273.15))
        kin = 0.5 * mass * (v[-1] ** 2 - v[0] ** 2) / WIN
        out.append((pm * ETA - mass * G * vm * grade - kin, mass * G * vm, vm, rho,
                    _bearing(w[0][7], w[0][8], w[-1][7], w[-1][8]), c, w[0][9] or 0, w[-1][9] or 0))
    return np.array(out, dtype=float) if out else None


_S = np.arange(0, 7.01, 0.25)
_TH = np.radians(np.arange(0, 360, 10))
_SS, _TT = [a.ravel() for a in np.meshgrid(_S, _TH)]


def fit_ride(W, crr):
    """-> dict: cda, se, wiatr, X (czlon powietrza dla najlepszego wiatru), pa (moc na powietrze), sse, sse0."""
    crr_v = np.array([crr.get(int(k), CRR_ANCHOR) for k in W[:, 5]])
    pa = W[:, 0] - W[:, 1] * crr_v
    va = W[:, 2][None, :] + _SS[:, None] * np.cos(_TT[:, None] - W[:, 4][None, :])
    X = 0.5 * W[:, 3][None, :] * va * np.abs(va) * W[:, 2][None, :]
    den = np.einsum("ij,ij->i", X, X)
    c = (X @ pa) / den
    sse = ((pa[None, :] - c[:, None] * X) ** 2).sum(1)
    k = int(np.argmin(sse))
    x0 = 0.5 * W[:, 3] * W[:, 2] ** 3
    c0 = float((x0 @ pa) / (x0 @ x0))
    sse0 = float(((pa - c0 * x0) ** 2).sum())
    return {"cda": float(c[k]), "se": float(math.sqrt(sse[k] / max(1, len(pa) - 1) / den[k])), "wind": float(_SS[k]),
            "wind_from": int(round(math.degrees(_TT[k]))) % 360, "X": X[k], "pa": pa, "sse": float(sse[k]), "sse0": sse0}


def spread(W):
    c, s = np.cos(W[:, 4]).sum(), np.sin(W[:, 4]).sum()
    return float(1 - math.hypot(c, s) / len(W))


BIKE_SHORT = {"Canyon Grail": "Grail", "Canyon Grizl": "Grizl", "Canyon Grand Canyon": "Monster"}


def bike_and_meter(cur, eid):
    """Rower: KANONICZNE qbot3.rides.activity_devices.bike_for_ride (audyt 19.10 -- jedna sciezka zamiast wlasnej kopii
    reguly AXS); nazwa skrocona BIKE_SHORT. Miernik: pierwszy bike_power z activity_device ('ant:<nr>' / 'sn:<serial>').
    FIT bez czujnikow -> rower None ('nieznany')."""
    cur.execute("SELECT device_type, manufacturer, ant_device_number, serial_number FROM qbot_v2.activity_device "
                "WHERE external_id=%s", (eid,))
    rows = cur.fetchall()
    pm = [r for r in rows if r[0] == "bike_power"]
    meter = (("ant:%s" % pm[0][2]) if pm[0][2] is not None else ("sn:%s" % pm[0][3])) if pm else None
    bike = None
    try:
        from qbot3.rides.activity_devices import bike_for_ride
        b = (bike_for_ride(cur.connection, str(eid)) or {}).get("bike")
        bike = BIKE_SHORT.get(b, b)
    except Exception:
        cur.connection.rollback()
        axs = [r[2] for r in rows if str(r[0]) == "34" and r[1] == "sram"]
        bike = AXS_BIKE.get(axs[0], "AXS %s" % axs[0]) if axs else ("Monster" if pm else None)
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


def load_ride(cur, eid, day):
    """-> (wiersz bazowy ride_cda, W albo None)."""
    from fitmodel.meter_physics import EXTRA_KG
    bike, meter = bike_and_meter(cur, eid)
    row = {"external_id": eid, "ride_date": day, "bike": bike, "meter_key": meter, "n_windows": 0, "dir_spread": None,
           "wind_ms": None, "wind_from_deg": None, "cda": None, "cda_se": None, "explained_pct": None, "rho": None,
           "status": "POMINIETA", "reason": None}
    why = _excluded(cur, eid, day) or CDA_BAD_METERS.get(meter)
    if why:
        row["reason"] = why
        return row, None
    cur.execute("SELECT w1_json FROM qbot_v2.ride_report_data WHERE ride_key=%s ORDER BY schema_version DESC LIMIT 1", (eid,))
    r = cur.fetchone()
    w1 = (json.loads(r[0]) if isinstance(r[0], str) else r[0]) if r else {}
    trace = (w1 or {}).get("trace")
    if not trace:
        row["reason"] = "brak raportu jazdy (nawierzchnia)"
        return row, None
    hpa = (((w1.get("weather") or {}).get("pressure_hpa") or {}).get("value")) or 1013
    cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE day<=%s AND weight_kg IS NOT NULL "
                "ORDER BY day DESC LIMIT 1", (day,))
    wr = cur.fetchone()
    mass = (float(wr[0]) if wr else 100.0) + EXTRA_KG
    cur.execute("SELECT sec, power_w, speed_mps, distance_m, altitude_m, cadence_rpm, temperature_c, lat, lon, "
                "extract(epoch from ts) FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (eid,))
    rows = [tuple(None if v is None else float(v) for v in x) for x in cur.fetchall()]
    rows, _drift = detrend_altitude(rows)          # 19.10: dryf cisnienia na petlach
    W = windows(rows, trace, mass, float(hpa))
    row["n_windows"] = 0 if W is None else len(W)
    if W is None or len(W) < MIN_WIN:
        row["reason"] = "za mało płaskich, równych odcinków"
        return row, None
    return row, W


QUALITY_W = {"A": 1.0, "B": 0.6, "C": 0.3}   # waga jakosci w kanonie roweru (razy 1/blad^2)


def ride_quality(n_windows, dir_spread, cda_v, cda_se, gravel_share):
    """Jakosc jazdy (audyt 19.10): A = brak slabych punktow, B = jeden, C = dwa i wiecej. Slabe punkty:
    < 40 odcinkow; malo kierunkow (rozrzut kursow < 0,3 -- wiatru nie da sie oddzielic, test: CdA +9..+19 %);
    blad CdA > 4 % wartosci; > 80 % odcinkow na szutrze (stan drogi nieznany, MyBIOM: +10-16 W w zle dni).
    Rozrzut kursow < 0,1 -> None (jazdy nie liczyc). -> (klasa | None, powody)."""
    if dir_spread is not None and dir_spread < 0.1:
        return None, ["jeden kierunek - wiatru nie da się oddzielić"]
    why = []
    if (n_windows or 0) < 40:
        why.append("mało odcinków (%d)" % (n_windows or 0))
    if dir_spread is not None and dir_spread < 0.3:
        why.append("mało kierunków")
    if cda_v and cda_se and cda_se / cda_v > 0.04:
        why.append("duży rozrzut (±%d%%)" % round(100 * cda_se / cda_v))
    if gravel_share is not None and gravel_share > 0.8:
        why.append("głównie szuter (%d%%) - stan drogi nieznany" % round(100 * gravel_share))
    return ("A" if not why else ("B" if len(why) == 1 else "C")), why


def joint_fit(rides, iters=10):
    """rides: [(row, W)] -> (crr {kat: wartosc}, {kat: (n_okien, n_jazd)}, wyniki per jazda).
    2026-10-19 (testy syntetyczne, tests/test_cda_synthetic.py): na zmiane (1) WIATR kazdej jazdy z siatki przy biezacym Crr,
    (2) JEDNO wspolne rozwiazanie liniowe (najmniejsze kwadraty) dla CdA wszystkich jazd i Crr kat. 2-4 naraz.
    Wczesniej Crr i CdA poprawiane osobno na zmiane -- zbiegalo powoli i zatrzymywalo sie za wczesnie
    (sztuczne jazdy: CdA +6,6 %, Crr szutru -7..-12 % przy dobrej kotwicy). Kat. 1 = kotwica (stala)."""
    crr = dict(CRR_START)
    counts = {k: (int(sum(int((W[:, 5] == k).sum()) for _r, W in rides)),
                  int(sum(1 for _r, W in rides if (W[:, 5] == k).any()))) for k in CRR_START}
    free = [k for k in (2, 3, 4) if counts[k][0] >= CRR_MIN_WIN]
    n = len(rides)
    for _ in range(iters if free else 0):
        fits = [fit_ride(W, crr) for _r, W in rides]
        blocks_a, blocks_y = [], []
        for i, ((_r, W), f) in enumerate(zip(rides, fits)):
            cats = W[:, 5].astype(int)
            fixed = np.array([0.0 if k in free else crr.get(k, CRR_ANCHOR) for k in cats])
            A = np.zeros((len(W), n + len(free)))
            A[:, i] = f["X"]
            for j, k in enumerate(free):
                m = cats == k
                A[m, n + j] = W[m, 1]
            blocks_a.append(A)
            blocks_y.append(W[:, 0] - W[:, 1] * fixed)
        sol = np.linalg.lstsq(np.vstack(blocks_a), np.concatenate(blocks_y), rcond=None)[0]
        new = dict(crr)
        for j, k in enumerate(free):
            new[k] = float(min(0.05, max(0.002, sol[n + j])))
        done = max(abs(new[k] - crr[k]) / crr[k] for k in free) < 0.001
        crr = new
        if done:
            break
    res = [fit_ride(W, crr) for _r, W in rides]
    return crr, counts, res


_UPSERT = ("INSERT INTO qbot_v2.ride_cda (external_id, ride_date, bike, meter_key, n_windows, dir_spread, wind_ms, "
           "wind_from_deg, cda, cda_se, explained_pct, rho, status, reason) VALUES "
           "(%(external_id)s,%(ride_date)s,%(bike)s,%(meter_key)s,%(n_windows)s,%(dir_spread)s,%(wind_ms)s,"
           "%(wind_from_deg)s,%(cda)s,%(cda_se)s,%(explained_pct)s,%(rho)s,%(status)s,%(reason)s) "
           "ON CONFLICT (external_id) DO UPDATE SET ride_date=EXCLUDED.ride_date, bike=EXCLUDED.bike, "
           "meter_key=EXCLUDED.meter_key, n_windows=EXCLUDED.n_windows, dir_spread=EXCLUDED.dir_spread, "
           "wind_ms=EXCLUDED.wind_ms, wind_from_deg=EXCLUDED.wind_from_deg, cda=EXCLUDED.cda, cda_se=EXCLUDED.cda_se, "
           "explained_pct=EXCLUDED.explained_pct, rho=EXCLUDED.rho, status=EXCLUDED.status, reason=EXCLUDED.reason, "
           "computed_at=now()")


def run(conn, lookback_days: int = 7, since: str | None = None, recheck: bool = True) -> dict:
    """Pelne przeliczenie od CDA_SINCE (Crr wspolny dla wszystkich jazd). lookback_days/recheck -- zgodnosc z daily_job."""
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT external_id, date FROM qbot_v2.training_sessions WHERE date >= %s::date "
                "AND avg_power_w IS NOT NULL AND distance_m > 10000 ORDER BY date", (since or CDA_SINCE,))
    all_rows, rides = [], []
    for eid, day in cur.fetchall():
        row, W = load_ride(cur, str(eid), day)
        all_rows.append(row)
        if W is not None:
            rides.append((row, W))
    if rides:
        crr, counts, res = joint_fit(rides)
    else:
        crr, counts, res = dict(CRR_START), {k: (0, 0) for k in CRR_START}, []
    for (row, W), f in zip(rides, res):
        row.update({"dir_spread": round(spread(W), 3), "wind_ms": f["wind"], "wind_from_deg": f["wind_from"],
                    "cda": round(f["cda"], 4), "cda_se": round(f["se"], 4),
                    "explained_pct": round(100 * (1 - f["sse"] / f["sse0"]), 1) if f["sse0"] else None,
                    "rho": round(float(W[:, 3].mean()), 4), "status": "OK", "reason": None})
        row["gravel_share"] = round(float((W[:, 5] != 1).mean()), 3)
        q, why = ride_quality(row["n_windows"], row["dir_spread"], row["cda"], row["cda_se"], row["gravel_share"])
        row.update({"quality": q, "quality_why": "; ".join(why) or None})
        if q is None:
            row.update({"status": "POMINIETA", "reason": why[0]})
        if not (0.15 <= f["cda"] <= 0.9):
            row.update({"status": "POMINIETA", "reason": "wynik poza zakresem fizycznym (%.2f)" % f["cda"]})
    for row in all_rows:
        cur.execute(_UPSERT, row)
        cur.execute("UPDATE qbot_v2.ride_cda SET quality=%s, quality_why=%s, gravel_share=%s WHERE external_id=%s",
                    (row.get("quality"), row.get("quality_why"), row.get("gravel_share"), row["external_id"]))
    for k, v in crr.items():
        src = "kotwica" if k == 1 else ("liczony" if counts[k][0] >= CRR_MIN_WIN else "za mało danych")
        cur.execute("INSERT INTO qbot_v2.cda_crr (cat, crr, n_windows, n_rides, source) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (cat) DO UPDATE SET crr=EXCLUDED.crr, n_windows=EXCLUDED.n_windows, n_rides=EXCLUDED.n_rides, "
                    "source=EXCLUDED.source, computed_at=now()", (k, round(v, 5), counts[k][0], counts[k][1], src))
    conn.commit()
    try:
        calib = calibrate_xss(conn)
    except Exception as exc:
        conn.rollback()
        calib = {"error": str(exc)}
    return {"ok": sum(1 for r in all_rows if r["status"] == "OK"), "pominiete": sum(1 for r in all_rows if r["status"] != "OK"),
            "crr": {k: round(v, 4) for k, v in crr.items()}, "xss_calib": calib}


def canon(external_id: str | None = None, day=None) -> dict:
    """KANON CdA/Crr/masy dla reszty QBota (2026-10-18). Wlasne polaczenie (dziala z kazdym kursorem wolajacego).
    cda: CdA tej jazdy (ride_cda OK) -> mediana roweru jazdy z CANON_DAYS -> mediana wszystkich -> 0,42.
    crr: {kat 1-4: wartosc} z cda_crr (kat. 5 i nieznana -> srednia kat. 2-4). mass: waga dnia + EXTRA_KG."""
    from fitmodel.api import _db_connect
    from fitmodel.meter_physics import EXTRA_KG
    out = {"cda": 0.42, "cda_src": "domyslne", "crr": dict(CRR_START), "mass": None}
    conn = _db_connect()
    try:
        ensure_table(conn)
        cur = conn.cursor()
        out["crr"] = _crr_now(cur)
        bike = None
        if external_id:
            cur.execute("SELECT cda, bike, status FROM qbot_v2.ride_cda WHERE external_id=%s", (str(external_id),))
            r = cur.fetchone()
            if r and r[2] == "OK" and r[0] is not None:
                out.update({"cda": float(r[0]), "cda_src": "ta jazda"})
            if r:
                bike = r[1]
            if bike is None:
                bike, _m = bike_and_meter(cur, str(external_id))
        if out["cda_src"] == "domyslne":
            q = ("SELECT cda, cda_se, quality FROM qbot_v2.ride_cda WHERE status='OK' AND ride_date >= CURRENT_DATE - %s"
                 + (" AND bike=%s" if bike else ""))
            cur.execute(q, (CANON_DAYS, bike) if bike else (CANON_DAYS,))
            vals = [(float(a), QUALITY_W.get(qq, 1.0) / max(float(b or 0.05), 0.01) ** 2) for a, b, qq in cur.fetchall()]
            if vals:
                out.update({"cda": _wmedian(vals), "cda_src": ("rower %s" % bike) if bike else "wszystkie jazdy"})
        cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL"
                    + (" AND day<=%s" if day else "") + " ORDER BY day DESC LIMIT 1", (day,) if day else ())
        w = cur.fetchone()
        out["mass"] = (float(w[0]) if w else 100.0) + EXTRA_KG
    finally:
        conn.close()
    g = [out["crr"][k] for k in (2, 3, 4) if k in out["crr"]]
    out["crr_unknown"] = sum(g) / len(g) if g else 0.010
    return out


XSS_FACTOR_DEFAULT = 1.17     # test 18.10 -- uzywany tylko gdy brak kalibracji w bazie
XSS_CALIB_DAYS = 7
DDL_XSS = """CREATE TABLE IF NOT EXISTS qbot_v2.cda_xss_calib (
    computed_at  timestamptz PRIMARY KEY DEFAULT now(),
    factor       real,
    n_rides      integer,
    err_new_pct  real,
    err_old_pct  real,
    half_new_pct real,
    half_old_pct real)"""
_RPP = {"t": 0, "v": None}


def route_physics_params() -> dict:
    """Dla route_xss_phys: CdA (kanon, wszystkie rowery), Crr asfalt / szuter (srednia kat. 2-4) / nieznana,
    EXTRA_KG, wspolczynnik zmiennosci z ostatniej kalibracji. Pamiec 10 min."""
    import time as _t
    if _RPP["v"] and _t.time() - _RPP["t"] < 600:
        return _RPP["v"]
    k = canon(None)
    from fitmodel.meter_physics import EXTRA_KG
    gravel = [k["crr"][i] for i in (2, 3, 4) if i in k["crr"]]
    unp = sum(gravel) / len(gravel) if gravel else 0.0105
    f = XSS_FACTOR_DEFAULT
    from fitmodel.api import _db_connect
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL_XSS)
            cur.execute("SELECT factor FROM qbot_v2.cda_xss_calib ORDER BY computed_at DESC LIMIT 1")
            r = cur.fetchone()
            if r and r[0]:
                f = float(r[0])
        conn.commit()
    finally:
        conn.close()
    v = {"cda": k["cda"], "crr_paved": k["crr"].get(1, CRR_ANCHOR), "crr_unpaved": unp,
         "crr_unknown": (k["crr"].get(1, CRR_ANCHOR) + unp) / 2, "extra_kg": EXTRA_KG, "factor": f}
    _RPP.update(t=_t.time(), v=v)
    return v


def calibrate_xss(conn, force: bool = False):
    """Test planera na wykonanych jazdach: ten sam route_xss_phys (predkosc z modelu, tryb normalny, bez wiatru) na sladzie
    jazdy vs rzeczywisty XSS (modelq2_ride, z mocy). Wspolczynnik = mediana rzeczywisty / plan. Raz na XSS_CALIB_DAYS."""
    from qbot3.routes.route_xss_phys import _estimate_route_xss_phys
    from fitmodel.modelq2.signature import Signature
    cur = conn.cursor()
    cur.execute(DDL_XSS)
    conn.commit()
    if not force:
        cur.execute("SELECT 1 FROM qbot_v2.cda_xss_calib WHERE computed_at > now() - %s * interval '1 day'", (XSS_CALIB_DAYS,))
        if cur.fetchone():
            return None
    _RPP.update(t=0, v=None)
    cur.execute("""SELECT r.external_id, r.ride_date, m.xss_total, m.sig_tp_w, m.sig_hie_kj, m.sig_pp_w
                   FROM qbot_v2.ride_cda r JOIN qbot_v2.modelq2_ride m ON m.external_id=r.external_id
                   WHERE r.status='OK' AND m.xss_source='power' AND m.xss_total > 0 ORDER BY r.ride_date""")
    out = []
    for eid, d, xss, tp, hie, pp in cur.fetchall():
        cur.execute("SELECT w1_json FROM qbot_v2.ride_report_data WHERE ride_key=%s ORDER BY schema_version DESC LIMIT 1", (eid,))
        r = cur.fetchone()
        w1 = (json.loads(r[0]) if isinstance(r[0], str) else r[0]) if r else {}
        tr = (w1 or {}).get("trace") or {}
        kms, cats = tr.get("km") or [], tr.get("surface_cat") or []
        cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE day<=%s AND weight_kg IS NOT NULL "
                    "ORDER BY day DESC LIMIT 1", (d,))
        w = cur.fetchone()
        weight = float(w[0]) if w else 100.0
        cur.execute("SELECT distance_m, altitude_m, lat, lon FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (eid,))
        rec = [x for x in cur.fetchall() if x[0] is not None and x[1] is not None]
        seg, i = [], 0
        while i < len(rec):
            j = i
            while j < len(rec) and rec[j][0] - rec[i][0] < 50:
                j += 1
            if j >= len(rec):
                break
            dist = rec[j][0] - rec[i][0]
            if dist > 0:
                k = max(0, min(len(kms) - 1, bisect.bisect_left(kms, rec[i][0] / 1000))) if kms else None
                cat = cats[k] if (k is not None and cats) else None
                seg.append({"len_m": dist, "grade_pct": 100.0 * (rec[j][1] - rec[i][1]) / dist,
                            "surface": "paved" if cat == 1 else ("unpaved" if cat in (2, 3, 4, 5) else None),
                            "mid_lat": rec[i][2], "mid_lon": rec[i][3]})
            i = j
        if not seg:
            continue
        sig = Signature.from_kj(float(tp), float(hie), float(pp))
        new = _estimate_route_xss_phys(seg, sig, weight, "normalny", None, factor=1.0)
        old = _estimate_route_xss_phys(seg, sig, weight, "normalny", None, legacy=True)
        if new and old:
            out.append((float(xss), new, old))
    if len(out) < 10:
        return None
    med = lambda xs: sorted(xs)[len(xs) // 2]
    f = med([a / n for a, n, _o in out])
    err_new = med([abs(a - f * n) / a for a, n, _o in out])
    err_old = med([abs(a - o) / a for a, _n, o in out])
    ev, od = out[0::2], out[1::2]
    fe = med([a / n for a, n, _o in ev])
    half_new = med([abs(a - fe * n) / a for a, n, _o in od])
    half_old = med([abs(a - o) / a for a, _n, o in od])
    row = {"factor": round(f, 4), "n_rides": len(out), "err_new_pct": round(100 * err_new, 1),
           "err_old_pct": round(100 * err_old, 1), "half_new_pct": round(100 * half_new, 1), "half_old_pct": round(100 * half_old, 1)}
    cur.execute("INSERT INTO qbot_v2.cda_xss_calib (factor, n_rides, err_new_pct, err_old_pct, half_new_pct, half_old_pct) "
                "VALUES (%(factor)s,%(n_rides)s,%(err_new_pct)s,%(err_old_pct)s,%(half_new_pct)s,%(half_old_pct)s)", row)
    conn.commit()
    _RPP.update(t=0, v=None)
    return row


# ---------------- podsumowanie dla strony ----------------

def _wmedian(vals):
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


def _gear(ride_keys):
    if not ride_keys:
        return {}
    g = sqlite3.connect(GARAGE_DB)
    try:
        names = {}
        for gid, brand, model in g.execute("SELECT id, brand, model FROM gear"):
            names[str(gid)] = ((brand or "") + " " + (model or "")).strip()
        for cid, brand, model in g.execute("SELECT id, brand, model FROM components"):
            names.setdefault("c%s" % cid, ((brand or "") + " " + (model or "")).strip())
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


def _crr_now(cur):
    cur.execute("SELECT cat, crr FROM qbot_v2.cda_crr")
    got = {int(k): float(v) for k, v in cur.fetchall() if v is not None}
    return {k: got.get(k, v) for k, v in CRR_START.items()}


def _aero_checks(conn, ok_rows):
    """Sprawdzian pola AERO z Karoo dla jazd, ktore maja jego zapis (od QExt2 0.4.1)."""
    from fitmodel import qext2_aero
    qext2_aero.ensure_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT external_id FROM qbot_v2.qext2_aero_record")
    have = {r[0] for r in cur.fetchall()}
    crr = _crr_now(cur)
    out = []
    for r in ok_rows:
        if r["external_id"] not in have:
            continue
        _row, W = load_ride(cur, r["external_id"], r["ride_date"])
        win_ts, win_cda = [], []
        if W is not None:
            f = fit_ride(W, crr)
            for t0, t1, pa, x in zip(W[:, 6], W[:, 7], f["pa"], f["X"]):
                if x > 1:
                    win_ts.append((float(t0), float(t1)))
                    win_cda.append(float(pa / x))
        chk = qext2_aero.ride_check(cur, r["external_id"], r["cda"], win_ts, win_cda)
        if chk:
            chk.update({"d": r["ride_date"].isoformat(), "id": r["external_id"], "bike": r["bike"]})
            out.append(chk)
    return out[-10:]


def _xss_calib_last(cur):
    try:
        cur.execute(DDL_XSS)
        cur.execute("SELECT computed_at, factor, n_rides, err_new_pct, err_old_pct, half_new_pct, half_old_pct "
                    "FROM qbot_v2.cda_xss_calib ORDER BY computed_at DESC LIMIT 1")
        r = cur.fetchone()
    except Exception:
        return None
    if not r:
        return None
    return {"at": r[0].isoformat(), "factor": r[1], "n": r[2], "err_new": r[3], "err_old": r[4], "half_new": r[5], "half_old": r[6]}


def summary(conn) -> dict:
    from qbot3.routes.route_surface_category_store import LABELS
    from fitmodel.meter_physics import EXTRA_KG
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT external_id, ride_date, bike, meter_key, n_windows, cda, cda_se, status, reason, wind_ms, "
                "dir_spread, explained_pct, computed_at, quality, quality_why FROM qbot_v2.ride_cda ORDER BY ride_date")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    ok = [r for r in rows if r["status"] == "OK"]
    today = dt.date.today()
    cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL ORDER BY day DESC LIMIT 1")
    wr = cur.fetchone()
    mass = (float(wr[0]) if wr else 100.0) + EXTRA_KG

    bikes = []
    for b in sorted({r["bike"] for r in rows if r["bike"]}):
        mine = [r for r in ok if r["bike"] == b and (today - r["ride_date"]).days <= CANON_DAYS]
        allb = [r for r in rows if r["bike"] == b]
        vals = [float(r["cda"]) for r in mine]
        med = _wmedian([(float(r["cda"]), QUALITY_W.get(r.get("quality"), 1.0) / max(float(r["cda_se"] or 0.05), 0.01) ** 2)
                        for r in mine]) if mine else None
        qcnt = {k: sum(1 for r in mine if r.get("quality") == k) for k in ("A", "B", "C")}
        lo, hi = _q(vals, 0.25), _q(vals, 0.75)
        meters = []
        for r in sorted(allb, key=lambda r: r["ride_date"]):
            if r["meter_key"] and (not meters or meters[-1]["meter"] != r["meter_key"]):
                meters.append({"meter": r["meter_key"], "from": r["ride_date"].isoformat()})
        last = max((r["ride_date"] for r in allb), default=None)
        bikes.append({"bike": b, "cda": med, "lo": lo, "hi": hi, "n_rides": len(mine),
                      "n_windows": sum(r["n_windows"] or 0 for r in mine), "status": _status(len(mine), lo or 0, hi or 0, med),
                      "last_ride": last.isoformat() if last else None, "meters": meters[-3:], "quality": qcnt})

    cur.execute("SELECT cat, crr, n_windows, n_rides, source FROM qbot_v2.cda_crr ORDER BY cat")
    crr_db = {int(c): (v, n, nr, s) for c, v, n, nr, s in cur.fetchall()}
    crr = []
    for cat in (1, 2, 3, 4, 5):
        v, n, nr, s = crr_db.get(cat, (None, 0, 0, "nie liczony"))
        crr.append({"cat": cat, "label": LABELS.get(cat, str(cat)), "crr": None if v is None else float(v),
                    "source": s if cat != 5 else "nie liczony", "n_windows": n or 0, "n_rides": nr or 0,
                    "w25": round(mass * G * float(v) * (25 / 3.6)) if v is not None else None})

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
        if r["bike"]:
            gb.setdefault(r["bike"], []).append(float(r["cda"]))
    cmp_bikes = []
    names = sorted(gb)
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
               "wind": r["wind_ms"], "spread": r["dir_spread"], "gear": gear.get(r["external_id"], {}),
               "q": r.get("quality"), "q_why": r.get("quality_why")} for r in ok]
    excl = {}
    for r in rows:
        if r["status"] != "OK":
            excl[r["reason"] or "inne"] = excl.get(r["reason"] or "inne", 0) + 1
    try:
        aero = _aero_checks(conn, ok)
    except Exception as exc:
        conn.rollback()
        aero = [{"error": str(exc)}]
    return {
        "updated": max(r["computed_at"] for r in rows).isoformat() if rows else None,
        "mass_kg": round(mass, 1), "rho_ref": 1.2,
        "bikes": bikes, "crr": crr, "compare": cmp_bikes + compare, "points": points, "aero_field": aero,
        "xss_calib": _xss_calib_last(cur),
        "quality": {"rides_total": len(rows), "rides_used": len(ok), "windows": sum(r["n_windows"] or 0 for r in ok),
                    "since": min(r["ride_date"] for r in rows).isoformat() if rows else None,
                    "excluded": [{"reason": k, "n": v} for k, v in sorted(excl.items(), key=lambda kv: -kv[1])],
                    "excluded_rides": [{"d": r["ride_date"].isoformat(), "id": r["external_id"], "bike": r["bike"],
                                        "reason": r["reason"]} for r in rows if r["status"] != "OK"][-60:],
                    "position": "pole AERO nie wie, w jakiej pozycji jedziesz (bez oznaczania), więc porównania chwytów "
                                "nie da się policzyć; zapis pola służy do sprawdzianu poniżej"},
        "assumptions": ["Opór toczenia asfaltu założony = %s (kotwica). Pozostałe nawierzchnie liczone z jazd względem asfaltu."
                        % str(CRR_ANCHOR).replace(".", ","),
                        "Od kotwicy zależy poziom CdA (±0,001 Crr ≈ ∓0,03 CdA), ale nie porównania między jazdami, strojem i rowerami.",
                        "Wiatr liczony z samej jazdy (różne kierunki); jazda w jednym kierunku = mniejsza pewność.",
                        "Masa = waga dnia + %s kg (rower, sprzęt)." % str(EXTRA_KG).replace(".", ","),
                        "Nawierzchnia 'ryzyko/niepewne' i nieznana nie wchodzą do liczenia."],
    }


if __name__ == "__main__":
    #   .venv/bin/python3 fitmodel/cda.py   (pelne przeliczenie od CDA_SINCE, kilka sekund)
    import os, sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    c = _db_connect()
    try:
        print(run(c))
    finally:
        c.close()
