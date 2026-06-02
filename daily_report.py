#!/usr/bin/env python3
"""Codzienny raport poranny Q → Telegram i email (retry 6:00-9:00).

PARTIAL mode: never blocks on missing non-critical data after 9:00.
Uses daily_report_adapter.py instead of legacy MCP tool calls.
"""

import json, httpx
from datetime import date, datetime, timedelta
from pathlib import Path
import smtplib, sys
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
sys.path.insert(0, '/opt/qbot/app')
import db
import email_template as _et
import qbot_config as cfg
from qbot_readiness import evaluate_readiness
from qbot_coach import build_daily_coach
from qbot_cache import cached_call
from qbot_report_status import mark_single_report, single_report_complete, single_report_state_for_date
from qbot_report_validator import validate_daily_report_data, validate_daily_from_provider, DATA_OK, DATA_PARTIAL, DATA_MISSING
from qbot_report_data_provider import ReportDataProvider
from qgpt_client import qgpt_text
import daily_report_adapter as _adapter

ATHLETE_ID    = cfg.INTERVALS_ATHLETE_ID
API_KEY       = cfg.INTERVALS_API_KEY
TOKEN         = cfg.TELEGRAM_TOKEN
CHAT_ID            = cfg.TELEGRAM_CHAT_ID
GMAIL_USER         = cfg.GMAIL_USER
GMAIL_PASS         = cfg.GMAIL_APP_PASSWORD
EMAIL_TO           = cfg.EMAIL_TO
WEIGHT_ANCHOR_DATE = "2026-05-05"
WEIGHT_ANCHOR_KG   = 103.627
WEIGHT_LOOKBACK_DAYS = 180
LOC_LAT = cfg.LOCATION_LAT
LOC_LON = cfg.LOCATION_LON

HDR  = cfg.intervals_headers()

SENT_FILE = Path("/opt/qbot/app/data/daily_report_sent.json")
EXTERNAL_CACHE_FILE = Path("/opt/qbot/app/data/daily_external_cache.json")
SENT_FILE.parent.mkdir(exist_ok=True)

today     = date.today()
yesterday = today - timedelta(days=1)
week_ago  = today - timedelta(days=7)

# Pipeline tracking
_PIPELINE_STAGE = "init"
_DATA_SOURCES: dict[str, str] = {}
_LAST_ERROR: str | None = None

def _save_state():
    """Write current pipeline state to SENT_FILE."""
    state = sent_state_today() or {}
    state["date"] = today.isoformat()
    state["pipeline_stage"] = _PIPELINE_STAGE
    state["last_attempt_at"] = datetime.now().isoformat()
    state["data_sources"] = dict(_DATA_SOURCES)
    if _LAST_ERROR:
        state["last_error"] = _LAST_ERROR[:500]
    channels = state.get("channels") or {}
    for ch in ("telegram", "email"):
        if ch not in channels:
            channels[ch] = "not_attempted"
    state["channels"] = channels
    mark_single_report(SENT_FILE, today.isoformat(), state.get("channels"))
    # Write full state
    import json as _json
    try:
        SENT_FILE.write_text(_json.dumps(state, ensure_ascii=False, indent=2, default=str))
    except Exception:
        pass

def sent_state_today():
    return single_report_state_for_date(SENT_FILE, today.isoformat())

def already_sent_today():
    return single_report_complete(SENT_FILE, today.isoformat())

def mark_sent(channels=None):
    mark_single_report(SENT_FILE, today.isoformat(), channels)

def icu_get(endpoint, params=None):
    r = httpx.get(f"https://intervals.icu/api/v1{endpoint}",
                  headers=HDR, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def send_telegram(msg):
    if not msg or not msg.strip():
        raise RuntimeError("Telegram: pusta treść raportu")
    # Telegram ma limit 4096 znaków
    for i in range(0, len(msg), 4000):
        r = httpx.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg[i:i+4000],
                  "parse_mode": "Markdown"},
            timeout=10
        )
        r.raise_for_status()



# ═══════════════════════════════════════════════════════ NOWE FUNKCJE v2 ══════

def send_email(subject, html, inline_image_path=None, inline_image_cid=None):
    if inline_image_path and inline_image_cid:
        msg = MIMEMultipart('related')
        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(html, 'html', 'utf-8'))
        msg.attach(alt)
        image_bytes = Path(inline_image_path).read_bytes()
        image = MIMEImage(image_bytes)
        image.add_header('Content-ID', f'<{inline_image_cid}>')
        image.add_header('Content-Disposition', 'inline', filename=Path(inline_image_path).name)
        msg.attach(image)
    else:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(html, 'html', 'utf-8'))
    msg['Subject'] = subject
    msg['From']    = GMAIL_USER
    msg['To']      = EMAIL_TO
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
        s.login(GMAIL_USER, GMAIL_PASS)
        s.send_message(msg)

