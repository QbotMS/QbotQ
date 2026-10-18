#!/usr/bin/env python3
"""Weekly QBot coach review -- Telegram (mail usuniety 2026-10-18, decyzja Michala)."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

import db
import qbot_config as cfg
from qbot_coach import build_weekly_review


ATHLETE_ID = cfg.INTERVALS_ATHLETE_ID
HDR = cfg.intervals_headers()
TOKEN = cfg.TELEGRAM_TOKEN
CHAT_ID = cfg.TELEGRAM_CHAT_ID
SENT_FILE = Path("/opt/qbot/app/data/weekly_review_sent.json")


def icu_get(endpoint, params=None):
    r = httpx.get(f"https://intervals.icu/api/v1{endpoint}", headers=HDR, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def send_telegram(text):
    for i in range(0, len(text), 4000):
        r = httpx.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text[i:i + 4000]},
            timeout=10,
        )
        r.raise_for_status()


def _sent_key(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def already_sent(day):
    if not SENT_FILE.exists():
        return False
    try:
        return _sent_key(day) in json.loads(SENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False


def mark_sent(day):
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if SENT_FILE.exists():
        try:
            data = json.loads(SENT_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[_sent_key(day)] = {"sent_at": date.today().isoformat()}
    SENT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upcoming_trips(today):
    return sorted(
        [
            {
                "name": t.get("name"),
                "start_date": t.get("start_date"),
                "days_to": (date.fromisoformat(t["start_date"]) - today).days,
                "distance_km": t.get("distance_km"),
                "elevation_m": t.get("elevation_m"),
            }
            for t in (db.get_trips(status="planned") or [])
            if t.get("start_date") and t["start_date"] >= today.isoformat()
        ],
        key=lambda x: x["start_date"],
    )[:2]


def render_text(review):
    s = review["summary"]
    blockers = "; ".join(review["blockers"])
    worked = "; ".join(review["what_worked"])
    return (
        "Tygodniowy review QBot\n\n"
        f"Trening: {s['activities']} aktywności, {s['hours']} h, TSS {s['tss']}, długie jazdy: {s['long_rides']}.\n"
        f"Regeneracja: HRV avg {s['avg_hrv'] or '—'} ms, sen avg {s['avg_sleep'] or '—'} h.\n"
        f"Bilans: {s['avg_balance'] or '—'} kcal/d, trend masy: {s['weight_trend'] or '—'} kg.\n\n"
        f"Co działało: {worked}.\n"
        f"Blokery: {blockers}.\n"
        f"Focus na kolejny tydzień: {review['next_week_focus']}."
    )


def main():
    today = date.today()
    preview = "--preview" in sys.argv
    if not preview and "--force" not in sys.argv and already_sent(today):
        print("✅ Tygodniowy review już wysłany w tym tygodniu.")
        return 0
    oldest = today - timedelta(days=6)
    wellness = icu_get(f"/athlete/{ATHLETE_ID}/wellness", {"oldest": oldest.isoformat(), "newest": today.isoformat()})
    activities = icu_get(f"/athlete/{ATHLETE_ID}/activities", {"oldest": oldest.isoformat(), "newest": today.isoformat(), "limit": 50})
    review = build_weekly_review(wellness, activities, upcoming_trips(today))
    if preview:
        print(render_text(review))
        return 0
    send_telegram(render_text(review))
    mark_sent(today)
    print("✅ Tygodniowy review wysłany.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
