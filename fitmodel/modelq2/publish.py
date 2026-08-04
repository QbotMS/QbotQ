"""Adapter cutoveru MQ2 -> produkcja (strategia B).

MQ2 zasila STARE kolumny qbot_v2.fitmodel_daily, z ktorych czytaja wszyscy konsumenci
(web, raporty jazd/tras, glikogen, wiadra, Karoo przez qbot_api). Konsumenci bez zmian.

Mapowanie (MQ2 -> fitmodel_daily):
  ftp_est_w        <- TP   (prog W'bal, Karoo + wszedzie)
  cp_modelq_w      <- TP   (kolumna ~prog, NIE LTP -- zweryfikowane na zywych danych)
  ltp_modelq_w     <- LTP (EMA28 z dziennego TP - HIE/400, od 2026-08-04)
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
from fitmodel.ltp_hrdrift import LTP_MEASURED_NOTE
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
    cur.execute("SELECT day,tp_w,hie_kj,pp_w,ltp_w,ctl,atl,tsb,source "
                "FROM qbot_v2.modelq2_signature ORDER BY day")
    n = 0
    # 2026-08-04: publikowane LTP = EMA28 z dziennego (TP - HIE/400).
    # LTP to parametr wolnozmienny, a dzienne HIE skacze po mocnej jezdzie
    # (TL_high), przez co surowe LTP nurkowalo -3.3 W dzien po dobrym treningu
    # ("model karze za dobra jazde", DECISIONS 2026-07-26). Backtest od 03.2026:
    # MAE vs Xert 3.48 -> 2.03 W, reakcja na skok HIE -3.3 -> -0.4 W (plasko),
    # zmiennosc d/d 1.46 -> 0.25 W, poziom bez zmian (190.9 -> 190.3).
    # Wygladzanie WEJSC (samego HIE) odrzucone: psulo naturalne znoszenie sie
    # szumow TP i HIE i dawalo odbicie +3 W po skoku. Sygnatura wewnetrzna
    # (TP/HIE -> W'bal/MPA/XSS) NIETKNIETA -- EMA istnieje tylko w publikacji.
    _LTP_EMA_N = 28
    _ltp_ema = None
    for day, tp, hie, pp, ltp, ctl, atl, tsb, src in cur.fetchall():
        _ltp_raw = float(ltp)
        if _ltp_ema is None:
            _ltp_ema = _ltp_raw
        else:
            _ltp_ema += (2.0 / (_LTP_EMA_N + 1)) * (_ltp_raw - _ltp_ema)
        ltp = round(_ltp_ema, 1)
        # 2026-07-26: MQ2 zapisuje wlasna notke proweniencyjna do ltp_modelq_note.
        # Kolumny *_r2 pochodzily z ModelQ v1 (regresja krzywej mocy) i od cutoveru
        # 2026-07-08 stoja puste. MQ2 nie dopasowuje krzywej -- LTP wychodzi ze wzoru
        # na sygnaturze -- wiec r2 nie ma tu sensu i jest jawnie zerowane, zeby
        # raport nie pokazywal pustego pola po nieistniejacym modelu.
        note = ("LTP = EMA28 z dziennego (TP - HIE/400) (wzor Xert, wygladzony "
                "na wyjsciu od 2026-08-04; surowe dzienne nurkowalo po mocnej "
                "jezdzie -- szczegoly DECISIONS). Zrodlo MQ2: %s "
                "(TP dryfuje za CTL wokol kotwicy, HIE za TL_high). "
                "To nie jest dopasowanie krzywej -- r2 nie wystepuje. "
                "TP=%.1f W, HIE=%.2f kJ, LTP_raw=%.1f W. || %s"
                % (src or "decay", float(tp), float(hie), _ltp_raw, LTP_MEASURED_NOTE))
        # cp_modelq_w niesie TP, nie CP i nie LTP -- historyczna nazwa kolumny.
        # Notka mowi to wprost, zeby raport nie sugerowal osobno wyznaczonego CP.
        cp_note = ("UWAGA: kolumna cp_modelq_w niesie TP (prog) z sygnatury MQ2, "
                   "nie osobno wyznaczone CP i nie LTP -- nazwa jest historyczna. "
                   "Zrodlo MQ2: %s. TP=%.1f W. Prawdziwe CP z okien 120-600 s "
                   "nie jest jeszcze liczone (zadanie otwarte)."
                   % (src or "decay", float(tp)))
        cur.execute("""UPDATE qbot_v2.fitmodel_daily SET
            ftp_est_w=%s, cp_modelq_w=%s, ltp_modelq_w=%s, wprime_modelq_kj=%s, pp_modelq_w=%s,
            ltp_modelq_note=%s, ltp_modelq_r2=NULL,
            cp_wprime_note=%s, cp_wprime_r2=NULL,
            ctl_xss=%s, atl_raw=%s, tsb_raw=%s, atl_plus=%s, tsb_plus=%s,
            w_per_kg=CASE WHEN weight_kg IS NOT NULL AND weight_kg>0 THEN %s::numeric/weight_kg ELSE w_per_kg END
            WHERE day=%s""",
            (tp, tp, ltp, hie, pp, note, cp_note, ctl, atl, tsb, atl, tsb, tp, day))
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