def mcp_call(tool, args=None):
    """Internal adapter — maps legacy tool names to direct calls."""
    global _PIPELINE_STAGE, _DATA_SOURCES, _LAST_ERROR
    _PIPELINE_STAGE = f"fetch:{tool}"
    try:
        if tool == "get_events":
            result = _adapter.get_events(args.get("oldest"), args.get("newest"))
            _DATA_SOURCES[tool] = "ok" if result else "empty"
            return result
        if tool == "get_weather":
            result = _adapter.get_weather(days=args.get("days", 2), location=args.get("location", cfg.LOCATION_NAME))
            _DATA_SOURCES[tool] = "ok" if result and not result.get("error") else "error"
            return result
        if tool == "get_xert_status":
            result = _adapter.get_xert_status()
            _DATA_SOURCES[tool] = "ok" if result and not result.get("error") else "error"
            return result
        if tool == "get_xert_activities":
            result = _adapter.get_xert_activities(limit=args.get("limit", 10))
            _DATA_SOURCES[tool] = "ok" if result else "empty"
            return result
        if tool == "get_garmin_wellness":
            result = _adapter.get_garmin_wellness(args.get("date"))
            _DATA_SOURCES[tool] = "ok" if result else "empty"
            return result
        _DATA_SOURCES[tool] = "unknown"
        print(f"  ⚠️  Unknown legacy tool: {tool}")
        return None
    except Exception as exc:
        _LAST_ERROR = str(exc)[:300]
        _DATA_SOURCES[tool] = f"error: {_LAST_ERROR[:60]}"
        print(f"  ⚠️  mcp_call({tool}): {exc}")
        return None

def parse_kcal(comments):
    if not comments:
        return None, None
    eaten = burned = None
    for line in comments.split('\n'):
        if 'Zjedzone:' in line:
            try: eaten = float(line.split('Zjedzone:')[1].split('kcal')[0].strip())
            except: pass
        if 'Spalone:' in line:
            try: burned = float(line.split('Spalone:')[1].split('kcal')[0].strip())
            except: pass
    return eaten, burned

def tp_z_aktywnosci(acts):
    cutoff = (date.today() - timedelta(days=5)).isoformat()
    for a in (acts or []):
        if a.get("threshold_power") and a.get("date", "") <= cutoff:
            return a["threshold_power"]
    return None

def latest_weight_record(records, skip_date=None):
    for rec in sorted(records or [], key=lambda x: x.get("id", ""), reverse=True):
        if skip_date and rec.get("id") == skip_date:
            continue
        if rec.get("weight") is not None:
            return rec
    return {}

# ════════════════════════════════════════════════════════════════════════════
if already_sent_today():
    print("✅ Raport dziś już wysłany — pomijam.")
    sys.exit(0)

print("📊 Pobieram dane...")

# Wellness ostatnie 7 dni
wellness = icu_get(f"/athlete/{ATHLETE_ID}/wellness",
                   {"oldest": week_ago.isoformat(), "newest": today.isoformat()})

# Ostatnie aktywności (7 dni)
activities = icu_get(f"/athlete/{ATHLETE_ID}/activities",
                     {"oldest": week_ago.isoformat(), "newest": today.isoformat(), "limit": 10})

# Kalendarz na dziś i kolejne dni do korekty planu
future_events = mcp_call(
    "get_events",
    {"oldest": today.isoformat(), "newest": (today + timedelta(days=4)).isoformat()},
) or []
if isinstance(future_events, dict) and future_events.get("error"):
    print(f"⚠️  Kalendarz niedostępny: {future_events['error']}")
    future_events = []

# Profil zawodnika
profile = icu_get(f"/athlete/{ATHLETE_ID}")

# Pogoda — projektowo wyłącznie przez MCP get_weather.
weather_condition = None
def _num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace("°C", "").replace("m/s", "").replace("km/h", "").replace("%", "").strip())
    except:
        return None

try:
    _weather_mcp = cached_call(
        EXTERNAL_CACHE_FILE,
        f"weather:{cfg.LOCATION_NAME}:2d",
        lambda: mcp_call("get_weather", {"days": 2, "location": cfg.LOCATION_NAME}),
    ) or {}
    if _weather_mcp.get("cache_hit"):
        print(f"⚠️  Pogoda z cache: {_weather_mcp.get('cache_reason')}")
    if _weather_mcp.get("error"):
        raise RuntimeError(_weather_mcp["error"])

    _hourly = _weather_mcp.get("hourly_forecast", [])
    _daily = _weather_mcp.get("prognoza", [])
    _d0 = _daily[0] if _daily else {}
    weather_condition = _d0.get("warunki") or (_weather_mcp.get("teraz") or {}).get("warunki")
    _wind_ms = _num(_d0.get("max_wiatr_ms"))
    weather_r = {
        "hourly": {
            "time": [h.get("czas") for h in _hourly],
            "precipitation_probability": [_num(h.get("szansa_deszczu")) or 0 for h in _hourly],
            "temperature_2m": [_num(h.get("temperatura")) for h in _hourly],
            # downstream code expects km/h and converts to m/s for display
            "windspeed_10m": [(_num(h.get("wiatr_ms")) or 0) * 3.6 for h in _hourly],
            "cloudcover": [_num(h.get("zachmurzenie")) or 0 for h in _hourly],
            "weathercode": [None for _ in _hourly],
        },
        "daily": {
            "weathercode": [None],
            "temperature_2m_max": [_num(_d0.get("temp_max")) or 0],
            "temperature_2m_min": [_num(_d0.get("temp_min")) or 0],
            "precipitation_probability_max": [_num(_d0.get("szansa_deszcz")) or 0],
            "windspeed_10m_max": [(_wind_ms or 0) * 3.6],
            "winddirection_10m_dominant": [0],
            "sunset": [""],
            "cloudcover_mean": [_num(_d0.get("zachmurzenie")) or 0],
        },
    }
