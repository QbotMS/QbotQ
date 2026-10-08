"""XSS z tetna (fallback dla jazd w kwarantannie miernika mocy).

DLACZEGO ISTNIEJE
-----------------
Kwarantanna (fitmodel_ride_quarantine) wylacza jazde z kotwic CP/W', ale XSS
liczony z watow i tak karmil CTL -> TP (odkryte 14.08.2026: sycylijskie jazdy
z dryfem zera zawyzaly obciazenie i sygnature). Tetno jest niezalezne od
miernika mocy -- dla jazd w AKTYWNEJ kwarantannie XSS liczymy z HR, zeby jazda
liczyla sie do obciazenia (decyzja Michala 11.08), ale uczciwa waluta.

FORMULA (od 17.08.2026: podzial Low/High)
-----------------------------------------
surowo, po sekundach JAZDY (v >= 1 m/s), waga (HR/LTHR)^2 * UNIT:
  - sekundy z HR <= LTHR  -> koszyk LOW,  wynik * K_LOW  (0.90)
  - sekundy z HR  > LTHR  -> koszyk HIGH, wynik * K_HIGH (0.17)
  - PEAK = 0 (zryww 15-30 s tetno fizycznie nie widzi -- nie udajemy)
UNIT = 100/3600 (spojnie z xss.py: 1h na progu = 100 XSS).

K_LOW=0.90 i K_HIGH=0.17: mediany (XSS_power_low / hr_raw_low) i
((XSS_power_high+peak) / hr_raw_high) z 33/29 czystych jazd 05-08.2026.
K_HIGH jest niski, bo HR tuz nad progiem czesto NIE oznacza watow nad
progiem (opoznienie i dryf tetna) -- tylko ~1/6 "energii" nad LTHR to
prawdziwe High wg watow. Rozrzut duzy (0.04-0.72) -- to fallback,
nie precyzja. Powod podzialu: gorskie jazdy (Sycylia 08.2026) mialy
realne akcenty nad progiem, a wersja "wszystko w Low" sztucznie
zanizala TL_high -> W'/HIE nurkowalo (decay.py dryfuje HIE za TL_high).

OGRANICZENIA
------------
- Dryf sercowy (upal, odwodnienie) zawyza HR pod koniec dlugiej jazdy.
- min_wbal dla jazd HR = NULL (brak watow = brak W'bal = zadnych kotwic).
- LTHR: od 2026-10-08 DYNAMICZNE (fitmodel/lthr.py, tabela lthr_daily, na dzien jazdy); K_LOW/K_HIGH z
  qbot_v2.hr_xss_calib (lthr.calibrate_hr_xss, co 28 dni lub po zmianie LTHR). Stale ponizej = awaryjne
  (dawny kanon 132 bpm byl o ~18 ud. za niski -- DECISIONS 2026-10-08).
"""
from __future__ import annotations

from fitmodel.ftp_resolver import _db_connect

LTHR_BPM = 132.0
UNIT = 100.0 / 3600.0   # jak w xss.py: 1h na progu = 100 XSS
HR_MIN = 60             # ponizej: dane smieciowe -> pomijamy
V_MIN_MPS = 1.0         # tylko jazda (odcina postoj, NIE strome podjazdy)
K_LOW = 0.90            # kalibracja koszyka Low (patrz naglowek)
K_HIGH = 0.17           # kalibracja koszyka High (patrz naglowek)


def fetch_hr_rows(external_id: str) -> list:
    """[(ts, hr_bpm, speed_mps), ...] 1Hz dla jazdy, posortowane po czasie."""
    conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT ts, hr_bpm, speed_mps FROM qbot_v2.activity_record "
            "WHERE external_id = %s ORDER BY ts", (external_id,))
        return [(ts, float(h) if h is not None else None,
                 float(v) if v is not None else None)
                for ts, h, v in cur.fetchall()]
    finally:
        conn.close()


_PCACHE: dict = {}


def params_for(day) -> tuple:
    """(lthr, k_low, k_high) na dzien jazdy: dynamiczne LTHR + najnowsza kalibracja K. Awaryjnie stale modulu."""
    if day in _PCACHE:
        return _PCACHE[day]
    lthr, kl, kh = LTHR_BPM, K_LOW, K_HIGH
    try:
        from fitmodel.lthr import get_lthr
        conn = _db_connect()
        try:
            lthr = float(get_lthr(conn, day))
            cur = conn.cursor()
            cur.execute("SELECT k_low, k_high FROM qbot_v2.hr_xss_calib ORDER BY day DESC LIMIT 1")
            r = cur.fetchone()
            if r:
                r = tuple(r.values()) if isinstance(r, dict) else tuple(r)
                kl, kh = float(r[0]), float(r[1])
            else:
                lthr, kl, kh = LTHR_BPM, K_LOW, K_HIGH   # bez kalibracji K nie mieszac nowego LTHR ze starymi K
        finally:
            conn.close()
    except Exception:
        lthr, kl, kh = LTHR_BPM, K_LOW, K_HIGH
    _PCACHE[day] = (lthr, kl, kh)
    return _PCACHE[day]


def compute_hr_xss_split(hr_rows: list, lthr_bpm: float | None = None,
                         k_low: float | None = None, k_high: float | None = None) -> tuple:
    """(xss_low, xss_high) z probek 1Hz. Dziury > 5 s pomijane. Brak parametrow -> dynamiczne na dzien jazdy."""
    if lthr_bpm is None or k_low is None or k_high is None:
        day = hr_rows[0][0].date() if hr_rows and hasattr(hr_rows[0][0], "date") else None
        dl, dkl, dkh = params_for(day)
        lthr_bpm = dl if lthr_bpm is None else lthr_bpm
        k_low = dkl if k_low is None else k_low
        k_high = dkh if k_high is None else k_high
    lo = hi = 0.0
    prev_ts = None
    for row in hr_rows:
        ts, hr, v = row[0], row[1], (row[2] if len(row) > 2 else None)
        if (prev_ts is not None and hr is not None and hr >= HR_MIN
                and v is not None and v >= V_MIN_MPS):
            dt_s = (ts - prev_ts).total_seconds()
            if 0 < dt_s <= 5:
                ratio = hr / lthr_bpm
                val = (ratio * ratio) * UNIT * dt_s
                if hr > lthr_bpm:
                    hi += val
                else:
                    lo += val
        prev_ts = ts
    return lo * k_low, hi * k_high


def compute_hr_xss(hr_rows: list, lthr_bpm: float | None = None) -> float:
    """Suma Low+High -- zachowane dla zgodnosci wstecz."""
    lo, hi = compute_hr_xss_split(hr_rows, lthr_bpm=lthr_bpm)
    return lo + hi
