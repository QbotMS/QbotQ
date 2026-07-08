"""Modul spinajacy -- progression: pelny dzienny szereg sygnatury ModelQ v2.

Laczy wszystkie filary w jeden przeplyw:
  activity_record (1Hz) --> XSS Low/High/Peak (xss.py, per jazda z modelq2_ride)
                        --> Training Load 3-system (training_load.py, EWMA)
                        --> dzienna sygnatura (decay.py, dryf za forma wokol WIELU kotwic)
                        --> zapis do modelq2_signature (sygnatura + CTL/ATL/TSB)

To jest odpowiednik cp_v3 dla starego modelu, ale dla pelnej sygnatury (TP+HIE+PP)
i z dzienna forma. Zwalidowane vs Xert na 272 dniach: HIE ~2.1kJ (3 kotwice), TP ~7W, PP ~30W.

FORMA (CTL/ATL/TSB) -- wlasna logika MQ2 (nie stary agregat):
  CTL = tl_total  (suma TL Low+High+Peak, chroniczne, tau=42) -- odpowiednik CTL/fitness
  ATL = rl_total  (suma RL Low+High+Peak, ostre, tau=7)       -- odpowiednik ATL/zmeczenie
  TSB = CTL - ATL                                              -- odpowiednik TSB/forma
  + rozbicie tl_low/tl_high/tl_peak (wyroznik MQ2 -- 3 systemy energetyczne osobno).
tl_total zwalidowane vs Xert training_load (~4% bledu, dynamika sledzi).

Kotwice = dni z przebiciem (max_effort) i jazda 1Hz, sygnatura z benchmarku Xerta.
Domyslne 3: 2025-12-27 (zima), 2026-03-29 (wiosna), 2026-06-20 (lato) -- rozlozone w czasie.

Uzycie: build_and_store() -> wypelnia modelq2_signature dzien-po-dniu (auto-kotwice).
"""
from __future__ import annotations
import datetime as dt

from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2.decay import (
    DecayAnchor, build_signature_series_multi, make_anchor)
from fitmodel.modelq2.training_load import build_load_series

# domyslne dni-kotwice (przebicie + jazda 1Hz), sygnatura brana z modelq2_xert_bench
DEFAULT_ANCHOR_DAYS = [dt.date(2025, 12, 27), dt.date(2026, 3, 29), dt.date(2026, 6, 20)]


def _load_xss_by_day(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT ride_date, xss_low, xss_high, xss_peak FROM qbot_v2.modelq2_ride ORDER BY ride_date")
    return {d: (float(l), float(h), float(p)) for d, l, h, p in cur.fetchall()}


def _load_tp_by_day(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT day, cp_v3_w FROM qbot_v2.fitmodel_daily WHERE cp_v3_w IS NOT NULL ORDER BY day")
    return {d: float(t) for d, t in cur.fetchall()}


def _build_anchors(conn, loads_by_day, anchor_days=None) -> list:
    """Buduje kotwice z benchmarku Xerta na wskazane dni."""
    anchor_days = anchor_days or DEFAULT_ANCHOR_DAYS
    cur = conn.cursor()
    anchors = []
    for ad in anchor_days:
        if ad not in loads_by_day:
            continue
        cur.execute("SELECT tp_w, hie_kj, pp_w FROM qbot_v2.modelq2_xert_bench WHERE day=%s", (ad,))
        r = cur.fetchone()
        if not r:
            continue
        sig = Signature.from_kj(tp_w=float(r[0]), hie_kj=float(r[1]), pp_w=float(r[2]))
        anchors.append(make_anchor(ad, sig, loads_by_day))
    return anchors


def ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.modelq2_signature (
        day date PRIMARY KEY,
        tp_w real NOT NULL,
        hie_kj real NOT NULL,
        pp_w real NOT NULL,
        ltp_w real,
        source text DEFAULT 'decay',
        updated_at timestamptz DEFAULT now()
    )""")
    # forma (CTL/ATL/TSB) + rozbicie 3-system -- dokladane do istniejacej tabeli
    for col in ("ctl real", "atl real", "tsb real",
                "tl_low real", "tl_high real", "tl_peak real"):
        cur.execute(f"ALTER TABLE qbot_v2.modelq2_signature ADD COLUMN IF NOT EXISTS {col}")
    conn.commit()


def build_and_store(conn=None, anchor_days=None) -> dict:
    """Buduje dzienna sygnature + forme (wiele kotwic) i zapisuje do modelq2_signature.
    Zwraca statystyki (ile dni, zakres, ile kotwic)."""
    own = conn is None
    if own:
        conn = _db_connect()
    try:
        ensure_table(conn)
        xss_by_day = _load_xss_by_day(conn)
        tp_by_day = _load_tp_by_day(conn)
        loads_by_day = {dl.day: dl for dl in build_load_series(xss_by_day)}
        anchors = _build_anchors(conn, loads_by_day, anchor_days)
        if not anchors:
            return {"error": "brak kotwic"}
        sigs = build_signature_series_multi(xss_by_day, anchors, tp_by_day=tp_by_day)

        cur = conn.cursor()
        n = 0
        for day in sorted(sigs):
            s = sigs[day]
            dl = loads_by_day.get(day)
            # forma z Training Load (suma 3 systemow)
            if dl:
                ctl = dl.low.tl + dl.high.tl + dl.peak.tl
                atl = dl.low.rl + dl.high.rl + dl.peak.rl
                tsb = ctl - atl
                tl_low, tl_high, tl_peak = dl.low.tl, dl.high.tl, dl.peak.tl
            else:
                ctl = atl = tsb = tl_low = tl_high = tl_peak = None
            cur.execute("""INSERT INTO qbot_v2.modelq2_signature
                (day, tp_w, hie_kj, pp_w, ltp_w, ctl, atl, tsb, tl_low, tl_high, tl_peak, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'decay')
                ON CONFLICT (day) DO UPDATE SET
                  tp_w=EXCLUDED.tp_w, hie_kj=EXCLUDED.hie_kj, pp_w=EXCLUDED.pp_w,
                  ltp_w=EXCLUDED.ltp_w, ctl=EXCLUDED.ctl, atl=EXCLUDED.atl, tsb=EXCLUDED.tsb,
                  tl_low=EXCLUDED.tl_low, tl_high=EXCLUDED.tl_high, tl_peak=EXCLUDED.tl_peak,
                  source='decay', updated_at=now()""",
                (day, round(s.tp_w, 1), round(s.hie_kj, 2), round(s.pp_w, 1), round(s.ltp_w, 1),
                 round(ctl, 1) if ctl is not None else None,
                 round(atl, 1) if atl is not None else None,
                 round(tsb, 1) if tsb is not None else None,
                 round(tl_low, 1) if tl_low is not None else None,
                 round(tl_high, 2) if tl_high is not None else None,
                 round(tl_peak, 3) if tl_peak is not None else None))
            n += 1
        conn.commit()
        days = sorted(sigs)
        return {"stored": n, "from": str(days[0]) if days else None,
                "to": str(days[-1]) if days else None, "anchors": len(anchors)}
    finally:
        if own:
            conn.close()


def latest_signature(conn=None) -> Signature | None:
    """Najnowsza dzienna sygnatura z modelq2_signature."""
    own = conn is None
    if own:
        conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tp_w, hie_kj, pp_w FROM qbot_v2.modelq2_signature ORDER BY day DESC LIMIT 1")
        r = cur.fetchone()
        if not r:
            return None
        return Signature.from_kj(tp_w=float(r[0]), hie_kj=float(r[1]), pp_w=float(r[2]))
    finally:
        if own:
            conn.close()