except Exception as _we:
    print(f"⚠️  Pogoda MCP niedostępna: {_we}")
    weather_r = {}
# Okno bez deszczu — znajdź godziny gdy prob >= 50%
_h = weather_r.get("hourly", {})
_rain_h = [int(t.split("T")[1][:2])
           for t, p in zip(_h.get("time", []), _h.get("precipitation_probability", []))
           if t.startswith(today.isoformat()) and p >= 50]

# Godzinowy wykres pogody (co 3h, od 6:00)
_hzip = zip(
    _h.get("time", []), _h.get("temperature_2m", []),
    _h.get("windspeed_10m", []), _h.get("cloudcover", []),
    _h.get("weathercode", []), _h.get("precipitation_probability", []),
)
pogoda_godzinowa = []
for _ht, _htemp, _hwind, _hcloud, _hcode, _hprec in _hzip:
    if not _ht.startswith(today.isoformat()):
        continue
    _hh = int(_ht.split("T")[1][:2])
    if _hh % 3 != 0 or _hh < 6:
        continue
    pogoda_godzinowa.append({
        "godzina":      f"{_hh:02d}:00",
        "temp":         round(float(_htemp), 1) if _htemp is not None else None,
        "wiatr_ms":     round(float(_hwind) / 3.6, 1) if _hwind is not None else None,
        "zachmurzenie": int(_hcloud) if _hcloud is not None else None,
        "kod":          int(_hcode)  if _hcode  is not None else 0,
        "deszcz_prob":  int(_hprec)  if _hprec  is not None else 0,
    })
if _rain_h:
    dry_window  = f"sucho do {min(_rain_h):02d}:00"
    rain_window = f"deszcz ok. {min(_rain_h):02d}:00–{max(_rain_h)+1:02d}:00"
else:
    dry_window  = "sucho cały dzień"
    rain_window = None

w = weather_r.get("daily", {})
WMO = {0:"☀️ Czyste niebo",1:"🌤️ Bezchmurnie",2:"⛅ Częściowe zachmurzenie",
       3:"☁️ Pochmurno",45:"🌫️ Mgła",48:"🌫️ Mgła z szronem",
       51:"🌦️ Mżawka",53:"🌦️ Mżawka",55:"🌦️ Gęsta mżawka",
       56:"🌧️ Marznąca mżawka",57:"🌧️ Marznąca mżawka",
       61:"🌧️ Deszcz",63:"🌧️ Deszcz",65:"🌧️ Silny deszcz",
       66:"🌧️ Marznący deszcz",67:"🌧️ Marznący deszcz",
       71:"❄️ Śnieg",73:"❄️ Śnieg",75:"❄️ Silny śnieg",77:"❄️ Ziarnisty śnieg",
       80:"🌦️ Przelotne opady",81:"🌧️ Przelotne opady",82:"⛈️ Gwałtowne opady",
       85:"🌨️ Przelotny śnieg",86:"🌨️ Silny przelotny śnieg",
       95:"⛈️ Burza",96:"⛈️ Burza z gradem",99:"⛈️ Burza z gradem"}
pogoda_dziś = {
    "warunki":  weather_condition or WMO.get(w.get("weathercode", [0])[0], "?"),
    "temp_max": f"{w.get('temperature_2m_max',[0])[0]}°C",
    "temp_min": f"{w.get('temperature_2m_min',[0])[0]}°C",
    "deszcz":   f"{w.get('precipitation_probability_max',[0])[0]}%",
    "wiatr":    f"{w.get('windspeed_10m_max',[0])[0]} km/h",
}

# ═══════════════════════════════════════════════════════════ DANE v2 ══════════

wellness_map = {w["id"]: w for w in wellness}
w_today      = wellness_map.get(today.isoformat(), {})
w_yesterday  = wellness_map.get(yesterday.isoformat(), {})
w_week_ago   = wellness_map.get(week_ago.isoformat(), {})

# Bilans kaloryczny
_e, _b       = parse_kcal(w_yesterday.get("comments"))
balance_yest = round(_e - _b) if _e and _b else None
_bals        = [_e2 - _b2 for w in wellness
                for _e2, _b2 in [parse_kcal(w.get("comments"))]
                if _e2 and _b2]
balance_7d   = round(sum(_bals) / len(_bals)) if _bals else None

# Waga
weight_today_raw = w_today.get("weight")
weight_records = wellness
if weight_today_raw is None:
    try:
        weight_records = icu_get(
            f"/athlete/{ATHLETE_ID}/wellness",
            {"oldest": (today - timedelta(days=WEIGHT_LOOKBACK_DAYS)).isoformat(), "newest": today.isoformat()},
        )
    except Exception as e:
        print(f"⚠️  Nie udało się pobrać historii wagi: {e}")

weight_latest = latest_weight_record(weight_records, skip_date=today.isoformat()) if weight_today_raw is None else {}
weight_report = weight_today_raw if weight_today_raw is not None else weight_latest.get("weight")
weight_report_date = today.isoformat() if weight_today_raw is not None else weight_latest.get("id")
weight_week_ago = w_week_ago.get("weight")

# HRV trend
hrv_trend = [w.get("hrv") for w in sorted(wellness, key=lambda x: x["id"]) if w.get("hrv")]

