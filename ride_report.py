#!/usr/bin/env python3
"""
ride_report.py — Analiza jazdy po treningu
Cron co 30 min sprawdza nowe aktywności z Garmin (przez Intervals.icu)
i wysyła raport emailem + Telegram.
"""
import sys, json, httpx, smtplib, time
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path
import qbot_config as cfg
from qbot_readiness import evaluate_readiness
from qbot_coach import build_ride_lesson
from qbot_report_status import activity_report_complete, mark_activity_report
from qbot_mcp_client import mcp_call as _shared_mcp_call

ATHLETE_ID    = cfg.INTERVALS_ATHLETE_ID
API_KEY       = cfg.INTERVALS_API_KEY
GMAIL_USER    = cfg.GMAIL_USER
GMAIL_PASS    = cfg.GMAIL_APP_PASSWORD
EMAIL_TO      = cfg.EMAIL_TO
TOKEN         = cfg.TELEGRAM_TOKEN
CHAT_ID       = cfg.TELEGRAM_CHAT_ID

ICU_HDR = cfg.intervals_headers()

REPORTED_FILE = Path("/opt/qbot/app/data/reported_activities.json")
REPORTED_FILE.parent.mkdir(exist_ok=True)
IN_PROGRESS_TTL_HOURS = 6
RIDE_REPORT_PREVIEW_DIR = Path("/opt/qbot/app/outgoing/ride_report_previews")

# ── Helpers ───────────────────────────────────────────────────────────────────

def icu_get(path, params=None):
    r = httpx.get(f"https://intervals.icu/api/v1{path}",
                  headers=ICU_HDR, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def mcp_call(tool, args=None):
    return _shared_mcp_call(tool, args, client_name="ride-report", logger=print)

def mcp_call_retry(tool, args=None, attempts=3, delay_s=8):
    last = None
    for attempt in range(1, attempts + 1):
        last = mcp_call(tool, args)
        if last is not None and not (isinstance(last, dict) and last.get("error")):
            return last
        if attempt < attempts:
            reason = last.get("error") if isinstance(last, dict) else "brak odpowiedzi MCP"
            print(f"⚠️  {tool} próba {attempt}/{attempts}: {reason} — ponawiam za {delay_s}s")
            time.sleep(delay_s)
    return last

def send_email(subject, html):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_USER
    msg['To']      = EMAIL_TO
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)

def send_telegram(msg):
    for i in range(0, len(msg), 4000):
        r = httpx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                       json={"chat_id": CHAT_ID, "text": msg[i:i+4000]}, timeout=10)
        r.raise_for_status()

def already_reported(activity_id):
    return activity_report_complete(REPORTED_FILE, str(activity_id), in_progress_ttl_hours=IN_PROGRESS_TTL_HOURS)

def mark_report_status(activity_id, activity_name, status, error=None, channels=None):
    mark_activity_report(REPORTED_FILE, str(activity_id), activity_name, status, error=error, channels=channels)

def mark_reported(activity_id, activity_name):
    mark_report_status(activity_id, activity_name, "sent")

# ── Dane ──────────────────────────────────────────────────────────────────────

def _safe_float(value, default=None):
    if value in (None, ""):
        return default
    try:
        text = str(value).strip().replace("%", "").replace(",", ".")
        return float(text)
    except (TypeError, ValueError):
        return default

def _safe_int(value, default=None):
    f = _safe_float(value, None)
    return int(f) if f is not None else default

def _activity_comment(details):
    for key in ("description", "notes", "comments", "comment"):
        text = details.get(key)
        if text:
            return str(text).strip()
    return ""

def _mentions_illness(*texts):
    haystack = " ".join(str(t or "").lower() for t in texts)
    markers = (
        "chor", "infek", "przezięb", "przezieb", "kaszel", "gorącz", "goracz",
        "ból", "bol ", "kontuz", "uraz", "antybiot", "zmęcz", "zmecz",
        "delegac", "niewyspan", "słaby sen", "slaby sen",
    )
    return any(m in haystack for m in markers)

def _wellness_by_date(wellness):
    return {str(w.get("id")): w for w in wellness if w.get("id")}

def _format_metric(value, suffix="", digits=0):
    if value in (None, ""):
        return "—"
    try:
        f = float(value)
        if digits == 0:
            return f"{int(round(f))}{suffix}"
        return f"{round(f, digits)}{suffix}"
    except (TypeError, ValueError):
        return f"{value}{suffix}"

def _surface_label(label):
    if not label:
        return "nieznana"
    raw = str(label).strip().lower()
    return {
        "asphalt": "asfalt",
        "paved": "asfalt",
        "concrete": "beton",
        "concrete:plates": "płyty betonowe",
        "cobblestone": "kostka brukowa",
        "sett": "kostka brukowa",
        "paving_stones": "kostka brukowa",
        "gravel": "gravel/żwir",
        "fine_gravel": "gravel drobny",
        "compacted": "ubita nawierzchnia",
        "dirt": "ziemia/grunt",
        "ground": "grunt",
        "earth": "grunt",
        "grass": "trawa",
        "sand": "piasek",
        "unpaved": "nieutwardzona",
        "unhewn_cobblestone": "surowa kostka",
    }.get(raw, raw.replace("_", " "))

