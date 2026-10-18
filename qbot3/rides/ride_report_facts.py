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


RULE_ROWNOSC = ("Rownosc oceniaj po mocy 30-s (pola moc30s_*), nie po pojedynczych sekundach. Na gravelu i w terenie krotkie zrywy"
                " (do ~10 s: piach, korzenie, wyjscie z zakretu, krotki podjazd) sa normalne i nie sa bledem; blad to dlugie (30 s+) mocne"
                " odcinki powyzej planu. Pisz konkretnie, np. 'X% czasu (moc 30 s) powyzej Y W przy planie A-B W'. Rady dawaj pod"
                " nawierzchnie z teren_jazdy: na gravelu lzejsze przelozenie i wyzsza kadencja na luznym, krotkie podjazdy na gornej granicy"
                " zakresu, rozped ze zjazdu, pole mocy 30 s na liczniku - nie szosowe 'trzymaj idealnie rowno'. Nie uzywaj slowa 'szarpana',"
                " gdy ocena odcinka to 'w planie'.")


def _roll(vals, n):
    """Srednia kroczaca n probek (zapis 1 Hz) - moc 30 s; na poczatku srednia z tego, co jest."""
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out.append(s / min(i + 1, n))
    return out


def _teren(w1):
    """Nawierzchnia sladu tej jazdy (w1.surface.types_pct): udzial poza 'twarda szybka' -> asfalt / mieszana / gravel."""
    off = None
    try:
        blk = (w1 or {}).get("surface") or {}
        tp = ((blk.get("value") if isinstance(blk, dict) and "value" in blk else blk) or {}).get("types_pct") or {}
        if tp:
            off = round(100.0 - float(tp.get("twarda szybka") or 0), 1)
    except Exception:
        off = None
    if off is None:
        return {"klasa": "mieszana", "poza_twarda_szybka_pct": None}
    return {"klasa": "asfalt" if off < 25 else ("mieszana" if off < 60 else "gravel"), "poza_twarda_szybka_pct": off}


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
    tr = []
    for x in cur.fetchall():
        ob, est = _f(x[3], 0), False
        if not ob and (x[1] or 0) > 0:   # jazda z czasem, a obciazenie puste / 0 -> szacunek z czasu (NIE 'plan 0')
            try:
                import qbot_trener_engine as _E
                ob = _E.xss_of("rower", x[2] or 2, int(x[1]))
            except Exception:
                ob = round(0.75 * x[1])
            est = True
        tr.append({"nazwa": x[0], "czas_min": x[1], "strefa": x[2], "obciazenie": ob, "status": x[4], "notatka": x[5],
                   **({"obciazenie_szacowane_z_czasu": True} if est else {})})
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
        # 2026-10-18: 'g/h' albo 'g weglowodanow na godzine'; 'l/h' albo '0,6 l na godzine' (przecinek)
        g = re.search(r"(\d+)\s*g(?:\s+w\w+)?\s*(?:/\s*h|na\s+godzin)", str(e.get("zywienie") or ""), re.I)
        l = re.search(r"(\d+(?:[.,]\d+)?)\s*l\s*(?:/\s*h|na\s+godzin)", str(e.get("pojenie") or ""), re.I)
        tryb = re.search(r"tryb\s+(\w+)", str(e.get("moc") or ""))
        et.append({"km": [float(z.group(1)), float(z.group(2))],
                   "moc_od": int(m.group(1)) if m else None, "moc_do": int(m.group(2)) if m else None,
                   "tryb": tryb.group(1) if tryb else None, "teren": e.get("tytul"), "wskazowka": e.get("opis"),
                   "wegle_g_h": int(g.group(1)) if g else None, "picie_l_h": float(l.group(1).replace(",", ".")) if l else None})
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
    teren = _teren(w1)
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
            hr = [float(x[2]) for x in mov if x[2]]
            avg = sum(pw) / len(pw)
            np_ = _np([float(x[1] or 0) for x in seg])
            lo, hi = e.get("moc_od"), e.get("moc_do")
            ocena, m30 = None, {}
            if lo and hi:
                # 2026-10-18 (decyzja Michala): rownosc po mocy 30-s (z sekundami toczenia), a nie po % sekund pedalowania
                # (to drugie z natury wychodzi wysoko, zwl. na gravelu). Progi zalezne od nawierzchni sladu jazdy.
                p30 = _roll(pw, 30)
                n30 = float(len(p30))
                hi_w = hi * 1.10
                m30 = {"moc30s_w_zakresie_pct": round(sum(1 for p in p30 if lo <= p <= hi) / n30 * 100),
                       "moc30s_powyzej_pct": round(sum(1 for p in p30 if p > hi) / n30 * 100),
                       "moc30s_wyraznie_powyzej_pct": round(sum(1 for p in p30 if p > hi_w) / n30 * 100),
                       "moc30s_wyraznie_od_w": round(hi_w),
                       "moc30s_ponizej_pct": round(sum(1 for p in p30 if p < lo) / n30 * 100)}
                kl = teren["klasa"]
                np_lim = hi * {"asfalt": 1.05, "mieszana": 1.08, "gravel": 1.12}[kl]
                prog = {"asfalt": 15, "mieszana": 25, "gravel": 35}[kl]
                m30["prog_nierownosci_pct"] = prog
                nierowno = (np_ is not None and np_ > np_lim) or m30["moc30s_wyraznie_powyzej_pct"] >= prog
                if avg > hi * 1.03:
                    ocena = "za mocno"
                elif nierowno:
                    ocena = "nierowno (za dlugie mocne odcinki - moc 30 s)"
                elif avg < lo * 0.97:
                    ocena = "za slabo"
                else:
                    ocena = "w planie"
            odc.append(dict({"km": e["km"], "teren": e.get("teren"), "tryb": e.get("tryb"), "plan_w": [lo, hi],
                             "sr_moc_w": round(avg), "np_w": round(np_) if np_ else None,
                             "sr_tetno": round(sum(hr) / len(hr)) if hr else None, "ocena": ocena}, **m30))
    # wejscie w jazde
    wej = {}
    cur.execute("SELECT readiness_score, readiness_label FROM qbot_v2.fitmodel_daily WHERE day=%s", (day,))
    r = cur.fetchone()
    if r:
        wej["gotowosc_rano"] = _f(r[0], 2)
        wej["gotowosc_opis"] = r[1]
    cur.execute("SELECT day, COALESCE(tsb_real, tsb_plus, tsb_raw), ctl_xss, COALESCE(atl_real, atl_plus, atl_raw) "   # kanon 14.10: faktyczne
                "FROM qbot_v2.fitmodel_daily WHERE day<%s ORDER BY day DESC LIMIT 1", (day,))
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
    # 2026-10-06: predkosc netto/brutto + odniesienie do tabeli predkosci uzytkownika (W1.speed)
    pr = _val((w1 or {}).get("speed"))
    return {"realnie": real, "predkosc": pr, "sumy": sumy, "odcinki": odc, "wejscie": wej, "podobne": pod,
            "teren_jazdy": teren, "jak_oceniac_rownosc": (RULE_ROWNOSC if odc else None)}


