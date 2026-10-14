"""Przeliczenie ModelQ po zmianie czulosci HIE (decay.py HIE_ELASTICITY 0.11, +-10 %) -- 2026-10-14, decyzja Michala.
Kopie bak_20261014b_*, build_and_store, XSS/W'bal jazd od 2026-08-10, build_and_store #2, publish, daily_job, kontrola.
  .venv/bin/python3 scripts/mq2_recalc_hie_20261014.py   (ok. 30 s)
Wycofanie: przywrocic decay.py z gita + tabele z qbot_v2.bak_20261014b_*."""
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

RECALC_FROM = dt.date(2026, 8, 10)
CHECK_DAYS = ["2026-08-30", "2026-09-19", "2026-09-27", "2026-10-11"]
T0 = time.time()


def log(*a):
    print("[%5.1fs]" % (time.time() - T0), *a, flush=True)


assert getattr(decay, "HIE_ELASTICITY", None) == 0.11, "decay.py bez nowej czulosci HIE - przerywam"
conn = _db_connect(); cur = conn.cursor()
for t in ("modelq2_signature", "modelq2_ride", "fitmodel_daily"):
    cur.execute(f"DROP TABLE IF EXISTS qbot_v2.bak_20261014b_{t}")
    cur.execute(f"CREATE TABLE qbot_v2.bak_20261014b_{t} AS SELECT * FROM qbot_v2.{t}")
conn.commit(); log("kopie bak_20261014b_* OK")
log("build_and_store #1:", build_and_store(conn))
cur.execute("SELECT external_id, ride_date FROM qbot_v2.modelq2_ride WHERE ride_date >= %s "
            "AND COALESCE(xss_source,'power') <> 'hr' ORDER BY ride_date", (RECALC_FROM,))
for eid, d in cur.fetchall():
    sig = _mq2_sig_before(cur, d)
    rows = io.fetch_ride_rows(eid)
    res = replay_mpa(rows, sig, smooth=True, keep_series=True)
    x = compute_xss(rows, sig)
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET sig_tp_w=%s, sig_hie_kj=%s, sig_pp_w=%s, min_wbal_pct=%s,
                   xss_low=%s, xss_high=%s, xss_peak=%s, xss_total=%s, computed_at=now() WHERE external_id=%s""",
                (sig.tp_w, sig.hie_kj, sig.pp_w, round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
                 round(x.peak, 3), round(x.total, 1), eid))
conn.commit()
log("build_and_store #2:", build_and_store(conn))
log("publish_to_daily:", publish_to_daily(conn))
cur.execute("SELECT ride_date, round(sig_hie_kj::numeric,1), round(min_wbal_pct::numeric,1) FROM qbot_v2.modelq2_ride "
            "WHERE ride_date::text = ANY(%s) ORDER BY ride_date", (CHECK_DAYS,))
log("KONTROLA (data, HIE, min W'bal %):", cur.fetchall())
cur.execute("SELECT min(hie_kj), max(hie_kj) FROM qbot_v2.modelq2_signature WHERE day >= '2026-08-17'")
log("HIE od 17.08 min/max:", cur.fetchone())
conn.close()
from fitmodel import daily_job
daily_job.main()
conn = _db_connect(); cur = conn.cursor()
cur.execute("SELECT day, cp_modelq_w, wprime_modelq_kj, ltp_modelq_w, ctl_xss, tsb_real, day_status "
            "FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 1")
log("KONIEC fitmodel_daily:", cur.fetchone())
conn.close()
log("GOTOWE")
