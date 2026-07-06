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
    return {
        "ftp_w": ftp, "cp_w": ftp,  # CP=FTP z ModelQ
        "ef_med_28d": float(r["ef_med_28d"]) if r.get("ef_med_28d") else None,
        "weight_kg": float(r["weight_kg"]) if r.get("weight_kg") else None,
        "wkg": float(r["w_per_kg"]) if r.get("w_per_kg") else None,
        "as_of": str(r.get("day")),
    }

def _xert_wprime(cur):
    try:
        cur.execute("SELECT w_prime_kj FROM qbot_v2.xert_profile_snapshots ORDER BY 1 DESC LIMIT 1")
        r = cur.fetchone()
        return float(r["w_prime_kj"])*1000.0 if r and r.get("w_prime_kj") is not None else None
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
            lat=d.get("position_lat"), lon=d.get("position_long")))
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

def _load(recs, form, ef_anchor):
    P=[r["p"] for r in recs]; n=len(recs)
    dur=recs[-1]["sec"]-recs[0]["sec"]
    dur_ride=len(recs)  # 1 Hz -> sekundy realnego nagrywania (bez postojow)
    dist=recs[-1]["dist"]/1000.0
    moving=[r for r in recs if r["spd"]>0.5]
    hr=[r["hr"] for r in recs if r["hr"]]
    np_=_np(P); avg=sum(P)/n
    ftp=form["ftp_w"]; mass=form["weight_kg"] or 101.0
    if_=np_/ftp if ftp else None
    tss=(dur_ride*np_*(if_ or 0))/(ftp*3600)*100 if ftp else None
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
        "tss":_tag(round(tss) if tss else None,"A","fit+modelq"),
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

