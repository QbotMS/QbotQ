#!/usr/bin/env python3
"""Brokul + jedzenie: tick dla crona (*/15). Import menu i harmonogramu, podtrzymanie sesji,
dokonczenie wpisow jedzenia, przypomnienie o koncu diety, wiadomosc dnia od 20:00.
Cron (root): */15 * * * * runuser -u qbot -- /opt/qbot/app/.venv/bin/python3 /opt/qbot/app/scripts/brokul_tick.py >> /opt/qbot/app/logs/brokul.log 2>&1
Jednorazowo: --init (tabele: sql/brokul_v1.sql + food_v1.sql + food_v2.sql), --import (import teraz),
             --send DD.MM.RRRR (wyslij wiadomosc dnia ponownie).
"""
import sys
sys.path.insert(0, "/opt/qbot/app")
from datetime import datetime
import qbot_brokul_meals as M

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--init" in a:
        with M._conn() as c:
            for f in ("brokul_v1.sql", "food_v1.sql", "food_v2.sql"):
                c.execute(open("/opt/qbot/app/sql/" + f, encoding="utf-8").read())
            c.commit()
        print("tabele OK")
    elif "--import" in a:
        print(M.import_menu())
    elif "--send" in a:
        import qbot_food_log as F
        d = datetime.strptime(a[a.index("--send") + 1], "%d.%m.%Y").date()
        print("wyslano:", F.send_day(d, force=True))
    else:
        M.tick()
