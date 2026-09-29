from __future__ import annotations

"""L3 -- ukryte zmeczenie (subiektywny koszt jazdy) -> ATL.

Warstwa ADDYTYWNA, AUDYTOWALNA i ODWRACALNA. NIE nadpisuje XSS/atl_raw/ctl_xss/tsb_raw.
W dni z jazda, gdy zawodnik zglosil gorsze samopoczucie (feel<0) lub chorobe, jazda
"kosztowala" wiecej -> doliczamy ukryty XSS, ktory zasila osobny strumien EWMA (tau=7,
jak ATL) i wchodzi WYLACZNIE do atl_plus/tsb_plus:

    xss_ukryty(d)  = koszt_jazdy(d) * narzut          (tylko dni z jazda; feel<0/choroba)
    narzut         = clamp( max(0,-feel)*A + (choroba? B), 0, CAP )
    atl_ukryty(d)  = atl_ukryty(d-1) + (xss_ukryty(d) - atl_ukryty(d-1))/TAU_RL
    atl_plus(d)    = atl_raw(d) + atl_ukryty(d)
    tsb_plus(d)    = ctl_xss(d) - atl_plus(d)

Jednokierunkowo: feel>0 NIE odejmuje ATL (nie zmyslamy regeneracji z dobrego humoru).
Koszt jazdy = modelq2_ride.xss_total (kanoniczny XSS jazdy MQ2). Dni bez jazdy: xss_ukryty=0
(strumien decayuje). Baza obiektywna (atl_raw/ctl/tsb_raw) i sygnatura CP/FTP/W' nietkniete.

Przelacznik: QBOT_L3_HIDDEN_FATIGUE=0 => wylaczone (atl_plus=atl_raw, kolumny ukryte=0)
=> pelna odwracalnosc bez ruszania raw. Backfill: python -m fitmodel.modelq2.hidden_fatigue.
"""

import os
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

A_FEEL = 0.10   # narzut na 1 punkt ujemnego feel (feel -2 => +20%)
B_ILLNESS = 0.15  # narzut za aktywna chorobe danego dnia
CAP = 0.35        # gorny limit narzutu (% kosztu jazdy)
TAU_RL = 7.0      # dni, ta sama stala co ATL

# --- L2-OBJ (przywrocone 2026-08-11, DECISIONS) ---------------------------
# Cutover MQ2 (08.07) zastapil OBIEKTYWNA korekte zmeczenia z ModelQ v1
# (fatigue_mult z readiness_score: HRV + RHR + sen) warstwa SUBIEKTYWNA L3
# (feel/choroba z kalendarza). W calej historii sa 3 wpisy feel, wiec
# atl_plus praktycznie rowna sie atl_raw i wymiar "ile mnie ta jazda
# naprawde kosztowala" zniknal z modelu.
# Przywracamy stale i formule 1:1 z v1 (archive/modelq_v1/training_load.py),
# ale ADDYTYWNIE i obok L3: liczymy sam NADMIAR wzgledem XSS surowego,
# wiec atl_raw/ctl_xss/tsb_raw pozostaja nietkniete i wszystko jest
# odwracalne przelacznikiem.
FATIGUE_MULT_K = 0.4      # v1: +/-0.4 readiness => +/-16% korekty
MULT_LO, MULT_HI = 0.5, 1.7
# Limit tygodniowy (2026-09-28, "opcja 2"): suma DODATNICH doplat z gotowosci w oknie
# 7 dni <= READY_WEEK_CAP * suma surowego XSS z tych 7 dni. Na seriach dni (wyjazd)
# mnoznik x1.6 dzien po dniu dawal TSB+ -118 (06-11.06.2026); symulacja na 634 dniach:
# ta sama zgodnosc z gotowoscia za 1-2 dni (0.154 vs 0.153), dolek -102. Ulga (swiezy,
# mnoznik <1) bez limitu. Przelacznik: QBOT_L2_WEEK_CAP=0.
READY_WEEK_CAP = 0.25
READY_WEEK_DAYS = 7


def _enabled() -> bool:
    return os.getenv("QBOT_L3_HIDDEN_FATIGUE", "1") not in ("0", "false", "False", "no")


def _obj_enabled() -> bool:
    return os.getenv("QBOT_L2_READINESS_FATIGUE", "1") not in ("0", "false", "False", "no")


def _week_cap_enabled() -> bool:
    return os.getenv("QBOT_L2_WEEK_CAP", "1") not in ("0", "false", "False", "no")


def _ill_norest_enabled() -> bool:
    """2026-09-28: dzien choroby BEZ jazdy nie jest odpoczynkiem -> ATL+ nie spada.
    Wczesniej leżenie w chorobie podbijalo Swiezosc (wrzesien: +38 'super wypoczety')."""
    return os.getenv("QBOT_L3_ILLNESS_NOREST", "1") not in ("0", "false", "False", "no")


