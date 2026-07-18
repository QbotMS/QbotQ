# -*- coding: utf-8 -*-
"""W1 builder — deterministyczny generator danych raportu z jazdy (schema_version=1).

Zasady kontraktu:
- Liczy WYLACZNIE fakty (moc/HR/biegi z FIT, forma z ModelQ, wellness z Garmin).
- Kazda wartosc ma tier (A=twarde z FIT / B=estymata / C=brak) i source.
- Wiatr i nawierzchnia = WTYCZKI: zwracaja status 'parked' i value=None do decyzji uzytkownika.
- Temperatura z FIT (pomiar). Forma: FTP=CP i W' z ModelQ (dzienny fitmodel_daily); Xert tylko jako fallback per-pole, gdy ModelQ nie ma swiezej wartosci (patrz DECISIONS.md 2026-07-06).
- Ta sama jazda -> ten sam W1 (brak losowosci, brak czasu 'teraz' w liczbach).
"""
import os, math, collections
from fitparse import FitFile

SCHEMA_VERSION = 1

# --- stale modelu (literaturowe / sprzet) ---
HR_MAX = 184
CDA = 0.42          # estymata: hoody, duzy zawodnik
CRR = 0.010         # estymata: srednia gravel
RHO = 1.22
G = 9.81
BIKE_KG = 9.0       # rower+bidon+sprzet (estymata do audytu energii)

def _tag(value, tier, source, **extra):
    d = {"value": value, "tier": tier, "source": source}
    d.update(extra)
    return d

def _plugin(reason):
    return {"value": None, "tier": "B", "source": "plugin", "status": "parked", "reason": reason}

# ---------- DB ----------
def _connect():
    try:
        import qbot_config  # laduje env
    except Exception:
        pass
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST","127.0.0.1"), port=os.getenv("PGPORT","5432"),
        dbname=os.getenv("PGDATABASE","qbot"), user=os.getenv("PGUSER","qbot"),
        password=os.getenv("PGPASSWORD",""), row_factory=dict_row,
        connect_timeout=5, autocommit=True)

def _modelq_form(cur):
    cur.execute("""SELECT day,ftp_est_w,ef_med_28d,weight_kg,w_per_kg
                   FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL
                   ORDER BY day DESC LIMIT 1""")
    r = cur.fetchone() or {}
    ftp = float(r["ftp_est_w"]) if r.get("ftp_est_w") else None
    weight = float(r["weight_kg"]) if r.get("weight_kg") else _garmin_weight(cur)
    wkg = float(r["w_per_kg"]) if r.get("w_per_kg") else (round(ftp/weight,2) if (ftp and weight) else None)
    return {
        "ftp_w": ftp, "cp_w": ftp,  # CP=FTP z ModelQ (=TP w MQ2)
        "ef_med_28d": float(r["ef_med_28d"]) if r.get("ef_med_28d") else None,
        "weight_kg": weight,
        "wkg": wkg,
        "as_of": str(r.get("day")),
    }

def _xert_wprime(cur):
    try:
        cur.execute("SELECT w_prime_kj FROM qbot_v2.xert_profile_snapshots ORDER BY 1 DESC LIMIT 1")
        r = cur.fetchone()
        return float(r["w_prime_kj"])*1000.0 if r and r.get("w_prime_kj") is not None else None
    except Exception:
        return None

def _garmin_weight(cur):
    """Najswiezsza waga z Garmina (body_latest_weight)."""
    try:
        cur.execute("SELECT weight_kg FROM qbot_v2.body_latest_weight ORDER BY date DESC LIMIT 1")
        r = cur.fetchone()
        return float(r["weight_kg"]) if r and r.get("weight_kg") is not None else None
    except Exception:
        return None

def _modelq_wprime(cur, ride_day):
    """W' z ModelQ (fitmodel_daily.wprime_modelq_kj) dla dnia jazdy -- najblizszy
    dostepny dzien <= data jazdy. Fallback do Xerta TYLKO gdy ModelQ nie ma
    wartosci (np. brak swiezego twardego fragmentu -- Krok 2, confidence low).
    Zwraca (wartosc_w_dzulach, zrodlo) -- zrodlo do uczciwego taga w raporcie."""
    try:
        cur.execute(
            "SELECT wprime_modelq_kj FROM qbot_v2.fitmodel_daily "
            "WHERE day<=%s AND wprime_modelq_kj IS NOT NULL ORDER BY day DESC LIMIT 1",
            (ride_day,),
        )
        r = cur.fetchone()
        if r and r.get("wprime_modelq_kj") is not None:
            return float(r["wprime_modelq_kj"])*1000.0, "modelq"
    except Exception:
        pass
    return _xert_wprime(cur), "xert"

def _ef_anchor(cur):
    try:
        cur.execute("SELECT value FROM qbot_v2.fitmodel_param WHERE key='ef_anchor'")
        r = cur.fetchone(); return float(r["value"]) if r else None
    except Exception:
        return None

def _wellness(cur, day):
    out = {}
    try:
        cur.execute("SELECT * FROM qbot_v2.wellness_daily WHERE date=%s", (day,))
        w = cur.fetchone() or {}
        cur.execute("SELECT * FROM qbot_v2.sleep_daily WHERE date=%s", (day,))
        s = cur.fetchone() or {}
        out = {
            "sleep_h": round(s["duration_min"]/60.0,2) if s.get("duration_min") else None,
            "sleep_score": s.get("score"),
            "deep_min": s.get("deep_min"), "light_min": s.get("light_min"), "rem_min": s.get("rem_min"),
            "hrv": s.get("hrv_ms"), "rhr": w.get("resting_hr_bpm") or s.get("resting_hr_bpm"),
            "bb_start": w.get("body_battery_start"), "bb_end": w.get("body_battery_end"),
            "stress": w.get("stress_avg"), "spo2": w.get("spo2_avg"), "resp": w.get("respiration_avg"),
        }
    except Exception:
        pass
    return out

def _rhr_base(cur):
    try:
        cur.execute("SELECT MIN(resting_hr_bpm) m FROM qbot_v2.wellness_daily WHERE date > (CURRENT_DATE - 60)")
        r = cur.fetchone(); return r["m"] if r else None
    except Exception:
        return None

def _nutrition(cur):
    daily=[]; gaps=[]
    try:
        cur.execute("""SELECT date,kcal,carbs_g,protein_g FROM qbot_v2.nutrition_daily_summary
                       WHERE date BETWEEN (CURRENT_DATE-6) AND CURRENT_DATE ORDER BY date""")
        have={}
        for r in cur.fetchall():
            have[str(r["date"])]=r
            daily.append({"day":str(r["date"]),"kcal":r.get("kcal"),
                          "cho":float(r["carbs_g"]) if r.get("carbs_g") else None,
                          "protein":float(r["protein_g"]) if r.get("protein_g") else None})
    except Exception:
        pass
    return {"daily":daily,"gaps":gaps}

def _plan_snapshot(cur, route_id="55957534"):
    try:
        cur.execute("SELECT data_json FROM qbot_v2.route_report_snapshots WHERE route_id=%s ORDER BY 1 DESC LIMIT 1",(route_id,))
        r = cur.fetchone()
        if not r: return None
        dj = r["data_json"]
        det = (dj or {}).get("details",{}) if isinstance(dj,dict) else {}
        strat = det.get("strategia") or {}
        return strat if strat else None
    except Exception:
        return None

def _plan_vs_actual(cur, recs, ride_key):
    """Plan vs realizacja: dopasowuje jazde do zaplanowanej trasy (_find_matching_route)
    i zestawia strukturalne liczby planu (dystans, przewyzszenie, cel mocy z prozy)
    z realnymi (dystans, przewyzszenie, NP, TSS, srednia predkosc). Brak dopasowania
    -> _matched False (renderer pokaze tylko realnie)."""
    import re
    P = [r["p"] for r in recs]
    dist_km = round(recs[-1]["dist"] / 1000.0, 1) if recs else None
    asc = 0.0; prev = None
    for r in recs:
        a = r.get("alt")
        if a is None:
            continue
        if prev is not None and a > prev:
            asc += (a - prev)
        prev = a
    dur_mov = sum(1 for r in recs if r["spd"] > 0.5)
    v_kmh = round(dist_km / (dur_mov / 3600.0), 1) if (dist_km and dur_mov) else None
    np_w = round(_np(P)) if P else None
    tss = None
    try:
        cur.execute("SELECT tss FROM qbot_v2.training_sessions WHERE external_id=%s", (ride_key,))
        _t = cur.fetchone()
        if _t and _t.get("tss") is not None:
            tss = round(float(_t["tss"]))
    except Exception:
        pass
    real = {"dist_km": dist_km, "ascent_m": round(asc), "np_w": np_w, "tss": tss, "v_kmh": v_kmh}
    matched = None
    try:
        cur.execute("SELECT lat, lon, ts FROM qbot_v2.activity_record WHERE external_id=%s AND lat IS NOT NULL ORDER BY sec ASC LIMIT 1", (ride_key,))
        _p = cur.fetchone()
        if _p and _p.get("lat") is not None:
            matched = _find_matching_route(cur, float(_p["lat"]), float(_p["lon"]), _p["ts"])
    except Exception:
        matched = None
    if not matched:
        return {"_matched": False, "_real": real}
    plan = None; strat = None; rname = None
    try:
        cur.execute("SELECT data_json FROM qbot_v2.route_report_snapshots WHERE route_id=%s ORDER BY 1 DESC LIMIT 1", (matched,))
        rr = cur.fetchone()
        dj = rr["data_json"] if rr else None
        if isinstance(dj, str):
            import json as _j
            dj = _j.loads(dj)
        dj = dj or {}
        ro = dj.get("route") or {}
        rname = ro.get("name")
        strat = (dj.get("details", {}) or {}).get("strategia")
        pw = None
        cal = (strat or {}).get("calosc") if isinstance(strat, dict) else None
        if isinstance(cal, str):
            mm = re.search(r"([0-9]{2,3}) *- *([0-9]{2,3}) *W", cal)
            if mm:
                pw = mm.group(1) + "-" + mm.group(2) + " W"
        plan = {"dist_km": ro.get("distance_km"), "ascent_m": ro.get("ascent_m"), "power_note": pw}
    except Exception:
        pass
    out = {"_matched": True, "_route_id": matched, "_route_name": rname, "_plan": plan, "_real": real}
    if isinstance(strat, dict):
        out["etapy"] = strat.get("etapy"); out["calosc"] = strat.get("calosc")
    return out


