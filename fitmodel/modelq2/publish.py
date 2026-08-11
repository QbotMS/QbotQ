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


# 2026-08-11 (DECISIONS, druga czesc): hamulce kotwicy EF.
# Mechanizm jest JEDNOSTRONNY (w gore od razu, w dol tylko decay), a EF liczy
# sie z tetna -- czyli z zaszumionego wejscia. Bez hamulcow dziala jak zapadka:
# kazdy przypadkowy skok EF podnosi prog na stale. Do tego kotwica wstawiana
# codziennie zasmieca modelq2_anchor, a logika "najblizszej kotwicy" zaczyna
# zawsze wybierac dzisiejsza -- zamrozone kotwice z Xerta staja sie martwe.
# UWAGA: hamulce NIE sluza cofnieciu progu 262.9 W (decyzja Michala: zostaje).
EF_ANCHOR_MIN_DAYS = 7      # najwyzej jedna auto-kotwica EF na tyle dni
EF_ANCHOR_MIN_SEGMENTS = 8  # min. segmentow w oknie EF, inaczej kotwica na szumie
EF_ANCHOR_MAX_RISE_W = 3.0  # maks. przyrost TP kotwicy na EF_ANCHOR_MIN_DAYS (proporcjonalnie do dni)
EF_ANCHOR_FRESH_DAYS = 14   # okno swiezosci: bez nowych jazd prog NIE rosnie
EF_ANCHOR_FRESH_MIN_SEG = 3 # min. segmentow w oknie swiezosci
EF_ANCHOR_SANITY_MULT = 1.35  # sufit: TP <= mult * mediana TP z 90 dni
EF_ANCHOR_NOTE_TAG = "kotwica EF (auto)"


