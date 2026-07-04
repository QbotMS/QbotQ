#!/usr/bin/env python3
"""Strażnik żywienia → Telegram.

Poranny status ostatnich dni + alert, gdy dzień jest pusty.
Czyta qbot_v2.intake_logs (kanon raportów) — pokazuje dokładnie to, co widać w raportach,
niezależnie od tego, który front (ChatGPT/Claude/Telegram) zapisywał lub zawiódł.

Uruchamianie (z crona/timera rano):
    .venv/bin/python scripts/nutrition_watchdog.py            # status 3 dni + alert
    .venv/bin/python scripts/nutrition_watchdog.py --days 5   # inny zakres
    .venv/bin/python scripts/nutrition_watchdog.py --alert-only  # wyślij tylko gdy pusty dzień
    .venv/bin/python scripts/nutrition_watchdog.py --dry-run  # nic nie wysyła, drukuje treść
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, "/opt/qbot/app")
import qbot_config as cfg  # ładuje env (PG*, TELEGRAM_*)
import psycopg
from psycopg.rows import dict_row
from qbot_telegram_client import send_message


def _db():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )


def _plural_wpis(n: int) -> str:
    if n == 1:
        return "wpis"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "wpisy"
    return "wpis\u00f3w"


def _day_stats(cur, d: date) -> tuple[int, float]:
    cur.execute(
        """SELECT COUNT(DISTINCT l.id) AS n, COALESCE(SUM(i.kcal), 0) AS kcal
           FROM qbot_v2.intake_logs l
           LEFT JOIN qbot_v2.intake_items i ON i.intake_log_id = l.id
           WHERE l.date = %s""",
        (d,),
    )
    r = cur.fetchone()
    return int(r["n"] or 0), float(r["kcal"] or 0)


def build_message(days: list[date]) -> tuple[str, list[date]]:
    lines = ["\U0001F4CB Stan \u017cywienia (baza):"]
    alerts: list[date] = []
    with _db() as c:
        cur = c.cursor()
        for d in days:
            n, kcal = _day_stats(cur, d)
            label = d.strftime("%d.%m")
            if n == 0:
                lines.append(f"{label}: BRAK wpis\u00f3w")
                alerts.append(d)
            else:
                lines.append(f"{label}: {n} {_plural_wpis(n)}, {round(kcal)} kcal")
    msg = "\n".join(lines)
    if alerts:
        al = ", ".join(a.strftime("%d.%m") for a in alerts)
        msg += f"\n\n\u26A0\uFE0F BRAK danych za: {al} \u2014 dopisz!"
    return msg, alerts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--alert-only", action="store_true",
                    help="wy\u015blij tylko gdy jest pusty dzie\u0144")
    ap.add_argument("--end", type=str, default=None,
                    help="ostatni sprawdzany dzie\u0144 YYYY-MM-DD (domy\u015blnie: wczoraj)")
    a = ap.parse_args()

    end = date.fromisoformat(a.end) if a.end else (date.today() - timedelta(days=1))
    days = [end - timedelta(days=i) for i in range(0, a.days)]  # od 'end' wstecz, najnowszy pierwszy

    msg, alerts = build_message(days)

    if a.alert_only and not alerts:
        print("[watchdog] brak alert\u00f3w, nic nie wysy\u0142am (alert-only)")
        return
    if a.dry_run:
        print("[DRY-RUN] nie wysy\u0142am. Tre\u015b\u0107:\n" + msg)
        return

    chat_id = cfg.TELEGRAM_CHAT_ID
    res = send_message(chat_id, msg)
    print("[watchdog] wys\u0142ano:", res.get("ok", res) if isinstance(res, dict) else res)


if __name__ == "__main__":
    main()