# ---------------------------------------------------------------- 3) konsekwencje (na zywo)
def live_consequences(cur, day):
    day = _d(day)
    # kanon 2026-10-14: zmeczenie/swiezosc FAKTYCZNE (treningi + stan ciala) - ta sama liczba co Forma, Start i Albert
    cur.execute("SELECT day, ctl_xss, COALESCE(atl_real, atl_plus, atl_raw), COALESCE(tsb_real, tsb_plus, tsb_raw), "
                "readiness_score, readiness_label, atl_raw FROM qbot_v2.fitmodel_daily "
                "WHERE day BETWEEN %s AND %s ORDER BY day", (day - timedelta(days=1), day + timedelta(days=7)))
    rows = [{"dzien": str(r[0]), "forma": _f(r[1], 1), "zmeczenie": _f(r[2], 1), "swiezosc": _f(r[3], 1),
             "gotowosc": _f(r[4], 2), "gotowosc_opis": r[5], "zmeczenie_z_treningow": _f(r[6], 1),
             "korekta_ciala": (round(float(r[2]) - float(r[6]), 1) if (r[2] is not None and r[6] is not None) else None)}
            for r in cur.fetchall()]
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
            "opis_pol": "forma=CTL (dlugi trend), zmeczenie=faktyczne: ATL z treningow (7 dni) + korekta stanu ciala (gotowosc, tetno spocz., Body Battery, infekcja, samopoczucie; zmeczenie_z_treningow + korekta_ciala), swiezosc=TSB=forma-zmeczenie (ujemna=zmeczony), gotowosc=poranny wskaznik (ujemny=zmeczony)"}


# ---------------------------------------------------------------- jedzenie
_LIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l)\b", re.I)


def _liters(name) -> float:
    """2026-10-18: objetosc napoju z nazwy pozycji Dziennika ('0,5 l', '500 ml'); brak -> 0."""
    m = _LIT_RE.search(str(name or ""))
    if not m:
        return 0.0
    v = float(m.group(1).replace(",", "."))
    return v / 1000.0 if m.group(2).lower() == "ml" else v


