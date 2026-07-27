#!/usr/bin/env python3
# Fast-path ModelQ: odpalany przez wrapper synchronizacji Karoo->Garmin PO udanym
# syncu profilu michal. Sprawdza, czy najnowsza jazda na Garminie jest NOWA; gdy tak
# -> ingest 1Hz + lekki recompute ModelQ v2 (run_after_ride) -> fitmodel_daily -> web Forma.
# Gdy nic nowego -> tani no-op. Retry, bo Garmin bywa opozniony po uploadzie.
# Wlasny lock (fcntl) -> nie nakłada sie z okresowym cronem ani drugim triggerem.
# Idempotentny i odporny: awaria recompute jest lapana w _recompute_fitmodel.
#
# Uzycie: trigger_modelq_after_ride.py [PROB=6] [SLEEP_S=90]
import fcntl
import os
import sys
import time

os.environ.setdefault("QBOT3_ENABLED", "1")
sys.path.insert(0, "/opt/qbot/app")
import qbot_activity_ingest as ing  # noqa: E402

TRIES = int(sys.argv[1]) if len(sys.argv) > 1 else 6
SLEEP_S = int(sys.argv[2]) if len(sys.argv) > 2 else 90


def _log(msg):
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {msg}", flush=True)


def main():
    lockf = open("/tmp/qbot-activity-ingest-trigger.lock", "w")
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _log("inny trigger/ingest dziala, wychodze")
        return 0

    gc = ing.garmin_client()  # auth raz na caly retry
    for i in range(1, TRIES + 1):
        conn = None
        try:
            conn = ing._db()
            acts = gc.get_activities(0, 15)
            cyc = next((a for a in acts if isinstance(a, dict) and ing._is_cycling(a)), None)
            if cyc is None:
                _log(f"brak jazdy w 15 ostatnich (proba {i}/{TRIES})")
            else:
                aid = str(cyc.get("activityId"))
                if ing._already(conn, aid):
                    _log(f"nic nowego (aid={aid}, proba {i}/{TRIES})")
                else:
                    _log(f"NEW aid={aid} (proba {i}/{TRIES}) - ingest+recompute")
                    r = ing.ingest_one(gc, conn, cyc, with_report=True)
                    conn.close()
                    conn = None
                    t0 = time.time()
                    ing._recompute_fitmodel(f"trigger_after_ride aid={r.get('aid')}")
                    _log(f"NEW-DONE aid={r.get('aid')} recompute={time.time() - t0:.1f}s")
                    return 10
        except Exception as e:
            _log(f"blad proba {i}/{TRIES}: {type(e).__name__}: {str(e)[:200]}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        if i < TRIES:
            time.sleep(SLEEP_S)
    _log("koniec bez nowej jazdy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
