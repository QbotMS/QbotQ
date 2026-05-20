#!/usr/bin/env python3
import os, json, httpx, base64
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv('/opt/qbot/app/.env')

ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID")
API_KEY    = os.getenv("INTERVALS_API_KEY")
GARMIN_EMAIL    = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
BASE       = "https://intervals.icu/api/v1"
_b64       = base64.b64encode(f"API_KEY:{API_KEY}".encode()).decode()
HDR        = {"Authorization": f"Basic {_b64}", "Content-Type": "application/json"}

os.environ['CRONOMETER_USERNAME'] = os.getenv("CRONOMETER_EMAIL")
os.environ['CRONOMETER_PASSWORD'] = os.getenv("CRONOMETER_PASSWORD")

from cronometer_mcp import CronometerClient
from garminconnect import Garmin

yesterday = date.today() - timedelta(days=1)

# Cronometer
c = CronometerClient()
c.authenticate()
rows    = c.get_daily_summary(yesterday, yesterday)
kcal_in = prot = carbs = fat = 0
if rows:
    r       = rows[0]
    kcal_in = float(r.get("Energy (kcal)", 0) or 0)
    prot    = float(r.get("Protein (g)", 0) or 0)
    carbs   = float(r.get("Carbs (g)", 0) or 0)
    fat     = float(r.get("Fat (g)", 0) or 0)

# Garmin
kcal_out = bmr = active = 0
try:
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise RuntimeError("Brak GARMIN_EMAIL / GARMIN_PASSWORD w .env")
    with open('/opt/qbot/app/.garmin_profile.json') as f:
        profile = json.load(f)
    g = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
    g.client.load('/opt/qbot/app/.garmin_tokens')
    g.display_name = profile['display_name']
    stats    = g.get_stats(yesterday.isoformat())
    kcal_out = float(stats.get('totalKilocalories', 0) or 0)
    bmr      = float(stats.get('bmrKilocalories', 0) or 0)
    active   = float(stats.get('activeKilocalories', 0) or 0)
except Exception as e:
    print(f'⚠️ Garmin: {e}')

bilans = kcal_in - kcal_out if kcal_out else 0
parts  = []
if kcal_in:
    parts.append(f"🍽️ Zjedzone: {kcal_in:.0f} kcal | B:{prot:.0f}g W:{carbs:.0f}g T:{fat:.0f}g")
if kcal_out:
    parts.append(f"🔥 Spalone: {kcal_out:.0f} kcal (BMR:{bmr:.0f} + aktywne:{active:.0f})")
if kcal_in and kcal_out:
    parts.append(f"⚖️ Bilans: {bilans:+.0f} kcal")

if parts:
    comment = '\n'.join(parts)
    resp = httpx.put(f"{BASE}/athlete/{ATHLETE_ID}/wellness/{yesterday.isoformat()}",
                     headers=HDR, json={"comments": comment}, timeout=10)
    print("✅" if resp.status_code in (200,201) else "❌", f"{yesterday}:\n{comment}")
else:
    print(f"⏭️  {yesterday}: brak danych")