# Xert
xert = cached_call(EXTERNAL_CACHE_FILE, "xert_status", lambda: mcp_call("get_xert_status")) or {}
if isinstance(xert, dict) and xert.get("cache_hit"):
    print(f"⚠️  Xert status z cache: {xert.get('cache_reason')}")
if isinstance(xert, dict) and xert.get("error"):
    print(f"⚠️  Xert status niedostępny: {xert['error']}")
    xert = {}

xert_acts = cached_call(
    EXTERNAL_CACHE_FILE,
    "xert_activities:10",
    lambda: mcp_call("get_xert_activities", {"limit": 10}),
) or []
if isinstance(xert_acts, dict) and xert_acts.get("error"):
    print(f"⚠️  Xert activities niedostępne: {xert_acts['error']}")
    xert_acts = []
tp_hist   = tp_z_aktywnosci(xert_acts)

# Snapshot Xert sprzed 7 dni
try:
    _snaps  = (db.search_garage("xert_snapshot") or {}).get("memories", [])
    tp_prev = next(
        (__import__("json").loads(m["content"]).get("tp")
         for m in _snaps if week_ago.isoformat() in m.get("content", "")),
        None
    ) or tp_hist
except:
    tp_prev = tp_hist

# Garmin
garmin = mcp_call("get_garmin_wellness", {"date": today.isoformat()}) or {}
_garmin_sleep = garmin.get("sen") or {}
_intervals_sleep_secs = w_today.get("sleepSecs")
_intervals_sleep_h = round(_intervals_sleep_secs / 3600, 1) if _intervals_sleep_secs is not None else None
_now_hour = datetime.now().hour

# Guard: dane snu — PARTIAL mode po 9:00
# Garmin jest źródłem priorytetowym po przebudzeniu; Intervals jest fallbackiem.
_sleep_ok = _garmin_sleep.get("czas_h") is not None or (_now_hour >= 7 and _intervals_sleep_h is not None)
_PIPELINE_STAGE = "sleep_check"
_DATA_SOURCES["sleep"] = "ok" if _sleep_ok else "missing"
_LAST_ERROR = None  # sleep delay is not an error
if not _sleep_ok:
    if _now_hour < 7:
        print(f"⏳ Brak danych snu, czekam (teraz {_now_hour}:xx, deadline 9:00 CEST (7:00 UTC)).")
        _PIPELINE_STAGE = "waiting_for_sleep_data"
        _save_state()
        sys.exit(0)
    else:
        print("⚠️  Brak danych snu po 9:00 — wysyłam raport PARTIAL bez danych ze snu.")
        _PIPELINE_STAGE = "partial_missing_sleep"

# Nadchodzące wyjazdy
try:
    upcoming = sorted(
        [{"name": t.get("name"), "start_date": t.get("start_date"),
          "distance_km": t.get("distance_km"), "elevation_m": t.get("elevation_m"),
          "days_to": (date.fromisoformat(t["start_date"]) - today).days}
         for t in (db.get_trips(status="planned") or [])
         if t.get("start_date") and t["start_date"] >= today.isoformat()],
        key=lambda x: x["start_date"]
    )[:2]
except Exception as _ex:
    upcoming = []
    print(f"⚠️  Trips: {_ex}")

# Historia bilansu kalorycznego (7 dni) do wykresu
bilans_historia_7d = []
for _bw in sorted(wellness, key=lambda x: x["id"]):
    _be, _bb = parse_kcal(_bw.get("comments", ""))
    if _be and _bb:
        bilans_historia_7d.append({
            "data":     _bw["id"],
            "przyjete": round(_be),
            "bilans":   round(_be - _bb),
        })

# Pre-computed HRV fact — single source of truth for all AI calls
_hrv_val  = w_today.get("hrv")
_hrv_norm = (garmin.get("hrv") or {}).get("srednia_tygodnia")
if _hrv_val and _hrv_norm:
    _hrv_rel     = "POWYŻEJ" if _hrv_val >= _hrv_norm else "PONIŻEJ"
    _hrv_fakt_str = f"HRV {_hrv_val} ms jest {_hrv_rel} normy tygodniowej {_hrv_norm} ms"
else:
    _hrv_fakt_str = None

# ════════════════════════════════════════════════════════════════════════════
# Save pipeline state after data fetch
_PIPELINE_STAGE = "data_fetched"
_save_state()

# Debug przed generowaniem
print(f"🔍 Xert TP: {xert.get('tp_ftp_watts')} | Garmin BB: {(garmin or {}).get('body_battery',{}).get('max_rano')} | HRV fakt: {_hrv_fakt_str}")
print("🤖 Generuję raporty (Telegram + Email)...")

