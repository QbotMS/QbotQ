"""Adapter cutoveru MQ2 -> produkcja (strategia B).

MQ2 zasila STARE kolumny qbot_v2.fitmodel_daily, z ktorych czytaja wszyscy konsumenci
(web, raporty jazd/tras, glikogen, wiadra, Karoo przez qbot_api). Konsumenci bez zmian.

Mapowanie (MQ2 -> fitmodel_daily):
  ftp_est_w        <- TP   (prog W'bal, Karoo + wszedzie)
  cp_modelq_w      <- TP   (kolumna ~prog, NIE LTP -- zweryfikowane na zywych danych)
  ltp_modelq_w     <- LTP
  wprime_modelq_kj <- HIE
  pp_modelq_w      <- PP
  ctl_xss          <- CTL
  atl_raw / atl_plus <- ATL
  tsb_raw / tsb_plus <- TSB   (korekta readiness pominieta w v2 -- osobny sygnal)

run_daily_v2(): pelny pipeline v2 do daily_job (zamiast starych silnikow sygnatury/formy).
Kolejnosc kauzalna: XSS nowych jazd z sygnatury MQ2 SPRZED jazdy -> przelicz sygnature -> publish.
"""
from __future__ import annotations
import bisect, datetime as dt

from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2 import io
from fitmodel.modelq2.xss import compute_xss
from fitmodel.modelq2.mpa import replay_mpa


def _mq2_sig_before(cur, day: dt.date) -> Signature | None:
    """Sygnatura MQ2 z dnia <= day (kauzalnie sprzed jazdy). None gdy brak."""
    cur.execute("SELECT tp_w,hie_kj,pp_w FROM qbot_v2.modelq2_signature "
                "WHERE day <= %s ORDER BY day DESC LIMIT 1", (day,))
    r = cur.fetchone()
    if not r:
        return None
    return Signature.from_kj(tp_w=float(r[0]), hie_kj=float(r[1]), pp_w=float(r[2]))


def ingest_new_rides_xss(conn, lookback_days: int = 14) -> int:
    """Liczy XSS dla jazd z ostatnich N dni ktore NIE maja jeszcze wpisu w modelq2_ride.
    Sygnatura per jazda z MQ2 (dzien <= jazda). Zwraca liczbe nowych jazd."""
    cur = conn.cursor()
    d_to = dt.date.today()
    d_from = d_to - dt.timedelta(days=lookback_days)
    rides = io.list_rides(d_from, d_to)
    byday = {}
    for eid, d, n in rides:
        if d not in byday or n > byday[d][1]:
            byday[d] = (eid, n)
    done = 0
    for d in sorted(byday):
        eid, n = byday[d]
        cur.execute("SELECT 1 FROM qbot_v2.modelq2_ride WHERE external_id=%s", (eid,))
        if cur.fetchone():
            continue  # juz policzone
        sig = _mq2_sig_before(cur, d)
        if sig is None:
            continue
        rows = io.fetch_ride_rows(eid)
        res = replay_mpa(rows, sig, smooth=True, keep_series=True)
        x = compute_xss(rows, sig)
        cur.execute("""INSERT INTO qbot_v2.modelq2_ride
            (external_id,ride_date,n_ticks,duration_s,sig_tp_w,sig_hie_kj,sig_pp_w,
             min_wbal_pct,xss_low,xss_high,xss_peak,xss_total)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (external_id) DO UPDATE SET
             xss_low=EXCLUDED.xss_low,xss_high=EXCLUDED.xss_high,xss_peak=EXCLUDED.xss_peak,
             xss_total=EXCLUDED.xss_total,min_wbal_pct=EXCLUDED.min_wbal_pct""",
            (eid, d, res.n_ticks, int(res.duration_s), sig.tp_w, sig.hie_kj, sig.pp_w,
             round(res.min_wbal_pct, 1), round(x.low, 1), round(x.high, 2),
             round(x.peak, 3), round(x.total, 1)))
        done += 1
    conn.commit()
    return done


def publish_to_daily(conn) -> int:
    """Zapisuje sygnature MQ2 -> stare kolumny fitmodel_daily (UPDATE po dniu).
    Zwraca liczbe zaktualizowanych dni."""
    cur = conn.cursor()
    cur.execute("SELECT day,tp_w,hie_kj,pp_w,ltp_w,ctl,atl,tsb FROM qbot_v2.modelq2_signature ORDER BY day")
    n = 0
    for day, tp, hie, pp, ltp, ctl, atl, tsb in cur.fetchall():
        cur.execute("""UPDATE qbot_v2.fitmodel_daily SET
            ftp_est_w=%s, cp_modelq_w=%s, ltp_modelq_w=%s, wprime_modelq_kj=%s, pp_modelq_w=%s,
            ctl_xss=%s, atl_raw=%s, tsb_raw=%s, atl_plus=%s, tsb_plus=%s
            WHERE day=%s""",
            (tp, tp, ltp, hie, pp, ctl, atl, tsb, atl, tsb, day))
        n += cur.rowcount
    conn.commit()
    return n


def run_daily_v2(conn) -> dict:
    """Pelny pipeline v2 dla daily_job (zastepuje stare silniki sygnatury/formy)."""
    from fitmodel.modelq2.progression import build_and_store
    new_rides = ingest_new_rides_xss(conn)
    stats = build_and_store(conn=conn)
    published = publish_to_daily(conn)
    return {"new_rides_xss": new_rides, "signature": stats, "published_days": published}
