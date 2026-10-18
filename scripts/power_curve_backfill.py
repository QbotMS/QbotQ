#!/usr/bin/env python3
"""Backfill krzywych mocy (qbot_v2.ride_power_curve) dla wszystkich jazd rowerowych. 2026-10-18.

Uruchamiaj w tle (dlugie!):
  cd /opt/qbot/app && nohup .venv/bin/python3 scripts/power_curve_backfill.py > /opt/qbot/artifacts/power_curve_backfill.txt 2>&1 &
Opcja --force przelicza tez juz policzone. Na koniec (lub przy bledzie) wiadomosc na Telegram.
Nowe jazdy dolicza sie same przy otwarciu zakladki Forma > Krzywa mocy (/api/power/curve).
"""
import os, sys, time
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"


def main():
    force = "--force" in sys.argv
    from fitmodel.api import _db_connect
    from fitmodel.telegram_notify import send as _telegram_send
    import qbot_power_curve as pc
    t0 = time.time()
    try:
        conn = _db_connect()
        cur = conn.cursor()
        cur.execute("SELECT external_id, date FROM qbot_v2.training_sessions "
                    "WHERE sport_type = ANY(%s) AND external_id IS NOT NULL ORDER BY date", (pc.BIKE,))
        rides = [(r["external_id"], r["date"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()]
        print("jazd rowerowych:", len(rides), flush=True)
        total = 0
        for i in range(0, len(rides), 25):
            done, _ = pc.ensure_curves(conn, rides[i:i + 25], force=force)
            total += done
            print("  %d/%d przetworzone, policzone %d" % (min(i + 25, len(rides)), len(rides), total), flush=True)
        cur.execute("SELECT count(*) AS n, count(*) FILTER (WHERE cardinality(durs) > 0) AS z_moca FROM qbot_v2.ride_power_curve")
        r = cur.fetchone()
        n, zm = (r["n"], r["z_moca"]) if isinstance(r, dict) else (r[0], r[1])
        msg = ("\u2705 Krzywa mocy: przeliczone %d jazd w %.0f s. W tabeli %d jazd, z pomiarem mocy %d. "
               "Forma \u2192 Krzywa mocy gotowa." % (total, time.time() - t0, n, zm))
        print(msg, flush=True)
        _telegram_send(msg)
    except Exception as exc:
        msg = "\u26a0\ufe0f Krzywa mocy: przeliczanie PRZERWANE: %s: %s" % (type(exc).__name__, str(exc)[:300])
        print(msg, flush=True)
        try:
            _telegram_send(msg)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