_data = {
    "dzisiaj": today.isoformat(),
    "pogoda": {
        "warunki": weather_condition or WMO.get(weather_r.get("daily", {}).get("weathercode", [0])[0], ""),
        "temp_max": f"{weather_r.get('daily', {}).get('temperature_2m_max', [0])[0]}\u00b0C",
        "wiatr_max": f"{weather_r.get('daily', {}).get('windspeed_10m_max', [0])[0]} km/h",
        "wiatr_ms": f"{round(weather_r.get('daily',{}).get('windspeed_10m_max',[0])[0] / 3.6, 1)} m/s",
        "zachod_slonca": ((weather_r.get("daily",{}).get("sunset",[""])[0] or "").split("T")[-1][:5] or "—"),
        "zachmurzenie_proc": weather_r.get("daily",{}).get("cloudcover_mean",[0])[0],
        "kierunek_wiatru": {0:'N',45:'NE',90:'E',135:'SE',180:'S',225:'SW',270:'W',315:'NW'}.get(
            round(weather_r.get('daily',{}).get('winddirection_10m_dominant',[0])[0] / 45) * 45 % 360, ""),
        "sucho_do": dry_window,
        "deszcz_okno": rain_window,
        "godzinowa": pogoda_godzinowa,
    },
    "sen": {
        "czas_h": round(
            (
                _garmin_sleep.get("czas_h")
                if _garmin_sleep.get("czas_h") is not None
                else (_intervals_sleep_h or 0)
            ),
            1,
        ),
        "score": (
            _garmin_sleep.get("score")
            if _garmin_sleep.get("score") is not None
            else w_today.get("sleepScore")
        ),
        "ocena": _garmin_sleep.get("ocena") if _garmin_sleep.get("ocena") is not None else None,
        "gleboki_min": _garmin_sleep.get("gleboki_min") if _garmin_sleep.get("gleboki_min") is not None else None,
        "rem_min": _garmin_sleep.get("rem_min") if _garmin_sleep.get("rem_min") is not None else None,
    },
    "regeneracja": {
        "hrv": w_today.get("hrv"),
        "hrv_norma": (garmin.get("hrv") or {}).get("srednia_tygodnia"),
        "hrv_status": (garmin.get("hrv") or {}).get("status"),
        "hrv_trend_7d": hrv_trend,
        "tetno_spoczynkowe": w_today.get("restingHR") or garmin.get("tetno_spoczynkowe"),
        "body_battery_rano": (garmin.get("body_battery") or {}).get("max_rano"),
        "body_battery_min":  (garmin.get("body_battery") or {}).get("min_wieczor"),
        "hrv_fakt": _hrv_fakt_str,
    },
    "forma": {
        "tp_teraz_w": xert.get("tp_ftp_watts"),
        "tp_7dni_temu_w": tp_prev,
        "obciazenie_dlugoterminowe": round(w_today.get("ctl", 0), 1),
        "obciazenie_dlugoterminowe_7d": round(w_week_ago.get("ctl", 0), 1),
        "swiezosc": (xert.get("forma") or {}).get("form_score"),
        "status": (xert.get("forma") or {}).get("status"),
        "zalecany_typ": (xert.get("trening_dzi\u015b") or {}).get("zalecany_typ"),
        "zalecany_focus_w": None,
    },
    "kontekst_ostatnie_7dni": [
        {"data": w.get("id"), "komentarz": w.get("comments","")}
        for w in sorted(wellness, key=lambda x: x["id"])
        if w.get("comments")
    ],
    "bilans": {
        "wczoraj_kcal": balance_yest,
        "srednia_7d_kcal": balance_7d,
        "waga_dzis_kg": weight_report,
        "waga_dzis_date": weight_report_date,
        "waga_dzis_fallback": weight_today_raw is None and weight_report is not None,
        "waga_tydzien_temu_kg": weight_week_ago,
        "waga_tydzien_temu_date": week_ago.isoformat(),
        "waga_anchor_date": WEIGHT_ANCHOR_DATE,
        "waga_anchor_kg": WEIGHT_ANCHOR_KG,
        "historia_7d": bilans_historia_7d,
    },
    "wyjazdy": upcoming,
    "brak_danych_snu": not _sleep_ok,
    "braki_danych": [src for src, st in _DATA_SOURCES.items() if st not in ("ok",)],
    "pipeline_stage": _PIPELINE_STAGE,
}
# ── Provider-based data validation gate ─────────────────────────────────
_provider = ReportDataProvider()
_provider_data = _provider.get_daily_report_data(today)
_provider_val_status, _provider_val_details = validate_daily_from_provider(_provider_data)

# Use provider data to complement/enrich the report data dict
_pd = _provider_data
if _pd.get("sleep", {}).get("status") not in ("missing",):
    _s = _pd["sleep"]
    _data["sen"] = {
        "czas_h": _s.get("czas_h"),
        "score": _s.get("score"),
        "ocena": None,
        "gleboki_min": _s.get("data", {}).get("deep_min"),
        "rem_min": _s.get("data", {}).get("rem_min"),
    }
    _data["regeneracja"]["hrv"] = _s.get("hrv_ms") or _data["regeneracja"].get("hrv")
    _data["regeneracja"]["tetno_spoczynkowe"] = _s.get("resting_hr_bpm") or _data["regeneracja"].get("tetno_spoczynkowe")
    _data["brak_danych_snu"] = False

if _pd.get("wellness", {}).get("status") not in ("missing",):
    _w = _pd["wellness"]
    if _w.get("hrv_ms") is not None:
        _data["regeneracja"]["hrv"] = _w["hrv_ms"]
    if _w.get("resting_hr_bpm") is not None:
        _data["regeneracja"]["tetno_spoczynkowe"] = _w["resting_hr_bpm"]
    if _w.get("body_battery_start") is not None:
        _data["regeneracja"]["body_battery_rano"] = _w["body_battery_start"]
    if _w.get("body_battery_end") is not None:
        _data["regeneracja"]["body_battery_min"] = _w["body_battery_end"]
    if _w.get("weight_kg") is not None:
        _data["bilans"]["waga_dzis_kg"] = _w["weight_kg"]

