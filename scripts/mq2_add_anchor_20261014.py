"""Nowa kotwica ModelQ 2026-10-14 z WLASNYCH danych (decyzja Michala 2026-10-14, MODELQ-PRZEGLAD Etap 3).

Kotwica: TP 238.8 W (bez zmian, ModelQ), HIE 20.0 kJ (kalibracja: replay_mpa 4 jazd z W'bal=0 -- 30.08, 19.09, 27.09,
11.10 -- przy HIE 20 min W'bal 6-11 %, zgodne z odczuciem "trudno, nie odcielo, ale niedaleko"; 18.2 = bezpiecznik,
24.2 = Xert z zawyzonym XSS 07-08), PP 988.8 W (bez zmian). Nic z Xerta nie jest przenoszone -- Xert tylko sprawdzian.
Kroki:
  1. kopie: bak_20261014_modelq2_anchor / _modelq2_signature / _modelq2_ride / _fitmodel_daily
  2. INSERT kotwicy 2026-10-14 (przerywa, jesli juz jest)
  3. build_and_store
  4. XSS + min W'bal jazd od 2026-08-10 (zrodlo 'power') od nowa z sygnatury sprzed jazdy (najblizsza kotwica od ~17.08 = nowa)
  5. build_and_store #2 + publish_to_daily
  6. fitmodel.daily_job.main() (gotowosc, realne obciazenie, status dnia, threshold_sync -> intervals/Karoo itd.)
  7. kontrola: min W'bal 4 jazd kalibracyjnych + dzisiejsza sygnatura
Odpalac W TLE przez SSH (dlugie, ~15 min):
  cd /opt/qbot/app && nohup .venv/bin/python3 scripts/mq2_add_anchor_20261014.py > /opt/qbot/artifacts/mq2_add_anchor.txt 2>&1 &
Wycofanie: DELETE FROM qbot_v2.modelq2_anchor WHERE day='2026-10-14'; potem build_and_store + przeliczenie XSS od 2026-08-10
  (albo przywrocenie tabel z qbot_v2.bak_20261014_*) + publish_to_daily + daily_job.main().
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

DAY = dt.date(2026, 10, 14)
TP, HIE, PP, CTL = 238.8, 20.0, 988.8, 58.4
NOTE = "kotwica wlasna 14.10.2026: TP/PP z ModelQ, HIE 20,0 kJ z kalibracji 4 jazd W'bal=0 + odczucie (MODELQ_PRZEGLAD)"
RECALC_FROM = dt.date(2026, 8, 10)
CHECK_DAYS = ("2026-08-30", "2026-09-19", "2026-09-27", "2026-10-11")
T0 = time.time()


def log(*a):
    print("[%5.1fs]" % (time.time() - T0), *a, flush=True)


conn = _db_connect(); cur = conn.cursor()


def today_vals(tag):
    cur.execute("SELECT day, tp_w, hie_kj, pp_w, ltp_w, ctl, atl, tsb FROM qbot_v2.modelq2_signature ORDER BY day DESC LIMIT 1")
    log(tag, "sygnatura:", cur.fetchone())
    cur.execute("SELECT day, cp_modelq_w, wprime_modelq_kj, ltp_modelq_w, ctl_xss, atl_real, tsb_real, day_status "
                "FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 1")
    log(tag, "fitmodel_daily:", cur.fetchone())


today_vals("PRZED")

# 1. kopie
for t in ("modelq2_anchor", "modelq2_signature", "modelq2_ride", "fitmodel_daily"):
    cur.execute(f"DROP TABLE IF EXISTS qbot_v2.bak_20261014_{t}")
    cur.execute(f"CREATE TABLE qbot_v2.bak_20261014_{t} AS SELECT * FROM qbot_v2.{t}")
conn.commit(); log("kopie zapasowe bak_20261014_* OK")

# 2. kotwica
cur.execute("SELECT day FROM qbot_v2.modelq2_anchor WHERE day=%s", (DAY,))
assert cur.fetchone() is None, "kotwica 2026-10-14 juz istnieje - przerywam"
cur.execute("INSERT INTO qbot_v2.modelq2_anchor (day, tp_w, hie_kj, pp_w, ctl_anchor, note, frozen_at) "
            "VALUES (%s,%s,%s,%s,%s,%s, now())", (DAY, TP, HIE, PP, CTL, NOTE))
conn.commit(); log("kotwica 14.10 dodana:", TP, HIE, PP)

# 3. sygnatura z nowa kotwica
log("build_and_store #1:", build_and_store(conn))

# 4. XSS + W'bal jazd od 10.08
cur.execute("SELECT external_id, ride_date, sig_hie_kj, xss_total, min_wbal_pct FROM qbot_v2.modelq2_ride "
            "WHERE ride_date >= %s AND COALESCE(xss_source,'power') <> 'hr' ORDER BY ride_date", (RECALC_FROM,))
rides = cur.fetchall(); log("jazd do przeliczenia:", len(rides))
for eid, d, old_hie, old_x, old_w in rides:
    sig = _mq2_sig_before(cur, d)
    rows = io.fetch_ride_rows(eid)
    res = replay_mpa(rows, sig, smooth=True, keep_series=True)
    x = compute_xss(rows, sig)
    cur.execute("""UPDATE qbot_v2.modelq2_ride SET sig_tp_w=%s, sig_hie_kj=%s, sig_pp_w=%s, min_wbal_pct=%s,
                   xss_low=%s, xss_high=%s, xss_peak=%s, xss_total=%s, computed_at=now() WHERE external_id=%s""",
                (sig.tp_w, sig.hie_kj, sig.pp_w, round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
                 round(x.peak, 3), round(x.total, 1), eid))
    log("  %s %s: HIE %.1f -> %.1f kJ, XSS %.1f -> %.1f, min W'bal %.0f%% -> %.0f%%" % (
        d, eid, old_hie or 0, sig.hie_kj, old_x or 0, x.total, old_w or 0, res.min_wbal_pct or 0))
conn.commit()

# 5. sygnatura z nowym XSS + publikacja
log("build_and_store #2:", build_and_store(conn))
log("publish_to_daily:", publish_to_daily(conn))
today_vals("PO MQ2")
cur.execute("SELECT ride_date, round(sig_hie_kj::numeric,1), round(min_wbal_pct::numeric,1) FROM qbot_v2.modelq2_ride "
            "WHERE ride_date::text = ANY(%s) ORDER BY ride_date", (list(CHECK_DAYS),))
log("KONTROLA jazd kalibracyjnych (data, HIE, min W'bal %):", cur.fetchall())
conn.close()

# 6. reszta potoku dziennego
log("daily_job.main() ...")
from fitmodel import daily_job
daily_job.main()
conn = _db_connect(); cur = conn.cursor()
today_vals("KONIEC")
conn.close()
log("GOTOWE")
