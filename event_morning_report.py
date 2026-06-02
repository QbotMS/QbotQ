#!/usr/bin/env python3
"""event_morning_report.py — Raport poranny na czas eventu rowerowego.

Generuje i wysyla emailem raport zawierajacy:
- Forme fizyczna (HRV, sen, zmeczenie)
- Pogode na trasie (OpenWeatherMap, strefowo co ~100km)
- Profil etapu (km, przewyzszenie, nawierzchnia)
- Podjazdy na dzis (z RWGPS, kategorie HC/Cat1-4)
- Atrakcje na trasie
- Resupply: sklepy, woda, knajpy
- Nocleg: gdzie, ile km zostalo

Uzycie:
    python event_morning_report.py --route-id 55257604 --stage 1 --km-from 0 --km-to 85
    python event_morning_report.py --route-id 55257604 --stage 2 --km-from 85 --km-to 170
"""
from __future__ import annotations
import argparse, os, sys, json, smtplib
from datetime import datetime, timezone, date
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

from dotenv import load_dotenv
load_dotenv(APP_DIR / ".env.local")

OWM_KEY = os.environ.get("OWM_API_KEY") or os.environ.get("OPENWEATHER_API_KEY","")
GMAIL_USER = os.environ.get("GMAIL_USER","")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD","")
TO_EMAIL = os.environ.get("REPORT_EMAIL", GMAIL_USER)

import httpx

def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--route-id", required=True)
    p.add_argument("--stage", type=int, default=1)
    p.add_argument("--km-from", type=float, default=0)
    p.add_argument("--km-to", type=float, default=100)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def _rwgps_route(route_id):
    env = dict(l.strip().split("=",1) for l in open(APP_DIR/".env.local") if "=" in l and not l.startswith("#"))
    url = "https://ridewithgps.com/routes/{}.json?apikey={}&auth_token={}&version=2".format(
        route_id, env.get("RWGPS_API_KEY",""), env.get("RWGPS_AUTH_TOKEN",""))
    r = httpx.get(url, timeout=15.0)
    return r.json().get("route",{})

