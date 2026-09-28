# -*- coding: utf-8 -*-
"""Fakty do analizy jazdy (W2 v2, 2026-09-28) — liczone DETERMINISTYCZNIE, zanim cokolwiek zobaczy LLM.

Cztery pytania uzytkownika:
  1) co zaplanowalem          -> plan (planner wyprawy, TRENER, kalendarz, etapy mocy z raportu trasy)
  2) jak pojechalem wobec planu i mozliwosci -> wykonanie (sumy plan/realnie, odcinki mocy, wejscie w jazde,
                                                podobne jazdy: EF = NP / srednie tetno)
  3) konsekwencje             -> konsekwencje (fitmodel_daily przed/po/dzis, prognoza swiezosci wg planu TRENERA)
  4) na co uwazac             -> wnioski LLM z powyzszego
Obciazenie = XSS ModelQ (modelq2_ride.xss_total) - kanon CTL/ATL/TSB. NIE training_sessions.tss (TSS Garmina)
i NIE fitmodel_wbal_ride (stara skala W'bal replay). Konsekwencje licz na zywo (live_consequences) - wiersze modelu formy
dnia jazdy przeliczaja sie w nocy, wiec W1 z dnia jazdy ma jeszcze stan sprzed jazdy.
"""
import re
from datetime import date, datetime, timedelta


def _f(x, nd=None):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if nd is not None else v


def _val(block):
    if isinstance(block, dict) and "value" in block:
        return block.get("value")
    return block


def _d(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])


def _np(powers):
    if not powers:
        return None
    w, s, roll = 30, 0.0, []
    q = []
    for p in powers:
        q.append(p)
        s += p
        if len(q) > w:
            s -= q.pop(0)
        if len(q) == w:
            roll.append(s / w)
    if not roll:
        return None
    return (sum(r ** 4 for r in roll) / len(roll)) ** 0.25


# obciazenie = XSS ModelQ (kanon CTL/ATL/TSB), nie TSS Garmina
_XSS = "(SELECT m.xss_total FROM qbot_v2.modelq2_ride m WHERE m.external_id = training_sessions.external_id LIMIT 1)"


def _session(cur, ride_key):
    cur.execute("SELECT date, started_at, ended_at, distance_m, duration_s, " + _XSS + ", normalized_power_w, avg_power_w, "
                "avg_hr_bpm, intensity_factor, activity_name FROM qbot_v2.training_sessions WHERE external_id=%s",
                (ride_key,))
    return cur.fetchone()


def _row(r, keys):
    return {k: r[i] for i, k in enumerate(keys)} if r else None


# ---------------------------------------------------------------- 1) plan
def plan_block(cur, day, w1):
    out = {"zrodla": []}
    cur.execute("SELECT xss, dist_km, moving_h, route_id, source FROM qbot_v2.planned_load_daily WHERE day=%s", (day,))
    r = cur.fetchone()
    if r:
        out["planer"] = {"obciazenie": _f(r[0], 0), "dist_km": _f(r[1], 1), "czas_ruchu_h": _f(r[2], 2),
                         "trasa": r[3], "zrodlo": r[4]}
        out["zrodla"].append("planer")
    cur.execute("SELECT name, dur_min, zone, xss, status, note FROM qbot_v2.trainer_session "
                "WHERE day=%s AND sport='rower' ORDER BY id", (day,))
    tr = [{"nazwa": x[0], "czas_min": x[1], "strefa": x[2], "obciazenie": _f(x[3], 0), "status": x[4], "notatka": x[5]}
          for x in cur.fetchall()]
    if tr:
        out["trener"] = tr
        out["zrodla"].append("trener")
    cur.execute("SELECT title, event_type, note FROM qbot_v2.calendar_entry WHERE kind='event' AND "
                "(day=%s OR (end_day IS NOT NULL AND day<=%s AND end_day>=%s))", (day, day, day))
    ev = [{"tytul": x[0], "typ": x[1], "notatka": x[2]} for x in cur.fetchall()]
    if ev:
        out["kalendarz"] = ev
        out["zrodla"].append("kalendarz")
    pva = _val((w1 or {}).get("plan_vs_actual")) or {}
    et = []
    for e in (pva.get("etapy") or []):
        m = re.search(r"(\d+)\s*[-\u2013]\s*(\d+)\s*W", str(e.get("moc") or ""))
        z = re.search(r"([\d.]+)\s*[-\u2013]\s*([\d.]+)", str(e.get("zakres_km") or ""))
        if not z:
            continue
        g = re.search(r"(\d+)\s*g/h", str(e.get("zywienie") or ""))
        l = re.search(r"([\d.]+)\s*l/h", str(e.get("pojenie") or ""))
        tryb = re.search(r"tryb\s+(\w+)", str(e.get("moc") or ""))
        et.append({"km": [float(z.group(1)), float(z.group(2))],
                   "moc_od": int(m.group(1)) if m else None, "moc_do": int(m.group(2)) if m else None,
                   "tryb": tryb.group(1) if tryb else None, "teren": e.get("tytul"), "wskazowka": e.get("opis"),
                   "wegle_g_h": int(g.group(1)) if g else None, "picie_l_h": float(l.group(1)) if l else None})
    if et:
        out["etapy"] = et
        out["zrodla"].append("trasa")
    if pva.get("_plan"):
        out["trasa"] = {"dist_km": _f(pva["_plan"].get("dist_km"), 1), "przewyzszenie_m": _f(pva["_plan"].get("ascent_m"), 0)}
    out["jest_plan"] = bool(out["zrodla"])
    return out


