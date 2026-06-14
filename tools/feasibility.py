"""feasibility.py — Modul A: Ocena wykonalnosci trasy na dany dzien.

Wejscie:
- forma: CTL/ATL/TSB z Xert + HRV/RHR z Garmin
- trasa: GPX lub RWGPS route_id (dystans, D+, profil podjazdow)
- pogoda: OWM (temp, wiatr kierunkowy, deszcz)
- godzina startu
Wyjscie:
- ocena: wykonalna / ryzykowna / odradzana
- szacowany czas jazdy
- strategia zywieniowa
"""
from __future__ import annotations
import math, os, sys, json, httpx
from datetime import date, datetime
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

# ── Stale ──────────────────────────────────────────────────────────────────
OWM_KEY = os.environ.get("OWM_API_KEY") or os.environ.get("OPENWEATHER_API_KEY", "")

# Progi oceny (TSB = Training Stress Balance = forma)
TSB_GOOD    =  5   # powyzej: dobra forma
TSB_OK      = -15  # powyzej: OK do jazdy
TSB_RISKY   = -30  # powyzej: ryzykowne
# ponizej TSB_RISKY: odradzane

# Progi HRV (odchylenie od normy tygodniowej)
HRV_OK_RATIO   = 0.90  # >= 90% normy: OK
HRV_RISKY_RATIO = 0.80  # >= 80%: ryzykowne

# Predkosc bazowa [km/h] dla gravel/MTB
BASE_SPEED_KMPH = 20.0
# Korekta predkosci za przewyzszenie: -X km/h za kazde 1000m D+
ELEV_SPEED_PENALTY_PER_1000M = 3.5
# Korekta za forme: TSB=-30 -> -10% predkosci
FORM_SPEED_FACTOR = {"wykonalna": 1.0, "ryzykowna": 0.92, "odradzana": 0.85}

# Kcal/h dla roznych intensywnosci
KCAL_PER_H_BASE = 600  # gravel luzna jazda
KCAL_PER_H_HARD = 900  # ciezkie podjazdy

# ── Pobieranie danych formy ───────────────────────────────────────────────

def _get_form_data(target_date: str | None = None) -> dict:
    """Pobierz CTL/ATL/TSB z Xert i HRV/RHR z Garmin dla danej daty."""
    ds = target_date or date.today().isoformat()
    form = {}
    try:
        import api_db
        conn = api_db.psycopg.connect(
            host=os.environ.get("PG_HOST","127.0.0.1"),
            port=int(os.environ.get("PG_PORT",5432)),
            dbname=os.environ.get("PG_DB","qbot"),
            user=os.environ.get("PG_USER","qbot"),
            password=os.environ.get("PG_PASS",""),
        )
        cur = conn.cursor(row_factory=api_db.psycopg.rows.dict_row)
        # Xert
        cur.execute("SELECT training_load, recovery_load, form_ratio, form_status, ftp_power_w FROM qbot_v2.xert_profile_snapshots WHERE date <= %s AND training_load IS NOT NULL ORDER BY date DESC LIMIT 1", (ds,))
        row = cur.fetchone()
        if row:
            form["ctl"] = float(row["training_load"] or 0)
            form["atl"] = float(row["recovery_load"] or 0)
            form["tsb"] = float(row["form_ratio"] or 0)
            form["form_status"] = row["form_status"] or "unknown"
            form["ftp"] = float(row["ftp_power_w"] or 0)
        # HRV + RHR
        cur.execute("SELECT hrv_ms, resting_hr_bpm FROM qbot_v2.wellness_daily WHERE date <= %s AND hrv_ms IS NOT NULL ORDER BY date DESC LIMIT 1", (ds,))
        row = cur.fetchone()
        if row:
            form["hrv"] = float(row["hrv_ms"] or 0)
            form["rhr"] = float(row["resting_hr_bpm"] or 0)
        # HRV norma tygodniowa
        cur.execute("SELECT AVG(hrv_ms) as avg_hrv FROM qbot_v2.wellness_daily WHERE date BETWEEN (%s::date - 7) AND %s AND hrv_ms IS NOT NULL", (ds, ds))
        row = cur.fetchone()
        if row and row["avg_hrv"]:
            form["hrv_norm_7d"] = float(row["avg_hrv"])
        conn.close()
    except Exception as e:
        form["_error"] = str(e)
    return form