def _wellness_today():
    try:
        import db
        conn = db.get_conn()
        cur = conn.cursor()
        today = date.today().isoformat()
        cur.execute("SELECT hrv_rmssd, resting_hr, sleep_score, sleep_hours, hrv_status FROM wellness WHERE date=%s", (today,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {"hrv": row[0], "resting_hr": row[1], "sleep_score": row[2], "sleep_hours": row[3], "hrv_status": row[4]}
    except Exception as e:
        pass
    return {}

def _weather_for_points(track_points, km_from, km_to, step_km=80):
    """Get weather for points along route every step_km km."""
    if not OWM_KEY or not track_points:
        return []
    pts_in_range = [p for p in track_points
                    if km_from*1000 <= float(p.get("d",0)) <= km_to*1000]
    if not pts_in_range:
        return []
    # sample every step_km
    step_m = step_km * 1000
    samples = []
    last_d = -step_m
    for p in pts_in_range:
        d = float(p.get("d",0))
        if d - last_d >= step_m:
            samples.append(p)
            last_d = d
    if not samples:
        samples = [pts_in_range[len(pts_in_range)//2]]
    results = []
    for p in samples[:5]:
        try:
            lat, lon = float(p.get("y",0)), float(p.get("x",0))
            url = "https://api.openweathermap.org/data/2.5/forecast?lat={}&lon={}&appid={}&units=metric&cnt=4&lang=pl".format(lat,lon,OWM_KEY)
            r = httpx.get(url, timeout=8.0)
            data = r.json()
            if data.get("list"):
                w = data["list"][0]
                km = round(float(p.get("d",0))/1000, 0)
                results.append({"km": km, "temp": w["main"]["temp"], "feels": w["main"]["feels_like"],
                    "desc": w["weather"][0]["description"], "wind_kmh": round(w["wind"]["speed"]*3.6,1),
                    "rain_mm": w.get("rain",{}).get("3h",0), "humidity": w["main"]["humidity"]})
        except Exception:
            pass
    return results

def _build_html(stage, km_from, km_to, route, wellness, weather, climbs, poi_summary):
    today = date.today().strftime("%d.%m.%Y")
    name = route.get("name","Trasa")
    dist = round((km_to - km_from),1)
    ele_gain = round(route.get("elevation_gain",0) * (dist/(route.get("distance",1)/1000)),0) if route.get("distance") else 0
    surface = route.get("surface","")
    unpaved = route.get("unpaved_pct","?")
    # wellness section
    hrv = wellness.get("hrv","—")
    rhr = wellness.get("resting_hr","—")
    sleep_h = wellness.get("sleep_hours","—")
    sleep_s = wellness.get("sleep_score","—")
    hrv_status = wellness.get("hrv_status","—")
    # weather section
    weather_rows = "".join('<tr><td>km {:.0f}</td><td>{:.1f}°C (odczuwalna {:.1f}°C)</td><td>{}</td><td>{} km/h</td><td>{} mm</td></tr>'.format(
        w["km"],w["temp"],w["feels"],w["desc"],w["wind_kmh"],w["rain_mm"]) for w in weather) if weather else "<tr><td colspan=5>Brak danych pogodowych</td></tr>"
    # climbs section
    climbs_rows = "".join('<tr><td>km {:.1f}–{:.1f}</td><td>{}m</td><td>+{}m</td><td>{:.1f}%</td><td>{:.1f}%</td><td>~{}:{:02d}</td><td><b>{}</b></td></tr>'.format(
        c["start_km"],c["end_km"],c["length_m"],c["elevation_gain_m"],c["avg_grade_pct"],c["max_grade_pct"],
        c["estimated_time_sec"]//60,c["estimated_time_sec"]%60,c["category"]) for c in climbs) if climbs else "<tr><td colspan=7>Brak znaczacych podjazdow</td></tr>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#222}}
h1{{color:#e05c00}}h2{{color:#444;border-bottom:2px solid #e05c00;padding-bottom:4px}}
table{{width:100%;border-collapse:collapse;margin:10px 0}}
th{{background:#e05c00;color:white;padding:8px;text-align:left}}
td{{padding:6px 8px;border-bottom:1px solid #eee}}
.badge{{display:inline-block;padding:3px 8px;border-radius:4px;font-weight:bold}}
.good{{background:#d4edda;color:#155724}}.warn{{background:#fff3cd;color:#856404}}.bad{{background:#f8d7da;color:#721c24}}
</style></head><body>
<h1>☀️ Raport poranny — Etap {stage} | {today}</h1>
<p><b>{name}</b> | km {km_from:.0f}–{km_to:.0f} | dystans: <b>{dist} km</b> | przewyzszenie: <b>+{ele_gain:.0f}m</b> | nawierzchnia: nieutwardzona {unpaved}%</p>
<h2>💪 Forma</h2>
<table><tr><th>HRV</th><th>RHR</th><th>Sen</th><th>Czas snu</th><th>Status HRV</th></tr>
<tr><td>{hrv} ms</td><td>{rhr} bpm</td><td>{sleep_s}/100</td><td>{sleep_h}h</td><td>{hrv_status}</td></tr></table>
<h2>🌤 Pogoda na trasie</h2>
<table><tr><th>Km</th><th>Temperatura</th><th>Opis</th><th>Wiatr</th><th>Deszcz</th></tr>{weather_rows}</table>
<h2>⛰ Podjazdy</h2>
<table><tr><th>Odcinek</th><th>Dlugosc</th><th>Gain</th><th>Avg %</th><th>Max %</th><th>Czas</th><th>Kategoria</th></tr>{climbs_rows}</table>
<h2>📍 POI na trasie</h2><p>{poi_summary}</p>
<hr><p style="color:#999;font-size:12px">Wygenerowano: {datetime.now().strftime("%Y-%m-%d %H:%M")} | QBot Event Morning Report</p>
</body></html>"""

def _send_email(subject, html, dry_run=False):
    if dry_run:
        print("DRY RUN — email nie wyslany")
        print(html[:500])
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_USER, [TO_EMAIL], msg.as_string())
    print("Email wyslany do", TO_EMAIL)

def main():
    args = _parse_args()
    print("Event Morning Report — etap", args.stage, "km", args.km_from, "-", args.km_to)
    route = _rwgps_route(args.route_id)
    tp = route.get("track_points",[])
    print(f"Track points: {len(tp)}")
    wellness = _wellness_today()
    print("Wellness:", wellness)
    weather = _weather_for_points(tp, args.km_from, args.km_to)
    print(f"Weather points: {len(weather)}")
    from tools.rwgps.climbs import detect_climbs
    climbs = detect_climbs(tp, km_from=args.km_from, km_to=args.km_to)
    print(f"Climbs: {len(climbs)}")
    # POI summary from cache
    poi_summary = "Analiza POI dostepna przez: qbot.query >> przeanalizuj poi toskania km {}-{}".format(int(args.km_from), int(args.km_to))
    html = _build_html(args.stage, args.km_from, args.km_to, route, wellness, weather, climbs, poi_summary)
    subject = "QBot Etap {} — {} | km {:.0f}-{:.0f}".format(args.stage, date.today().strftime("%d.%m"), args.km_from, args.km_to)
    _send_email(subject, html, dry_run=args.dry_run)
    print("Gotowe.")

if __name__ == "__main__":
    main()