# ---------------------------------------------------------------- 2) wykonanie
def execution_block(cur, ride_key, day, w1, plan, ses):
    load = (w1 or {}).get("load") or {}
    lv = lambda k: _val(load.get(k))
    real = {"dist_km": _f(lv("dist_km"), 1), "czas_ruchu_h": _f((lv("dur_moving_s") or 0) / 3600.0, 2) or None,
            "czas_calkowity_h": _f((lv("dur_elapsed_s") or 0) / 3600.0, 2) or None,
            "obciazenie": _f(ses[5], 0) if ses else None, "np_w": _f(lv("np_w"), 0), "sr_moc_w": _f(lv("avg_p_w"), 0),
            "if": _f(lv("if"), 2), "vi": _f(lv("vi"), 2), "praca_kj": _f(lv("kj"), 0), "ftp_w": _f(lv("ftp_w"), 0)}
    pl = plan.get("planer") or {}
    tr0 = (plan.get("trener") or [{}])[0]
    ref = {"dist_km": pl.get("dist_km") or (plan.get("trasa") or {}).get("dist_km"),
           "czas_ruchu_h": pl.get("czas_ruchu_h") or ((tr0.get("czas_min") or 0) / 60.0 or None),
           "obciazenie": pl.get("obciazenie") or tr0.get("obciazenie")}
    sumy = []
    for k, lab in (("dist_km", "dystans km"), ("czas_ruchu_h", "czas ruchu h"), ("obciazenie", "obciazenie")):
        p, r = ref.get(k), real.get(k)
        sumy.append({"co": lab, "plan": _f(p, 2), "realnie": r,
                     "roznica_pct": (round((r - p) / p * 100) if (p and r is not None) else None)})
    # odcinki mocy
    odc = []
    et = plan.get("etapy") or []
    if et:
        cur.execute("SELECT distance_m, power_w, hr_bpm, speed_mps FROM qbot_v2.activity_record "
                    "WHERE external_id=%s ORDER BY sec", (ride_key,))
        rec = cur.fetchall()
        for e in et:
            a, b = e["km"][0] * 1000.0, e["km"][1] * 1000.0
            seg = [x for x in rec if x[0] is not None and a <= float(x[0]) <= b]
            mov = [x for x in seg if (x[3] or 0) > 0.5]
            if len(mov) < 60:
                continue
            pw = [float(x[1] or 0) for x in mov]
            ped = [p for p in pw if p > 0]
            hr = [float(x[2]) for x in mov if x[2]]
            avg = sum(pw) / len(pw)
            np_ = _np([float(x[1] or 0) for x in seg])
            lo, hi = e.get("moc_od"), e.get("moc_do")
            ocena, pin, pab = None, None, None
            if lo and hi:
                if ped:
                    pin = round(sum(1 for p in ped if lo <= p <= hi) / len(ped) * 100)
                    pab = round(sum(1 for p in ped if p > hi) / len(ped) * 100)
                # srednia z postojami/zjazdami bywa nizsza niz plan, a i tak jazda byla "szarpana":
                # NP > gorna granica o 5% albo >=30% czasu pedalowania powyzej zakresu = nierowno
                nierowno = (np_ is not None and np_ > hi * 1.05) or (pab is not None and pab >= 30)
                if avg > hi * 1.03:
                    ocena = "za mocno"
                elif nierowno:
                    ocena = "nierowno (za duzo mocnych zrywow)"
                elif avg < lo * 0.97:
                    ocena = "za slabo"
                else:
                    ocena = "w planie"
            odc.append({"km": e["km"], "teren": e.get("teren"), "tryb": e.get("tryb"), "plan_w": [lo, hi],
                        "sr_moc_w": round(avg), "np_w": round(np_) if np_ else None,
                        "sr_tetno": round(sum(hr) / len(hr)) if hr else None,
                        "czas_w_zakresie_pct": pin, "czas_powyzej_pct": pab, "ocena": ocena})
    # wejscie w jazde
    wej = {}
    cur.execute("SELECT readiness_score, readiness_label FROM qbot_v2.fitmodel_daily WHERE day=%s", (day,))
    r = cur.fetchone()
    if r:
        wej["gotowosc_rano"] = _f(r[0], 2)
        wej["gotowosc_opis"] = r[1]
    cur.execute("SELECT day, tsb_raw, ctl_xss, atl_raw FROM qbot_v2.fitmodel_daily WHERE day<%s ORDER BY day DESC LIMIT 1", (day,))
    r = cur.fetchone()
    if r:
        wej["swiezosc_przed"] = _f(r[1], 1)
        wej["forma_przed"] = _f(r[2], 1)
        wej["zmeczenie_przed"] = _f(r[3], 1)
    wl = _val(((w1 or {}).get("physio") or {}).get("wellness")) or {}
    for k_src, k_dst in (("sleep_h", "sen_h"), ("sleep_score", "sen_ocena"), ("hrv", "hrv"), ("rhr", "tetno_spoczynkowe"),
                         ("rhr_base", "tetno_spoczynkowe_norma")):
        if wl.get(k_src) is not None:
            wej[k_dst] = wl.get(k_src)
    # podobne jazdy (EF = NP / srednie tetno, wyzej = lepiej)
    pod = {}
    if ses and ses[4]:
        cur.execute("SELECT date, activity_name, distance_m, duration_s, normalized_power_w, avg_hr_bpm, " + _XSS + " "
                    "FROM qbot_v2.training_sessions WHERE external_id<>%s AND date<%s AND date>=%s "
                    "AND sport_type ILIKE %s AND duration_s BETWEEN %s AND %s "
                    "AND normalized_power_w IS NOT NULL AND avg_hr_bpm>0 ORDER BY date DESC LIMIT 6",
                    (ride_key, day, day - timedelta(days=180), "%cycl%", ses[4] * 0.65, ses[4] * 1.5))
        rows = cur.fetchall()
        ef_this = (float(ses[6]) / float(ses[8])) if (ses[6] and ses[8]) else None
        lst = []
        for x in rows:
            ef = float(x[4]) / float(x[5])
            lst.append({"data": str(x[0]), "nazwa": x[1], "dist_km": _f((x[2] or 0) / 1000.0, 0),
                        "czas_h": _f((x[3] or 0) / 3600.0, 1), "np_w": _f(x[4], 0), "sr_tetno": _f(x[5], 0),
                        "ef": round(ef, 2), "obciazenie": _f(x[6], 0)})
        if lst:
            efs = sorted(y["ef"] for y in lst)
            med = efs[len(efs) // 2]
            pod = {"uwaga": "orientacyjnie: inne trasy, pogoda i teren; EF=NP/srednie tetno, wyzej=lepiej",
                   "ta_jazda_ef": round(ef_this, 2) if ef_this else None, "mediana_ef": med,
                   "roznica_pct": (round((ef_this - med) / med * 100) if ef_this else None), "jazdy": lst}
    return {"realnie": real, "sumy": sumy, "odcinki": odc, "wejscie": wej, "podobne": pod}


# ---------------------------------------------------------------- 3) konsekwencje (na zywo)
def live_consequences(cur, day):
    day = _d(day)
    cur.execute("SELECT day, ctl_xss, atl_raw, tsb_raw, readiness_score, readiness_label FROM qbot_v2.fitmodel_daily "
                "WHERE day BETWEEN %s AND %s ORDER BY day", (day - timedelta(days=1), day + timedelta(days=7)))
    rows = [{"dzien": str(r[0]), "forma": _f(r[1], 1), "zmeczenie": _f(r[2], 1), "swiezosc": _f(r[3], 1),
             "gotowosc": _f(r[4], 2), "gotowosc_opis": r[5]} for r in cur.fetchall()]
    today = date.today()
    cur.execute("SELECT day, name, xss, zone, status FROM qbot_v2.trainer_session WHERE day>%s AND day<=%s "
                "ORDER BY day, id", (day, day + timedelta(days=7)))
    nxt = [{"dzien": str(r[0]), "nazwa": r[1], "obciazenie": _f(r[2], 0), "strefa": r[3], "status": r[4]} for r in cur.fetchall()]
    prog = []
    last = None
    for r in rows:
        if r["forma"] is not None and r["zmeczenie"] is not None and _d(r["dzien"]) <= today:
            last = r
    if last and (today - day).days <= 7:
        ctl, atl = last["forma"], last["zmeczenie"]
        d0 = _d(last["dzien"])
        load_by_day = {}
        for n in nxt:
            if n["status"] in ("plan", "done") and n["obciazenie"]:
                load_by_day[n["dzien"]] = load_by_day.get(n["dzien"], 0) + n["obciazenie"]
        for i in range(1, 8):
            dd = d0 + timedelta(days=i)
            L = load_by_day.get(str(dd), 0)
            ctl += (L - ctl) / 42.0
            atl += (L - atl) / 7.0
            prog.append({"dzien": str(dd), "obciazenie_plan": L, "swiezosc": round(ctl - atl, 1)})
    back = next((p["dzien"] for p in prog if p["swiezosc"] >= 0), None)
    return {"dni": rows, "nastepne_treningi": nxt, "prognoza_wg_planu": prog,
            "swiezosc_na_plusie_od": back,
            "opis_pol": "forma=CTL (dlugi trend), zmeczenie=ATL (7 dni), swiezosc=TSB=forma-zmeczenie (ujemna=zmeczony), gotowosc=poranny wskaznik (ujemny=zmeczony)"}


# ---------------------------------------------------------------- jedzenie
def nutrition_block(cur, day, plan, ses, real):
    et = plan.get("etapy") or []
    g = next((e["wegle_g_h"] for e in et if e.get("wegle_g_h")), None)
    l = next((e["picie_l_h"] for e in et if e.get("picie_l_h")), None)
    mh = real.get("czas_ruchu_h")
    out = {"plan_wegle_g_h": g, "plan_picie_l_h": l,
           "plan_wegle_razem_g": round(g * mh) if (g and mh) else None}
    try:
        cur.execute("SELECT l.eaten_at, i.carbs_g, i.kcal FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i "
                    "ON i.intake_log_id=l.id WHERE l.date=%s", (day,))
        rows = cur.fetchall()
    except Exception:
        cur.connection.rollback()
        rows = []
    out["wpisy"] = len(rows)
    out["dzien_wegle_g"] = round(sum(float(r[1] or 0) for r in rows)) if rows else None
    out["dzien_kcal"] = round(sum(float(r[2] or 0) for r in rows)) if rows else None
    if rows and ses and ses[1] and ses[2]:
        a, b = ses[1], ses[2]
        s = 0.0
        for r in rows:
            t = r[0]
            try:
                if isinstance(t, datetime):
                    tt = t if t.tzinfo else t.replace(tzinfo=a.tzinfo)
                    if a <= tt <= b:
                        s += float(r[1] or 0)
                elif t is not None:
                    tt = datetime.combine(_d(day), t, tzinfo=a.tzinfo)
                    if a <= tt <= b:
                        s += float(r[1] or 0)
            except Exception:
                pass
        out["w_trakcie_wegle_g"] = round(s)
    return out


def _conn():
    import os, sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    return _db_connect()


def live_for_day(day):
    """Konsekwencje na zywo dla endpointu (wlasne polaczenie, krotki odczyt)."""
    c = _conn()
    try:
        return live_consequences(c.cursor(), day)
    finally:
        c.close()


def build_facts(ride_key, w1, conn=None):
    own = conn is None
    conn = conn or _conn()
    try:
        return _build(conn, ride_key, w1)
    finally:
        if own:
            conn.close()


def _build(conn, ride_key, w1):
    cur = conn.cursor()
    ses = _session(cur, ride_key)
    day = _d(ses[0]) if ses else _d(((w1 or {}).get("ride") or {}).get("date"))
    plan = plan_block(cur, day, w1)
    wyk = execution_block(cur, ride_key, day, w1, plan, ses)
    kon = live_consequences(cur, day)
    jed = nutrition_block(cur, day, plan, ses, wyk["realnie"])
    return {"dzien": str(day), "plan": plan, "wykonanie": wyk, "konsekwencje": kon, "jedzenie": jed}
