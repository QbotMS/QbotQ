"""Kwarantanna A+B (decyzja Michala 2026-10-08): XSS z tetna dla jazd z wadliwym miernikiem + przeliczenie ModelQ.

A. Jazdy JUZ w kwarantannie, ale z XSS z mocy (dodane do kwarantanny po policzeniu XSS): 22.07, 25.07, 26.07, 30.07, 02.08.
B. Nowe do kwarantanny (ten sam wyjazd/miernik co 02.08): 01.08 Opole (kalibracja rano -170), 03.08 Prudnik (fizyka +28 %).
Potem: sygnatura -> XSS jazd z mocy od 22.07 z nowej sygnatury sprzed jazdy -> sygnatura -> publikacja -> daily_job.
Odpalac w tle przez SSH:
  cd /opt/qbot/app && nohup .venv/bin/python3 -u scripts/mq2_quarantine_hr_20261008.py > /opt/qbot/artifacts/mq2_quarantine_hr.txt 2>&1 &
Kopie: qbot_v2.bak_20261008b_{fitmodel_ride_quarantine,modelq2_signature,modelq2_ride,fitmodel_daily}.
"""
import os, sys, time, datetime as dt
os.environ["QBOT3_ENABLED"] = "1"
sys.path.insert(0, "/opt/qbot/app")
from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2 import io
from fitmodel.modelq2.progression import build_and_store
from fitmodel.modelq2.publish import publish_to_daily, _mq2_sig_before
from fitmodel.modelq2.xss import compute_xss
from fitmodel.modelq2.mpa import replay_mpa
from fitmodel.modelq2.hr_xss import fetch_hr_rows, compute_hr_xss_split

NEW_Q = {
    "23815504718": "2026-08-01 Opole: ten sam wyjazd i miernik co 02.08 (kalibracja rano 1.08 -170, dryf zera); XSS z HR -- DECISIONS 2026-10-08",
    "23837272768": "2026-08-03 Prudnik: fizyka podjazdow miernik/fizyka 1.28 (meter_phys, 3.08 kalibracja ok. -90); XSS z HR -- DECISIONS 2026-10-08",
}
FROM = dt.date(2026, 7, 22)
T0 = time.time()
def log(*a): print("[%5.1fs]" % (time.time() - T0), *a, flush=True)

conn = _db_connect(); cur = conn.cursor()
def state(tag):
    cur.execute("SELECT day, tp_w, ctl FROM qbot_v2.modelq2_signature WHERE day IN ('2026-08-03','2026-08-20','2026-10-08') ORDER BY day")
    log(tag, "TP/CTL 03.08, 20.08, 08.10:", cur.fetchall())
state("PRZED")
for t in ("fitmodel_ride_quarantine", "modelq2_signature", "modelq2_ride", "fitmodel_daily"):
    cur.execute(f"DROP TABLE IF EXISTS qbot_v2.bak_20261008b_{t}")
    cur.execute(f"CREATE TABLE qbot_v2.bak_20261008b_{t} AS SELECT * FROM qbot_v2.{t}")
conn.commit(); log("kopie bak_20261008b_* OK")

# B: nowe wpisy kwarantanny
for eid, why in NEW_Q.items():
    cur.execute("SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine WHERE external_id=%s", (eid,))
    if cur.fetchone():
        cur.execute("UPDATE qbot_v2.fitmodel_ride_quarantine SET released=NULL, reason=reason || ' | ' || %s WHERE external_id=%s", (why, eid))
    else:
        cur.execute("INSERT INTO qbot_v2.fitmodel_ride_quarantine (external_id, reason, added) VALUES (%s, %s, CURRENT_DATE)", (eid, why))
conn.commit(); log("kwarantanna: dodane", list(NEW_Q))

# A+B: XSS z tetna dla wszystkich aktywnych kwarantann, ktore maja jeszcze XSS z mocy
cur.execute("""SELECT m.external_id, m.ride_date, m.xss_total FROM qbot_v2.modelq2_ride m
               JOIN qbot_v2.fitmodel_ride_quarantine q ON q.external_id = m.external_id AND q.released IS NULL
               WHERE COALESCE(m.xss_source,'power') <> 'hr' ORDER BY m.ride_date""")
todo = cur.fetchall(); log("do XSS z tetna:", len(todo))
for eid, d, old in todo:
    hr_rows = fetch_hr_rows(eid)
    lo, hi = compute_hr_xss_split(hr_rows)
    dur = int((hr_rows[-1][0] - hr_rows[0][0]).total_seconds()) if len(hr_rows) > 1 else 0
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET n_ticks=%s, duration_s=%s, min_wbal_pct=NULL, xss_low=%s, xss_high=%s,
                   xss_peak=0, xss_total=%s, xss_source='hr', computed_at=now() WHERE external_id=%s""",
                (len(hr_rows), dur, round(lo, 1), round(hi, 2), round(lo + hi, 1), eid))
    log("  %s %s: XSS moc %.1f -> tetno %.1f" % (d, eid, old or 0, lo + hi))
conn.commit()

log("build_and_store #1:", build_and_store(conn))
# XSS jazd z mocy od 22.07 z nowej sygnatury sprzed jazdy
cur.execute("SELECT external_id, ride_date, sig_tp_w, xss_total FROM qbot_v2.modelq2_ride WHERE ride_date >= %s "
            "AND COALESCE(xss_source,'power') <> 'hr' ORDER BY ride_date", (FROM,))
rides = cur.fetchall(); log("jazd z mocy do przeliczenia:", len(rides))
for eid, d, old_tp, old_x in rides:
    sig = _mq2_sig_before(cur, d)
    rows = io.fetch_ride_rows(eid)
    res = replay_mpa(rows, sig, smooth=True, keep_series=True)
    x = compute_xss(rows, sig)
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET sig_tp_w=%s, sig_hie_kj=%s, sig_pp_w=%s, min_wbal_pct=%s,
                   xss_low=%s, xss_high=%s, xss_peak=%s, xss_total=%s, computed_at=now() WHERE external_id=%s""",
                (sig.tp_w, sig.hie_kj, sig.pp_w, round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
                 round(x.peak, 3), round(x.total, 1), eid))
    log("  %s: TP %.1f -> %.1f, XSS %.1f -> %.1f" % (d, old_tp or 0, sig.tp_w, old_x or 0, x.total))
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