# Skok obciazenia (2026-09-28): srednie XSS 7 dni / srednie 28 dni (ACWR, rolling).
# Liczony z surowego XSS jazd; None gdy baza 28 dni za mala (< RAMP_MIN_BASE XSS/dzien).
RAMP_SHORT, RAMP_LONG, RAMP_MIN_BASE = 7, 28, 10.0


def fatigue_multiplier(readiness_score) -> float:
    """v1 1:1. readiness>0 (swiezy) => mnoznik <1, readiness<0 (zmeczony) => >1."""
    if readiness_score is None:
        return 1.0
    mult = 1.0 - FATIGUE_MULT_K * float(readiness_score)
    return max(MULT_LO, min(MULT_HI, mult))


def apply_hidden_fatigue(conn) -> dict:
    """Przelicza atl_plus/tsb_plus + kolumny audytu z ukrytego zmeczenia. Zwraca statystyki."""
    enabled = _enabled()
    obj_on = _obj_enabled()
    cur = conn.cursor()
    cur.execute("ALTER TABLE qbot_v2.fitmodel_daily "
                "ADD COLUMN IF NOT EXISTS atl_ready_adj NUMERIC")
    cur.execute("ALTER TABLE qbot_v2.fitmodel_daily "
                "ADD COLUMN IF NOT EXISTS load_ramp NUMERIC")
    cur.execute("ALTER TABLE qbot_v2.fitmodel_daily "
                "ADD COLUMN IF NOT EXISTS load_7d NUMERIC, ADD COLUMN IF NOT EXISTS load_28d NUMERIC")
    conn.commit()
    norest_on = _ill_norest_enabled()
    from collections import deque
    ramp_win = deque(maxlen=RAMP_LONG)
    cap_on = _week_cap_enabled()
    wk_hist = deque(maxlen=READY_WEEK_DAYS - 1)   # (surowy XSS, doplata z gotowosci) poprzednich dni
    prev_atl_plus = None

    # baza obiektywna z fitmodel_daily
    cur.execute("SELECT day, atl_raw, ctl_xss, tsb_raw FROM qbot_v2.fitmodel_daily ORDER BY day")
    base = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    if not base:
        return {"enabled": enabled, "updated": 0}
    days_sorted = sorted(base.keys())
    d0, d1 = days_sorted[0], days_sorted[-1]

    # koszt jazdy per dzien (kanoniczny XSS MQ2; suma gdy kilka jazd)
    cur.execute("SELECT ride_date, SUM(xss_total) FROM qbot_v2.modelq2_ride "
                "WHERE ride_date BETWEEN %s AND %s GROUP BY ride_date", (d0, d1))
    rides = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    # feel per dzien (ostatni wpis z danego dnia)
    cur.execute("SELECT day, feel FROM qbot_v2.calendar_entry "
                "WHERE kind='feel' AND feel IS NOT NULL AND day BETWEEN %s AND %s "
                "ORDER BY day, id", (d0, d1))
    feels = {}
    for day, feel in cur.fetchall():
        feels[day] = int(feel)

    # choroba: zbior dni objetych aktywna choroba
    cur.execute("SELECT day, COALESCE(end_day, day) FROM qbot_v2.calendar_entry "
                "WHERE kind='illness'")
    ill_days = set()
    for a, b in cur.fetchall():
        dd = a
        while dd <= b:
            ill_days.add(dd)
            dd = dd + dt.timedelta(days=1)

    cur.execute("SELECT day, readiness_score FROM qbot_v2.fitmodel_daily "
                "WHERE day BETWEEN %s AND %s AND readiness_score IS NOT NULL", (d0, d1))
    readiness = {r[0]: float(r[1]) for r in cur.fetchall()}

    hidden_atl = 0.0
    ready_atl = 0.0   # L2-OBJ: strumien EWMA nadmiaru z gotowosci
    updated = 0
    nz = 0
    d = d0
    while d <= d1:
        ride_xss = rides.get(d, 0.0)
        feel = feels.get(d)
        ill = d in ill_days
        norest = False
        if enabled and ride_xss > 0:
            neg = (-feel) if (feel is not None and feel < 0) else 0
            surcharge = min(CAP, neg * A_FEEL + (B_ILLNESS if ill else 0.0))
            xss_hidden = ride_xss * surcharge
        elif enabled and norest_on and ill and prev_atl_plus is not None:
            # choroba bez jazdy: wkladamy do strumienia tyle, ile wynosilo ATL+ wczoraj
            # -> suma ATL+ (raw + ukryte + gotowosc, wszystkie tau=7) zostaje plasko.
            surcharge = 0.0
            xss_hidden = max(0.0, float(prev_atl_plus))
            norest = True
        else:
            surcharge = 0.0
            xss_hidden = 0.0
        ramp_win.append(ride_xss)
        load_ramp = None
        load_7d = load_28d = None   # srednie dzienne XSS (obciazenie dlugoterminowe, Forma)
        if len(ramp_win) == RAMP_LONG:
            _l = sum(ramp_win) / RAMP_LONG
            _s = sum(list(ramp_win)[-RAMP_SHORT:]) / RAMP_SHORT
            load_7d, load_28d = round(_s, 1), round(_l, 1)
            if _l >= RAMP_MIN_BASE:
                load_ramp = round(_s / _l, 2)
        if enabled:
            hidden_atl = hidden_atl + (xss_hidden - hidden_atl) / TAU_RL
        else:
            hidden_atl = 0.0

        # L2-OBJ: nadmiar/ulga wzgledem XSS surowego wg gotowosci tego dnia.
        # Moze byc UJEMNY (swiezy = jazda kosztuje mniej) -- inaczej niz L3,
        # ktore jest jednokierunkowe. Zacisk MULT_LO/HI jak w v1.
        capped = False
        if obj_on and ride_xss > 0:
            mult = fatigue_multiplier(readiness.get(d))
            xss_ready = ride_xss * (mult - 1.0)
            if cap_on and xss_ready > 0:
                raw7 = sum(h[0] for h in wk_hist) + ride_xss
                ext7 = sum(max(0.0, h[1]) for h in wk_hist)
                lim = max(0.0, READY_WEEK_CAP * raw7 - ext7)
                if xss_ready > lim:
                    xss_ready = lim
                    capped = True
        else:
            mult = 1.0
            xss_ready = 0.0
        wk_hist.append((ride_xss, xss_ready))
        if obj_on:
            ready_atl = ready_atl + (xss_ready - ready_atl) / TAU_RL
        else:
            ready_atl = 0.0

        if d in base:
            atl_raw, ctl, tsb_raw = base[d]
            if atl_raw is not None:
                atl_plus = round(float(atl_raw) + hidden_atl + ready_atl, 1)
                tsb_plus = (round(float(tsb_raw) - hidden_atl - ready_atl, 1)
                            if tsb_raw is not None else None)
            else:
                atl_plus = None
                tsb_plus = None
            if atl_plus is not None:
                prev_atl_plus = atl_plus
            note = None
            if norest:
                note = ("choroba bez jazdy: zmeczenie nie spada jak w odpoczynku (+%.1f xss ukryte); atl_ukryte +%.2f"
                        % (xss_hidden, hidden_atl))
                nz += 1
            elif xss_hidden > 0:
                bits = []
                if feel is not None and feel < 0:
                    bits.append("feel %+d" % feel)
                if ill:
                    bits.append("choroba")
                note = ("%s, jazda %.0f XSS, +%.0f%% -> +%.1f xss; atl_ukryte +%.2f"
                        % (", ".join(bits), ride_xss, surcharge * 100, xss_hidden, hidden_atl))
                nz += 1
            if obj_on and ride_xss > 0 and abs(mult - 1.0) > 0.01:
                bit = ("gotowosc %+.2f -> koszt x%.2f (%+.0f xss%s); atl_gotowosc %+.2f"
                       % (readiness.get(d, 0.0), mult, xss_ready,
                          ", limit tyg. 25%" if capped else "", ready_atl))
                note = (note + " || " + bit) if note else bit
            cur.execute(
                "UPDATE qbot_v2.fitmodel_daily SET atl_plus=%s, tsb_plus=%s, "
                "xss_hidden_subj=%s, atl_hidden_subj=%s, atl_ready_adj=%s, "
                "atl_plus_note=%s, load_ramp=%s, load_7d=%s, load_28d=%s WHERE day=%s",
                (atl_plus, tsb_plus, round(xss_hidden, 1), round(hidden_atl, 2),
                 round(ready_atl, 2), note, load_ramp, load_7d, load_28d, d),
            )
            updated += cur.rowcount
        d = d + dt.timedelta(days=1)

    conn.commit()
    # status dnia (fitmodel/day_status.py) - korzysta z load_ramp i gotowosci, wiec liczony PO korektach zmeczenia
    try:
        from fitmodel.day_status import apply_day_status
        ds = apply_day_status(conn)
    except Exception as exc:
        ds = {"error": str(exc)}
    return {"enabled": enabled, "obj_enabled": obj_on, "illness_norest": norest_on, "day_status": ds,
            "week_cap": cap_on,
            "updated": updated, "days_with_hidden": nz}


if __name__ == "__main__":
    from fitmodel.ftp_resolver import _db_connect
    conn = _db_connect()
    print(apply_hidden_fatigue(conn))
    conn.close()
