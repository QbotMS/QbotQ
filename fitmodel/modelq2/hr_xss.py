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
- LTHR=132 bpm: kanon z QExt2/DECISIONS (strefy Coggan %%LTHR).
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


def compute_hr_xss_split(hr_rows: list, lthr_bpm: float = LTHR_BPM,
                         k_low: float = K_LOW, k_high: float = K_HIGH) -> tuple:
    """(xss_low, xss_high) z probek 1Hz. Dziury > 5 s pomijane."""
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


def compute_hr_xss(hr_rows: list, lthr_bpm: float = LTHR_BPM) -> float:
    """Suma Low+High -- zachowane dla zgodnosci wstecz."""
    lo, hi = compute_hr_xss_split(hr_rows, lthr_bpm=lthr_bpm)
    return lo + hi