def _wprime(recs, cp, Wp, wp_source="xert"):
    if not cp or not Wp:
        return {"_meta":{"tier":"C","source":"modelq/xert","reason":"brak CP lub W'"}}
    P=[r["p"] for r in recs]
    below=[p for p in P if p<cp]
    dcp=cp-(sum(below)/len(below) if below else cp)
    tau=546*math.exp(-0.01*dcp)+316
    bal=Wp; series=[]; k=1-math.exp(-1.0/tau)
    for p in P:
        if p>=cp: bal-=(p-cp)
        else: bal+=(Wp-bal)*k
        if bal>Wp: bal=Wp
        if bal<0: bal=0  # brakujacy dolny clamp -- ujawnil sie przy mniejszym, dokladniejszym W' z ModelQ
        series.append(bal)
    mn=min(series); mn_i=series.index(mn)
    # seria do wykresu: min % W' w koszykach 5 km
    _bins={}
    for _i,_b in enumerate(series):
        _k=int(recs[_i]["dist"]//5000)
        _pct=100*_b/Wp
        _bins[_k]=min(_bins.get(_k,1e9),_pct)
    wbal_series=[{"km":_k*5+5,"min_pct":round(_v)} for _k,_v in sorted(_bins.items())]
    lt50=sum(1 for b in series if b<0.5*Wp)
    lt25=sum(1 for b in series if b<0.25*Wp)
    # top efforty > CP (grupowanie ciagle)
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
    return {
        "cp_w":_tag(round(cp),"A","modelq"),
        "wprime_j":_tag(round(Wp),"A" if wp_source=="modelq" else "B",wp_source,
                       note=None if wp_source=="modelq" else "fallback Xert -- ModelQ bez swiezej wartosci"),
        "wbal_min_pct":_tag(round(100*mn/Wp),"A" if wp_source=="modelq" else "B",f"modelq_cp+{wp_source}_wprime"),
        "time_lt50_min":_tag(round(lt50/60),"B","derived"),
        "time_lt25_min":_tag(round(lt25/60),"B","derived"),
        "tau_s":_tag(round(tau),"B","skiba"),
        "cutoff":_tag({"km":round(recs[mn_i]["dist"]/1000.0,1),
                       "grade":recs[mn_i]["grade"],"speed_kmh":round(recs[mn_i]["spd"]*3.6,1),
                       "surface":None,"wind_ms":None},"B","fit+plugins"),
        "wbal_series":_tag(wbal_series,"B","derived"),
        "top_efforts":_tag(efforts[:3],"A","fit"),
    }

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

DISABLED=[
    {"blok":"Bilans L/P, torque, pedal smoothness","powod":"AXS = moc calkowita, brak pomiaru L/P"},
    {"blok":"TSB/CTL/ATL, durability","powod":"profil turysty / za malo wysilkow max"},
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
        cur.execute("SELECT * FROM qbot_v2.fitmodel_xert_bench ORDER BY week DESC LIMIT 1"); bench=cur.fetchone()
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
    current = {
        "as_of": str(cr.get("day")),
        "ftp_w": round(f(cr.get("ftp_est_w")),1) if cr.get("ftp_est_w") else None,
        "cp_w": round(f(cr.get("cp_modelq_w")),1) if cr.get("cp_modelq_w") else None,
        "wprime_kj": round(f(cr.get("wprime_modelq_kj")),1) if cr.get("wprime_modelq_kj") else None,
        "wprime_lo_kj": round(f(cr.get("wprime_lo_kj")),1) if cr.get("wprime_lo_kj") else None,
        "wprime_hi_kj": round(f(cr.get("wprime_hi_kj")),1) if cr.get("wprime_hi_kj") else None,
        "wprime_confidence": cr.get("wprime_confidence"),
        "wprime_source": cr.get("wprime_source"),
        "ef_28d": round(f(cr.get("ef_med_28d")),3) if cr.get("ef_med_28d") else None,
        "weight_kg": f(cr.get("weight_kg")),
        "wkg": round(f(cr.get("w_per_kg")),2) if cr.get("w_per_kg") else None,
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
    impact["ride_strain"] = round(f(bucket["total_strain"]),0) if (bucket and bucket.get("total_strain")) else None
    impact["ride_ef_mean"] = round(f(seg["ef"]),2) if (seg and seg.get("ef")) else None
    impact["ride_segments"] = seg["n"] if seg else None
    benchmark=None
    if bench:
        benchmark={
            "ftp_modelq": f(bench.get("ftp_est_w")), "ftp_xert": f(bench.get("xert_tp_w")), "ftp_delta": f(bench.get("delta_w")),
            "ltp_modelq": f(bench.get("cp_modelq_w")), "ltp_xert": f(bench.get("ltp_xert_w")), "ltp_delta": f(bench.get("delta_cp_w")),
            "wprime_modelq": f(bench.get("wprime_modelq_kj")), "wprime_xert": f(bench.get("hie_xert_kj")), "wprime_delta": f(bench.get("delta_wprime_kj")),
        }
    return {"current": current, "ride_impact": impact, "benchmark_xert": benchmark,
            "_meta": {"tier": "A", "source": "ModelQ (fitmodel) + benchmark Xert"}}


# ---------- API ----------
def build_w1(fit_path, ride_key, inputs=None):
    recs, events, session = _parse_fit(fit_path)
    conn=_connect(); cur=conn.cursor()
    day = str(recs[0]["ts"].date())
    form=_modelq_form(cur); Wp,wp_source=_modelq_wprime(cur, day); efa=_ef_anchor(cur)
    wellness=_wellness(cur, day); rhr_base=_rhr_base(cur)
    w1={
        "schema_version":SCHEMA_VERSION,
        "ride_key":ride_key,
        "ride":{"date":day,"dist_km":round(recs[-1]["dist"]/1000.0,1)},
        "inputs":inputs or {},
        "load":_load(recs, form, efa),
        "wprime":_wprime(recs, form["cp_w"], Wp, wp_source),
        "wind":_plugin("zrodlo pogody — decyzja uzytkownika (osobna sesja)"),
        "weather":_weather_from_fit(recs),
        "surface":_plugin("dopasowanie trasy — decyzja uzytkownika (Ad2)"),
        "drivetrain":_drivetrain(recs, events),
        "physio":_physio(recs, wellness, rhr_base),
        "energy":_energy(recs),
        "splits":_splits(recs),
        "plan_vs_actual":_tag(_plan_snapshot(cur),"A","snapshot"),
        "nutrition":_tag(_nutrition(cur),"A","nutrition_daily"),
        "disabled":DISABLED,
        "modelq":_modelq_block(cur, day),
        "form_context":form,
    }
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
