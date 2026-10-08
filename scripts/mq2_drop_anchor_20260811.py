"""Usuniecie skazonej kotwicy EF z 11.08.2026 (TP 265.5) + przeliczenie ModelQ (decyzja Michala 2026-10-08).

Tlo: DECISIONS 2026-10-04 (kotwica policzona na skazonej sprawnosci, miernik +25 % na 11.08) i 2026-10-08.
Kroki:
  1. kopie zapasowe: bak_20261008_modelq2_anchor / _modelq2_signature / _modelq2_ride / _fitmodel_daily
  2. DELETE kotwicy 2026-08-11 (tylko ta, z tagiem 'kotwica EF (auto)')
  3. build_and_store (sygnatura z kotwic: 20.06 i wczesniejsze)
  4. XSS jazd od 2026-08-11 (zrodlo 'power') od nowa z NOWEJ sygnatury sprzed jazdy; jazdy z XSS z tetna ('hr') bez zmian
  5. build_and_store jeszcze raz (XSS -> forma -> dryf TP) + publish_to_daily
  6. fitmodel.daily_job.main() (gotowosc, realne obciazenie, status dnia, threshold_sync -> intervals/Karoo itd.)
Odpalac W TLE przez SSH (dlugie):
  cd /opt/qbot/app && nohup .venv/bin/python3 scripts/mq2_drop_anchor_20260811.py > /opt/qbot/artifacts/mq2_drop_anchor.txt 2>&1 &
Wycofanie: odtworzyc wiersz z qbot_v2.bak_20261008_modelq2_anchor i odpalic build_and_store + publish_to_daily.
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

DAY = dt.date(2026, 8, 11)
T0 = time.time()
def log(*a):
    print("[%5.1fs]" % (time.time() - T0), *a, flush=True)

conn = _db_connect(); cur = conn.cursor()
def today_vals(tag):
    cur.execute("SELECT day, tp_w, ltp_w, ctl, atl, tsb FROM qbot_v2.modelq2_signature ORDER BY day DESC LIMIT 1")
    log(tag, "sygnatura:", cur.fetchone())
    cur.execute("SELECT day, cp_modelq_w, ltp_modelq_w, ctl_xss, atl_real, tsb_real, day_status FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 1")
    log(tag, "fitmodel_daily:", cur.fetchone())

today_vals("PRZED")

# 1. kopie
for t in ("modelq2_anchor", "modelq2_signature", "modelq2_ride", "fitmodel_daily"):
    cur.execute(f"DROP TABLE IF EXISTS qbot_v2.bak_20261008_{t}")
    cur.execute(f"CREATE TABLE qbot_v2.bak_20261008_{t} AS SELECT * FROM qbot_v2.{t}")
conn.commit(); log("kopie zapasowe bak_20261008_* OK")

# 2. kotwica
cur.execute("SELECT day, tp_w, note FROM qbot_v2.modelq2_anchor WHERE day=%s", (DAY,))
row = cur.fetchone(); log("kotwica:", row)
assert row and "kotwica EF (auto)" in (row[2] or ""), "nie ta kotwica - przerywam"
cur.execute("DELETE FROM qbot_v2.modelq2_anchor WHERE day=%s AND note LIKE %s", (DAY, "kotwica EF (auto)%"))
assert cur.rowcount == 1
conn.commit(); log("kotwica 11.08 usunieta")

# 3. sygnatura bez kotwicy
log("build_and_store #1:", build_and_store(conn))

# 4. XSS jazd od 11.08 od nowa
cur.execute("SELECT external_id, ride_date, sig_tp_w, xss_total FROM qbot_v2.modelq2_ride "
            "WHERE ride_date >= %s AND COALESCE(xss_source,'power') <> 'hr' ORDER BY ride_date", (DAY,))
rides = cur.fetchall(); log("jazd do przeliczenia:", len(rides))
for eid, d, old_tp, old_x in rides:
    sig = _mq2_sig_before(cur, d)
    rows = io.fetch_ride_rows(eid)
    res = replay_mpa(rows, sig, smooth=True, keep_series=True)
    x = compute_xss(rows, sig)
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET sig_tp_w=%s, sig_hie_kj=%s, sig_pp_w=%s, min_wbal_pct=%s,
                   xss_low=%s, xss_high=%s, xss_peak=%s, xss_total=%s, computed_at=now() WHERE external_id=%s""",
                (sig.tp_w, sig.hie_kj, sig.pp_w, round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
                 round(x.peak, 3), round(x.total, 1), eid))
    log("  %s %s: TP %.1f -> %.1f, XSS %.1f -> %.1f, min W'bal %.0f%%" % (d, eid, old_tp or 0, sig.tp_w, old_x or 0, x.total, res.min_wbal_pct or 0))
conn.commit()

# 5. sygnatura z nowym XSS + publikacja
log("build_and_store #2:", build_and_store(conn))
log("publish_to_daily:", publish_to_daily(conn))
today_vals("PO MQ2")
conn.close()

# 6. reszta potoku dziennego
log("daily_job.main() ...")
from fitmodel import daily_job
daily_job.main()
conn = _db_connect(); cur = conn.cursor()
today_vals("KONIEC")
conn.close()
log("GOTOWE")
