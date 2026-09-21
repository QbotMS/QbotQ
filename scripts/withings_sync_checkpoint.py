#!/usr/bin/env python3
"""Przypomnienie mailem: kontrola syncu Withings -> Garmin przed wygasnieciem
subskrypcji SmartScaleSync (do 5 wrzesnia 2026).

Po co: dopoki SmartScaleSync dziala rownolegle, nasz sync zwykle widzi "duplicate"
i nigdy nie udowodni, ze potrafi zapisac SAM. Awaria bylaby niewidoczna az do
5 wrzesnia. Ten skrypt liczy statusy w pliku stanu i przysyla werdykt mailem.

Statusy w state/processed_withings_measures.json:
  uploaded  = NASZ skrypt zapisal samodzielnie  <- tego szukamy
  duplicate = SmartScaleSync byl pierwszy       <- nic nie dowodzi

Uruchamiany z crona 1 i 4 wrzesnia. Po 5 wrzesnia wpisy cron mozna usunac.
"""

from __future__ import annotations

import json
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

STATE = APP_DIR / "state/processed_withings_measures.json"
SUB_END = date(2026, 9, 5)

import qbot_config as cfg  # noqa: E402


def analyse() -> dict:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        measures = data.get("measures", {})
    except Exception as exc:
        return {"error": f"nie udalo sie odczytac pliku stanu: {exc}"}

    counts: dict[str, int] = {}
    recent: list[tuple[str, str, float | None]] = []
    cutoff = datetime.now() - timedelta(days=21)

    for entry in measures.values():
        status = entry.get("status", "?")
        counts[status] = counts.get(status, 0) + 1
        try:
            when = datetime.fromtimestamp(entry["ts"])
        except Exception:
            continue
        if when >= cutoff:
            recent.append((when.strftime("%Y-%m-%d %H:%M"), status, entry.get("weight_kg")))

    recent.sort(reverse=True)
    return {
        "counts": counts,
        "recent": recent,
        "uploaded": counts.get("uploaded", 0),
        "duplicate": counts.get("duplicate", 0),
        "failed": counts.get("failed", 0),
        "total": len(measures),
    }


def build_html(res: dict) -> tuple[str, str]:
    days_left = (SUB_END - date.today()).days

    if res.get("error"):
        verdict = "NIE WIEM - brak danych"
        colour = "#b00"
        advice = res["error"]
    elif res["uploaded"] > 0:
        verdict = "DZIALA SAMODZIELNIE"
        colour = "#0a0"
        advice = (f"Nasz sync zapisal do Garmina samodzielnie {res['uploaded']} raz(y). "
                  "Wygasniecie subskrypcji 5.09 mozna przyjac spokojnie.")
    elif res["failed"] > 0:
        verdict = "SA BLEDY - SPRAWDZIC"
        colour = "#b00"
        advice = (f"Nieudanych zapisow: {res['failed']}. Zajrzec do "
                  "/opt/qbot/logs/withings_garmin_sync.log ZANIM subskrypcja wygasnie.")
    else:
        verdict = "NIEPOTWIERDZONE"
        colour = "#c80"
        advice = ("Wszystkie pomiary trafialy do Garmina przez SmartScaleSync (duplicate), "
                  "wiec nasz sync nigdy nie zapisal sam. Mechanizm byl sprawdzony testem "
                  "24.08, ale warto zrobic kontrolny zapis przed 5.09.")

    rows = "".join(
        f"<tr><td>{d}</td><td>{s}</td><td>{w if w is not None else '-'} kg</td></tr>"
        for d, s, w in res.get("recent", [])[:10]
    ) or "<tr><td colspan='3'>brak pomiarow w ostatnich 21 dniach</td></tr>"

    html = f"""<html><body style="font-family:system-ui,sans-serif;max-width:640px">
<h2>Withings &rarr; Garmin: kontrola przed wygasnieciem subskrypcji</h2>
<p style="font-size:18px"><b style="color:{colour}">{verdict}</b></p>
<p>{advice}</p>
<p>SmartScaleSync wygasa <b>5 wrzesnia 2026</b> (za {days_left} dni).</p>
<h3>Statusy zapisow</h3>
<ul>
<li>zapisane przez NASZ sync (uploaded): <b>{res.get('uploaded', 0)}</b></li>
<li>ubiegl nas SmartScaleSync (duplicate): {res.get('duplicate', 0)}</li>
<li>nieudane (failed): {res.get('failed', 0)}</li>
</ul>
<h3>Ostatnie pomiary</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
<tr><th>kiedy</th><th>status</th><th>waga</th></tr>{rows}</table>
<h3>Gdyby trzeba bylo sprawdzic recznie</h3>
<pre style="background:#f4f4f4;padding:10px">/opt/qbot/app/scripts/run_withings_garmin_sync.sh
tail -20 /opt/qbot/logs/withings_garmin_sync.log</pre>
<p style="color:#888;font-size:12px">Automat: scripts/withings_sync_checkpoint.py</p>
</body></html>"""

    subject = f"[QBot] Withings->Garmin: {verdict} (subskrypcja wygasa za {days_left} dni)"
    return subject, html


def main() -> int:
    res = analyse()
    subject, html = build_html(res)

    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText(html, "html", "utf-8"))
    msg["Subject"] = subject
    msg["From"] = cfg.GMAIL_USER
    msg["To"] = cfg.EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(cfg.GMAIL_USER, cfg.GMAIL_APP_PASSWORD)
        s.send_message(msg)

    print(f"[{datetime.now().isoformat(timespec='seconds')}] wyslano: {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