if _pd.get("energy", {}).get("status") not in ("missing",):
    _e = _pd["energy"]
    if _e.get("total_kcal") is not None and _data.get("bilans", {}).get("wczoraj_kcal") is None:
        _data["bilans"]["wczoraj_kcal"] = round(_e["total_kcal"])

if _pd.get("nutrition", {}).get("status") not in ("missing",):
    _n = _pd["nutrition"]

if _pd.get("body_composition", {}).get("status") not in ("missing",):
    _bc = _pd["body_composition"]
    if _bc.get("weight_kg") is not None and _data.get("bilans", {}).get("waga_dzis_kg") is None:
        _data["bilans"]["waga_dzis_kg"] = _bc["weight_kg"]

if _pd.get("activity_summary", {}).get("status") not in ("missing",):
    _act = _pd["activity_summary"]
    if not activities and _act.get("activities"):
        activities = _act["activities"]
        _data["kontekst_ostatnie_7dni"] = [
            {"data": str(a.get("date", "")), "komentarz": ""}
            for a in _act["activities"]
        ]

# Add validation metadata to _data
_data["sources_freshness"] = _provider.get_source_freshness(today)
_data["provider_validation"] = _provider_val_status

_data["coach"] = build_daily_coach(_data, future_events=future_events)
_SYS = (
    "Jeste\u015b Q \u2014 osobistym asystentem kolarskim. Zawsze po polsku. "
    "Styl: konkretny, motywuj\u0105cy, jak dobry trener. "
    "ZAKAZ: skr\u00f3t\u00f3w CTL/ATL/TSB \u2014 u\u017cywaj: obci\u0105\u017cenie d\u0142ugoterminowe / "
    "obci\u0105\u017cenie kr\u00f3tkoterminowe / \u015bwie\u017co\u015b\u0107. "
    "ZAKAZ: wspominania eventu z Xert. "
    "Nie powtarzaj liczb tam gdzie wystarczy ocena s\u0142owna."
)

def _ai(prompt, max_t=600):
    try:
        text = qgpt_text(prompt, system=_SYS, max_tokens=max(max_t, 600))
        if text and text.strip():
            return text.strip()
    except Exception as e:
        print(f"⚠️  LLM: {e}")
    return _fallback_ai(prompt)

def _fmt(v, suffix=""):
    return f"{v}{suffix}" if v is not None else "—"

