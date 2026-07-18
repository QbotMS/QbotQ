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
from datetime import timedelta

def _get_stage_date(stage, event_keyword="Toskan"):
    """Data etapu = date_start eventu z kalendarza + (stage-1) dni."""
    event_start_date = _get_event_start_date(event_keyword=event_keyword)
    if event_start_date:
        return event_start_date + timedelta(days=stage - 1)
    return date.today()


def _get_event_start_date(event_keyword="Toskan"):
    """Pobierz date startu eventu z qbot_planning_facts (route_stages)."""
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.environ.get("PGHOST","127.0.0.1"),
            port=int(os.environ.get("PGPORT",5432)),
            dbname=os.environ.get("PGDATABASE","qbot"),
            user=os.environ.get("PGUSER","qbot"),
            password=os.environ.get("PGPASSWORD",""),
            connect_timeout=5,
        )
        cur = conn.cursor()
        kw = "%" + event_keyword + "%"
        cur.execute(
            "SELECT date FROM qbot_planning_facts "
            "WHERE fact_type='route_stages' AND title ILIKE %s "
            "ORDER BY date LIMIT 1",
            (kw,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print("Event start date error:", e)
    return None

def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--route-id", required=True)
    p.add_argument("--stage", type=int, default=None, help="Optional manual override for stage number")
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

def _wellness_today(stage_date=None):
    if stage_date is None:
        stage_date = date.today()
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.getenv("PGHOST","127.0.0.1"),
            port=int(os.getenv("PGPORT",5432)),
            dbname=os.getenv("PGDATABASE","qbot"),
            user=os.getenv("PGUSER","qbot"),
            password=os.getenv("PGPASSWORD",""),
            connect_timeout=5,
        )
        cur = conn.cursor()
        today = stage_date.isoformat()
        cur.execute(
            "SELECT hrv_ms, resting_hr_bpm, sleep_score, sleep_duration_min, readiness_label "
            "FROM qbot_wellness_daily WHERE date=%s ORDER BY source_priority", (today,)
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT hrv_ms, resting_hr_bpm, sleep_score, sleep_duration_min, readiness_label, date "
                "FROM qbot_wellness_daily ORDER BY date DESC, source_priority LIMIT 1"
            )
            row_ext = cur.fetchone()
            if row_ext:
                return {"hrv": row_ext[0], "resting_hr": row_ext[1],
                        "sleep_score": row_ext[2], "sleep_hours": row_ext[3],
                        "hrv_status": row_ext[4], "_fallback_date": str(row_ext[5])}
        conn.close()
        if row:
            return {"hrv": row[0], "resting_hr": row[1], "sleep_score": row[2],
                    "sleep_hours": row[3], "hrv_status": row[4]}
    except Exception as e:
        print("Wellness error:", e)
    return {}

def _form_today(stage_date=None):
    if stage_date is None:
        stage_date = date.today()
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.getenv("PGHOST","127.0.0.1"),
            port=int(os.getenv("PGPORT",5432)),
            dbname=os.getenv("PGDATABASE","qbot"),
            user=os.getenv("PGUSER","qbot"),
            password=os.getenv("PGPASSWORD",""),
            connect_timeout=5,
        )
        cur = conn.cursor()
        today = stage_date.isoformat()
        cur.execute(
            "SELECT training_load, recovery_load, form_ratio, form_status, freshness, fatigue, strain, difficulty, ftp_power_w, date "
            "FROM qbot_v2.xert_profile_snapshots "
            "WHERE date=%s AND training_load IS NOT NULL "
            "ORDER BY snapshot_at DESC LIMIT 1",
            (today,)
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT training_load, recovery_load, form_ratio, form_status, freshness, fatigue, strain, difficulty, ftp_power_w, date "
                "FROM qbot_v2.xert_profile_snapshots "
                "ORDER BY date DESC, snapshot_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return {
                    "ctl": row[0],
                    "atl": row[1],
                    "tsb": row[2],
                    "form_status": row[3],
                    "freshness": row[4],
                    "fatigue": row[5],
                    "strain": row[6],
                    "difficulty": row[7],
                    "ftp": row[8],
                    "_fallback_date": str(row[9]),
                }
        conn.close()
        if row:
            return {
                "ctl": row[0],
                "atl": row[1],
                "tsb": row[2],
                "form_status": row[3],
                "freshness": row[4],
                "fatigue": row[5],
                "strain": row[6],
                "difficulty": row[7],
                "ftp": row[8],
            }
    except Exception as e:
        print("Form error:", e)
    return {}

def _wind_dir(deg):
    dirs = ["N","NE","E","SE","S","SW","W","NW"]
    return dirs[round(deg/45) % 8]

