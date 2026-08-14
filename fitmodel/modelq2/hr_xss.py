"""XSS z tetna (fallback dla jazd w kwarantannie miernika mocy).

DLACZEGO ISTNIEJE
-----------------
Kwarantanna (fitmodel_ride_quarantine) wylacza jazde z kotwic CP/W', ale XSS
liczony z watow i tak karmil CTL -> TP (odkryte 14.08.2026: sycylijskie jazdy
z dryfem zera zawyzaly obciazenie i sygnature). Tetno jest niezalezne od
miernika mocy -- dla jazd w AKTYWNEJ kwarantannie XSS liczymy z HR, zeby jazda
liczyla sie do obciazenia (decyzja Michala 11.08), ale uczciwa waluta.

FORMULA
-------
hrXSS = CAL_K * suma po sekundach JAZDY: (HR/LTHR)^2 * UNIT
  - UNIT = 100/3600 (spojnie z xss.py: 1h na progu = 100 XSS)
  - kwadrat = klasyczne hrTSS (Coggan)
  - JAZDA = probki z v >= 1 m/s. Bez filtra postoje (HR 80-100 na
    przerwie) zawyzaly wynik o 30-50%. Prog 3 m/s (jak w guardzie)
    odrzucony: wycinal strome podjazdy (7-9 km/h), czyli najciezsza prace.
  - CAL_K = 0.69: mediana (XSS_power / hrXSS_raw) z 36 czystych jazd
    05-08.2026 (miernik OK, bez kwarantanny) = 0.686, identyczna dla
    dlugich jazd (>100 XSS, n=19). Czyste jazdy z upalu: 0.645 i 0.677.
    Rozrzut dlugich 0.54-0.82 -- to fallback, nie precyzja; blad
    kilkanascie %% vs +18..42%% bledu watow.
Calosc ladowana w Low -- z tetna nie da sie uczciwie wydzielic High/Peak
(HR jest wolne i sie opoznia), wiec nie udajemy, ze wiemy wiecej niz wiemy.

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
CAL_K = 0.69            # kalibracja do waluty XSS (patrz naglowek)


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


def compute_hr_xss(hr_rows: list, lthr_bpm: float = LTHR_BPM,
                   cal_k: float = CAL_K) -> float:
    """hrXSS (odpowiednik xss_low) z probek 1Hz. Dziury > 5 s pomijane."""
    total = 0.0
    prev_ts = None
    for row in hr_rows:
        ts, hr, v = row[0], row[1], (row[2] if len(row) > 2 else None)
        if (prev_ts is not None and hr is not None and hr >= HR_MIN
                and v is not None and v >= V_MIN_MPS):
            dt_s = (ts - prev_ts).total_seconds()
            if 0 < dt_s <= 5:
                ratio = hr / lthr_bpm
                total += (ratio * ratio) * UNIT * dt_s
        prev_ts = ts
    return total * cal_k
