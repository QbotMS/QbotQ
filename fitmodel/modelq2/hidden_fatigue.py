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


def _enabled() -> bool:
    return os.getenv("QBOT_L3_HIDDEN_FATIGUE", "1") not in ("0", "false", "False", "no")


def apply_hidden_fatigue(conn) -> dict:
    """Przelicza atl_plus/tsb_plus + kolumny audytu z ukrytego zmeczenia. Zwraca statystyki."""
    enabled = _enabled()
    cur = conn.cursor()

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

    hidden_atl = 0.0
    updated = 0
    nz = 0
    d = d0
    while d <= d1:
        ride_xss = rides.get(d, 0.0)
        feel = feels.get(d)
        ill = d in ill_days
        if enabled and ride_xss > 0:
            neg = (-feel) if (feel is not None and feel < 0) else 0
            surcharge = min(CAP, neg * A_FEEL + (B_ILLNESS if ill else 0.0))
            xss_hidden = ride_xss * surcharge
        else:
            surcharge = 0.0
            xss_hidden = 0.0
        if enabled:
            hidden_atl = hidden_atl + (xss_hidden - hidden_atl) / TAU_RL
        else:
            hidden_atl = 0.0

        if d in base:
            atl_raw, ctl, tsb_raw = base[d]
            if atl_raw is not None:
                atl_plus = round(float(atl_raw) + hidden_atl, 1)
                tsb_plus = round(float(tsb_raw) - hidden_atl, 1) if tsb_raw is not None else None
            else:
                atl_plus = None
                tsb_plus = None
            note = None
            if xss_hidden > 0:
                bits = []
                if feel is not None and feel < 0:
                    bits.append("feel %+d" % feel)
                if ill:
                    bits.append("choroba")
                note = ("%s, jazda %.0f XSS, +%.0f%% -> +%.1f xss; atl_ukryte +%.2f"
                        % (", ".join(bits), ride_xss, surcharge * 100, xss_hidden, hidden_atl))
                nz += 1
            cur.execute(
                "UPDATE qbot_v2.fitmodel_daily SET atl_plus=%s, tsb_plus=%s, "
                "xss_hidden_subj=%s, atl_hidden_subj=%s, atl_plus_note=%s WHERE day=%s",
                (atl_plus, tsb_plus, round(xss_hidden, 1), round(hidden_atl, 2), note, d),
            )
            updated += cur.rowcount
        d = d + dt.timedelta(days=1)

    conn.commit()
    return {"enabled": enabled, "updated": updated, "days_with_hidden": nz}


if __name__ == "__main__":
    from fitmodel.ftp_resolver import _db_connect
    conn = _db_connect()
    print(apply_hidden_fatigue(conn))
    conn.close()
