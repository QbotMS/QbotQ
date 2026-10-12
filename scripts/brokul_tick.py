#!/usr/bin/env python3
"""Brokul: tick dla crona (*/15). Import menu, podtrzymanie sesji, Telegram o 20:00.
Cron (root): */15 * * * * runuser -u qbot -- /opt/qbot/app/.venv/bin/python3 /opt/qbot/app/scripts/brokul_tick.py >> /opt/qbot/app/logs/brokul.log 2>&1
Jednorazowo: --init (tabele z sql/brokul_v1.sql), --import (import teraz), --send DD.MM.RRRR (wyslij podsumowanie dnia).
"""
import sys
sys.path.insert(0, "/opt/qbot/app")
from datetime import datetime
import qbot_brokul_meals as M

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--init" in a:
        sql = open("/opt/qbot/app/sql/brokul_v1.sql", encoding="utf-8").read()
        with M._conn() as c:
            c.execute(sql)
            c.commit()
        print("tabele OK")
    elif "--import" in a:
        print(M.import_menu())
    elif "--send" in a:
        d = datetime.strptime(a[a.index("--send") + 1], "%d.%m.%Y").date()
        print("wyslano:", M.send_day(d, force=True))
    else:
        M.tick()