# ---------- FIT ----------
def _parse_fit(path):
    ff = FitFile(path); recs=[]; t0=None; laps=[]; session={}
    for m in ff.get_messages("record"):
        d={f.name:f.value for f in m}
        if "timestamp" not in d: continue
        if t0 is None: t0=d["timestamp"]
        recs.append(dict(
            ts=d["timestamp"], sec=(d["timestamp"]-t0).total_seconds(),
            p=(d.get("power") or 0), spd=(d.get("enhanced_speed") or d.get("speed") or 0),
            cad=(d.get("cadence") or 0),
            alt=(d.get("enhanced_altitude") if d.get("enhanced_altitude") is not None else d.get("altitude")),
            grade=d.get("grade"), dist=(d.get("distance") or 0),
            hr=d.get("heart_rate"), temp=d.get("temperature"),
            lat=d.get("position_lat"), lon=d.get("position_long"),
            kwbal=d.get("qext2_wbal_pct"), kcp=d.get("qext2_cp_eff_w"),
            kwe=d.get("qext2_wprime_eff_kj"), kzero=d.get("qext2_wbal_zero"),
            kcf=d.get("qext2_cf")))
    events=[]
    for m in ff.get_messages("event"):
        d={f.name:f.value for f in m}
        if d.get("rear_gear_num") is not None or d.get("front_gear_num") is not None:
            events.append((d["timestamp"], d.get("front_gear_num"), d.get("rear_gear_num")))
    for m in ff.get_messages("session"):
        session={f.name:f.value for f in m}; break
    return recs, events, session

# ---------- bloki ----------
def _np(P):
    if len(P)<30: return sum(P)/len(P) if P else 0
    roll=[]; s=sum(P[:30])
    roll.append(s/30)
    for i in range(30,len(P)):
        s+=P[i]-P[i-30]; roll.append(s/30)
    return (sum(x**4 for x in roll)/len(roll))**0.25

def _load(recs, form, ef_anchor, xss_block, buckets=None):
    P=[r["p"] for r in recs]; n=len(recs)
    dur=recs[-1]["sec"]-recs[0]["sec"]
    dur_ride=len(recs)  # 1 Hz -> sekundy realnego nagrywania (bez postojow)
    dist=recs[-1]["dist"]/1000.0
    moving=[r for r in recs if r["spd"]>0.5]
    hr=[r["hr"] for r in recs if r["hr"]]
    np_=_np(P); avg=sum(P)/n
    ftp=form["ftp_w"]; mass=form["weight_kg"] or 101.0
    if_=np_/ftp if ftp else None
    ef=(np_/(sum(hr)/len(hr))) if hr else None
    kj=sum(P)/1000.0
    # strefy mocy (Coggan %FTP)
    zb=[0.55,0.75,0.90,1.05,1.20,1.50]
    zc=[0]*7
    for p in P:
        f=p/ftp if ftp else 0
        z=0
        for i,t in enumerate(zb):
            if f>t: z=i+1
        zc[z]+=1
    zones_power=[round(100*c/n) for c in zc]
    # strefy HR (%HRmax)
    hb=[0.60,0.70,0.80,0.90]; hzc=[0]*5
    for r in recs:
        if not r["hr"]: continue
        f=r["hr"]/HR_MAX; z=0
        for i,t in enumerate(hb):
            if f>t: z=i+1
        hzc[z]+=1
    thr=sum(hzc) or 1
    zones_hr=[round(100*c/thr) for c in hzc]
    # MMP
    def best(w):
        if w>len(P): return None
        s=sum(P[:w]); mx=s
        for i in range(w,len(P)): s+=P[i]-P[i-w]; mx=max(mx,s)
        return round(mx/w)
    mmp={"5s":best(5),"1min":best(60),"5min":best(300),"20min":best(1200),"60min":best(3600)}
    return {
        "np_w":_tag(round(np_),"A","fit"),
        "avg_p_w":_tag(round(avg),"A","fit"),
        "if":_tag(round(if_,2) if if_ else None,"A","fit+modelq"),
        "xss":xss_block,
        "wiadra":_tag(buckets,"A" if buckets else "C","modelq2"),
        "vi":_tag(round(np_/avg,2) if avg else None,"A","fit"),
        "ef":_tag(round(ef,2) if ef else None,"A","fit"),
        "kj":_tag(round(kj),"A","fit"),
        "kj_h":_tag(round(kj/(dur_ride/3600)) if dur_ride else None,"A","fit"),
        "wkg_np":_tag(round(np_/mass,2) if mass else None,"A","fit+modelq"),
        "max_p_w":_tag(max(P),"A","fit"),
        "ftp_w":_tag(round(ftp) if ftp else None,"A","modelq",as_of=form["as_of"]),
        "ef_anchor":_tag(ef_anchor,"A","modelq"),
        "dist_km":_tag(round(dist,1),"A","fit"),
        "dur_moving_s":_tag(int(len(moving)),"A","fit"),
        "dur_elapsed_s":_tag(int(dur),"A","fit"),
        "zones_power_pct":_tag(zones_power,"A","fit"),
        "zones_hr_pct":_tag(zones_hr,"A","fit"),
        "mmp":_tag(mmp,"A","fit"),
    }

def _last_ef(cur):
    """Ostatnia zapisana EF 28d z fitmodel_daily (carry-forward, gdy dzien pusty)."""
    try:
        cur.execute("SELECT ef_med_28d FROM qbot_v2.fitmodel_daily WHERE ef_med_28d IS NOT NULL ORDER BY day DESC LIMIT 1")
        r=cur.fetchone()
        return float(r["ef_med_28d"]) if r and r.get("ef_med_28d") is not None else None
    except Exception:
        return None

def _mq2_sig_before(cur, day):
    """Sygnatura MQ2 z dnia <= day (kauzalnie sprzed jazdy) do replay W'bal."""
    try:
        from fitmodel.modelq2.signature import Signature
        cur.execute("SELECT tp_w,hie_kj,pp_w FROM qbot_v2.modelq2_signature WHERE day<=%s ORDER BY day DESC LIMIT 1",(day,))
        r=cur.fetchone()
        if not r: return None
        return Signature.from_kj(tp_w=float(r["tp_w"]), hie_kj=float(r["hie_kj"]), pp_w=float(r["pp_w"]))
    except Exception:
        return None

def _mq2_buckets(cur, day):
    """Wiadra XSS (Low/High/Peak) tej jazdy z modelq2_ride (po dacie)."""
    try:
        cur.execute("""SELECT xss_low,xss_high,xss_peak,xss_total,min_wbal_pct
                       FROM qbot_v2.modelq2_ride WHERE ride_date=%s
                       ORDER BY xss_total DESC NULLS LAST LIMIT 1""",(day,))
        r=cur.fetchone()
        if not r: return None
        g=lambda k: float(r[k]) if r.get(k) is not None else None
        return {"low":g("xss_low"),"high":g("xss_high"),"peak":g("xss_peak"),
                "total":g("xss_total"),"min_wbal_pct":g("min_wbal_pct")}
    except Exception:
        return None

def _mq2_ride_row(cur, day):
    """Kanoniczny wiersz MQ2 tej jazdy (po dacie): external_id, sygnatura uzyta
    do replay, wiadra XSS, min W'bal. Zrodlo prawdy = modelq2_ride."""
    try:
        from fitmodel.modelq2.signature import Signature
        cur.execute("""SELECT external_id,sig_tp_w,sig_hie_kj,sig_pp_w,
                              xss_low,xss_high,xss_peak,xss_total,min_wbal_pct
                       FROM qbot_v2.modelq2_ride WHERE ride_date=%s
                       ORDER BY xss_total DESC NULLS LAST LIMIT 1""",(day,))
        r=cur.fetchone()
        if not r: return None
        g=lambda k: float(r[k]) if r.get(k) is not None else None
        sig=None
        if r.get("sig_tp_w") and r.get("sig_hie_kj") and r.get("sig_pp_w"):
            sig=Signature.from_kj(tp_w=float(r["sig_tp_w"]), hie_kj=float(r["sig_hie_kj"]), pp_w=float(r["sig_pp_w"]))
        return {"external_id": r["external_id"], "sig": sig,
                "buckets":{"low":g("xss_low"),"high":g("xss_high"),"peak":g("xss_peak"),
                           "total":g("xss_total"),"min_wbal_pct":g("min_wbal_pct")}}
    except Exception:
        return None

def _fetch_activity_rows(cur, external_id):
    """1Hz z activity_record (KANONICZNE dane) + dystans do koszykow 5 km."""
    try:
        cur.execute("SELECT ts, power_w, distance_m FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY ts",(external_id,))
        out=[]
        for r in cur.fetchall():
            out.append({"ts":r["ts"],
                        "p":(float(r["power_w"]) if r["power_w"] is not None else 0.0),
                        "dist":(float(r["distance_m"]) if r["distance_m"] is not None else 0.0)})
        return out or None
    except Exception:
        return None