def _ef_segment_count(conn, day, window_days: int = 28) -> int:
    """Ile segmentow z dobrym HR wchodzi do okna EF na dany dzien."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM qbot_v2.fitmodel_segment "
        "WHERE hr_quality_ok IS TRUE AND ef_norm IS NOT NULL "
        "AND started_at > %s AND started_at < %s",
        (day - dt.timedelta(days=window_days), day + dt.timedelta(days=1)))
    return int(cur.fetchone()[0])


def ef_anchor_step(conn, days_back: int = 45) -> dict:
    """2026-08-11 (DECISIONS): przywrocenie EF do MQ2 po cutoverze z 17.07.

    Cutover odlaczyl ftp_resolver i zaden pisarz nie wypelnial juz ef_med_28d --
    TP dryfowal za CTL slepy na wydajnosc i przegapil poprawe EF +9.6 pct
    (blok 07-08.2026), stad zanizone CP i absurdalne kotwice W' z drogi.

    1) Obserwowalnosc: ef_med_28d znow zapisywane do fitmodel_daily
       (UPDATE, ostatnie days_back dni).
    2) Kotwica EF: gdy TP z EF (formula ftp_resolver: ftp_anchor*EF/ef_anchor)
       przekracza TP modelu o >2 W, wstawiamy/odswiezamy kotwice w modelq2_anchor
       na DZIS: TP tlumione (ftp_damping_factor, dom. 0.5), HIE/PP z modelu
       (EF nic nie mowi o W' ani PP). JEDNOSTRONNIE jak w ftp_resolver: niski
       EF nie ciagnie TP w dol -- w dol dziala wylacznie naturalny decay.
    """
    from fitmodel.ftp_resolver import load_params, compute_ef_median, compute_ftp_est
    cur = conn.cursor()
    params = load_params(conn)
    today = dt.date.today()
    n_ef = 0
    for i in range(days_back, -1, -1):
        d = today - dt.timedelta(days=i)
        ef = compute_ef_median(conn, d)
        if ef is None:
            continue
        cur.execute("UPDATE qbot_v2.fitmodel_daily SET ef_med_28d=%s WHERE day=%s",
                    (round(float(ef), 4), d))
        n_ef += cur.rowcount
    out = {"ef_days_written": n_ef, "anchor": None}
    ef_t = compute_ef_median(conn, today)
    tp_ef = compute_ftp_est(ef_t, params)
    if tp_ef is not None:
        cur.execute("SELECT tp_w, hie_kj, pp_w FROM qbot_v2.modelq2_signature "
                    "WHERE day<=%s ORDER BY day DESC LIMIT 1", (today,))
        r = cur.fetchone()
        if r:
            tp_m, hie_m, pp_m = (float(x) for x in r)
            if float(tp_ef) > tp_m + 2.0:
                damp = params.get("ftp_damping_factor", 0.5)
                tp_a = round(tp_m + damp * (float(tp_ef) - tp_m), 1)
                # --- HAMULEC A: dosc segmentow w oknie EF
                n_seg = _ef_segment_count(conn, today)
                if n_seg < EF_ANCHOR_MIN_SEGMENTS:
                    out["anchor_skipped"] = ("za malo segmentow w oknie EF: %d < %d"
                                             % (n_seg, EF_ANCHOR_MIN_SEGMENTS))
                    conn.commit()
                    return out
                # --- HAMULEC A2 (swiezosc): okno EF ma 28 dni, wiec przy braku jazd
                # stare segmenty o niskim EF wypadaja i sama mediana rosnie -- prog
                # pialby sie w gore PODCZAS ODPOCZYNKU. Wymagamy swiezych jazd.
                n_fresh = _ef_segment_count(conn, today, window_days=EF_ANCHOR_FRESH_DAYS)
                if n_fresh < EF_ANCHOR_FRESH_MIN_SEG:
                    out["anchor_skipped"] = ("brak swiezych jazd: %d segmentow w %d dni "
                                             "(< %d) -- prog nie rosnie na odpoczynku"
                                             % (n_fresh, EF_ANCHOR_FRESH_DAYS,
                                                EF_ANCHOR_FRESH_MIN_SEG))
                    conn.commit()
                    return out
                # --- HAMULEC B: karencja + limit przyrostu wzgledem ostatniej auto-kotwicy
                cur.execute("SELECT day, tp_w FROM qbot_v2.modelq2_anchor "
                            "WHERE note LIKE %s ORDER BY day DESC LIMIT 1",
                            (EF_ANCHOR_NOTE_TAG + "%",))
                prev = cur.fetchone()
                reuse_day = None
                if prev:
                    prev_day, prev_tp = prev[0], float(prev[1])
                    age = (today - prev_day).days
                    # --- HAMULEC A3 (nowe dane): prog rosnie WYLACZNIE na podstawie
                    # nowych jazd. Bez tego kotwica goni TP_ef, ktory sam pelznie
                    # w gore, bo z okna 28 dni wypadaja starsze segmenty o niskim EF
                    # (test 11.08: +12.9 W w dwa tygodnie BEZ ani jednej nowej jazdy).
                    cur.execute("SELECT COUNT(*) FROM qbot_v2.fitmodel_segment "
                                "WHERE hr_quality_ok IS TRUE AND ef_norm IS NOT NULL "
                                "AND started_at > %s",
                                (dt.datetime.combine(prev_day, dt.time.max),))
                    if int(cur.fetchone()[0]) == 0:
                        out["anchor_skipped"] = ("brak nowych segmentow od ostatniej "
                                                 "kotwicy (%s) -- prog nie rosnie bez "
                                                 "nowych danych" % prev_day)
                        conn.commit()
                        return out
                    # Limit przyrostu liczony OD CZASU, nie od liczby uruchomien.
                    # Wersja "cap = prev + 3 W" przy karencji dopuszczala +3 W co
                    # 2-3 dni (test 11.08: 262.9 -> 274.7 W w 10 dni). Teraz budzet
                    # przyrostu narasta proporcjonalnie: EF_ANCHOR_MAX_RISE_W na
                    # kazde EF_ANCHOR_MIN_DAYS dni od ostatniego podniesienia.
                    budget = EF_ANCHOR_MAX_RISE_W * max(age, 0) / float(EF_ANCHOR_MIN_DAYS)
                    cap = prev_tp + budget
                    if tp_a <= prev_tp + 0.1 or budget < 0.1:
                        out["anchor_skipped"] = ("limit czasowy: %d dni od ostatniej "
                                                 "kotwicy, budzet %.2f W"
                                                 % (age, budget))
                        conn.commit()
                        return out
                    tp_a = round(min(tp_a, cap), 1)
                    if age < EF_ANCHOR_MIN_DAYS:
                        reuse_day = prev_day  # w karencji aktualizujemy istniejaca
                # --- HAMULEC C: sufit sanity wzgledem mediany TP z 90 dni
                cur.execute("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY tp_w) "
                            "FROM qbot_v2.modelq2_signature WHERE day > %s",
                            (today - dt.timedelta(days=90),))
                rmed = cur.fetchone()
                if rmed and rmed[0]:
                    ceiling = float(rmed[0]) * EF_ANCHOR_SANITY_MULT
                    if tp_a > ceiling:
                        out["anchor_capped"] = {"chcialo": tp_a, "sufit": round(ceiling, 1)}
                        tp_a = round(ceiling, 1)
                if reuse_day is not None:
                    today = reuse_day  # aktualizujemy istniejaca kotwice, nie tworzymy nowej
                cur.execute("SELECT ctl FROM qbot_v2.modelq2_signature "
                            "WHERE day<=%s AND ctl IS NOT NULL ORDER BY day DESC LIMIT 1",
                            (today,))
                rc = cur.fetchone()
                ctl_a = round(float(rc[0]), 2) if rc else 0.0
                note = ("kotwica EF (auto): TP_ef=%.1f W z EF=%.3f, tlumienie %.2f "
                        "od TP modelu %.1f W" % (float(tp_ef), float(ef_t), damp, tp_m))
                cur.execute("SELECT 1 FROM qbot_v2.modelq2_anchor WHERE day=%s", (today,))
                if cur.fetchone():
                    cur.execute("UPDATE qbot_v2.modelq2_anchor SET tp_w=%s, hie_kj=%s, pp_w=%s, "
                                "ctl_anchor=%s, note=%s WHERE day=%s",
                                (tp_a, round(hie_m, 2), round(pp_m, 1), ctl_a, note, today))
                else:
                    cur.execute("INSERT INTO qbot_v2.modelq2_anchor "
                                "(day, tp_w, hie_kj, pp_w, ctl_anchor, note) "
                                "VALUES (%s,%s,%s,%s,%s,%s)",
                                (today, tp_a, round(hie_m, 2), round(pp_m, 1), ctl_a, note))
                out["anchor"] = {"day": str(today), "tp_anchor_w": tp_a,
                                 "tp_ef_w": round(float(tp_ef), 1),
                                 "ef": round(float(ef_t), 3)}
    conn.commit()
    return out


def run_daily_v2(conn) -> dict:
    """Pelny pipeline v2 dla daily_job (zastepuje stare silniki sygnatury/formy)."""
    from fitmodel.modelq2.progression import build_and_store
    new_rides = ingest_new_rides_xss(conn)
    ef_stats = ef_anchor_step(conn)   # 2026-08-11: EF wraca do MQ2 (obserwowalnosc + kotwica)
    stats = build_and_store(conn=conn)
    published = publish_to_daily(conn)
    return {"new_rides_xss": new_rides, "ef": ef_stats,
            "signature": stats, "published_days": published}
