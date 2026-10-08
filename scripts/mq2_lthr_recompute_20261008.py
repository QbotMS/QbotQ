"""Przeliczenie po wdrozeniu dynamicznego LTHR (decyzja Michala 2026-10-08).
1. XSS z tetna WSZYSTKICH jazd z xss_source='hr' od nowa (LTHR na dzien jazdy z lthr_daily + K z hr_xss_calib).
2. Sygnatura -> XSS jazd z mocy od 2026-07-04 z nowej sygnatury sprzed jazdy -> sygnatura -> publikacja.
3. daily_job.main(): m.in. krok lthr, lthr_sync (LTHR + strefy HR do intervals.icu -> Karoo).
Odpalac w tle:
  cd /opt/qbot/app && nohup .venv/bin/python3 -u scripts/mq2_lthr_recompute_20261008.py > /opt/qbot/artifacts/mq2_lthr_recompute.txt 2>&1 &
Kopie: qbot_v2.bak_20261008c_{modelq2_signature,modelq2_ride,fitmodel_daily}."""
import os, sys, time, datetime as dt
os.environ["QBOT3_ENABLED"] = "1"
sys.path.insert(0, "/opt/qbot/app")
from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2 import io
from fitmodel.modelq2.progression import build_and_store
from fitmodel.modelq2.publish import publish_to_daily, _mq2_sig_before
from fitmodel.modelq2.xss import compute_xss
from fitmodel.modelq2.mpa import replay_mpa
from fitmodel.modelq2.hr_xss import fetch_hr_rows, compute_hr_xss_split, params_for

T0 = time.time()
def log(*a): print("[%5.1fs]" % (time.time() - T0), *a, flush=True)
conn = _db_connect(); cur = conn.cursor()
def state(tag):
    cur.execute("SELECT day, tp_w, ctl FROM qbot_v2.modelq2_signature WHERE day IN ('2026-08-03','2026-08-20','2026-10-08') ORDER BY day")
    log(tag, "TP/CTL 03.08, 20.08, 08.10:", cur.fetchall())
state("PRZED")
for t in ("modelq2_signature", "modelq2_ride", "fitmodel_daily"):
    cur.execute(f"DROP TABLE IF EXISTS qbot_v2.bak_20261008c_{t}")
    cur.execute(f"CREATE TABLE qbot_v2.bak_20261008c_{t} AS SELECT * FROM qbot_v2.{t}")
conn.commit(); log("kopie bak_20261008c_* OK")

cur.execute("SELECT external_id, ride_date, xss_total FROM qbot_v2.modelq2_ride WHERE xss_source='hr' ORDER BY ride_date")
for eid, d, old in cur.fetchall():
    hr_rows = fetch_hr_rows(eid)
    lo, hi = compute_hr_xss_split(hr_rows)
    L, kl, kh = params_for(hr_rows[0][0].date() if hr_rows else None)
    cur.execute("UPDATE qbot_v2.modelq2_ride SET xss_low=%s, xss_high=%s, xss_total=%s, computed_at=now() WHERE external_id=%s",
                (round(lo, 1), round(hi, 2), round(lo + hi, 1), eid))
    log("  HR %s: XSS %.1f -> %.1f (LTHR %.0f, K %.3f/%.3f)" % (d, old or 0, lo + hi, L, kl, kh))
conn.commit()

log("build_and_store #1:", build_and_store(conn))
cur.execute("SELECT external_id, ride_date, xss_total FROM qbot_v2.modelq2_ride WHERE ride_date >= '2026-07-04' "
            "AND COALESCE(xss_source,'power') <> 'hr' ORDER BY ride_date")
for eid, d, old_x in cur.fetchall():
    sig = _mq2_sig_before(cur, d)
    rows = io.fetch_ride_rows(eid)
    res = replay_mpa(rows, sig, smooth=True, keep_series=True)
    x = compute_xss(rows, sig)
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET sig_tp_w=%s, sig_hie_kj=%s, sig_pp_w=%s, min_wbal_pct=%s,
                   xss_low=%s, xss_high=%s, xss_peak=%s, xss_total=%s, computed_at=now() WHERE external_id=%s""",
                (sig.tp_w, sig.hie_kj, sig.pp_w, round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
                 round(x.peak, 3), round(x.total, 1), eid))
    log("  moc %s: TP %.1f, XSS %.1f -> %.1f" % (d, sig.tp_w, old_x or 0, x.total))
conn.commit()
log("build_and_store #2:", build_and_store(conn))
log("publish_to_daily:", publish_to_daily(conn))
state("PO MQ2")
conn.close()
log("daily_job.main() ...")
from fitmodel import daily_job
daily_job.main()
conn = _db_connect(); cur = conn.cursor()
state("KONIEC")
cur.execute("SELECT day, cp_modelq_w, ltp_modelq_w, ctl_xss, atl_real, tsb_real, day_status FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 1")
log("KONIEC fitmodel_daily:", cur.fetchone())
conn.close()
log("GOTOWE")