def _date_dmy(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m")
    except Exception:
        return str(value)

def _weight_report_text(b):
    weight = _fmt(b.get("waga_dzis_kg"), " kg")
    if b.get("waga_dzis_fallback") and b.get("waga_dzis_date"):
        return f"{weight} (ostatnie ważenie z {_date_dmy(b.get('waga_dzis_date'))})"
    return weight

def _sleep_label():
    if _data["brak_danych_snu"]:
        return "brak danych ze snu"
    h = _data["sen"].get("czas_h")
    score = _data["sen"].get("score")
    if h and h >= 7 and (score is None or score >= 70):
        return "sen wygląda solidnie"
    if h and h >= 6:
        return "sen jest akceptowalny, ale bez dużego zapasu"
    return "sen wygląda słabo"

def _readiness():
    readiness = evaluate_readiness(
        hrv=_data["regeneracja"].get("hrv"),
        hrv_norm=_data["regeneracja"].get("hrv_norma"),
        body_battery=_data["regeneracja"].get("body_battery_rano"),
        sleep_hours=None if _data["brak_danych_snu"] else _data["sen"].get("czas_h"),
        form=_data["forma"].get("swiezosc"),
        illness_context=bool(_data["regeneracja"].get("choroba") or _data["regeneracja"].get("injury")),
        resting_hr=_data["regeneracja"].get("tetno_spoczynkowe"),
    )
    return readiness.verdict, readiness.short

def _fallback_telegram():
    verdict, short = _readiness()
    p = _data["pogoda"]
    s = _data["sen"]
    r = _data["regeneracja"]
    f = _data["forma"]
    b = _data["bilans"]
    coach = _data.get("coach", {})
    decision = coach.get("decision", {})
    alerts = coach.get("risk_alerts", [])
    rain = p.get("deszcz_okno") or p.get("sucho_do") or "brak danych o opadach"
    hrv = _fmt(r.get("hrv"), " ms")
    hrv_norm = _fmt(r.get("hrv_norma"), " ms")
    bb = _fmt(r.get("body_battery_rano"))
    weight = _weight_report_text(b)
    return (
        f"Q-raport {today.isoformat()}: {decision.get('action') or short}.\n"
        f"Czas: {decision.get('duration', '—')}, intensywność: {decision.get('intensity', '—')}.\n"
        f"{'Alert: ' + alerts[0] if alerts else 'Brak dużej czerwonej flagi w danych.'}\n\n"
        f"🌤️ POGODA\n{p.get('warunki') or 'brak pełnych danych'}, max {p.get('temp_max','—')}, "
        f"wiatr {p.get('wiatr_ms','—')} m/s. {rain}.\n\n"
        f"😴 SEN / ❤️ REGENERACJA\n{_sleep_label()}. "
        f"Sen: {_fmt(s.get('czas_h'), ' h')}, score {_fmt(s.get('score'))}. "
        f"HRV: {hrv} vs norma {hrv_norm}, Body Battery rano: {bb}.\n\n"
        f"📈 FORMA\nWerdykt: {verdict}. "
        f"Obciążenie długoterminowe: {_fmt(f.get('obciazenie_dlugoterminowe'))}, "
        f"świeżość: {_fmt(f.get('swiezosc'))}, TP: {_fmt(f.get('tp_teraz_w'), ' W')}.\n\n"
        f"🍽️ BILANS\nWczoraj: {_fmt(b.get('wczoraj_kcal'), ' kcal')} | "
        f"Śr. 7 dni: {_fmt(b.get('srednia_7d_kcal'), ' kcal')}. "
        f"Waga: {weight}.\n\n"
        f"🚴 DZIŚ: {decision.get('action') or short}. Jeśli dane snu są niepełne, trzymaj intensywność w ryzach."
    )

def _fallback_ai(prompt):
    pl = prompt.lower()
    verdict, short = _readiness()
    hrv_fact = _data["regeneracja"].get("hrv_fakt")
    sleep = _sleep_label()
    if "format plain text" in pl or "krótki poranny raport" in pl:
        return _fallback_telegram()
    if '"verdict"' in pl:
        return json.dumps({"verdict": verdict, "skrot": short}, ensure_ascii=False)
    if "rozdzielone tylko ###" in pl:
        rec = (
            f"Werdykt na dziś: {short}. {sleep.capitalize()}. "
            f"{hrv_fact + '. ' if hrv_fact else ''}"
            "Trzymaj jedną główną decyzję treningową i nie dokładaj intensywności, "
            "jeśli regeneracja albo sen są niepełne."
        )
        tip = "Najpierw domknij regenerację, potem dopiero dokładaj akcenty."
        return f"{rec}###{tip}"
    if "podsumowania dnia" in pl:
        return (
            f"Dziś punkt wyjścia to: {sleep}. "
            f"{hrv_fact + '. ' if hrv_fact else ''}"
            f"Pogoda: {_data['pogoda'].get('warunki') or 'brak pełnych danych'}, "
            f"temperatura maksymalna {_data['pogoda'].get('temp_max','—')}. "
            f"Bilans z wczoraj: {_fmt(_data['bilans'].get('wczoraj_kcal'), ' kcal')}."
        )
    if "liczby snu" in pl:
        return (
            f"{sleep.capitalize()}: {_fmt(_data['sen'].get('czas_h'), ' h')} "
            f"i score {_fmt(_data['sen'].get('score'))}. "
            "Dobierz trening tak, żeby nie maskować zmęczenia ambicją."
        )
    if "interpretacja hrv" in pl:
        return (
            f"{hrv_fact or 'HRV bez pełnej normy porównawczej.'} "
            f"Tętno spoczynkowe: {_fmt(_data['regeneracja'].get('tetno_spoczynkowe'))}. "
            "To jest sygnał do spokojnej, kontrolowanej decyzji treningowej."
        )
    if "formie" in pl:
        return (
            f"Obciążenie długoterminowe wynosi {_fmt(_data['forma'].get('obciazenie_dlugoterminowe'))}, "
            f"świeżość {_fmt(_data['forma'].get('swiezosc'))}. "
            "Forma wymaga dziś rozsądnej kontroli, nie dokładania pracy za wszelką cenę."
        )
    if "bilansie kalorycznym" in pl:
        return (
            f"Wczoraj bilans wyniósł {_fmt(_data['bilans'].get('wczoraj_kcal'), ' kcal')}, "
            f"średnia z 7 dni {_fmt(_data['bilans'].get('srednia_7d_kcal'), ' kcal')}. "
            f"Waga: {_weight_report_text(_data['bilans'])}."
        )
    if "sprawdź:" in pl:
        return "OK"
    return _fallback_telegram()

_tg = _fallback_telegram()

# ── Email: pe\u0142na wersja HTML ─────────────────────────────────────────────────
_banner_path = Path("/opt/qbot/app/outgoing/banners/tuscany_gravel_banner.png")
_banner_cid = "tuscany-gravel-banner"
_email_html = _et.render(_data, _ai, banner_cid=_banner_cid if _banner_path.exists() else None)

# ── Data validation ─────────────────────────────────────────────────────────
# Primary: provider-based validation (reads from local DB)
_validation_status = _provider_val_status
_validation_details = _provider_val_details

# Fallback: if provider says OK but we have incomplete runtime data, use runtime check
if _validation_status in (DATA_OK, DATA_PARTIAL):
    _runtime_sources = {
        "sleep_wellness": "ok" if _sleep_ok else ("empty" if _now_hour >= 7 else "missing"),
        "calories_expenditure": "ok" if balance_yest is not None else "empty",
        "nutrition": "ok" if _e is not None else "empty",
        "activity_summary": "ok" if activities else "empty",
        "garmin_sync": "ok" if garmin and not garmin.get("error") else "failed",
    }
    _runtime_status, _runtime_details = validate_daily_report_data(_runtime_sources, today)
    # If runtime sees DATA_MISSING but provider sees OK, trust runtime for alert
    if _runtime_status == DATA_MISSING:
        _validation_status = DATA_MISSING
        _validation_details = _runtime_details

if _validation_status == DATA_MISSING:
    _alert_msg = _validation_details.get("alert_message", "Raport nie zosta\u0142 wygenerowany \u2014 brak danych krytycznych.")
    print(f"\u26a0\ufe0f  {_alert_msg}")
    _PIPELINE_STAGE = "validation_failed_data_missing"
    _save_state()
    _tg_alert = (
        f"\u26a0\ufe0f *Raport dobowy nie zosta\u0142 wygenerowany*\n\n"
        f"{_alert_msg}\n\n"
        f"Sprawd\u017a: synchronizacj\u0119 Garmin, Intervals.icu, "
        f"oraz czy dane wellness/sleep s\u0105 dost\u0119pne w bazie."
    )
    try:
        if not already_sent_today():
            send_telegram(_tg_alert)
            print("\U0001f4f1 Alert techniczny wys\u0142any (Telegram)")
    except Exception as _tge:
        print(f"\u26a0\ufe0f  Alert Telegram: {_tge}")

    _email_alert_html = f"""<!DOCTYPE html><html lang="pl"><body style="background:#0f1117;color:#f0f2f8;font-family:Arial;padding:40px;">
<h2 style="color:#e05555;">\u26a0\ufe0f Raport dobowy nie zosta\u0142 wygenerowany</h2>
<p>{_alert_msg}</p>
<hr style="border-color:#2a2e3d;">
<p style="color:#7a8299;font-size:13px;">Sprawd\u017a \u017ar\u00f3d\u0142a danych i spr\u00f3buj ponownie.</p>
<pre style="color:#c8cdd8;font-size:12px;background:#1a1d27;padding:16px;border-radius:8px;">
BRAKUJ\u0104CE: {', '.join(_validation_details.get('missing', _validation_details.get('partial', [])))}
GARMIN_SYNC: {str(_validation_details.get('garmin_sync_failed', '?'))}
</pre></body></html>"""
    try:
        if not already_sent_today():
            send_email(
                f"\u26a0\ufe0f Raport dobowy nie wygenerowany \u2014 {today:%d.%m.%Y}",
                _email_alert_html,
            )
            print("\U0001f4e7 Alert techniczny wys\u0142any (Email)")
    except Exception as _e:
        print(f"\u26a0\ufe0f  Alert Email: {_e}")
    _PIPELINE_STAGE = "validation_data_missing_alert_sent"
    _save_state()
    sys.exit(0)

if _validation_status == DATA_PARTIAL:
    print(f"\u26a0\ufe0f  Raport cz\u0119\u015bciowy: {_validation_details.get('alert_message', '')}")
    _PIPELINE_STAGE = "partial_data"
    if "braki_danych" not in _data:
        _data["braki_danych"] = []
    _data["braki_danych"].extend(_validation_details.get("missing", []))
    _data["braki_danych"].extend(_validation_details.get("partial", []))
    _data["validation_partial"] = True
    _data["validation_alert"] = _validation_details.get("alert_message")

# ── Wysy\u0142ka ─────────────────────────────────────────────────────────────────
_sent_state = sent_state_today()
_channels = dict(_sent_state.get("channels") or {})

if _channels.get("telegram") == "sent":
    print("✅ Telegram już wysłany — pomijam.")
else:
    _PIPELINE_STAGE = "sending_telegram"
    _save_state()
    print("📱 Wysyłam Telegram...")
    try:
        send_telegram(_tg)
        _channels["telegram"] = "sent"
        mark_sent(_channels)
        _PIPELINE_STAGE = "telegram_sent"
        _save_state()
    except Exception as _tge:
        _channels["telegram"] = "failed"
        _LAST_ERROR = str(_tge)[:300]
        _PIPELINE_STAGE = "telegram_failed"
        _save_state()
        print(f"⚠️  Telegram: {_tge}")
        # Telegram fail is non-critical — continue to email

if _channels.get("email") == "sent":
    print("✅ Email już wysłany — pomijam.")
else:
    _PIPELINE_STAGE = "sending_email"
    _save_state()
    print("📧 Wysyłam email...")
    try:
        send_email(
            f"🚴 Q-raport {today:%d.%m.%Y}",
            _email_html,
            inline_image_path=_banner_path if _banner_path.exists() else None,
            inline_image_cid=_banner_cid if _banner_path.exists() else None,
        )
        _channels["email"] = "sent"
        mark_sent(_channels)
        _PIPELINE_STAGE = "email_sent"
        _save_state()
        print("✅ Email wysłany!")
    except Exception as _e:
        _channels["email"] = "failed"
        _LAST_ERROR = str(_e)[:300]
        _PIPELINE_STAGE = "email_failed"
        _save_state()
        mark_sent(_channels)
        print(f"⚠️  Email: {_e}")
        # Don't re-raise — pipeline continues even if email fails

# ── Snapshot Xert ────────────────────────────────────────────────────────────
if xert:
    try:
        db.save_memory(topic="xert_snapshot", content=json.dumps({
            "date": today.isoformat(),
            "tp":   xert.get("tp_ftp_watts"),
            "tl":   (xert.get("forma") or {}).get("training_load"),
            "form": (xert.get("forma") or {}).get("form_score"),
        }))
        print("\U0001f4be Snapshot Xert zapisany")
    except Exception as _e:
        print(f"\u26a0\ufe0f  Snapshot: {_e}")

print("\u2705 Gotowe!")