def nutrition_block(cur, day, plan, ses, real):
    et = plan.get("etapy") or []
    g = next((e["wegle_g_h"] for e in et if e.get("wegle_g_h")), None)
    l = next((e["picie_l_h"] for e in et if e.get("picie_l_h")), None)
    mh = real.get("czas_ruchu_h")
    out = {"plan_wegle_g_h": g, "plan_picie_l_h": l,
           "plan_wegle_razem_g": round(g * mh) if (g and mh) else None}
    try:
        cur.execute("SELECT l.eaten_at, i.carbs_g, i.kcal, l.meal_type, i.food_name FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i "
                    "ON i.intake_log_id=l.id WHERE l.date=%s", (day,))
        rows = cur.fetchall()
    except Exception:
        cur.connection.rollback()
        rows = []
    out["wpisy"] = len(rows)
    out["dzien_wegle_g"] = round(sum(float(r[1] or 0) for r in rows)) if rows else None
    out["dzien_kcal"] = round(sum(float(r[2] or 0) for r in rows)) if rows else None
    if rows and ses and ses[1]:
        # 2026-10-18: okno jazdy takze bez ended_at (start + czas x 1,2 + 15 min); wpisy 'na_rowerze' licza sie zawsze
        a = ses[1]
        b = ses[2] or (a + timedelta(seconds=int(float(ses[4] or 0) * 1.2) + 900))
        s, k, fl = 0.0, 0.0, 0.0
        for r in rows:
            t, inn = r[0], r[3] == "na_rowerze"
            try:
                if not inn and isinstance(t, datetime):
                    tt = t if t.tzinfo else t.replace(tzinfo=a.tzinfo)
                    inn = a <= tt <= b
                elif not inn and t is not None:
                    inn = a <= datetime.combine(_d(day), t, tzinfo=a.tzinfo) <= b
            except Exception:
                inn = False
            if inn:
                s += float(r[1] or 0)
                k += float(r[2] or 0)
                fl += _liters(r[4])
        out["w_trakcie_wegle_g"] = round(s)
        out["w_trakcie_kcal"] = round(k)
        if fl:   # 2026-10-18: plyny z nazwy pozycji Dziennika ('0,5 l', '500 ml')
            out["w_trakcie_plyny_l"] = round(fl, 2)
            if mh:
                out["w_trakcie_plyny_l_h"] = round(fl / mh, 2)
            out["plyny_uwaga"] = "tylko plyny wpisane do Dziennika; woda z bidonu zwykle nie jest wpisywana - nie zakladaj, ze to calosc"
        if mh and s:
            out["w_trakcie_wegle_g_h"] = round(s / mh)
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