def _weather_for_points(track_points, km_from, km_to, step_km=80, stage_date=None):
    if stage_date is None:
        stage_date = date.today()
    """Prognoza godzinowa 7:00-19:00 dla srodka etapu."""
    if not OWM_KEY or not track_points:
        return []
    pts_in_range = [p for p in track_points
                    if km_from*1000 <= float(p.get("d",0)) <= km_to*1000]
    if not pts_in_range:
        return []
    mid_pt = pts_in_range[len(pts_in_range)//2]
    lat, lon = float(mid_pt.get("y",0)), float(mid_pt.get("x",0))
    try:
        url = ("https://api.openweathermap.org/data/2.5/forecast"
               "?lat={}&lon={}&appid={}&units=metric&cnt=16&lang=pl".format(lat,lon,OWM_KEY))
        r = httpx.get(url, timeout=10.0)
        data = r.json()
    except Exception as e:
        print("Weather error:", e)
        return []
    results = []
    today_str = stage_date.isoformat()
    for w in data.get("list", []):
        dt_txt = w.get("dt_txt","")
        if not dt_txt.startswith(today_str):
            continue
        hour = int(dt_txt[11:13])
        if hour < 7 or hour > 19:
            continue
        results.append({
            "hour": f"{hour:02d}:00",
            "temp": w["main"]["temp"],
            "feels": w["main"]["feels_like"],
            "desc": w["weather"][0]["description"],
            "wind_kmh": round(w["wind"]["speed"]*3.6, 1),
            "wind_dir": _wind_dir(w["wind"].get("deg",0)),
            "rain_mm": round(w.get("rain",{}).get("3h",0), 1),
            "humidity": w["main"]["humidity"],
        })
    return results

def _poi_for_stage(stage: int) -> str:
    """Pobierz skrót POI etapu z qbot_planning_facts (poi_stage_detail)."""
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.environ.get("PGHOST","127.0.0.1"),
            port=int(os.environ.get("PGPORT",5432)),
            dbname=os.environ.get("PGDATABASE","qbot"),
            user=os.environ.get("PGUSER","qbot"),
            password=os.environ.get("PGPASSWORD",""),
            connect_timeout=5,
            options="-c search_path=qbot_v2",
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT fact_json FROM qbot_planning_facts "
            "WHERE fact_type='poi_stage_detail' AND fact_json->>'stage' = %s "
            "ORDER BY id LIMIT 1",
            (str(stage),)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return f"Brak POI dla etapu {stage} w bazie."
        data = row[0] if isinstance(row[0], dict) else __import__('json').loads(row[0] or "{}")
        if data.get("poi_stale"):
            return f"POI etapu {stage} wymaga odświeżenia po zmianie trasy"
        lines = []
        section_map = {
            "water":  "Woda",
            "food":   "Jedzenie/sklepy",
            "attractions": "Atrakcje",
            "accommodation": "Nocleg",
        }
        for key, label in section_map.items():
            items = data.get(key, []) + data.get(key + "_google", [])
            if not items:
                continue
            lines.append(f"<b>{label} ({len(items)}):</b>")
            for item in items[:5]:
                if isinstance(item, dict):
                    _n = item.get("name","")
                    if not _n or (_n.split() and _n.split()[-1].isdigit()):
                        for _p in str(item.get("source_tags","")).split(";"):
                            if _p.strip().startswith("name="): _n = _p.strip()[5:]; break
                        if not _n or (_n.split() and _n.split()[-1].isdigit()):
                            _n = item.get("category","poi").capitalize()
                    name = _n or "?"
                else:
                    name = str(item)
                km = item.get("route_km") or item.get("km","") if isinstance(item, dict) else ""
                km_str = f" km {km:.1f}" if isinstance(km, (int,float)) else (f" km {km}" if km else "")
                dist = item.get("distance_to_track_m","") if isinstance(item, dict) else ""
                dist_str = f" — {int(dist)}m" if isinstance(dist, (int,float)) and dist else ""
                lines.append(f"  • {name}{km_str}{dist_str}")
            if len(items) > 5:
                lines.append(f"  ... i {len(items)-5} więcej")
        return "<br>".join(lines) if lines else "Brak POI w bazie dla tego etapu."
    except Exception as e:
        return f"Błąd POI: {e}"


def _build_html(stage, km_from, km_to, route, wellness, weather, climbs, poi_summary, stage_date=None):
    if stage_date is None:
        stage_date = date.today()
    today = stage_date.strftime("%d.%m.%Y")
    name = route.get("name","Trasa")
    dist = round((km_to - km_from),1)
    ele_gain = round(sum(c["elevation_gain_m"] for c in climbs), 0) if climbs else 0
    if ele_gain == 0 and route.get("elevation_gain") and route.get("distance"):
        ele_gain = round(route["elevation_gain"] * (dist/(route["distance"]/1000)), 0)
    surface = route.get("surface","")
    unpaved = route.get("unpaved_pct","?")
    # wellness section
    hrv = wellness.get("hrv","—")
    rhr = wellness.get("resting_hr","—")
    sleep_h = wellness.get("sleep_hours","—")
    sleep_s = wellness.get("sleep_score","—")
    hrv_status = wellness.get("hrv_status","—")
    wellness_note = ""
    if wellness.get("_fallback_date"):
        wellness_note = f' <span style="color:#888;font-size:11px">(dane z {wellness["_fallback_date"]}, sync Garmin w toku)</span>'
    hrv_color = {"good":"#d4edda","strained":"#fff3cd","low":"#f8d7da"}.get(
        str(hrv_status).lower(), "#e9ecef")
    form = _form_today(stage_date=stage_date)
    ctl = form.get("ctl","—")
    atl = form.get("atl","—")
    tsb = form.get("tsb","—")
    form_status = form.get("form_status","—")
    freshness = form.get("freshness","—")
    fatigue = form.get("fatigue","—")
    form_note = ""
    if form.get("_fallback_date"):
        form_note = f' <span style="color:#888;font-size:11px">(dane z {form["_fallback_date"]})</span>'
    tsb_color = "#d4edda"
    if isinstance(tsb, (int, float)):
        if tsb < -15:
            tsb_color = "#f8d7da"
        elif tsb < 5:
            tsb_color = "#fff3cd"
    # weather section
    weather_rows = "".join(
        '<tr><td>{}</td><td>{:.1f}\u00b0C <span style="color:#888">({:.1f}\u00b0C)</span></td>'.format(w["hour"],w["temp"],w["feels"]) +
        '<td>{}</td><td>{} {} km/h</td><td style="color:{}">{} mm</td><td>{}%</td></tr>'.format(
            w["desc"],w["wind_dir"],w["wind_kmh"],
            "#cc3300" if w["rain_mm"]>0 else "#333",w["rain_mm"],w["humidity"])
        for w in weather
    ) if weather else "<tr><td colspan=6>Brak danych pogodowych</td></tr>"
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
	<h2>💪 Forma{wellness_note}</h2>
	<table><tr><th>HRV</th><th>RHR</th><th>Sen</th><th>Czas snu</th><th>Status HRV</th></tr>
	<tr><td style="background:{hrv_color}">{hrv} ms</td><td>{rhr} bpm</td><td>{sleep_s}/100</td><td>{sleep_h}h</td><td style="background:{hrv_color}">{hrv_status}</td></tr></table>
	<h2>📈 Obciążenie / forma{form_note}</h2>
	<table><tr><th>CTL</th><th>ATL</th><th>TSB</th><th>Status</th><th>Freshness</th><th>Fatigue</th></tr>
	<tr><td>{ctl}</td><td>{atl}</td><td style="background:{tsb_color}">{tsb}</td><td>{form_status}</td><td>{freshness}</td><td>{fatigue}</td></tr></table>
	<h2>🌤 Pogoda na trasie (7:00–19:00)</h2>
	<table><tr><th>Godz.</th><th>Temperatura</th><th>Opis</th><th>Wiatr</th><th>Deszcz</th><th>Wilg.</th></tr>{weather_rows}</table>
<h2>⛰ Podjazdy</h2>
<p style="color:#555;font-size:13px">Łączze przewyższenie z podjazdów: <b>+{ele_gain:.0f}m</b></p>
<table><tr><th>Odcinek</th><th>Dlugosc</th><th>Gain</th><th>Avg %</th><th>Max %</th><th>Czas</th><th>Kategoria</th></tr>{climbs_rows}</table>
<h2>📍 POI na trasie</h2><div style="line-height:1.7">{poi_summary}</div>
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
    event_start_date = _get_event_start_date()
    if args.stage is None:
        if event_start_date:
            args.stage = (date.today() - event_start_date).days + 1
        else:
            args.stage = 1
    print("Event Morning Report — etap", args.stage, "km", args.km_from, "-", args.km_to)
    route = _rwgps_route(args.route_id)
    tp = route.get("track_points",[])
    print(f"Track points: {len(tp)}")
    stage_date = _get_stage_date(args.stage)
    print("Stage date:", stage_date)
    print("Event start date:", event_start_date or "nieznana")
    wellness = _wellness_today(stage_date=stage_date)
    print("Wellness:", wellness)
    weather = _weather_for_points(tp, args.km_from, args.km_to, stage_date=stage_date)
    print(f"Weather points: {len(weather)}")
    from tools.rwgps.climbs import detect_climbs
    climbs = detect_climbs(tp, km_from=args.km_from, km_to=args.km_to)
    print(f"Climbs: {len(climbs)}")
    poi_summary = _poi_for_stage(args.stage)
    html = _build_html(args.stage, args.km_from, args.km_to, route, wellness, weather, climbs, poi_summary, stage_date=stage_date)
    subject = "QBot Etap {} — {} | km {:.0f}-{:.0f}".format(args.stage, stage_date.strftime("%d.%m"), args.km_from, args.km_to)
    _send_email(subject, html, dry_run=args.dry_run)
    print("Gotowe.")

if __name__ == "__main__":
    main()