def _wprime_karoo(recs):
    """Realna krzywa W'bal z Karoo (pola developerskie QExt2 w FIT). Pomiar Z ROWERU,
    skalowany gotowoscia dnia (cf/todayFactor) -> blizszy prawdzie niz statyczny replay."""
    K=[r for r in recs if r.get("kwbal") is not None]
    if not K: return None
    wb=[float(r["kwbal"]) for r in K]; mn=min(wb)
    step=max(1,len(K)//1500); curve=[]
    for i in range(0,len(K),step):
        curve.append([round((K[i].get("dist") or 0)/1000.0,3), round(float(K[i]["kwbal"]))])
    bins={}
    for r in K:
        kk=int((r.get("dist") or 0)//5000); bins[kk]=min(bins.get(kk,1e9), float(r["kwbal"]))
    series=[{"km":kk*5+5,"min_pct":round(v)} for kk,v in sorted(bins.items())]
    cpv=[float(r["kcp"]) for r in K if r.get("kcp") is not None]
    wev=[float(r["kwe"]) for r in K if r.get("kwe") is not None]
    cfv=[float(r["kcf"]) for r in K if r.get("kcf") is not None]
    return {
        "cp_avg": round(sum(cpv)/len(cpv)) if cpv else None,
        "cp_min": round(min(cpv)) if cpv else None,
        "we_avg_j": round(sum(wev)/len(wev)*1000) if wev else None,
        "cf_avg": round(sum(cfv)/len(cfv),2) if cfv else None,
        "min_pct": round(mn), "zero": any(bool(r.get("kzero")) for r in K),
        "lt50": sum(1 for v in wb if v<50), "lt25": sum(1 for v in wb if v<25),
        "series": series, "curve": curve,
    }

def _overlay_karoo(out, recs):
    """Jesli FIT ma realna krzywa W'bal z Karoo -> nadpisz nia pola W'bal, zachowujac
    statyczny min do porownania (wbal_min_static_pct) oraz top_efforts z replayu."""
    if not out: return out
    kar=_wprime_karoo(recs)
    if not kar: return out
    out["wbal_min_static_pct"]=out.get("wbal_min_pct")
    out["wbal_min_pct"]=_tag(kar["min_pct"],"A","karoo (QExt2)")
    out["wbal_series"]=_tag(kar["series"],"A","karoo (QExt2)")
    out["wbal_curve"]=_tag(kar["curve"],"A","karoo (QExt2)")
    out["wbal_zero"]=_tag(kar["zero"],"A","karoo (QExt2)")
    if kar["cp_avg"] is not None:
        out["cp_eff_w"]=_tag(kar["cp_avg"],"A","karoo cp_eff (QExt2)", cp_min_w=kar["cp_min"])
    if kar["we_avg_j"] is not None:
        out["wprime_eff_j"]=_tag(kar["we_avg_j"],"A","karoo w'_eff (QExt2)")
    if kar["cf_avg"] is not None:
        out["cf_avg"]=_tag(kar["cf_avg"],"A","karoo todayFactor")
    out["time_lt50_min"]=_tag(round(kar["lt50"]/60),"B","karoo")
    out["time_lt25_min"]=_tag(round(kar["lt25"]/60),"B","karoo")
    out["source_note"]=_tag("W'bal = realny pomiar z Karoo (QExt2), skalowany gotowoscia dnia (cf). Statyczny replay w wbal_min_static_pct.","A","karoo")
    return out

def _wprime(recs, mq_rows, sig, cp_fallback=None, wp_fallback=None, wp_source="xert"):
    """W'bal JEDNYM silnikiem MQ2 (replay_mpa) na KANONICZNYCH danych
    (activity_record) i sygnaturze z modelq2_ride -> min W'bal IDENTYCZNY jak
    modelq2_ride. Kolejnosc: activity_record -> FIT (fallback) -> stary inline."""
    def _run(rows_dd, cp, Wp, data_tag):
        from fitmodel.modelq2.mpa import replay_mpa
        rows=[(x["ts"], x["p"]) for x in rows_dd]
        res=replay_mpa(rows, sig, smooth=True, keep_series=True)
        S=res.series
        if not S: return None
        by_ts={x["ts"]:x for x in rows_dd}
        _bins={}
        for pt in S:
            xx=by_ts.get(pt["ts"]); d=(xx["dist"] if xx else 0.0)
            _k=int(d//5000); _bins[_k]=min(_bins.get(_k,1e9),100*pt["wbal"]/Wp)
        wbal_series=[{"km":_k*5+5,"min_pct":round(_v)} for _k,_v in sorted(_bins.items())]
        _cstep=max(1,len(S)//1500)
        wbal_curve=[]
        for _ci in range(0,len(S),_cstep):
            _pt=S[_ci]; _xx=by_ts.get(_pt["ts"]); _dk=((_xx["dist"] if _xx else 0.0)/1000.0)
            wbal_curve.append([round(_dk,3), round(100*_pt["wbal"]/Wp)])
        lt50=sum(1 for pt in S if pt["wbal"]<0.5*Wp)
        lt25=sum(1 for pt in S if pt["wbal"]<0.25*Wp)
        mn_pt=min(S,key=lambda p:p["wbal"]); mn=mn_pt["wbal"]; mr=by_ts.get(mn_pt["ts"])
        efforts=[]; i=0; N=len(S)
        while i<N:
            if S[i]["power_eff"]>=cp:
                j=i; cost=0.0
                while j<N and S[j]["power_eff"]>=cp:
                    cost+=S[j]["power_eff"]-cp; j+=1
                x0=by_ts.get(S[i]["ts"])
                efforts.append({"km":round((x0["dist"] if x0 else 0.0)/1000.0,1),"dur_s":j-i,
                                "avg_w":round(sum(p["power_eff"] for p in S[i:j])/(j-i)),
                                "cost_kj":round(cost/1000.0,1)})
                i=j
            else: i+=1
        efforts.sort(key=lambda e:-e["cost_kj"])
        tau_ref=round(546*math.exp(-0.01*cp)+316)
        return {
            "cp_w":_tag(round(cp),"A","modelq2 (TP)"),
            "wprime_j":_tag(round(Wp),"A","modelq2 (HIE)"),
            "wbal_min_pct":_tag(round(100*mn/Wp),"A",f"modelq2_replay ({data_tag})"),
            "time_lt50_min":_tag(round(lt50/60),"B","derived"),
            "time_lt25_min":_tag(round(lt25/60),"B","derived"),
            "tau_s":_tag(tau_ref,"B","mq2 dyn (ref @rest)"),
            "cutoff":_tag({"km":round((mr["dist"] if mr else 0.0)/1000.0,1),
                           "grade":None,"speed_kmh":None,
                           "surface":None,"wind_ms":None},"B",data_tag),
            "wbal_series":_tag(wbal_series,"A",f"modelq2_replay ({data_tag})"),
            "wbal_curve":_tag(wbal_curve,"A",f"modelq2_replay ({data_tag})"),
            "top_efforts":_tag(efforts[:3],"A","fit"),
        }
    _out=None
    if sig is not None and mq_rows:
        _out=_run(mq_rows, sig.tp_w, sig.hie_j, "activity_record")
    if _out is None and sig is not None and recs:
        _out=_run(recs, sig.tp_w, sig.hie_j, "fit")
    if _out is not None:
        return _overlay_karoo(_out, recs)
    # --- ostatni fallback: stary inline ---
    cp=cp_fallback; Wp=wp_fallback
    if not cp or not Wp:
        return {"_meta":{"tier":"C","source":"modelq2","reason":"brak danych/sygnatury MQ2 i CP/W'"}}
    P=[r["p"] for r in recs]
    below=[p for p in P if p<cp]
    dcp=cp-(sum(below)/len(below) if below else cp)
    tau=546*math.exp(-0.01*dcp)+316
    bal=Wp; series=[]; k=1-math.exp(-1.0/tau)
    for p in P:
        if p>=cp: bal-=(p-cp)
        else: bal+=(Wp-bal)*k
        if bal>Wp: bal=Wp
        if bal<0: bal=0
        series.append(bal)
    mn=min(series); mn_i=series.index(mn)
    _bins={}
    for _i,_b in enumerate(series):
        _k=int(recs[_i]["dist"]//5000)
        _bins[_k]=min(_bins.get(_k,1e9),100*_b/Wp)
    wbal_series=[{"km":_k*5+5,"min_pct":round(_v)} for _k,_v in sorted(_bins.items())]
    _cstep=max(1,len(series)//1500)
    wbal_curve=[]
    for _ci in range(0,len(series),_cstep):
        wbal_curve.append([round(recs[_ci]["dist"]/1000.0,3), round(100*series[_ci]/Wp)])
    lt50=sum(1 for b in series if b<0.5*Wp)
    lt25=sum(1 for b in series if b<0.25*Wp)
    efforts=[]; i=0
    while i<len(P):
        if P[i]>=cp:
            j=i; cost=0
            while j<len(P) and P[j]>=cp:
                cost+=P[j]-cp; j+=1
            efforts.append({"km":round(recs[i]["dist"]/1000.0,1),"dur_s":j-i,
                            "avg_w":round(sum(P[i:j])/(j-i)),"cost_kj":round(cost/1000.0,1)})
            i=j
        else: i+=1
    efforts.sort(key=lambda e:-e["cost_kj"])
    return _overlay_karoo({
        "cp_w":_tag(round(cp),"B","legacy_inline"),
        "wprime_j":_tag(round(Wp),"B","legacy_inline"),
        "wbal_min_pct":_tag(round(100*mn/Wp),"B","legacy_inline"),
        "time_lt50_min":_tag(round(lt50/60),"B","derived"),
        "time_lt25_min":_tag(round(lt25/60),"B","derived"),
        "tau_s":_tag(round(tau),"B","skiba"),
        "cutoff":_tag({"km":round(recs[mn_i]["dist"]/1000.0,1),
                       "grade":recs[mn_i]["grade"],"speed_kmh":round(recs[mn_i]["spd"]*3.6,1),
                       "surface":None,"wind_ms":None},"B","fit+plugins"),
        "wbal_series":_tag(wbal_series,"B","legacy_inline"),
        "wbal_curve":_tag(wbal_curve,"B","legacy_inline"),
        "top_efforts":_tag(efforts[:3],"A","fit"),
    }, recs)

def _drivetrain(recs, events):
    events=sorted(events,key=lambda x:x[0])
    def gear_at(ts):
        g=None
        for t,f,r in events:
            if t<=ts: g=r
            else: break
        return g
    cog=collections.Counter(); fronts=set()
    for t,f,r in events:
        if f is not None: fronts.add(f)
    for r in recs:
        g=gear_at(r["ts"])
        if g is not None: cog[g]+=1
    tot=sum(cog.values()) or 1
    cog_pct={str(c):round(100*cog[c]/tot) for c in sorted(cog)}
    rears=[e[2] for e in events if e[2] is not None]
    hardest=min(rears) if rears else None
    spin=sum(1 for r in recs if gear_at(r["ts"])==hardest and r["cad"]>95 and r["p"]<120 and (r["grade"] or 0)<-1)
    # kadencja wg nachylenia
    buck={"zjazd":[], "plasko":[], "podgore":[], "stromo":[]}
    for r in recs:
        if r["cad"]<=0: continue
        gr=r["grade"] or 0
        key="zjazd" if gr<-1 else ("plasko" if gr<1 else ("podgore" if gr<4 else "stromo"))
        buck[key].append(r["cad"])
    cad_grade={k:(round(sum(v)/len(v)) if v else None) for k,v in buck.items()}
    grind=sum(1 for r in recs if r["cad"]>0 and r["cad"]<=60 and r["p"]>220)
    # quadrant (prog moc 0.75*? uzyjemy 186 jak wczesniej -> parametrycznie: mediana? uzyjmy 75% z max cad median)
    cadmed=70; CPq=186
    q={"grind":0,"grupetto":0,"aero":0,"spin":0}
    for r in recs:
        if r["cad"]<=0: continue
        hp=r["p"]>=CPq; hc=r["cad"]>=cadmed
        q["grind" if(hp and not hc) else "aero" if(hp and hc) else "grupetto" if(not hp and not hc) else "spin"]+=1
    quad={k:round(v/60) for k,v in q.items()}
    # hamowanie / coasting
    brake=0.0
    for i in range(1,len(recs)):
        dv=recs[i]["spd"]-recs[i-1]["spd"]
        if dv<-0.3 and recs[i]["p"]<20:
            v1,v2=recs[i-1]["spd"],recs[i]["spd"]
            brake+=0.5*(108.0)*(v1*v1-v2*v2)/1000.0
    coast=sum(1 for r in recs if r["p"]==0 and r["spd"]>2)
    return {
        "shifts":_tag(len(events),"A","fit"),
        "front":_tag(sorted(fronts),"A","fit"),
        "cog_time_pct":_tag(cog_pct,"A","fit"),
        "spinout_s":_tag(spin,"A","fit"),
        "cad_by_grade":_tag(cad_grade,"A","fit"),
        "grind_min":_tag(round(grind/60),"A","fit"),
        "quadrant_min":_tag(quad,"A","fit"),
        "braking_kj":_tag(round(brake),"B","derived"),
        "coasting_min":_tag(round(coast/60),"A","fit"),
    }

def _physio(recs, wellness, rhr_base):
    hr=[r["hr"] for r in recs if r["hr"]]
    hr_avg=round(sum(hr)/len(hr)) if hr else None
    hr_max=max(hr) if hr else None
    # decoupling Pw:HR (polowa/polowa, tylko ruch z HR)
    mv=[r for r in recs if r["spd"]>0.5 and r["hr"]]
    half=len(mv)//2
    def ef(seg):
        pp=[r["p"] for r in seg]; hh=[r["hr"] for r in seg]
        return (sum(pp)/len(pp))/(sum(hh)/len(hh)) if seg else None
    e1,e2=ef(mv[:half]),ef(mv[half:])
    dec=round(100*(e1-e2)/e1,1) if (e1 and e2) else None
    w=dict(wellness); w["rhr_base"]=rhr_base
    return {
        "hr_avg":_tag(hr_avg,"A","fit"),
        "hr_max":_tag(hr_max,"A","fit"),
        "pct_hrmax":_tag(round(100*hr_max/HR_MAX) if hr_max else None,"A","fit"),
        "decoupling_pct":_tag(dec,"A","derived"),
        "wellness":_tag(w,"A","garmin"),
    }

def _energy(recs):
    aero=roll=climb=kin=0.0
    for i in range(1,len(recs)):
        v=recs[i]["spd"]
        if v>0:
            aero+=0.5*RHO*CDA*v**3; roll+=CRR*108.0*G*v
        a0,a1=recs[i-1]["alt"],recs[i]["alt"]
        if a0 is not None and a1 is not None and a1>a0: climb+=108.0*G*(a1-a0)
        dv=v-recs[i-1]["spd"]
        if dv>0: kin+=0.5*108.0*(v*v-recs[i-1]["spd"]**2)
    tot=aero+roll+climb+kin or 1
    P=[r["p"] for r in recs]; work=sum(P)/1000.0
    ftp=None
    cho=fat=0.0
    for p in P:
        share=0.5 if p<0.55*253 else (0.7 if p<0.75*253 else 0.9)
        cho+=p*share; fat+=p*(1-share)
    cho_pct=round(100*cho/(cho+fat)) if (cho+fat) else None
    carbs=round(work/4.1*0.85/4.0*(cho/(cho+fat))) if (cho+fat) else None
    return {
        "work_kj":_tag(round(work),"A","fit"),
        "audit_pct":_tag({"aero":round(100*aero/tot),"toczenie":round(100*roll/tot),
                          "wznoszenie":round(100*climb/tot),"kinetyka":round(100*kin/tot)},"B","estymata CdA/Crr"),
        "substrate":_tag({"cho_pct":cho_pct,"carbs_g_est":carbs},"B","model populacyjny"),
    }

def _splits(recs):
    half=recs[-1]["dist"]/2
    def blk(s):
        P=[r["p"] for r in s]; mv=[r for r in s if r["spd"]>0.5]; hr=[r["hr"] for r in s if r["hr"]]
        return {"np_w":round(_np(P)),"v_kmh":round(sum(r["spd"] for r in mv)/len(mv)*3.6,1),
                "hr":round(sum(hr)/len(hr)) if hr else None}
    return _tag({"first":blk([r for r in recs if r["dist"]<half]),
                 "second":blk([r for r in recs if r["dist"]>=half])},"A","fit")

def _weather_from_fit(recs):
    t=[r["temp"] for r in recs if r["temp"] is not None]
    return {
        "temp_c":_tag({"min":min(t),"max":max(t),"avg":round(sum(t)/len(t),1)} if t else None,"A","fit"),
        "apparent_c":_plugin("open-meteo — pogoda parked"),
        "rh_pct":_plugin("open-meteo — pogoda parked"),
        "pressure_hpa":_plugin("open-meteo — pogoda parked"),
        "cloud_pct":_plugin("open-meteo — pogoda parked"),
        "wbgt_max":_plugin("open-meteo — pogoda parked"),
        "sun_pct":_plugin("cien — wymaga trasy (parked)"),
    }

def _wbgt(ta, rh, solar, wind):
    """WBGT na otwartym (przyblizenie): baza ACSM 'w cieniu' + dodatek od naslonecznienia,
    tlumiony przez wiatr. Zwraca stopnie C. To estymata dla kolarza, nie pomiar."""
    if ta is None or rh is None:
        return None
    import math
    e = (rh / 100.0) * 6.105 * math.exp(17.27 * ta / (237.7 + ta))
    wbgt_shade = 0.567 * ta + 0.393 * e + 3.94
    s = max(solar or 0.0, 0.0)
    w = max(wind or 0.5, 0.5)
    solar_term = min(min(s, 1200.0) / 1000.0, 1.2) * 4.0 / math.sqrt(w)
    return wbgt_shade + min(solar_term, 6.0)


def _weather_block(recs, day):
    """Pogoda jazdy: temperatura z FIT (pomiar, tier A) + wilgotnosc/zachmurzenie/
    cisnienie/odczuwalna/WBGT z open-meteo dla godzin jazdy (tier B). sun_pct parked."""
    t = [r["temp"] for r in recs if r["temp"] is not None]
    temp_fit = {"min": min(t), "max": max(t), "avg": round(sum(t) / len(t), 1)} if t else None
    out = {
        "temp_c": _tag(temp_fit, "A", "fit"),
        "apparent_c": _plugin("open-meteo - brak danych"),
        "rh_pct": _plugin("open-meteo - brak danych"),
        "pressure_hpa": _plugin("open-meteo - brak danych"),
        "cloud_pct": _plugin("open-meteo - brak danych"),
        "wbgt_max": _plugin("open-meteo - brak danych"),
        "sun_pct": _plugin("cien - wymaga trasy (parked)"),
    }
    pos = [r for r in recs if r.get("lat") is not None and r.get("lon") is not None]
    if not pos:
        return out
    try:
        from tools.rwgps.route_weather import _fetch_open_meteo
        lat0, lon0 = _deg(pos[0]["lat"]), _deg(pos[0]["lon"])
        hourly = _fetch_open_meteo(lat0, lon0, day)
        keys = sorted({r["ts"].strftime("%Y-%m-%dT%H") for r in recs})
        rows = [hourly[k] for k in keys if k in hourly]
        if not rows:
            return out
        SRC = "open-meteo + GPS tej jazdy"
        def _avg(field):
            v = [x[field] for x in rows if x.get(field) is not None]
            return round(sum(v) / len(v), 1) if v else None
        rh = _avg("rh"); cloud = _avg("cloud"); press = _avg("pressure")
        if rh is not None:
            out["rh_pct"] = _tag(rh, "B", SRC)
        if cloud is not None:
            out["cloud_pct"] = _tag(cloud, "B", SRC)
        if press is not None:
            out["pressure_hpa"] = _tag(press, "B", SRC)
        app = [x["apparent"] for x in rows if x.get("apparent") is not None]
        if app:
            out["apparent_c"] = _tag({"min": round(min(app), 1), "max": round(max(app), 1),
                                      "avg": round(sum(app) / len(app), 1)}, "B", SRC)
        wbgts = []
        for x in rows:
            wb = _wbgt(x.get("temp"), x.get("rh"), x.get("solar"), x.get("wspeed"))
            if wb is not None:
                wbgts.append(wb)
        if wbgts:
            out["wbgt_max"] = _tag(round(max(wbgts), 1), "B", "open-meteo WBGT (T+RH+slonce+wiatr)")
    except Exception:
        pass
    return out


SC_DEG = 180.0 / (2 ** 31)

def _deg(v):
    """FIT position (semicircles) -> stopnie. None jesli brak."""
    return v * SC_DEG if v is not None else None

def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0

def _find_matching_route(cur, lat0, lon0, ride_start_ts, max_dist_m=500.0,
                         lookback_days=30, grace_min=10):
    """Heurystyka dopasowania: czy ta jazda zaczyna sie blisko poczatku jakiejs
    juz przeliczonej trasy (route_elevation_samples, punkt startowy) ORAZ czy
    ta trasa istniala PRZED startem jazdy (inaczej nie mogla byc planem na ta
    jazde -- np. ktos przeliczyl inna trase w tej samej okolicy PO fakcie).
    Malo tras w route_base (rzedu kilkunastu) -> pelny skan jest tani."""
    try:
        cur.execute("""SELECT DISTINCT ON (route_id) route_id, route_base_id, updated_at
                       FROM qbot_v2.route_base ORDER BY route_id, updated_at DESC""")
        candidates = cur.fetchall()
        cutoff_late = ride_start_ts + __import__("datetime").timedelta(minutes=grace_min)
        cutoff_early = ride_start_ts - __import__("datetime").timedelta(days=lookback_days)
        best_route, best_dist = None, max_dist_m
        for c in candidates:
            ua = c.get("updated_at")
            if ua is None or ua > cutoff_late or ua < cutoff_early:
                continue  # trasa nie istniala jeszcze w momencie startu (albo zbyt stara)
            cur.execute("""SELECT lat, lon FROM qbot_v2.route_elevation_samples
                           WHERE route_base_id=%s ORDER BY sample_index ASC LIMIT 1""",
                        (c["route_base_id"],))
            r = cur.fetchone()
            if not r or r.get("lat") is None:
                continue
            d = _haversine_m(lat0, lon0, r["lat"], r["lon"])
            if d < best_dist:
                best_dist, best_route = d, c["route_id"]
        return best_route
    except Exception:
        return None

def _surface_wind_from_route(cur, route_id, day, start_time):
    """Jazda pasuje do juz przeliczonej trasy -> reuzycie: nawierzchnia z
    kanonicznej warstwy 50 m (bez Overpass), wiatr z silnika METEO liczony
    na PRAWDZIWYM czasie startu tej jazdy (nie na planowanym)."""
    reason_prefix = f"reuzycie trasy {route_id}"
    surface = _plugin(f"{reason_prefix}: nawierzchnia niedostepna")
    wind = _plugin(f"{reason_prefix}: wiatr niedostepny")
    try:
        from qbot3.routes.route_segments_50m import load_canonical_segments_50m
        seg = load_canonical_segments_50m(route_id=route_id)
        rows = seg.get("segments") or []
        tot = sum(r.get("len_m") or 0 for r in rows) or 1.0
        paved = sum(r.get("len_m") or 0 for r in rows if r.get("surface_class") == "paved")
        unpaved = sum(r.get("len_m") or 0 for r in rows if r.get("surface_class") == "unpaved")
        unknown = max(tot - paved - unpaved, 0.0)
        surface = _tag({"paved_pct": round(100 * paved / tot, 1),
                        "unpaved_pct": round(100 * unpaved / tot, 1),
                        "unknown_pct": round(100 * unknown / tot, 1)},
                       "A", f"route_match:{route_id}",
                       note="dopasowano do juz przeliczonej trasy (start < 500 m)")
    except Exception as exc:
        surface = _plugin(f"{reason_prefix}: nawierzchnia - blad ({exc})")
    try:
        from qbot3.routes.route_meteo_engine import run_meteo_engine
        mres = run_meteo_engine(route_id, day, start_time=start_time)
        segs = mres.get("per_segment") or []
        tails = [s.get("wind_tail_ms") for s in segs if s.get("wind_tail_ms") is not None]
        if tails:
            wind = _tag({"avg_tail_ms": round(sum(tails) / len(tails), 2),
                        "min_tail_ms": round(min(tails), 2),
                        "max_tail_ms": round(max(tails), 2)},
                       "A", f"route_match:{route_id}",
                       note="METEO liczone na prawdziwym czasie startu tej jazdy")
        else:
            wind = _plugin(f"{reason_prefix}: METEO bez danych wiatru")
    except Exception as exc:
        wind = _plugin(f"{reason_prefix}: wiatr - blad ({exc})")
    return surface, wind

def _export_gpx(points, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">',
             "<trk><trkseg>"]
    for lat, lon in points:
        lines.append('<trkpt lat="%.7f" lon="%.7f"></trkpt>' % (lat, lon))
    lines.append("</trkseg></trk></gpx>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def _cat_pct_by_km(segments):
    """Rozklad 5 kategorii nawierzchni po dystansie (km) - kanonicznie jak analiza trasy."""
    try:
        from qbot3.routes.route_surface_category_store import compute_category
    except Exception:
        return None
    km = {}
    for sg in segments or []:
        a = sg.get("km_from"); z = sg.get("km_to")
        if a is None or z is None:
            continue
        d = z - a
        if d <= 0:
            continue
        try:
            _c, lab, _ = compute_category(surface=sg.get("surface_refined"), tracktype=sg.get("tracktype"),
                                          highway=sg.get("highway"), classification_source=sg.get("classification_source"),
                                          smoothness=sg.get("smoothness"), ctx=None)
        except Exception:
            continue
        km[lab] = km.get(lab, 0.0) + d
    if not km:
        return None
    tot = sum(km.values()) or 1.0
    return {lab: round(100.0 * v / tot, 1) for lab, v in sorted(km.items())}


def _surface_wind_from_track(have_pos, ride_key, day):
    """Brak dopasowania do zaplanowanej trasy -> liczymy z GPS tej jazdy:
    silnik nawierzchni (slad -> GPX -> route_surface_engine) + Open-Meteo
    z kierunkiem jazdy (jak POC 2026-07-06)."""
    surface = _plugin("silnik nawierzchni nie zwrocil wyniku")
    _segments = []
    km_tails = []
    tick_tails = {}
    tick_cross = {}
    try:
        from tools.rwgps.route_surface_engine import analyze_route_surface
        gpx_path = f"/opt/qbot/artifacts/analysis/exec_gpx/{ride_key}.gpx"
        _export_gpx([(_deg(r["lat"]), _deg(r["lon"])) for r in have_pos], gpx_path)
        surf = analyze_route_surface(artifact_path=gpx_path, mode="gravel_detail",
                                     sample_distance_m=50, use_landcover=True)
        if surf.get("ok"):
            surface = _tag({"tagged_pct": surf.get("tagged_surface_pct"),
                           "inferred_pct": surf.get("inferred_surface_pct"),
                           "unknown_pct": surf.get("unknown_surface_pct"),
                           "types_pct": _cat_pct_by_km(surf.get("segments")) or surf.get("surface_percentages_refined")},
                          "B", "route_surface_engine 5-kat (slad GPS tej jazdy)")
            _segments = surf.get("segments") or []
        else:
            surface = _plugin(f"silnik nawierzchni: {surf.get('error')}")
    except Exception as exc:
        surface = _plugin(f"silnik nawierzchni nie powiodl sie: {exc}")

    wind = _plugin("brak danych pogodowych")
    try:
        from tools.rwgps.route_weather import _fetch_open_meteo, _rel_wind
        lat0, lon0 = _deg(have_pos[0]["lat"]), _deg(have_pos[0]["lon"])
        hourly = _fetch_open_meteo(lat0, lon0, day)
        buckets = []
        start = have_pos[0]
        last_d = have_pos[0].get("dist") or 0.0
        for r in have_pos[1:]:
            d = r.get("dist") or 0.0
            if d - last_d >= 1000.0:
                buckets.append((start, r))
                start, last_d = r, d
        if start is not have_pos[-1]:
            buckets.append((start, have_pos[-1]))
        tails = []; km_tails = []
        for a, b in buckets:
            if a is b:
                continue
            hdg = _bearing_deg(_deg(a["lat"]), _deg(a["lon"]), _deg(b["lat"]), _deg(b["lon"]))
            hourkey = b["ts"].strftime("%Y-%m-%dT%H")
            wx = hourly.get(hourkey) or {}
            tail, _cross, _delta = _rel_wind(hdg, wx.get("wdir"), wx.get("wspeed"))
            if tail is not None:
                tails.append(tail)
                km_tails.append(((a.get("dist") or 0.0)/1000.0, (b.get("dist") or 0.0)/1000.0, tail))
        try:
            for _i in range(len(have_pos)):
                _j = min(_i+8, len(have_pos)-1)
                if _j <= _i: continue
                _h = _bearing_deg(_deg(have_pos[_i]["lat"]), _deg(have_pos[_i]["lon"]), _deg(have_pos[_j]["lat"]), _deg(have_pos[_j]["lon"]))
                _wx = hourly.get(have_pos[_i]["ts"].strftime("%Y-%m-%dT%H")) or {}
                _t, _c, _d = _rel_wind(_h, _wx.get("wdir"), _wx.get("wspeed"))
                if _t is not None:
                    tick_tails[have_pos[_i]["ts"]] = _t
                    if _c is not None:
                        tick_cross[have_pos[_i]["ts"]] = _c
        except Exception:
            pass
        if tails:
            wind = _tag({"avg_tail_ms": round(sum(tails) / len(tails), 2),
                        "min_tail_ms": round(min(tails), 2),
                        "max_tail_ms": round(max(tails), 2)},
                       "B", "open-meteo + kierunek GPS tej jazdy")
        else:
            wind = _plugin("brak godzin pogodowych dla tej jazdy")
    except Exception as exc:
        wind = _plugin(f"pogoda nie powiodla sie: {exc}")
    return surface, wind, {"segments": _segments, "km_tails": km_tails, "tick_tails": tick_tails, "tick_cross": tick_cross}

def _trace(recs, tick_tails=None, tick_cross=None, wbal_curve=None, target_pts=1200, min_window_s=10):
    """Przebieg jazdy usredniony w oknach czasowych (bloki). Serie: moc, HR, kadencja,
    wysokosc, temperatura, EF kroczace (moc30s/HR30s), W'bal% (interpol. z MQ2 po km),
    tail (skladowa wiatru wzdluz jazdy) do paska pod wykresem. Moc wygladzona 3-blok."""
    import math as _m, bisect as _bi
    from collections import deque as _dq
    if not recs:
        return None
    total_s = (recs[-1].get("sec") or 0) - (recs[0].get("sec") or 0)
    if total_s <= 0:
        total_s = len(recs)
    win = max(min_window_s, int(_m.ceil(total_s / max(1, target_pts))))

    def _roll(arr, w):
        out=[None]*len(arr); q=_dq(); s=0.0; c=0
        for i,v in enumerate(arr):
            q.append(v)
            if v is not None: s+=v; c+=1
            if len(q)>w:
                o=q.popleft()
                if o is not None: s-=o; c-=1
            out[i]=(s/c) if c else None
        return out
    Pr=_roll([(x.get("p") or 0) for x in recs], 300)
    Hr=_roll([x.get("hr") for x in recs], 300)
    ef_tick=[(Pr[i]/Hr[i]) if (Pr[i] is not None and Hr[i]) else None for i in range(len(recs))]

    bins={}; order=[]
    for idx,c in enumerate(recs):
        b=int((c.get("sec") or 0)//win)
        g=bins.get(b)
        if g is None:
            g={"sec":[],"dist":[],"p":[],"hr":[],"cad":[],"alt":[],"temp":[],"ef":[],"tail":[],"cross":[],"lat":[],"lon":[]}
            bins[b]=g; order.append(b)
        g["sec"].append(c.get("sec") or 0)
        if c.get("dist") is not None: g["dist"].append(c["dist"])
        if c.get("p") is not None: g["p"].append(c["p"])
        if c.get("hr"): g["hr"].append(c["hr"])
        if c.get("cad") is not None: g["cad"].append(c["cad"])
        if c.get("alt") is not None: g["alt"].append(c["alt"])
        if c.get("temp") is not None: g["temp"].append(c["temp"])
        if c.get("lat") is not None:
            _la=_deg(c["lat"])
            if _la is not None: g["lat"].append(_la)
        if c.get("lon") is not None:
            _lo=_deg(c["lon"])
            if _lo is not None: g["lon"].append(_lo)
        if ef_tick[idx] is not None: g["ef"].append(ef_tick[idx])
        if tick_tails:
            tv=tick_tails.get(c.get("ts"))
            if tv is not None: g["tail"].append(tv)
        if tick_cross:
            cvv=tick_cross.get(c.get("ts"))
            if cvv is not None: g["cross"].append(cvv)
    order.sort()
    def av(a): return (sum(a)/len(a)) if a else None
    t=[]; km=[]; power=[]; hr=[]; cad=[]; alt=[]; temp=[]; ef=[]; tail=[]; cross=[]; lat=[]; lon=[]
    for b in order:
        g=bins[b]
        t.append(int(round(av(g["sec"]) or 0)))
        km.append(round((g["dist"][-1] if g["dist"] else 0.0)/1000.0, 3))
        power.append(int(round(av(g["p"]))) if g["p"] else None)
        hr.append(int(round(av(g["hr"]))) if g["hr"] else None)
        cad.append(int(round(av(g["cad"]))) if g["cad"] else None)
        alt.append(int(round(av(g["alt"]))) if g["alt"] else None)
        temp.append(round(av(g["temp"]),1) if g["temp"] else None)
        ef.append(round(av(g["ef"]),3) if g["ef"] else None)
        tail.append(round(av(g["tail"]),2) if g["tail"] else None)
        cross.append(round(av(g["cross"]),2) if g["cross"] else None)
        lat.append(round(av(g["lat"]),6) if g["lat"] else None)
        lon.append(round(av(g["lon"]),6) if g["lon"] else None)
    sp=list(power)
    for i in range(len(power)):
        vals=[power[j] for j in (i-1,i,i+1) if 0<=j<len(power) and power[j] is not None]
        if vals: sp[i]=int(round(sum(vals)/len(vals)))
    wbal=[None]*len(km)
    if wbal_curve:
        cur=sorted((float(x[0]),float(x[1])) for x in wbal_curve if x and x[0] is not None and x[1] is not None)
        if cur:
            xs=[a for a,_ in cur]
            for i,kk in enumerate(km):
                j=_bi.bisect_left(xs,kk)
                if j<=0: v=cur[0][1]
                elif j>=len(cur): v=cur[-1][1]
                else:
                    x0,y0=cur[j-1]; x1,y1=cur[j]; v=y0+(y1-y0)*((kk-x0)/((x1-x0) or 1))
                wbal[i]=round(v)
    return {"t":t,"km":km,"power":sp,"hr":hr,"cad":cad,"alt":alt,"temp":temp,
            "ef":ef,"wbal_pct":wbal,"tail":tail,"cross":cross,"lat":lat,"lon":lon,"n":len(t),"window_s":win}

def _terrain_impact(recs, raw, splits, wprime, physio, weather):
    """Rozklad wysilku: (1) moc/HR/kadencja/predkosc per typ nawierzchni,
    (2) moc/HR/kadencja/predkosc + koszt beztlenowy (W' ponad CP) wg kierunku
    wiatru (pod wiatr / z wiatrem / boczny). Kategoria wiatru = kierunek GPS x
    stabilny kierunek wiatru; predkosc wiatru zgrubna (prognoza godzinowa)."""
    import bisect
    raw = raw or {}
    out = {"_meta": {"tier": "B", "source": "rozklad po nawierzchni i kierunku wiatru"}}
    cpv = (wprime or {}).get("cp_w"); cpv = cpv.get("value") if isinstance(cpv, dict) else cpv
    CP = float(cpv) if cpv else None

    segs = [x for x in (raw.get("segments") or []) if x.get("km_to") is not None]
    surface_by_type = None
    if segs:
        segs.sort(key=lambda x: x.get("km_from") or 0.0)
        starts = [x.get("km_from") or 0.0 for x in segs]
        def _sa(km, _s=segs, _st=starts):
            i = bisect.bisect_right(_st, km) - 1
            if 0 <= i < len(_s) and (_s[i].get("km_from") or 0) <= km < (_s[i].get("km_to") or 0):
                return _s[i]
            return None
        acc = {}
        _prevd = None
        from qbot3.routes.route_surface_category_store import compute_category as _cc, LABELS as _CATLAB
        _catcache = {}
        def _seg_cat(_sg):
            _k = id(_sg)
            if _k in _catcache: return _catcache[_k]
            try:
                _c, _l, _ = _cc(surface=_sg.get("surface_refined"), tracktype=_sg.get("tracktype"),
                                highway=_sg.get("highway"), classification_source=_sg.get("classification_source"),
                                smoothness=_sg.get("smoothness"), ctx=None)
            except Exception:
                _c, _l = None, None
            _catcache[_k] = (_c, _l); return (_c, _l)
        for r in recs:
            _d = (r.get("dist") or 0.0)
            _sg = _sa(_d/1000.0)
            _dm = (_d - _prevd) if (_prevd is not None) else 0.0
            _prevd = _d
            if _dm < 0 or _dm > 200.0: _dm = 0.0
            if not _sg: continue
            cat, lab = _seg_cat(_sg)
            if cat is None: continue
            b = acc.setdefault(cat, {"lab":lab,"n":0,"m":0.0,"p":0.0,"hr":0.0,"hrn":0,"cad":0.0,"cadn":0,"sp":0.0,"spn":0,"gr":0.0,"grn":0})
            b["n"]+=1; b["m"]+=_dm; b["p"]+=r["p"]
            if r.get("hr"): b["hr"]+=r["hr"]; b["hrn"]+=1
            if r.get("cad"): b["cad"]+=r["cad"]; b["cadn"]+=1
            if r["spd"]>0.5: b["sp"]+=r["spd"]; b["spn"]+=1
            g=r.get("grade")
            if g is not None:
                try: b["gr"]+=float(g); b["grn"]+=1
                except Exception: pass
        tot_m = sum(b["m"] for b in acc.values()) or 1
        MIN = 60
        def _pack(cat, b):
            return {"surface": b.get("lab") or _CATLAB.get(cat) or str(cat),
                    "category": cat,
                    "pct_dist": round(100*b["m"]/tot_m,1),
                    "avg_power_w": round(b["p"]/b["n"]) if b["n"] else None,
                    "avg_hr": round(b["hr"]/b["hrn"]) if b["hrn"] else None,
                    "avg_cad": round(b["cad"]/b["cadn"]) if b["cadn"] else None,
                    "avg_speed_kmh": round(3.6*b["sp"]/b["spn"],1) if b["spn"] else None,
                    "avg_grade": round(b["gr"]/b["grn"],1) if b["grn"] else None}
        surface_by_type = [_pack(cat,acc[cat]) for cat in sorted(acc.keys())]
    out["surface_by_type"] = surface_by_type

    tt = raw.get("tick_tails") or {}
    wind_by_dir = None; wind_note = None
    if tt:
        THR = 1.0
        def _z(): return {"n":0,"p":0.0,"hr":0.0,"hrn":0,"cad":0.0,"cadn":0,"sp":0.0,"spn":0,"ex":0.0}
        cats = {"pod wiatr": _z(), "z wiatrem": _z(), "boczny/neutralny": _z()}
        for r in recs:
            t = tt.get(r["ts"])
            if t is None: continue
            cat = "pod wiatr" if t <= -THR else ("z wiatrem" if t >= THR else "boczny/neutralny")
            b = cats[cat]; b["n"]+=1; b["p"]+=r["p"]
            if CP: b["ex"] += max(0.0, r["p"]-CP)
            if r.get("hr"): b["hr"]+=r["hr"]; b["hrn"]+=1
            if r.get("cad"): b["cad"]+=r["cad"]; b["cadn"]+=1
            if r["spd"]>0.5: b["sp"]+=r["spd"]; b["spn"]+=1
        totw = sum(b["n"] for b in cats.values()) or 1
        wind_by_dir = []
        for cat in ("pod wiatr","z wiatrem","boczny/neutralny"):
            b = cats[cat]
            if b["n"] == 0: continue
            wind_by_dir.append({"cat": cat, "pct_time": round(100*b["n"]/totw,1),
                "avg_power_w": round(b["p"]/b["n"]),
                "avg_hr": round(b["hr"]/b["hrn"]) if b["hrn"] else None,
                "avg_cad": round(b["cad"]/b["cadn"]) if b["cadn"] else None,
                "avg_speed_kmh": round(3.6*b["sp"]/b["spn"],1) if b["spn"] else None,
                "wprime_over_cp_kj": round(b["ex"]/1000.0,1) if CP else None})
        pw = cats["pod wiatr"]; zw = cats["z wiatrem"]
        if pw["n"] and zw["n"]:
            pmp = pw["p"]/pw["n"]; pmz = zw["p"]/zw["n"]
            if abs(pmz-pmp) >= 5:
                if pmz > pmp:
                    wind_note = "Wiecej mocy Z WIATREM (%d W) niz pod wiatr (%d W) -- goniona predkosc z plecami, nie walka z wiatrem." % (round(pmz), round(pmp))
                else:
                    wind_note = "Wiecej mocy POD WIATR (%d W) niz z wiatrem (%d W)." % (round(pmp), round(pmz))
    out["wind_by_dir"] = wind_by_dir
    out["wind_note"] = wind_note
    return out

def _surface_from_route_canonical(cur, route_id):
    """Nawierzchnia z kanonicznej warstwy 50 m dopasowanej trasy (System A):
    karty 5-kat (compute_category na resolved surface) + segmenty do tabeli D.
    Wiatr NIE stad -- zostaje per-tick z GPS tej jazdy."""
    try:
        from qbot3.routes.route_segments_50m import load_canonical_segments_50m
        seg = load_canonical_segments_50m(route_id=route_id)
        rows = seg.get("segments") or []
        if not rows:
            return None, None
        segs_r = []
        for r in rows:
            a = r.get("km_from"); z = r.get("km_to")
            if a is None or z is None:
                continue
            sv = r.get("surface")
            segs_r.append({"km_from": a, "km_to": z, "surface_refined": sv,
                           "tracktype": None, "highway": None,
                           "classification_source": ("tagged_surface" if sv else None),
                           "smoothness": None})
        if not segs_r:
            return None, None
        types5 = _cat_pct_by_km(segs_r)
        tot = sum((r.get("len_m") or 0.0) for r in rows) or 1.0
        with_s = sum((r.get("len_m") or 0.0) for r in rows if r.get("surface"))
        tagged = round(100.0 * with_s / tot, 1)
        unknown = round(100.0 * (tot - with_s) / tot, 1)
        surface = _tag({"types_pct": types5, "tagged_pct": tagged,
                        "inferred_pct": None, "unknown_pct": unknown},
                       "A", f"kanoniczna 50m (trasa {route_id})",
                       note="nawierzchnia z dopasowanej trasy; wiatr per-tick z GPS tej jazdy")
        return surface, segs_r
    except Exception:
        return None, None


def _surface_and_wind(cur, recs, day, ride_key):
    """Punkt wejscia. Nawierzchnia: jesli jazda pasuje do przeliczonej trasy ->
    z kanonicznej warstwy 50 m (System A); inaczej z GPS (Overpass). Wiatr ZAWSZE
    per-tick z GPS tej jazdy (tick_tails/tick_cross zachowane dla wykresu)."""
    have_pos = [r for r in recs if r.get("lat") is not None and r.get("lon") is not None]
    if not have_pos:
        reason = "brak pozycji GPS w FIT"
        return _plugin(reason), _plugin(reason), None
    lat0, lon0 = _deg(have_pos[0]["lat"]), _deg(have_pos[0]["lon"])
    _mts = have_pos[0]["ts"]
    try:
        cur.execute("SELECT lat, lon, ts FROM qbot_v2.activity_record WHERE external_id=%s AND lat IS NOT NULL ORDER BY sec ASC LIMIT 1", (ride_key,))
        _p = cur.fetchone()
        if _p and _p.get("lat") is not None:
            lat0, lon0, _mts = float(_p["lat"]), float(_p["lon"]), _p["ts"]
    except Exception:
        pass
    route_id = _find_matching_route(cur, lat0, lon0, _mts)
    surf_t, wind_t, terr_t = _surface_wind_from_track(have_pos, ride_key, day)
    if route_id:
        surf_r, segs_r = _surface_from_route_canonical(cur, route_id)
        if surf_r is not None:
            terr = dict(terr_t or {})
            terr["segments"] = segs_r
            return surf_r, wind_t, terr
    return surf_t, wind_t, terr_t

DISABLED=[
    {"blok":"Bilans L/P, torque, pedal smoothness","powod":"AXS = moc calkowita, brak pomiaru L/P"},
    {"blok":"Durability (fade)","powod":"za malo wysilkow max w profilu"},
]

def _modelq_block(cur, ride_date):
    """ModelQ: aktualna forma + wplyw tej jazdy + benchmark vs Xert."""
    def f(x): 
        return float(x) if x is not None else None
    cur.execute("SELECT * FROM qbot_v2.fitmodel_daily WHERE day=%s", (ride_date,))
    day_row = cur.fetchone()
    cur.execute("SELECT * FROM qbot_v2.fitmodel_daily WHERE day<%s AND ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1", (ride_date,))
    prev = cur.fetchone()
    cur_row = day_row if (day_row and day_row.get("ftp_est_w") is not None) else None
    if cur_row is None:
        cur.execute("SELECT * FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1")
        cur_row = cur.fetchone()
    bench=None
    try:
        cur.execute("SELECT day,tp_w,ltp_w,hie_kj,pp_w FROM qbot_v2.modelq2_xert_bench ORDER BY day DESC LIMIT 1"); bench=cur.fetchone()
    except Exception: pass
    bucket=None
    try:
        cur.execute("SELECT total_strain, ftp_used_w FROM qbot_v2.fitmodel_ride_buckets WHERE started_at::date=%s ORDER BY started_at DESC LIMIT 1", (ride_date,)); bucket=cur.fetchone()
    except Exception: pass
    seg=None
    try:
        cur.execute("SELECT AVG(ef_norm) AS ef, COUNT(*) AS n FROM qbot_v2.fitmodel_segment WHERE started_at::date=%s", (ride_date,)); seg=cur.fetchone()
    except Exception: pass
    cr = cur_row or {}
    _gw = _garmin_weight(cur)
    _ef28 = f(cr.get("ef_med_28d")) or _last_ef(cur)
    _weight = f(cr.get("weight_kg")) or _gw
    _ftp = f(cr.get("ftp_est_w"))
    _wkg = round(f(cr.get("w_per_kg")),2) if cr.get("w_per_kg") else (round(_ftp/_weight,2) if (_ftp and _weight) else None)
    current = {
        "as_of": str(cr.get("day")),
        "ftp_w": round(_ftp,1) if _ftp else None,
        "cp_w": round(f(cr.get("cp_modelq_w")),1) if cr.get("cp_modelq_w") else None,
        "pp_w": round(f(cr.get("pp_modelq_w")),1) if cr.get("pp_modelq_w") else None,
        "wprime_kj": round(f(cr.get("wprime_modelq_kj")),1) if cr.get("wprime_modelq_kj") else None,
        "wprime_lo_kj": round(f(cr.get("wprime_lo_kj")),1) if cr.get("wprime_lo_kj") else None,
        "wprime_hi_kj": round(f(cr.get("wprime_hi_kj")),1) if cr.get("wprime_hi_kj") else None,
        "wprime_confidence": cr.get("wprime_confidence"),
        "wprime_source": cr.get("wprime_source"),
        "ef_28d": round(_ef28,3) if _ef28 else None,
        "ef_28d_stale": (cr.get("ef_med_28d") is None and _ef28 is not None),
        "ctl": round(f(cr.get("ctl_xss")),1) if cr.get("ctl_xss") is not None else None,
        "atl": round(f(cr.get("atl_raw")),1) if cr.get("atl_raw") is not None else None,
        "tsb": round(f(cr.get("tsb_raw")),1) if cr.get("tsb_raw") is not None else None,
        "readiness": round(f(cr.get("readiness_score")),2) if cr.get("readiness_score") is not None else None,
        "weight_kg": _weight,
        "weight_source": (None if cr.get("weight_kg") else ("garmin" if _gw else None)),
        "wkg": _wkg,
        "cp_r2": f(cr.get("cp_wprime_r2")),
        "cp_note": cr.get("cp_wprime_note"),
        "ltp_w": round(f(cr.get("ltp_modelq_w")),1) if cr.get("ltp_modelq_w") else None,
        "ltp_r2": f(cr.get("ltp_modelq_r2")),
        "ltp_note": cr.get("ltp_modelq_note"),
    }
    impact = {"prev_day": str(prev["day"]) if prev else None}
    if prev and cr.get("ftp_est_w") and prev.get("ftp_est_w"):
        impact["ftp_delta"] = round(f(cr["ftp_est_w"])-f(prev["ftp_est_w"]),1)
    if prev and cr.get("ef_med_28d") and prev.get("ef_med_28d"):
        impact["ef_delta"] = round(f(cr["ef_med_28d"])-f(prev["ef_med_28d"]),3)
    if prev and cr.get("cp_modelq_w") and prev.get("cp_modelq_w"):
        impact["cp_delta"] = round(f(cr["cp_modelq_w"])-f(prev["cp_modelq_w"]),1)
    if prev and cr.get("ltp_modelq_w") and prev.get("ltp_modelq_w"):
        impact["ltp_delta"] = round(f(cr["ltp_modelq_w"])-f(prev["ltp_modelq_w"]),1)
    if prev and cr.get("wprime_modelq_kj") and prev.get("wprime_modelq_kj"):
        impact["wprime_delta"] = round(f(cr["wprime_modelq_kj"])-f(prev["wprime_modelq_kj"]),1)
    if prev and cr.get("pp_modelq_w") and prev.get("pp_modelq_w"):
        impact["pp_delta"] = round(f(cr["pp_modelq_w"])-f(prev["pp_modelq_w"]),1)
    impact["ride_strain"] = round(f(bucket["total_strain"]),0) if (bucket and bucket.get("total_strain")) else None
    impact["ride_ef_mean"] = round(f(seg["ef"]),2) if (seg and seg.get("ef")) else None
    impact["ride_segments"] = seg["n"] if seg else None
    benchmark=None
    if bench:
        _d = lambda a,b,nd=1: round(a-b,nd) if (a is not None and b is not None) else None
        _mtp=f(cr.get("ftp_est_w")); _mltp=f(cr.get("ltp_modelq_w")); _mhie=f(cr.get("wprime_modelq_kj")); _mpp=f(cr.get("pp_modelq_w"))
        _xtp=f(bench.get("tp_w")); _xltp=f(bench.get("ltp_w")); _xhie=f(bench.get("hie_kj")); _xpp=f(bench.get("pp_w"))
        benchmark={
            "as_of": str(bench.get("day")),
            "ftp_modelq": _mtp, "ftp_xert": _xtp, "ftp_delta": _d(_mtp,_xtp),
            "ltp_modelq": _mltp, "ltp_xert": _xltp, "ltp_delta": _d(_mltp,_xltp),
            "wprime_modelq": _mhie, "wprime_xert": _xhie, "wprime_delta": _d(_mhie,_xhie,2),
            "pp_modelq": _mpp, "pp_xert": _xpp, "pp_delta": _d(_mpp,_xpp),
        }
    return {"current": current, "ride_impact": impact, "benchmark_xert": benchmark,
            "_meta": {"tier": "A", "source": "ModelQ (fitmodel) + benchmark Xert"}}


def _ride_xss(conn, ride_key):
    """XSS tej jazdy z fitmodel_wbal_ride (Skiba W'bal replay). Jesli jeszcze
    nie policzone (nowa jazda) -- liczymy na zywo i zapisujemy, zeby kolejne
    odczyty byly juz z cache. XSS ZASTEPUJE TSS w calym raporcie (2026-07-07,
    patrz DECISIONS.md) -- TSS to zgrubny wzor Coggana (NP/IF), XSS to realna
    fizyka W'bal (moc wzgledem CP + zmeczenie z W' w czasie)."""
    cur = conn.cursor()
    cur.execute(
        "SELECT status, xss, xss_per_h FROM qbot_v2.fitmodel_wbal_ride WHERE external_id=%s",
        (ride_key,),
    )
    row = cur.fetchone()
    if row is None:
        try:
            from fitmodel.wbal_replay import replay_wbal, upsert_wbal_ride, ensure_wbal_table
            ensure_wbal_table(conn)
            result = replay_wbal(ride_key, verbose=False)
            upsert_wbal_ride(conn, result)
            row = result
        except Exception as exc:
            return _plugin(f"XSS: przeliczenie na zywo nie powiodlo sie ({exc})")
    status = row.get("status")
    if status != "OK" or row.get("xss") is None:
        reason = {
            "NO_BASELINE": "brak dziennego CP/W' z ModelQ na ten dzien",
            "NO_DATA": "brak danych GPS/mocy do przeliczenia",
        }.get(status, f"status={status}")
        return _plugin(f"XSS niedostepne: {reason}")
    return _tag(
        round(float(row["xss"]), 1), "A", "wbal_replay",
        xss_per_h=round(float(row["xss_per_h"]), 1) if row.get("xss_per_h") is not None else None,
    )


# ---------- API ----------
def build_w1(fit_path, ride_key, inputs=None):
    recs, events, session = _parse_fit(fit_path)
    conn=_connect(); cur=conn.cursor()
    day = str(recs[0]["ts"].date())
    form=_modelq_form(cur); Wp,wp_source=_modelq_wprime(cur, day); efa=_ef_anchor(cur)
    _mqr=_mq2_ride_row(cur, day)
    _buckets=_mqr["buckets"] if _mqr else None
    _sig=_mqr["sig"] if (_mqr and _mqr.get("sig")) else _mq2_sig_before(cur, day)
    _mq_rows=_fetch_activity_rows(cur, _mqr["external_id"]) if _mqr else None
    wellness=_wellness(cur, day); rhr_base=_rhr_base(cur)
    try:
        cur.execute("SELECT started_at FROM qbot_v2.training_sessions WHERE external_id=%s",(ride_key,))
        _sr=cur.fetchone()
        _stime=_sr["started_at"].strftime("%H:%M") if (_sr and _sr.get("started_at")) else recs[0]["ts"].strftime("%H:%M")
    except Exception:
        _stime=recs[0]["ts"].strftime("%H:%M")
    _surf_block, _wind_block, _terr_raw = _surface_and_wind(cur, recs, day, ride_key)
    _xss_block = _ride_xss(conn, ride_key)
    w1={
        "schema_version":SCHEMA_VERSION,
        "ride_key":ride_key,
        "ride":{"date":day,"time":_stime,"dist_km":round(recs[-1]["dist"]/1000.0,1)},
        "inputs":inputs or {},
        "load":_load(recs, form, efa, _xss_block, _buckets),
        "wprime":_wprime(recs, _mq_rows, _sig, form["cp_w"], Wp, wp_source),
        "wind":_wind_block,
        "weather":_weather_block(recs, day),
        "surface":_surf_block,
        "drivetrain":_drivetrain(recs, events),
        "physio":_physio(recs, wellness, rhr_base),
        "energy":_energy(recs),
        "splits":_splits(recs),
        "plan_vs_actual":_tag(_plan_vs_actual(cur, recs, ride_key),"A","plan vs realnie"),
        "nutrition":_tag(_nutrition(cur),"A","nutrition_daily"),
        "disabled":DISABLED,
        "modelq":_modelq_block(cur, day),
        "form_context":form,
    }
    w1["terrain_impact"] = _terrain_impact(recs, _terr_raw, w1["splits"], w1["wprime"], w1["physio"], w1["weather"])
    w1["trace"] = _trace(recs, (_terr_raw or {}).get("tick_tails"), (_terr_raw or {}).get("tick_cross"), ((w1["wprime"] or {}).get("wbal_curve") or {}).get("value"))
    conn.close()
    return w1

def save_report(ride_key, fit_path, inputs, w1, w2=None):
    import json
    conn=_connect(); cur=conn.cursor()
    cur.execute("""INSERT INTO qbot_v2.ride_report_data (ride_key,schema_version,fit_path,inputs_json,w1_json,w2_json,built_at)
                   VALUES (%s,%s,%s,%s,%s,%s,now())
                   ON CONFLICT (ride_key,schema_version) DO UPDATE
                   SET fit_path=EXCLUDED.fit_path, inputs_json=EXCLUDED.inputs_json,
                       w1_json=EXCLUDED.w1_json, w2_json=EXCLUDED.w2_json, built_at=now()""",
                (ride_key, SCHEMA_VERSION, fit_path, json.dumps(inputs or {}),
                 json.dumps(w1, default=str), json.dumps(w2) if w2 else None))
    conn.close()