def get_weather(lat: float, lon: float, start_hour: int = 8) -> dict:
    """Pobierz prognozę pogody z OWM dla punktu startu."""
    try:
        url="https://api.openweathermap.org/data/2.5/forecast?lat={}&lon={}&appid={}&units=metric&cnt=8&lang=pl".format(lat,lon,OWM_KEY)
        items=httpx.get(url,timeout=8.0).json().get("list",[])
        best=next((i for i in items if datetime.fromtimestamp(i["dt"]).hour>=start_hour),items[0] if items else None)
        if not best: return {"_error":"Brak prognozy"}
        return {"temp_c":best["main"]["temp"],"feels_c":best["main"]["feels_like"],
                "wind_kmh":round(best["wind"]["speed"]*3.6,1),"wind_deg":best["wind"].get("deg",0),
                "desc":best["weather"][0]["description"],"rain_3h_mm":best.get("rain",{}).get("3h",0),
                "humidity_pct":best["main"]["humidity"],"dt_local":datetime.fromtimestamp(best["dt"]).strftime("%H:%M")}
    except Exception as exc: return {"_error":str(exc)}

def assess_feasibility(form,route,weather,start_hour=8):
    issues=[]; bonuses=[]
    tsb=form.get("tsb")
    if tsb is None: issues.append("Brak TSB"); form_score=0
    elif tsb>=TSB_GOOD: bonuses.append("TSB={:.1f} — swietna forma".format(tsb)); form_score=2
    elif tsb>=TSB_OK: bonuses.append("TSB={:.1f} — dobra forma".format(tsb)); form_score=1
    elif tsb>=TSB_RISKY: issues.append("TSB={:.1f} — zmeczenie".format(tsb)); form_score=0
    else: issues.append("TSB={:.1f} — duze zmeczenie!".format(tsb)); form_score=-1
    hrv=form.get("hrv"); hrv_norm=form.get("hrv_norm_7d")
    if hrv and hrv_norm and hrv_norm>0:
        ratio=hrv/hrv_norm
        if ratio>=HRV_OK: bonuses.append("HRV={:.0f}ms ({:.0f}% normy)".format(hrv,ratio*100))
        elif ratio>=HRV_RISKY: issues.append("HRV={:.0f}ms — niepelna regen.".format(hrv)); form_score-=1
        else: issues.append("HRV={:.0f}ms — slaba regen!".format(hrv)); form_score-=2
    dist=route.get("distance_km",0); elev=route.get("elevation_gain_m",0); max_gr=route.get("max_grade_pct",0)
    if dist==0: issues.append("Brak danych trasy"); route_score=0
    elif dist>150 or elev>3000: issues.append("Wymagajaca trasa: {}km +{}m".format(dist,elev)); route_score=-1
    elif dist>100 or elev>1500: route_score=0
    else: route_score=1
    if max_gr>15: issues.append("Max nachylenie {:.0f}% — bardzo strome".format(max_gr))
    elif max_gr>10: issues.append("Max nachylenie {:.0f}% — strome".format(max_gr))
    weather_score=0
    if not weather.get("_error"):
        temp=weather.get("feels_c",20); wind=weather.get("wind_kmh",0); rain=weather.get("rain_3h_mm",0)
        if temp<5: issues.append("Zimno: {:.0f}C".format(temp)); weather_score-=1
        elif temp>35: issues.append("Upal: {:.0f}C".format(temp)); weather_score-=1
        if wind>40: issues.append("Silny wiatr: {:.0f}km/h".format(wind)); weather_score-=1
        elif wind>25: issues.append("Wiatr: {:.0f}km/h".format(wind))
        if rain>5: issues.append("Deszcz: {:.1f}mm".format(rain)); weather_score-=1
    total=form_score+route_score+weather_score
    verdict="wykonalna" if total>=2 else ("ryzykowna" if total>=0 else "odradzana")
    speed=max(10.0,BASE_SPEED-(elev/1000)*ELEV_PENALTY)*{"wykonalna":1.0,"ryzykowna":0.92,"odradzana":0.85}[verdict]
    est_h=dist/speed if speed>0 else 0; finish=start_hour+est_h
    kcal_h=KCAL_BASE+(KCAL_HARD-KCAL_BASE)*min(1.0,elev/3000)
    windows=[{"km":float(km),"time":"{:d}:{:02d}".format(int(start_hour+km/speed),int((km/speed%1)*60)),"kcal":round(kcal_h*(20/speed))} for km in range(20,int(dist)+1,20)]
    return {"verdict":verdict,"verdict_pl":{"wykonalna":"WYKONALNA","ryzykowna":"RYZYKOWNA","odradzana":"ODRADZANA"}[verdict],
        "score":total,"issues":issues,"bonuses":bonuses,
        "estimated_time_h":round(est_h,1),"estimated_speed_kmh":round(speed,1),
        "finish_hour_est":"{:d}:{:02d}".format(int(finish),int(finish%1*60)),
        "form":form,"route_summary":{"distance_km":dist,"elevation_gain_m":elev,"max_grade_pct":max_gr,"climbs_count":route.get("climbs_count",0)},
        "weather_summary":weather,
        "nutrition_strategy":{"przed_startem":"Posilek 2-3h przed (wegle+bialko). 30min przed: 1 zel/banan.",
            "kcal_per_hour":round(kcal_h),"total_kcal":round(kcal_h*est_h),
            "hydration_ml_h":500 if weather.get("feels_c",20)<20 else 750,
            "windows_co_20km":windows[:8],"po_trasie":"20-30g bialka + wegle w 30-60min po."}}

