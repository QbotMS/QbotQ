"""Modul spinajacy -- progression: pelny dzienny szereg sygnatury ModelQ v2.

Laczy wszystkie filary w jeden przeplyw:
  activity_record (1Hz) --> XSS Low/High/Peak (xss.py, per jazda z modelq2_ride)
                        --> Training Load 3-system (training_load.py, EWMA)
                        --> dzienna sygnatura (decay.py, dryf za forma wokol kotwicy)
                        --> zapis do modelq2_signature

To jest odpowiednik cp_v3 dla starego modelu, ale dla pelnej sygnatury (TP+HIE+PP)
i z dzienna forma. Zwalidowane vs Xert na 272 dniach: HIE ~2.4kJ, TP ~7W(mediana), PP ~31W.

Uzycie: build_and_store(anchor, tp_by_day) -> wypelnia modelq2_signature dzien-po-dniu.
"""
from __future__ import annotations
import datetime as dt

from fitmodel.ftp_resolver import _db_connect
from fitmodel.modelq2.signature import Signature
from fitmodel.modelq2.decay import DecayAnchor, build_signature_series


def _load_xss_by_day(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT ride_date, xss_low, xss_high, xss_peak FROM qbot_v2.modelq2_ride ORDER BY ride_date")
    return {d: (float(l), float(h), float(p)) for d, l, h, p in cur.fetchall()}


def _load_tp_by_day(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT day, cp_v3_w FROM qbot_v2.fitmodel_daily WHERE cp_v3_w IS NOT NULL ORDER BY day")
    return {d: float(t) for d, t in cur.fetchall()}


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
    conn.commit()


def build_and_store(anchor: DecayAnchor, conn=None) -> dict:
    """Buduje dzienna sygnature dla calego okna i zapisuje do modelq2_signature.
    Zwraca statystyki (ile dni, zakres)."""
    own = conn is None
    if own:
        conn = _db_connect()
    try:
        ensure_table(conn)
        xss_by_day = _load_xss_by_day(conn)
        tp_by_day = _load_tp_by_day(conn)
        sigs = build_signature_series(xss_by_day, anchor, tp_by_day=tp_by_day)

        cur = conn.cursor()
        n = 0
        for day in sorted(sigs):
            s = sigs[day]
            cur.execute("""INSERT INTO qbot_v2.modelq2_signature (day, tp_w, hie_kj, pp_w, ltp_w, source)
                VALUES (%s,%s,%s,%s,%s,'decay')
                ON CONFLICT (day) DO UPDATE SET
                  tp_w=EXCLUDED.tp_w, hie_kj=EXCLUDED.hie_kj, pp_w=EXCLUDED.pp_w,
                  ltp_w=EXCLUDED.ltp_w, source='decay', updated_at=now()""",
                (day, round(s.tp_w, 1), round(s.hie_kj, 2), round(s.pp_w, 1), round(s.ltp_w, 1)))
            n += 1
        conn.commit()
        days = sorted(sigs)
        return {"stored": n, "from": str(days[0]) if days else None,
                "to": str(days[-1]) if days else None}
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