def _surface_percent(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace("%", "")
    try:
        return int(round(float(text)))
    except (TypeError, ValueError):
        return None

def _surface_summary(surface):
    if not isinstance(surface, dict) or surface.get("error"):
        return {
            "available": False,
            "summary": None,
            "detail": None,
            "context": None,
        }

    counts = surface.get("nawierzchnia") or {}
    ranked = []
    unknown_pct = 0
    for label, pct_text in counts.items():
        pct = _surface_percent(pct_text)
        if pct is None:
            continue
        nice = _surface_label(label)
        if nice == "nieznana":
            unknown_pct += pct
            continue
        ranked.append((nice, pct))

    ranked.sort(key=lambda item: (-item[1], item[0]))
    dominant = _surface_label(surface.get("dominujaca"))
    dominant_pct = next((pct for label, pct in ranked if label == dominant), None)
    if dominant_pct is None and ranked:
        dominant, dominant_pct = ranked[0]

    if not ranked and unknown_pct <= 0:
        return {
            "available": False,
            "summary": None,
            "detail": None,
            "context": None,
        }

    if not ranked:
        return {
            "available": True,
            "summary": "nawierzchnia nieznana",
            "detail": None,
            "context": surface.get("kontekst_kadencji"),
        }

    if len(ranked) == 1 and (unknown_pct < 15):
        summary = f"{ranked[0][0]} {ranked[0][1]}%"
    else:
        summary = f"mieszana, przewaga {dominant} {dominant_pct}%" if dominant_pct is not None else "mieszana"

    detail_parts = [f"{label} {pct}%" for label, pct in ranked[:3]]
    if unknown_pct >= 25:
        detail_parts.append(f"nieznana {unknown_pct}%")
    detail = ", ".join(detail_parts) if detail_parts else None

    return {
        "available": True,
        "summary": summary,
        "detail": detail,
        "context": surface.get("kontekst_kadencji"),
    }

def _healthy_activity(activity, wellness_map):
    day = str(activity.get("start_date_local", ""))[:10]
    w = wellness_map.get(day, {})
    return not _mentions_illness(activity.get("description"), activity.get("notes"), w.get("comments"))

def _similar_activities(current, activities, wellness_map, activity_id):
    cur_dist = _safe_float(current.get("distance"), 0) or 0
    rows = []
    for act in activities:
        if str(act.get("id")) == str(activity_id):
            continue
        if not _healthy_activity(act, wellness_map):
            continue
        dist = _safe_float(act.get("distance"), 0) or 0
        if cur_dist and dist and not (cur_dist * 0.5 <= dist <= cur_dist * 1.5):
            continue
        rows.append({
            "date": str(act.get("start_date_local", ""))[:10] or act.get("start_date", ""),
            "name": act.get("name", "Aktywność"),
            "distance_km": round(dist / 1000, 1) if dist else None,
            "np": act.get("icu_weighted_avg_watts") or act.get("weighted_average_watts"),
            "avg_hr": act.get("average_heartrate"),
            "ef": act.get("icu_efficiency_factor"),
            "cadence": act.get("average_cadence"),
        })
    return rows[:5]

def _long_ride_rows(activities, activity_id):
    rows = []
    for act in activities:
        if str(act.get("id")) == str(activity_id):
            continue
        dist = _safe_float(act.get("distance"), 0) or 0
        moving = _safe_float(act.get("moving_time"), 0) or 0
        if moving > 3 * 3600 or dist > 80000:
            rows.append({
                "date": str(act.get("start_date_local", ""))[:10] or act.get("start_date", ""),
                "name": act.get("name", "Długa jazda"),
                "distance_km": round(dist / 1000, 1) if dist else None,
                "hours": round(moving / 3600, 1) if moving else None,
                "np": act.get("icu_weighted_avg_watts") or act.get("weighted_average_watts"),
                "avg_hr": act.get("average_heartrate"),
                "ef": act.get("icu_efficiency_factor"),
            })
    return rows[:3]

def _avg(values):
    vals = [_safe_float(v) for v in values if _safe_float(v) is not None]
    return round(sum(vals) / len(vals), 1) if vals else None

def _half_split_analysis(details):
    streams = details.get("fit_streams") or {}
    power = ((streams.get("power") or {}).get("probki_co_30s")) or []
    hr = ((streams.get("heart_rate") or {}).get("probki_co_30s")) or []
    cadence = ((streams.get("cadence") or {}).get("probki_co_30s")) or []
    n = max(len(power), len(hr), len(cadence))
    if n < 4:
        return {
            "available": False,
            "source": "brak wystarczających próbek FIT co 30 s",
        }
    mid = n // 2
    p1, p2 = _avg(power[:mid]), _avg(power[mid:])
    h1, h2 = _avg(hr[:mid]), _avg(hr[mid:])
    c1, c2 = _avg(cadence[:mid]), _avg(cadence[mid:])
    fade_pct = round((p2 - p1) / p1 * 100, 1) if p1 and p2 is not None else None
    hr_drift_pct = round((h2 - h1) / h1 * 100, 1) if h1 and h2 is not None else None
    return {
        "available": True,
        "source": "FIT samples every 30 s",
        "power_first_half": p1,
        "power_second_half": p2,
        "power_fade_pct": fade_pct,
        "hr_first_half": h1,
        "hr_second_half": h2,
        "hr_drift_pct": hr_drift_pct,
        "cadence_first_half": c1,
        "cadence_second_half": c2,
    }

def build_ride_protocol(d):
    act = d.get("aktywnosc", {}) or {}
    wellness = d.get("wellness_7dni", []) or []
    w_today = d.get("wellness_dzis", {}) or {}
    garmin = d.get("garmin", {}) or {}
    surface = d.get("nawierzchnia", {}) or {}
    bike = d.get("bike", {}) or {}
    comment = _activity_comment(act)
    wellness_comments = " ".join(str(w.get("comments") or "") for w in wellness)

    hrv_today = _safe_float(w_today.get("hrv"))
    hrv_values = [_safe_float(w.get("hrv")) for w in wellness if _safe_float(w.get("hrv")) is not None]
    hrv_norm = round(sum(hrv_values) / len(hrv_values), 1) if hrv_values else None
    hrv_delta = round(hrv_today - hrv_norm, 1) if hrv_today is not None and hrv_norm is not None else None
    illness = _mentions_illness(comment, wellness_comments)
    resting_hr = _safe_float(w_today.get("restingHR"))
    body_battery = garmin.get("body_battery_rano")
    tsb = w_today.get("form") or w_today.get("tsb") or w_today.get("icu_training_load_balance")

    readiness = evaluate_readiness(
        hrv=hrv_today,
        hrv_norm=hrv_norm,
        body_battery=body_battery,
        sleep_hours=(_safe_float(w_today.get("sleepSecs")) or 0) / 3600 if w_today.get("sleepSecs") else None,
        form=tsb,
        illness_context=illness,
        resting_hr=resting_hr,
    )

    surface_summary = _surface_summary(surface)
    route_ok = bool(surface and not surface.get("error"))
    recording_stops = act.get("recording_stops") or act.get("icu_recording_stops")
    avg_watts = act.get("icu_average_watts") or act.get("avg_power")
    np_watts = act.get("icu_weighted_avg_watts") or act.get("norm_power")
    intensity = act.get("icu_intensity")
    if _safe_float(intensity) is not None and _safe_float(intensity) > 2:
        intensity = round(_safe_float(intensity) / 100, 3)
    hr_avg = act.get("average_heartrate") or act.get("avg_hr")
    ef = act.get("icu_efficiency_factor")
    cadence = act.get("average_cadence")
    vi = act.get("icu_variability_index")
    temp = act.get("average_temp")
    decoup_display, decoup_opis, decoup_bad = interpret_decoupling(act.get("decoupling"))

    distance_m = _safe_float(act.get("distance"), 0) or 0
    moving_s = _safe_float(act.get("moving_time"), 0) or 0
    is_long = moving_s > 3 * 3600 or distance_m > 80000

    split = _half_split_analysis(act) if is_long else {"available": False, "source": "not a long ride"}

    if route_ok:
        cadence_rule = "Kadencja oceniana po sprawdzeniu nawierzchni i typu roweru."
    else:
        cadence_rule = "Nie oceniam kadencji względem terenu bez danych o nawierzchni."

    return {
        "health": {
            "hrv_today": hrv_today,
            "hrv_norm": hrv_norm,
            "hrv_delta": readiness.hrv_delta,
            "resting_hr": resting_hr,
            "body_battery": body_battery,
            "tsb": tsb,
            "readiness": readiness.color,
            "verdict": readiness.verdict,
            "note": readiness.note,
        },
        "comment": comment,
        "route": {
            "available": route_ok,
            "location": surface.get("lokalizacja") if isinstance(surface, dict) else None,
            "surface": surface_summary,
            "surface_counts": surface.get("nawierzchnia") if isinstance(surface, dict) else {},
            "dominant": surface.get("dominujaca") if isinstance(surface, dict) else None,
            "recording_stops": recording_stops,
            "cadence_rule": cadence_rule,
        },
        "coach": {
            "avg_watts": avg_watts,
            "np_watts": np_watts,
            "if": intensity,
            "vi": vi,
            "avg_hr": hr_avg,
            "max_hr": act.get("max_heartrate"),
            "ef": ef,
            "decoupling": decoup_display,
            "decoupling_note": decoup_opis,
            "decoupling_bad": decoup_bad,
            "cadence": cadence,
            "bike_type": bike.get("typ"),
            "temperature": temp,
        },
        "comparison": d.get("porownanie_podobne", []),
        "long_rides": {
            "current_is_long": is_long,
            "previous": d.get("ostatnie_dlugie_jazdy", []),
            "split": split,
            "note": "Analiza pierwszej i drugiej połowy oparta na próbkach FIT co 30 s." if is_long and split.get("available") else "",
        },
    }

def fetch_activity_data(activity_id):
    """Pobierz wszystkie dane o aktywności"""
    today = date.today()

    print(f"📊 Pobieram dane dla aktywności {activity_id}...")

    # Szczegóły aktywności
    details   = mcp_call("get_activity_details", {"activity_id": str(activity_id)}) or {}
    surface   = mcp_call_retry("get_route_surface", {"activity_id": str(activity_id)}, attempts=3, delay_s=10) or {}
    xert      = mcp_call("get_xert_status") or {}
    # Pobierz datę aktywności z Intervals
    act_for_date = icu_get(f"/athlete/{ATHLETE_ID}/activities/{activity_id}") if False else None
    act_date_str = today.isoformat()  # domyślnie dziś
    all_acts = icu_get(f"/athlete/{ATHLETE_ID}/activities",
                       {"oldest": (today - timedelta(days=14)).isoformat(),
                        "newest": today.isoformat(), "limit": 20})
    for a in all_acts:
        if str(a.get("id")) == str(activity_id):
            act_date_str = a.get("start_date_local","")[:10]
            break
    act_date = date.fromisoformat(act_date_str)

    # Plany z kalendarza na dzień aktywności
    _events_raw = mcp_call("get_events", {"oldest": act_date.isoformat(), "newest": act_date.isoformat()}) or []
    planned_events = _events_raw if isinstance(_events_raw, list) else []
    garmin    = mcp_call("get_garmin_wellness", {"date": act_date_str}) or {}

    # Wellness dla dnia jazdy i kontekstu 7 dni
    wellness = icu_get(f"/athlete/{ATHLETE_ID}/wellness",
                       {"oldest": (act_date - timedelta(days=7)).isoformat(), "newest": act_date.isoformat()})
    w_today  = next((w for w in wellness if w.get("id") == act_date_str), {})

    # Ostatnie aktywności (kontekst i porównania)
    activities = icu_get(f"/athlete/{ATHLETE_ID}/activities",
                         {"oldest": (act_date - timedelta(days=7)).isoformat(),
                          "newest": act_date.isoformat(), "limit": 20})
    long_activities = icu_get(f"/athlete/{ATHLETE_ID}/activities",
                              {"oldest": (act_date - timedelta(days=365)).isoformat(),
                               "newest": act_date.isoformat(), "limit": 200})

    # Sprzęt (identyfikacja roweru)
    gear_id   = "b16355769"  # domyślnie, nadpisane z aktywności
    gear_list = mcp_call("get_gear") or []
    gear_map  = {g["strava_gear_id"]: g for g in gear_list}

    # Pobierz ID sprzętu z aktywności
    act_basic = next((a for a in icu_get(
        f"/athlete/{ATHLETE_ID}/activities",
        {"oldest": act_date.isoformat(), "newest": act_date.isoformat(), "limit": 20}
    ) if str(a.get("id")) == str(activity_id)), {})
    gear_id = (act_basic.get("gear") or {}).get("id", gear_id)
    bike_info = gear_map.get(gear_id, {})
    bike_name = bike_info.get("nazwa", "Rower")

    # Klasyfikuj typ roweru po nazwie
    name_lower = bike_name.lower()
    if any(x in name_lower for x in ["grizl","gravel","griz","gravl","terra","checkpoint"]):
        bike_type = "gravel"
    elif any(x in name_lower for x in ["mtb","kloc","mountain","hardtail","enduro"]):
        bike_type = "mtb"
    elif any(x in name_lower for x in ["aero","tt","time trial","triathlon"]):
        bike_type = "tt"
    else:
        bike_type = "szosa"

    # Wyjazdy z garażu
    try:
        import sys; sys.path.insert(0, '/opt/qbot/app')
        import db
        trips = db.get_trips(status="planned") or []
        upcoming = sorted(
            [{"name": t.get("name"), "start_date": t.get("start_date"),
              "days_to": (date.fromisoformat(t["start_date"]) - today).days,
              "distance_km": t.get("distance_km"), "elevation_m": t.get("elevation_m")}
             for t in trips if t.get("start_date") and t["start_date"] >= today.isoformat()],
            key=lambda x: x["start_date"]
        )[:1]
    except:
        upcoming = []

    return {
        "activity_id": activity_id,
        "dzisiaj": today.isoformat(),
        "data_aktywnosci": act_date_str,
        "aktywnosc": details,
        "nawierzchnia": surface,
        "wellness_dzis": w_today,
        "wellness_7dni": wellness,
        "ostatnie_aktywnosci": activities[:5],
        "porownanie_podobne": _similar_activities(details, activities, _wellness_by_date(wellness), activity_id),
        "ostatnie_dlugie_jazdy": _long_ride_rows(long_activities, activity_id),
        "xert": {
            "tp_ftp_w": xert.get("tp_ftp_watts"),
            "forma_status": (xert.get("forma") or {}).get("status"),
            "obciazenie": (xert.get("forma") or {}).get("training_load"),
            "swiezosc": (xert.get("forma") or {}).get("form_score"),
        },
        "garmin": {
            "hrv": (garmin.get("hrv") or {}).get("srednia_noc"),
            "hrv_status": (garmin.get("hrv") or {}).get("status"),
            "body_battery_rano": (garmin.get("body_battery") or {}).get("max_rano"),
        },
        "wyjazd": upcoming[0] if upcoming else None,
        "plany_na_dzien": planned_events,
        "bike": {
            "id": gear_id,
            "nazwa": bike_name,
            "typ": bike_type,
            "dystans_km": bike_info.get("dystans_km"),
        },
    }

# ── Raport ────────────────────────────────────────────────────────────────────

def interpret_decoupling(raw_value):
    """
    Intervals.icu: dodatnia wartość oznacza większy dryf/decoupling.
    Zwraca: (wartość_do_wyswietlenia_str, opis, jest_zly)
    """
    value = _safe_float(raw_value)
    if value is None:
        return "—", "brak danych", False
    drift = round(value, 1)
    is_bad = drift > 5
    if drift > 5:
        note = "cardiac drift — HR rosło szybciej niż moc"
    elif drift > 0:
        note = "lekki drift — jeszcze w granicy akceptacji"
    else:
        note = "brak dryfu — HR stabilne względem mocy"
    return f"{drift:.1f}%", note, is_bad

BG      = "#0f1117"
BG2     = "#1a1d27"
BG_OK   = "#0d2318"
BG_WARN = "#241c08"
BG_BAD  = "#220d0d"
TXT     = "#f0f2f8"
TXT2    = "#c8cdd8"
TXT3    = "#7a8299"
OK      = "#5dba7a"
WARN    = "#e8a840"
BAD     = "#e05555"
BORDER  = "#2a2e3d"

def card3(items):
    """3 kafelki obok siebie"""
    cells = ""
    for label, value, color in items:
        c = color or TXT
        cells += (f'<td style="padding:5px;" width="33%">'
                  f'<table width="100%" cellpadding="14" cellspacing="0" bgcolor="{BG2}"'
                  f' style="border-radius:10px;border:1px solid {BORDER};">'
                  f'<tr><td>'
                  f'<div style="font-size:12px;color:{TXT2};margin-bottom:4px;">{label}</div>'
                  f'<div style="font-size:20px;font-weight:bold;color:{c};">{value}</div>'
                  f'</td></tr></table></td>')
    return f'<table width="100%" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>'

def section(title, content):
    return (f'<div style="font-size:11px;font-weight:bold;color:{TXT3};text-transform:uppercase;'
            f'letter-spacing:1.2px;margin:22px 0 12px;">{title}</div>'
            f'{content}')

def txt_block(text):
    return (f'<div style="font-size:17px;color:{TXT2};line-height:1.8;'
            f'text-align:justify;margin:10px 0;">{text}</div>')

def sep():
    return f'<div style="border-top:1px solid {BORDER};margin:20px 0;"></div>'

def _kv_rows(rows):
    body = ""
    for label, value in rows:
        body += (
            f'<tr><td style="padding:7px 8px;color:{TXT3};font-size:13px;border-bottom:1px solid {BORDER};">'
            f'{escape(str(label))}</td>'
            f'<td style="padding:7px 8px;color:{TXT};font-size:13px;text-align:right;border-bottom:1px solid {BORDER};">'
            f'{escape(str(value))}</td></tr>'
        )
    return f'<table width="100%" cellpadding="0" cellspacing="0">{body}</table>'

def _small_table(headers, rows):
    if not rows:
        return txt_block("Brak porównywalnych zdrowych jazd w sprawdzonym oknie danych.")
    th = "".join(
        f'<th style="padding:7px 6px;color:{TXT3};font-size:12px;text-align:{"left" if i == 0 else "right"};border-bottom:1px solid {BORDER};">{escape(h)}</th>'
        for i, h in enumerate(headers)
    )
    trs = ""
    for row in rows:
        trs += "<tr>" + "".join(
            f'<td style="padding:8px 6px;color:{TXT2};font-size:13px;text-align:{"left" if i == 0 else "right"};border-bottom:1px solid {BORDER};">{escape(str(cell if cell not in (None, "") else "—"))}</td>'
            for i, cell in enumerate(row)
        ) + "</tr>"
    return f'<table width="100%" cellpadding="0" cellspacing="0"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'

def _stop_summary(stops):
    if not stops:
        return "—"
    if isinstance(stops, list):
        return f"{len(stops)} pauz/rejestracji"
    return str(stops)

def _has_any_metric(row, keys):
    return any(row.get(k) not in (None, "", "—") for k in keys)

def _concise_recommendation(protocol):
    h = protocol.get("health", {})
    coach = protocol.get("coach", {})
    route = protocol.get("route", {})
    long_rides = protocol.get("long_rides", {})
    split = long_rides.get("split", {}) or {}
    rec = []
    readiness = h.get("readiness")
    if readiness == "czerwona":
        rec.append("Dzisiaj priorytetem jest regeneracja; kolejny trening tylko lekki Z1.")
    elif readiness == "żółta":
        rec.append("Kolejny trening trzymaj w Z1-Z2, bez mocnego akcentu.")
    else:
        rec.append("Możesz kontynuować plan, o ile poranne HRV i samopoczucie nie spadną.")

    if coach.get("decoupling_bad"):
        rec.append("Dryf HR przekroczył 5%, więc kolejną jazdę zacznij spokojniej i pilnuj jedzenia od początku.")
    elif split.get("available") and _safe_float(split.get("power_fade_pct")) is not None and _safe_float(split.get("power_fade_pct")) < -8:
        rec.append("W drugiej połowie moc spadła, więc przy dłuższych jazdach jedz wcześniej.")
    if route.get("available") is False:
        rec.append("Brak danych nawierzchni, więc nie wyciągam wniosku o kadencji względem terenu.")
    elif coach.get("cadence") not in (None, "") and coach.get("bike_type"):
        rec.append(f"Kadencję oceniaj w kontekście roweru: {coach.get('bike_type')}, średnio {_format_metric(coach.get('cadence'), ' rpm')}.")

    return " ".join(rec[:3])

def _trainer_analysis(protocol):
    h = protocol.get("health", {})
    route = protocol.get("route", {})
    coach = protocol.get("coach", {})
    long_rides = protocol.get("long_rides", {})
    split = long_rides.get("split", {}) or {}
    surface_counts = route.get("surface_counts") or {}
    surface_line = ", ".join(f"{k}: {v}" for k, v in surface_counts.items()) if surface_counts else "brak danych"
    loc = route.get("location")
    if isinstance(loc, dict):
        loc_txt = ", ".join(str(v) for v in (loc.get("miasto"), loc.get("gmina")) if v)
    else:
        loc_txt = loc or "—"

    context = (
        "Start był z obniżoną gotowością, więc wynik trzeba czytać ostrożnie: organizm dowiózł jazdę, ale nie była to baza pod kolejny mocny dzień."
        if h.get("readiness") != "zielona"
        else "Start był z dobrą gotowością, więc jazda jest wiarygodna jako bodziec treningowy."
    )
    if long_rides.get("current_is_long"):
        context += " To była długa jednostka, więc najważniejsze są stabilność drugiej połowy, paliwo i koszt narastający po kilku godzinach."
    else:
        context += " To była krótsza jednostka, więc ważniejsze są równość mocy i koszt tlenowy niż sam czas spędzony na siodle."

    avg_watts = _format_metric(coach.get("avg_watts"), " W")
    np_watts = _format_metric(coach.get("np_watts"), " W")
    vi = _format_metric(coach.get("vi"), "", 2)
    if_txt = _format_metric(coach.get("if"), "", 2)
    execution = f"NP było dużo wyżej niż średnia moc ({np_watts} vs {avg_watts}), czyli jazda kosztowała więcej niż sugeruje sama średnia. VI {vi} wskazuje na bardzo nierówne obciążenie: teren, postoje albo krótkie podjazdy podbijały koszt mimo spokojniejszej średniej. IF {if_txt} mieści jazdę w spokojniejszym zakresie, ale długość robi z niej istotne obciążenie."

    hr_avg = _format_metric(coach.get("avg_hr"), " bpm")
    decoupling = coach.get("decoupling")
    cadence = _format_metric(coach.get("cadence"), " rpm")
    physiology = f"Średnie HR {hr_avg} sugeruje kontrolowany koszt tlenowy, ale trzeba je zestawiać z długością i zmiennością mocy. {coach.get('decoupling_note') or 'Dryft HR pozostaje w granicach akceptacji.'} Kadencja {cadence} na {coach.get('bike_type') or 'rower'} wymaga oceny przez teren: sama liczba nie wystarcza bez nawierzchni i podjazdów."
    if split.get("available") and _safe_float(split.get("power_fade_pct")) is not None:
        physiology = (
            f"Średnie HR {hr_avg} sugeruje kontrolowany koszt tlenowy, ale trzeba je zestawiać z długością i zmiennością mocy. "
            f"Dryft HR między połowami był mały, więc limiterem bardziej wygląda spadek mocy/paliwa niż narastające tętno. "
            f"Power fade { _format_metric(split.get('power_fade_pct'), '%', 1)} mówi, że druga połowa siadła; na podobnej trasie trzeba zacząć spokojniej albo jeść wcześniej. "
            f"Kadencja {cadence} na {coach.get('bike_type') or 'rower'} wymaga oceny przez teren: sama liczba nie wystarcza bez nawierzchni i podjazdów."
        )

    route_text = f"Trasa była mieszana mimo największego udziału asfaltu: {surface_line}. To tłumaczy część zmienności mocy i niższą kadencję. Dużo pauz/rejestracji ({_stop_summary(route.get('recording_stops'))}) może zaniżać płynność jazdy i utrudniać porównanie do treningu ciągłego."
    if loc_txt and loc_txt != "—":
        route_text = f"Trasa przebiegała w okolicach {loc_txt}, na terenie podmiejskim z bardzo zróżnicowaną nawierzchnią. {route_text}"

    return [
        ("Kontekst", context),
        ("Wykonanie", execution),
        ("Fizjologia", physiology),
        ("Trasa", route_text),
    ]

def protocol_html(protocol):
    h = protocol["health"]
    route = protocol["route"]
    coach = protocol["coach"]
    lesson = protocol.get("lesson") or {}
    readiness_color = {"zielona": OK, "żółta": WARN, "czerwona": BAD}.get(h["readiness"], TXT)
    loc = route.get("location")
    if isinstance(loc, dict):
        loc_txt = ", ".join(str(v) for v in (loc.get("miasto"), loc.get("gmina")) if v)
    else:
        loc_txt = loc or "—"
    surf = route.get("surface") or {}
    surf_counts = route.get("surface_counts") or {}
    surf_txt = ", ".join(f"{k}: {v}" for k, v in surf_counts.items()) if surf_counts else "—"
    route_rows = [
        ("Status get_route_surface", "OK" if route.get("available") else "brak danych / błąd"),
        ("Lokalizacja", loc_txt),
        ("Nawierzchnia", surf_txt),
        ("Recording stops", _stop_summary(route.get("recording_stops"))),
        ("Reguła kadencji", route.get("cadence_rule") or "—"),
    ]
    cmp_rows = [
        [r.get("date"), r.get("name"), r.get("distance_km"), r.get("np"), r.get("avg_hr"), _format_metric(r.get("ef"), "", 2)]
        for r in protocol.get("comparison", [])
        if _has_any_metric(r, ("np", "avg_hr", "ef", "cadence"))
    ]
    long_rows = [
        [r.get("date"), r.get("distance_km"), r.get("hours"), r.get("np"), r.get("avg_hr")]
        for r in protocol.get("long_rides", {}).get("previous", [])
    ]
    split = protocol.get("long_rides", {}).get("split", {})
    if split.get("available"):
        split_html = (
            _kv_rows([
                ("Moc I połowa / II połowa", f'{_format_metric(split.get("power_first_half"), " W")} / {_format_metric(split.get("power_second_half"), " W")}'),
                ("Power fade", _format_metric(split.get("power_fade_pct"), "%", 1)),
                ("HR I połowa / II połowa", f'{_format_metric(split.get("hr_first_half"), " bpm")} / {_format_metric(split.get("hr_second_half"), " bpm")}'),
                ("Dryft HR", _format_metric(split.get("hr_drift_pct"), "%", 1)),
                ("Kadencja I połowa / II połowa", f'{_format_metric(split.get("cadence_first_half"), " rpm")} / {_format_metric(split.get("cadence_second_half"), " rpm")}'),
                ("Źródło", split.get("source", "—")),
            ])
        )
    else:
        split_html = txt_block(split.get("source") or "Brak splitów pierwsza/druga połowa.")

    long_section = ""
    if protocol.get("long_rides", {}).get("current_is_long"):
        long_section = (
            sep() +
            section("Protokół 6 — jazda długa",
                split_html +
                "<div style='height:12px'></div>" +
                _small_table(["Data", "km", "h", "NP", "HR śr."], long_rows) +
                txt_block(protocol["long_rides"].get("note") or "Jazda spełnia próg >3h lub >80 km.")
            )
        )

    return (
        '<svg width="640" height="80" viewBox="0 0 640 80" xmlns="http://www.w3.org/2000/svg" style="display:block;border-radius:12px;margin-bottom:18px;max-width:100%;"><defs><linearGradient id="hg" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#0d1e35"/><stop offset="100%" stop-color="#0f1117"/></linearGradient></defs><rect width="640" height="80" fill="url(#hg)"/><polygon points="260,6 400,72 120,72" fill="#1a3050" opacity="0.7"/><polygon points="390,14 510,72 270,72" fill="#122540" opacity="0.85"/><polygon points="490,18 590,72 390,72" fill="#0c1c30" opacity="0.9"/><path d="M0,74 Q160,62 320,67 Q480,72 640,60" stroke="#1e3a5f" stroke-width="3" fill="none"/><circle cx="70" cy="22" r="17" fill="#e8a840" opacity="0.9"/><circle cx="70" cy="22" r="23" fill="none" stroke="#e8a840" stroke-width="1" opacity="0.25"/><g transform="translate(582,42)" fill="none" stroke="#5dba7a" stroke-width="2" opacity="0.75"><circle cx="-20" cy="16" r="11"/><circle cx="20" cy="16" r="11"/><polyline points="-20,16 -10,4 4,4 20,16" /><polyline points="4,4 -5,16 -20,16"/><polyline points="4,4 4,-3 10,-3"/><circle cx="4" cy="-3" r="2" fill="#5dba7a" stroke="none"/></g><text x="320" y="42" text-anchor="middle" fill="#ffffff" font-family="Arial,sans-serif" font-size="13" letter-spacing="3" opacity="0.55">Q · RAPORT KOLARZA</text></svg>' +
        section("Podsumowanie", txt_block(
            f"{_format_metric(protocol.get('summary_distance_km'), ' km', 1) if protocol.get('summary_distance_km') is not None else '—'} / "
            f"{protocol.get('summary_duration') or '—'}; "
            f"moc śr./NP {protocol.get('summary_avg_power') or '—'} / {protocol.get('summary_np_power') or '—'}; "
            f"HR śr./max {protocol.get('summary_avg_hr') or '—'} / {protocol.get('summary_max_hr') or '—'}; "
            f"TSS/IF {protocol.get('summary_tss') or '—'} / {protocol.get('summary_if') or '—'}."
        )) +
        section("Protokół 1 — kontekst zdrowotny",
            card3([
                ("HRV vs norma", f'{_format_metric(h.get("hrv_today"), " ms")} / {_format_metric(h.get("hrv_norm"), " ms")}', readiness_color),
                ("HR spocz. / BB rano", f'{_format_metric(h.get("resting_hr"), " bpm")} / {_format_metric(h.get("body_battery"))}', TXT),
                ("Gotowość", h.get("readiness", "—"), readiness_color),
            ]) +
            txt_block(h.get("note", ""))
        ) +
        sep() +
        section("Analiza trenera",
            _kv_rows(_trainer_analysis(protocol))
        ) +
        sep() +
        section("Trasa i dane pomocnicze",
            _kv_rows(route_rows)
        ) +
        sep() +
        section("Moc, HR, kadencja",
            _kv_rows([
                ("Moc śr. / NP", f'{_format_metric(coach.get("avg_watts"), " W")} / {_format_metric(coach.get("np_watts"), " W")}'),
                ("IF / VI", f'{_format_metric(coach.get("if"), "", 2)} / {_format_metric(coach.get("vi"), "", 2)}'),
                ("HR śr. / max", f'{_format_metric(coach.get("avg_hr"), " bpm")} / {_format_metric(coach.get("max_hr"), " bpm")}'),
                ("EF / decoupling", f'{_format_metric(coach.get("ef"), "", 2)} / {coach.get("decoupling")}'),
                ("Kadencja / rower", f'{_format_metric(coach.get("cadence"), " rpm")} / {coach.get("bike_type") or "—"}'),
                ("Temperatura", _format_metric(coach.get("temperature"), "°C")),
            ]) +
            txt_block(coach.get("decoupling_note") or "")
        ) +
        sep() +
        section("Porównanie z podobnymi jazdami",
            _small_table(["Data", "Jazda", "km", "NP", "HR śr.", "EF"], cmp_rows)
        ) +
        sep() +
        section("Rekomendacja", txt_block(_concise_recommendation(protocol))) +
        sep() +
        section(
            "Lekcja na następną jazdę",
            _kv_rows([
                ("Temat", lesson.get("title") or "Jedna rzecz na następną jazdę"),
                ("Wniosek", lesson.get("text") or "Powtórz podobny trening z jednym kontrolowanym celem."),
            ])
        ) +
        long_section
    )

def generate_html(d, activity_name):
    act = d.get("aktywnosc", {})
    today_str = d.get("dzisiaj", date.today().isoformat())
    dt = date.fromisoformat(today_str)
    dni = ["Poniedziałek","Wtorek","Środa","Czwartek","Piątek","Sobota","Niedziela"]
    mce = ["","stycznia","lutego","marca","kwietnia","maja","czerwca",
           "lipca","sierpnia","września","października","listopada","grudnia"]
    dfmt = f"{dni[dt.weekday()]}, {dt.day} {mce[dt.month]} {dt.year}"

    czas_min = int((_safe_float(act.get("moving_time"), 0) or 0) // 60)
    dystans = round((_safe_float(act.get("distance"), 0) or 0) / 1000, 1)
    avg_watts = act.get("icu_average_watts") or act.get("avg_power")
    np_watts = act.get("icu_weighted_avg_watts") or act.get("norm_power")
    hr_avg = act.get("average_heartrate") or act.get("avg_hr")
    hr_max = act.get("max_heartrate")
    tss = act.get("icu_training_load") or act.get("tss")
    act_if = round((_safe_float(act.get("icu_intensity"), 0) or 0) / 100, 2) if act.get("icu_intensity") else act.get("if")
    czas_s = f"{czas_min // 60}h {czas_min % 60}min" if czas_min >= 60 else f"{czas_min} min"

    summary = (
        f"{_format_metric(dystans, ' km', 1)} / {czas_s}; "
        f"moc śr./NP {_format_metric(avg_watts, ' W')} / {_format_metric(np_watts, ' W')}; "
        f"HR śr./max {_format_metric(hr_avg, ' bpm')} / {_format_metric(hr_max, ' bpm')}; "
        f"TSS/IF {_format_metric(tss)} / {_format_metric(act_if, '', 2)}."
    )

    d["protokol_oceny"] = build_ride_protocol(d)
    d["protokol_oceny"]["lesson"] = build_ride_lesson(d["protokol_oceny"], d)
    d["protokol_oceny"]["summary_distance_km"] = dystans
    d["protokol_oceny"]["summary_duration"] = czas_s
    d["protokol_oceny"]["summary_avg_power"] = _format_metric(avg_watts, " W")
    d["protokol_oceny"]["summary_np_power"] = _format_metric(np_watts, " W")
    d["protokol_oceny"]["summary_avg_hr"] = _format_metric(hr_avg, " bpm")
    d["protokol_oceny"]["summary_max_hr"] = _format_metric(hr_max, " bpm")
    d["protokol_oceny"]["summary_tss"] = _format_metric(tss)
    d["protokol_oceny"]["summary_if"] = _format_metric(act_if, "", 2)

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<style type="text/css">
  body, html {{ background-color:{BG} !important; margin:0; padding:0; }}
</style>
</head>
<body bgcolor="{BG}" style="background-color:{BG} !important; margin:0; padding:0;">
<div style="background-color:{BG};margin:0;padding:0;">
<table width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background-color:{BG} !important;">
<tr><td bgcolor="{BG}" style="background-color:{BG} !important;">
<table width="640" cellpadding="28" cellspacing="0" bgcolor="{BG}" align="center"
       style="font-family:Arial,Helvetica,sans-serif;color:{TXT};font-size:17px;line-height:1.55;background-color:{BG};">
<tr><td bgcolor="{BG}" style="background-color:{BG} !important;">

  <div style="border-bottom:2px solid {BORDER};padding-bottom:16px;margin-bottom:22px;">
    <div style="font-size:12px;color:{TXT3};text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">{dfmt}</div>
    <div style="font-size:28px;font-weight:bold;color:{TXT};margin-bottom:4px;">Raport jazdy</div>
    <div style="font-size:16px;color:{TXT2};">{escape(activity_name)}</div>
  </div>

  <table width="100%" cellpadding="16" cellspacing="0" bgcolor="{BG_WARN}" style="border-radius:10px;border:1px solid {BORDER};"><tr><td style="font-size:21px;color:{WARN};line-height:1.8;text-align:justify;">{escape(_concise_recommendation(d["protokol_oceny"]))}</td></tr></table>
  <div style="height:14px"></div>
  {section("Podsumowanie", txt_block(summary))}
  {sep()}
  {protocol_html(d["protokol_oceny"])}

  <div style="margin-top:22px;font-size:12px;color:{TXT3};text-align:center;">Q · Raport jazdy · {dfmt}</div>

</td></tr>
</table>
</td></tr>
</table>
</div>
</body>
</html>
"""
    return html

# ── Sprawdzanie nowych aktywności (tryb cron) ─────────────────────────────────

def check_new_activities():
    """Sprawdź czy jest nowa aktywność z dzisiaj, której jeszcze nie raportowano"""
    today = date.today()

    acts = icu_get(f"/athlete/{ATHLETE_ID}/activities",
                   {"oldest": today.isoformat(), "newest": today.isoformat(), "limit": 10})

    new_acts = []
    for a in acts:
        # Tylko jazdy i treningi (nie aktywności bez danych)
        if a.get("type") not in ("Ride", "VirtualRide", "Run", "Swim", "TrailRun"):
            if a.get("moving_time", 0) < 600:  # krócej niż 10 min — pomijaj
                continue
        act_id = a.get("id")
        if not act_id or already_reported(act_id):
            continue
        new_acts.append(a)

    return new_acts

# ── Main ──────────────────────────────────────────────────────────────────────

def process_activity(activity_id, activity_name="Trening"):
    print(f"🚴 Generuję raport dla: {activity_name} ({activity_id})")
    channels = {"email": "pending", "telegram": "pending"}
    mark_report_status(activity_id, activity_name, "in_progress", channels=channels)
    try:
        data = fetch_activity_data(activity_id)
        html = generate_html(data, activity_name)
        RIDE_REPORT_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = str(activity_id).replace("/", "_")
        (RIDE_REPORT_PREVIEW_DIR / f"{safe_id}.html").write_text(html, encoding="utf-8")

        today_str = date.today().strftime("%d.%m.%Y")
        subject   = f"🚴 Raport jazdy — {activity_name} · {today_str}"

        print("📧 Wysyłam email...")
        send_email(subject, html)
        channels["email"] = "sent"
        mark_report_status(activity_id, activity_name, "in_progress", channels=channels)

        print("📱 Wysyłam Telegram...")
        tg_msg = (f"🚴 *Raport jazdy gotowy*\n"
                  f"_{activity_name}_ · {today_str}\n"
                  f"Sprawdź email po pełną analizę.")
        send_telegram(tg_msg)
        channels["telegram"] = "sent"

        mark_report_status(activity_id, activity_name, "sent", channels=channels)
        print(f"✅ Raport wysłany!")
    except Exception as exc:
        if channels.get("email") != "sent":
            channels["email"] = "failed"
        elif channels.get("telegram") != "sent":
            channels["telegram"] = "failed"
        mark_report_status(activity_id, activity_name, "failed", error=exc, channels=channels)
        print(f"❌ Raport nie wysłany: {exc}")
        raise

def render_activity_preview(activity_id, activity_name="Trening"):
    print(f"🧪 Generuję podgląd raportu dla: {activity_name} ({activity_id})")
    data = fetch_activity_data(activity_id)
    html = generate_html(data, activity_name)
    RIDE_REPORT_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = str(activity_id).replace("/", "_")
    out = RIDE_REPORT_PREVIEW_DIR / f"{safe_id}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ Podgląd zapisany: {out}")
    return out

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--html":
        act_id = sys.argv[2]
        act_name = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "Trening"
        render_activity_preview(act_id, act_name)
    elif len(sys.argv) > 1:
        # Ręczne uruchomienie z ID aktywności
        act_id   = sys.argv[1]
        act_name = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Trening"
        process_activity(act_id, act_name)
    else:
        # Tryb cron — sprawdź nowe aktywności
        print("🔍 Sprawdzam nowe aktywności...")
        new_acts = check_new_activities()
        if not new_acts:
            print("ℹ️  Brak nowych aktywności.")
        else:
            for act in new_acts:
                process_activity(act["id"], act.get("name","Trening"))