# Aliasy stałych (używane w assess_feasibility)
BASE_SPEED   = BASE_SPEED_KMPH
ELEV_PENALTY = ELEV_SPEED_PENALTY_PER_1000M
KCAL_BASE    = KCAL_PER_H_BASE
KCAL_HARD    = KCAL_PER_H_HARD
HRV_OK       = HRV_OK_RATIO
HRV_RISKY    = HRV_RISKY_RATIO


def _rwgps_env() -> dict:
    """Załaduj credentials RWGPS ze zmiennych środowiskowych lub .env."""
    env = {
        "RWGPS_API_KEY": os.environ.get("RWGPS_API_KEY", ""),
        "RWGPS_AUTH_TOKEN": os.environ.get("RWGPS_AUTH_TOKEN", ""),
    }
    # Fallback: próbuj różne pliki .env
    for env_file in ["/opt/qbot/app/.env", "/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"]:
        try:
            for line in open(env_file):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    if k in ("RWGPS_API_KEY", "RWGPS_AUTH_TOKEN") and not env[k]:
                        env[k] = v
        except Exception:
            pass
    return env


def get_form(target_date=None) -> dict:
    """Alias dla _get_form_data."""
    return _get_form_data(target_date)


def get_route(route_id=None, gpx_path=None) -> dict:
    """Pobierz dane trasy z RWGPS lub GPX. Zwraca distance_km, elevation_gain_m, max_grade_pct."""
    result = {"distance_km": 0, "elevation_gain_m": 0, "max_grade_pct": 0, "climbs_count": 0}
    try:
        if route_id:
            env = _rwgps_env()
            url = "https://ridewithgps.com/routes/{}.json?apikey={}&auth_token={}&version=2".format(
                route_id, env.get("RWGPS_API_KEY", ""), env.get("RWGPS_AUTH_TOKEN", ""))
            rd = httpx.get(url, timeout=15.0).json().get("route", {})
            result["distance_km"] = round(float(rd.get("distance", 0)) / 1000, 1)
            result["elevation_gain_m"] = round(float(rd.get("elevation_gain", 0)), 0)
            # max grade z track_points
            tps = rd.get("track_points", [])
            grades = []
            for i in range(1, len(tps)):
                d = float(tps[i].get("d", 0)) - float(tps[i-1].get("d", 0))
                e = float(tps[i].get("e", 0)) - float(tps[i-1].get("e", 0))
                if d > 10:
                    grades.append(abs(e / d * 100))
            result["max_grade_pct"] = round(max(grades), 1) if grades else 0
            # climbs
            try:
                from tools.rwgps.climbs import detect_climbs
                climbs = detect_climbs(tps)
                result["climbs_count"] = len(climbs)
            except Exception:
                pass
        elif gpx_path:
            import xml.etree.ElementTree as ET
            tree = ET.parse(gpx_path)
            root = tree.getroot()
            ns = {"g": "http://www.topografix.com/GPX/1/1"}
            pts = root.findall(".//g:trkpt", ns)
            if pts:
                eles = [float(p.find("g:ele", ns).text) for p in pts if p.find("g:ele", ns) is not None]
                gain = sum(max(0, eles[i] - eles[i-1]) for i in range(1, len(eles)))
                result["elevation_gain_m"] = round(gain)
                # Przybliżony dystans
                result["distance_km"] = round(len(pts) * 0.02, 1)
    except Exception as exc:
        result["_error"] = str(exc)
    return result


