"""Przeliczenie ModelQ po zmianie reguly TP (decay.py: 0.45 W/CTL, CTL sprzed 14 dni) -- 2026-10-14, decyzja Michala.
Regula TP dziala na KAZDY dzien daleko od kotwicy => XSS/W'bal WSZYSTKICH jazd (zrodlo 'power') od nowa.
Kopie bak_20261014c_*, build_and_store, XSS jazd, build_and_store #2, publish, daily_job, kontrola.
  .venv/bin/python3 scripts/mq2_recalc_tp_20261014.py   (ok. 1 min)
Wycofanie: decay.py z gita + tabele z qbot_v2.bak_20261014c_*."""
import os, sys, time, datetime as dt
os.environ["QBOT3_ENABLED"] = "1"
sys.path.insert(0, "/opt/qbot/app")
from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2 import io
from fitmodel.modelq2.progression import build_and_store
from fitmodel.modelq2.publish import publish_to_daily, _mq2_sig_before
from fitmodel.modelq2.xss import compute_xss
from fitmodel.modelq2.mpa import replay_mpa
from fitmodel.modelq2 import decay

T0 = time.time()


def log(*a):
    print("[%5.1fs]" % (time.time() - T0), *a, flush=True)


assert decay.TP_K_DRIFT == 0.45 and decay.TP_LAG_DAYS == 14, "decay.py bez nowej reguly TP - przerywam"
conn = _db_connect(); cur = conn.cursor()
cur.execute("SELECT day, tp_w FROM qbot_v2.modelq2_signature WHERE day IN ('2025-09-01','2026-01-15','2026-08-30','2026-09-27','2026-10-14') ORDER BY day")
log("TP PRZED:", cur.fetchall())
for t in ("modelq2_signature", "modelq2_ride", "fitmodel_daily"):
    cur.execute(f"DROP TABLE IF EXISTS qbot_v2.bak_20261014c_{t}")
    cur.execute(f"CREATE TABLE qbot_v2.bak_20261014c_{t} AS SELECT * FROM qbot_v2.{t}")
conn.commit(); log("kopie bak_20261014c_* OK")
log("build_and_store #1:", build_and_store(conn))
cur.execute("SELECT external_id, ride_date FROM qbot_v2.modelq2_ride WHERE COALESCE(xss_source,'power') <> 'hr' ORDER BY ride_date")
rides = cur.fetchall(); log("jazd:", len(rides))
for eid, d in rides:
    sig = _mq2_sig_before(cur, d)
    rows = io.fetch_ride_rows(eid)
    if not rows:
        continue
    res = replay_mpa(rows, sig, smooth=True, keep_series=True)
    x = compute_xss(rows, sig)
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET sig_tp_w=%s, sig_hie_kj=%s, sig_pp_w=%s, min_wbal_pct=%s,
                   xss_low=%s, xss_high=%s, xss_peak=%s, xss_total=%s, computed_at=now() WHERE external_id=%s""",
                (sig.tp_w, sig.hie_kj, sig.pp_w, round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
                 round(x.peak, 3), round(x.total, 1), eid))
conn.commit(); log("XSS przeliczone")
log("build_and_store #2:", build_and_store(conn))
log("publish_to_daily:", publish_to_daily(conn))
cur.execute("SELECT day, tp_w FROM qbot_v2.modelq2_signature WHERE day IN ('2025-09-01','2026-01-15','2026-08-30','2026-09-27','2026-10-14') ORDER BY day")
log("TP PO:", cur.fetchall())
cur.execute("SELECT ride_date, round(sig_hie_kj::numeric,1), round(sig_tp_w::numeric,1), round(min_wbal_pct::numeric,1) FROM qbot_v2.modelq2_ride "
            "WHERE ride_date::text = ANY(%s) ORDER BY ride_date", (["2026-08-30", "2026-09-19", "2026-09-27", "2026-10-11"],))
log("KONTROLA 4 jazd (data, HIE, TP, min W'bal %):", cur.fetchall())
conn.close()
from fitmodel import daily_job
daily_job.main()
conn = _db_connect(); cur = conn.cursor()
cur.execute("SELECT day, cp_modelq_w, wprime_modelq_kj, ltp_modelq_w, ctl_xss, tsb_real, day_status FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 1")
log("KONIEC fitmodel_daily:", cur.fetchone())
conn.close()
log("GOTOWE")
