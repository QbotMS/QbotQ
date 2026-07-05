#!/usr/bin/env python3
"""Strażnik żywienia → Telegram.

Poranny status ostatnich dni + alert, gdy dzień jest pusty LUB poniżej normy.
Czyta qbot_v2.intake_logs (kanon raportów) — pokazuje dokładnie to, co widać w raportach,
niezależnie od tego, który front (ChatGPT/Claude/Telegram) zapisywał lub zawiódł.

"Poniżej normy" = dzień ma wpisy, ale kcal < próg * mediana(ostatnie 14 dni z wpisami).
Łapie częściową utratę posiłków (np. 3 z 4), której alert "pusty dzień" nie widzi.

Uruchamianie (z crona/timera rano):
    .venv/bin/python scripts/nutrition_watchdog.py            # status 3 dni + alerty
    .venv/bin/python scripts/nutrition_watchdog.py --days 5   # inny zakres
    .venv/bin/python scripts/nutrition_watchdog.py --alert-only  # wyślij tylko gdy pusty/poniżej-normy
    .venv/bin/python scripts/nutrition_watchdog.py --low-frac 0.4  # mniej czuły próg (0 = wyłącz)
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


def _baseline_median(cur, d: date, window: int = 14, min_samples: int = 5):
    """Mediana kcal z ostatnich `window` dni przed d (tylko dni z wpisami i kcal>0).

    Zwraca None, gdy za mało historii (< min_samples) — wtedy nie oceniamy 'poniżej normy'.
    """
    vals = []
    for i in range(1, window + 1):
        n, kcal = _day_stats(cur, d - timedelta(days=i))
        if n > 0 and kcal > 0:
            vals.append(kcal)
    if len(vals) < min_samples:
        return None
    vals.sort()
    m = len(vals) // 2
    return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2


def build_message(days: list[date], low_frac: float = 0.5) -> tuple[str, list[date]]:
    lines = ["\U0001F4CB Stan \u017cywienia (baza):"]
    empty: list[date] = []
    low: list[tuple] = []  # (dzien, kcal, baza)
    with _db() as c:
        cur = c.cursor()
        for d in days:
            n, kcal = _day_stats(cur, d)
            label = d.strftime("%d.%m")
            if n == 0:
                lines.append(f"{label}: BRAK wpis\u00f3w")
                empty.append(d)
            else:
                line = f"{label}: {n} {_plural_wpis(n)}, {round(kcal)} kcal"
                base = _baseline_median(cur, d) if low_frac > 0 else None
                if base and kcal < low_frac * base:
                    line += f"  \u2757 poni\u017cej normy (~{round(base)} typowo)"
                    low.append((d, kcal, base))
                lines.append(line)
    msg = "\n".join(lines)
    if empty:
        al = ", ".join(a.strftime("%d.%m") for a in empty)
        msg += f"\n\n\u26A0\uFE0F BRAK danych za: {al} \u2014 dopisz!"
    if low:
        ll = ", ".join(f"{d.strftime('%d.%m')} ({round(k)}/{round(b)} kcal)" for d, k, b in low)
        msg += f"\n\u2757 Poni\u017cej normy: {ll} \u2014 sprawd\u017a czy nic nie zgin\u0119\u0142o."
    triggers = empty + [d for d, _, _ in low]
    return msg, triggers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--alert-only", action="store_true",
                    help="wy\u015blij tylko gdy pusty lub poni\u017cej-normy dzie\u0144")
    ap.add_argument("--low-frac", type=float, default=0.5,
                    help="pr\u00f3g 'poni\u017cej normy' jako u\u0142amek mediany 14 dni (0 = wy\u0142\u0105cz)")
    ap.add_argument("--end", type=str, default=None,
                    help="ostatni sprawdzany dzie\u0144 YYYY-MM-DD (domy\u015blnie: wczoraj)")
    a = ap.parse_args()

    end = date.fromisoformat(a.end) if a.end else (date.today() - timedelta(days=1))
    days = [end - timedelta(days=i) for i in range(0, a.days)]  # od 'end' wstecz, najnowszy pierwszy

    msg, alerts = build_message(days, a.low_frac)

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