def energy_block(cur, ride_key, day, ses, jed):
    """2026-10-18 (decyzja Michala): 'Energia na jezdzie' - wydatek i spalone weglowodany (wzory i stale fitmodel.glycogen),
    jedzenie przed startem (3 h / od polnocy) i w trakcie, glikogen start/meta wg modelu QBota (koniec poprzedniego dnia
    - drenaz do startu + wchloniete weglowodany sprzed startu), spadek mocy i mocy/tetno na ostatnich 25% jazdy. Szacunek."""
    try:
        import fitmodel.glycogen as G
        if not ses or not ses[1]:
            return None
        a = ses[1]
        cur.execute("SELECT power_w, hr_bpm, speed_mps FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (ride_key,))
        rec = cur.fetchall()
        rows = [{"power": float(r[0])} for r in rec if r[0] is not None]
        if len(rows) < 600:
            return None
        par = G.load_params(cur.connection)
        cur.execute("SELECT ftp_est_w FROM qbot_v2.fitmodel_daily WHERE day<=%s AND ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1", (day,))
        r = cur.fetchone()
        ftp = float(r[0]) if r and r[0] else float(par.get("ftp_anchor_w", 245.0))
        kcal = G._compute_ride_kcal_rows(rows)
        cho = G._compute_cho_burn_rows(rows, ftp)
        absr = float(par.get("cho_absorption_factor", G.DEFAULT_CHO_ABSORPTION))
        drain = float(par.get("glycogen_drain_base_g_day", G.DEFAULT_GLYCOGEN_DRAIN))
        cap_kg = float(par.get("glycogen_capacity_g_per_kg", G.DEFAULT_CAPACITY_PER_KG))
        cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE day<=%s AND weight_kg IS NOT NULL ORDER BY day DESC LIMIT 1", (day,))
        r = cur.fetchone()
        w = float(r[0]) if r and r[0] else G.DEFAULT_WEIGHT_KG
        cap = cap_kg * w
        d0 = datetime.combine(_d(day), datetime.min.time(), tzinfo=a.tzinfo)
        cur.execute("SELECT l.eaten_at, i.carbs_g, l.meal_type FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i "
                    "ON i.intake_log_id=l.id WHERE l.date=%s", (day,))
        before_day = before_3h = 0.0
        for t, cg, mt in cur.fetchall():
            if mt == "na_rowerze" or not isinstance(t, datetime):
                continue
            tt = t if t.tzinfo else t.replace(tzinfo=a.tzinfo)
            if tt < a:
                before_day += float(cg or 0)
                if tt >= a - timedelta(hours=3):
                    before_3h += float(cg or 0)
        during = float((jed or {}).get("w_trakcie_wegle_g") or 0)
        out = {"wydatek_kcal": round(kcal), "spalone_wegle_g": round(cho), "ftp_w": round(ftp),
               "zjedzone_przed_3h_wegle_g": round(before_3h), "zjedzone_dzis_przed_startem_wegle_g": round(before_day),
               "w_trakcie_wegle_g": round(during), "pojemnosc_g": round(cap)}
        cur.execute("SELECT glycogen_g, glycogen_confidence FROM qbot_v2.fitmodel_daily WHERE day<%s AND glycogen_g IS NOT NULL "
                    "ORDER BY day DESC LIMIT 1", (day,))
        r = cur.fetchone()
        if r and r[0] is not None and cap:
            hrs = (a - d0).total_seconds() / 3600.0
            g0 = max(0.0, min(cap, float(r[0]) - drain * hrs / 24.0 + absr * before_day))
            g1 = max(0.0, min(cap, g0 - cho + absr * during))
            out.update({"glikogen_start_g": round(g0), "glikogen_start_pct": round(g0 / cap * 100),
                        "glikogen_meta_g": round(g1), "glikogen_meta_pct": round(g1 / cap * 100), "pewnosc_startu": r[1]})
        mov = [(float(x[0] or 0), float(x[1]) if x[1] else None) for x in rec if (x[2] or 0) > 0.5]
        if len(mov) >= 1200:
            cut = int(len(mov) * 0.75)

            def _m(seg):
                p = sum(x[0] for x in seg) / len(seg)
                hs = [x[1] for x in seg if x[1]]
                h = sum(hs) / len(hs) if hs else None
                return p, (p / h if h else None)
            p1, e1 = _m(mov[:cut])
            p2, e2 = _m(mov[cut:])
            out["koncowka"] = {"czesc": "ostatnie 25% czasu ruchu vs wczesniejsze 75%", "moc_wczesniej_w": round(p1),
                               "moc_koncowka_w": round(p2),
                               "spadek_mocy_pct": round((p1 - p2) / p1 * 100) if p1 else None,
                               "spadek_ef_pct": round((e1 - e2) / e1 * 100) if (e1 and e2) else None}
        out["uwaga"] = ("szacunek modelu glikogenu QBota (fitmodel.glycogen): wydatek = moc / 0,23, frakcja weglowodanow wg %%FTP, "
                        "pojemnosc = %.1f g/kg x %.0f kg; start = koniec poprzedniego dnia - drenaz do startu + wchloniete "
                        "weglowodany sprzed startu" % (cap_kg, w))
        return out
    except Exception as e:  # dodatek - raport ma powstac i bez niego
        print("ride_report_facts energia:", e)
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return None


def feel_block(cur, day):
    """2026-10-18: odczucia Michala z tego dnia - ocena planu i komentarz z Trenera (trainer_rating, rower) oraz jego
    wpisy samopoczucia z Kalendarza (bez kopii komentarza z Trenera, source='trener'). Brak -> None."""
    out = {}
    try:
        cur.execute("SELECT rating, note FROM qbot_v2.trainer_rating WHERE day=%s AND sport='rower' ORDER BY updated_at DESC LIMIT 1", (day,))
        r = cur.fetchone()
        if r:
            out["ocena_planu_1_5"] = int(r[0])
            if r[1]:
                out["komentarz_Michala"] = r[1]
        cur.execute("SELECT title, feel, note FROM qbot_v2.calendar_entry WHERE kind='feel' AND day=%s AND COALESCE(source,'')<>'trener' "
                    "ORDER BY id", (day,))
        sam = [{"tytul": x[0], "ocena": x[1], "opis": x[2]} for x in cur.fetchall()]
        if sam:
            out["samopoczucie_z_Kalendarza"] = sam
    except Exception as e:  # odczucia sa dodatkiem - raport ma powstac i bez nich
        print("ride_report_facts odczucia:", e)
        return None
    return out or None


def _build(conn, ride_key, w1):
    cur = conn.cursor()
    ses = _session(cur, ride_key)
    day = _d(ses[0]) if ses else _d(((w1 or {}).get("ride") or {}).get("date"))
    plan = plan_block(cur, day, w1)
    wyk = execution_block(cur, ride_key, day, w1, plan, ses)
    kon = live_consequences(cur, day)
    jed = nutrition_block(cur, day, plan, ses, wyk["realnie"])
    return {"dzien": str(day), "plan": plan, "wykonanie": wyk, "konsekwencje": kon, "jedzenie": jed,
            "odczucia": feel_block(cur, day), "energia": energy_block(cur, ride_key, day, ses, jed)}