def check_feasibility(route_id=None,gpx_path=None,start_lat=None,start_lon=None,start_hour=8,target_date=None):
    form=get_form(target_date); route=get_route(route_id=route_id,gpx_path=gpx_path)
    lat,lon=start_lat,start_lon
    if not lat and route_id:
        try:
            env=_rwgps_env()
            url="https://ridewithgps.com/routes/{}.json?apikey={}&auth_token={}&version=2".format(route_id,env.get("RWGPS_API_KEY",""),env.get("RWGPS_AUTH_TOKEN",""))
            rd=httpx.get(url,timeout=10.0).json().get("route",{})
            lat,lon=rd.get("first_lat"),rd.get("first_lng")
        except Exception: pass
    weather=get_weather(float(lat),float(lon),start_hour) if lat and lon else {}
    return assess_feasibility(form,route,weather,start_hour)

def format_report(r):
    e={"wykonalna":"OK","ryzykowna":"UWAGA","odradzana":"STOP"}.get(r["verdict"],"?")
    lines=["[{}] OCENA: {} (score={})".format(e,r["verdict_pl"],r["score"]),
           "Czas: ~{}h ({}km/h) | Finisz: {}".format(r["estimated_time_h"],r["estimated_speed_kmh"],r["finish_hour_est"]),""]
    if r["bonuses"]: lines+=["Plusy:"]+["  + "+b for b in r["bonuses"]]+[""]
    if r["issues"]: lines+=["Uwagi:"]+["  ! "+i for i in r["issues"]]+[""]
    rs=r["route_summary"]
    lines.append("Trasa: {}km +{}m | {} podjazdow | max {:.0f}%".format(rs["distance_km"],rs["elevation_gain_m"],rs["climbs_count"],rs["max_grade_pct"]))
    w=r["weather_summary"]
    if w and not w.get("_error"): lines.append("Pogoda: {:.0f}C (odcz.{:.0f}C) | {}km/h | {}".format(w["temp_c"],w["feels_c"],w["wind_kmh"],w["desc"]))
    ns=r["nutrition_strategy"]
    lines+=[""]+["Strategia:","  Przed: "+ns["przed_startem"],
            "  ~{} kcal/h | ~{} kcal total | {} ml/h".format(ns["kcal_per_hour"],ns["total_kcal"],ns["hydration_ml_h"])]
    for ww in ns["windows_co_20km"][:6]: lines.append("  km{:.0f} (~{}): {} kcal".format(ww["km"],ww["time"],ww["kcal"]))
    lines.append("  Po: "+ns["po_trasie"])
    return chr(10).join(lines)
