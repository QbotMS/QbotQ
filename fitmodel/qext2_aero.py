# -*- coding: utf-8 -*-
"""Pole AERO z QExt2 (Karoo) w QBocie -- zapis z pliku FIT i sprawdzian (2026-10-18).

QExt2 (docs/AERO.md w repo QExt2, od 0.4.1) zapisuje co sekunde 4 pola: qext2_aero_state (0 brak warunkow /
1 zbiera / 2 pewny), qext2_aero_dw_w (zmiana W vs poprzedni poziom), qext2_aero_cda (CdA biezacego poziomu),
qext2_aero_ref_cda (odniesienie). Pole liczy na zywo wlasnym, uproszczonym modelem (Crr 0,007, m = waga + 9 kg,
bez wiatru) -- QBot NIE uzywa tych pol do liczenia CdA, tylko do SPRAWDZENIA, jak pole dzialalo (Forma > Centrum CdA).
Tabela qbot_v2.qext2_aero_record (1 Hz). Zapis: fit_ingest po podsumowaniu QExt2 (store), recznie: backfill(fit_path).
Od QExt2 0.4.2 (AERO v3, 19.10): + ver (3), conf (0 brak / 1 niska / 2 dobra), wind_head (m/s uzyty w rownaniu),
surface (0 nieznana / 1 asfalt / 2 szuter); w starszych jazdach NULL.
"""
from __future__ import annotations

import datetime as dt

FIELDS = ("qext2_aero_state", "qext2_aero_dw_w", "qext2_aero_cda", "qext2_aero_ref_cda")
FIELDS_V3 = ("qext2_aero_ver", "qext2_aero_conf", "qext2_aero_wind_head", "qext2_aero_surface")

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.qext2_aero_record (
    external_id text NOT NULL,
    ts          timestamptz NOT NULL,
    state       smallint,
    dw_w        real,
    cda         real,
    ref_cda     real,
    PRIMARY KEY (external_id, ts))"""


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("ALTER TABLE qbot_v2.qext2_aero_record ADD COLUMN IF NOT EXISTS ver smallint, "
                    "ADD COLUMN IF NOT EXISTS conf smallint, ADD COLUMN IF NOT EXISTS wind_head real, "
                    "ADD COLUMN IF NOT EXISTS surface smallint")
    conn.commit()


def _utc(t):
    """Czas zapisany TAK SAMO jak w activity_record (naiwny czas UTC z FIT, baza traktuje go jak lokalny) -- inaczej
    sekundy pola AERO rozjezdzaja sie z danymi jazdy o 2 h (sprawdzone 18.10: activity_record 08:24+02 przy starcie 10:24)."""
    if t is None:
        return None
    return t.astimezone(dt.timezone.utc).replace(tzinfo=None) if t.tzinfo else t


def store(conn, ride_id: str, recs: list) -> int:
    """recs: rekordy z fit_ingest.parse_fit_qext2_records (musza miec 'timestamp' i pola FIELDS)."""
    rows = [(str(ride_id), _utc(r.get("timestamp")), r.get("qext2_aero_state"), r.get("qext2_aero_dw_w"),
             r.get("qext2_aero_cda"), r.get("qext2_aero_ref_cda"), r.get("qext2_aero_ver"), r.get("qext2_aero_conf"),
             r.get("qext2_aero_wind_head"), r.get("qext2_aero_surface"))
            for r in recs if r.get("timestamp") is not None and r.get("qext2_aero_state") is not None]
    if not rows:
        return 0
    ensure_table(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM qbot_v2.qext2_aero_record WHERE external_id=%s", (str(ride_id),))
        try:
            from psycopg2.extras import execute_values
            execute_values(cur, "INSERT INTO qbot_v2.qext2_aero_record (external_id, ts, state, dw_w, cda, ref_cda, ver, conf, "
                                "wind_head, surface) VALUES %s "
                                "ON CONFLICT DO NOTHING", rows, page_size=2000)
        except ImportError:
            cur.executemany("INSERT INTO qbot_v2.qext2_aero_record (external_id, ts, state, dw_w, cda, ref_cda, ver, conf, "
                            "wind_head, surface) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", rows)
    conn.commit()
    return len(rows)


def backfill(conn, fit_path: str, ride_id: str) -> int:
    from fitmodel.fit_ingest import parse_fit_qext2_records
    return store(conn, ride_id, parse_fit_qext2_records(fit_path))


def ride_check(cur, eid: str, qbot_cda: float | None, win_ts=None, win_cda=None) -> dict | None:
    """Sprawdzian jednej jazdy: czas w stanach, wykryte zmiany (km, W), CdA pola vs QBot, zgodnosc na odcinkach QBota.
    win_ts: [(t0, t1)] epoch s odcinkow QBota; win_cda: CdA QBota na tych odcinkach."""
    cur.execute("SELECT extract(epoch from ts), state, dw_w, cda, ref_cda FROM qbot_v2.qext2_aero_record "
                "WHERE external_id=%s ORDER BY ts", (eid,))
    rec = [(float(a), b, c, d, e) for a, b, c, d, e in cur.fetchall()]
    if not rec:
        return None
    n = len(rec)
    share = {s: round(100.0 * sum(1 for r in rec if r[1] == s) / n, 1) for s in (0, 1, 2)}
    cur.execute("SELECT extract(epoch from ts), distance_m FROM qbot_v2.activity_record WHERE external_id=%s "
                "AND ts IS NOT NULL ORDER BY ts", (eid,))
    dist = [(float(a), b) for a, b in cur.fetchall() if b is not None]
    import bisect
    dts = [d[0] for d in dist]

    def km(t):
        if not dist:
            return None
        j = max(0, min(len(dist) - 1, bisect.bisect_left(dts, t)))
        return round(dist[j][1] / 1000, 1)

    # zmiana wykryta przez pole = poczatek odcinka, gdy pole pokazuje dW != 0 (odniesienie rozne od biezacego poziomu),
    # albo nowe odniesienie w trakcie takiego odcinka. dW = 0 przy ref == cda to tylko budowanie poziomu, nie zmiana.
    changes, prev_dw, prev_ref = [], 0.0, None
    for t, s, dw, c, ref in rec:
        dwv = float(dw) if dw is not None else 0.0
        on = s in (1, 2) and abs(dwv) >= 1 and ref and ref > 0
        if on and (abs(prev_dw) < 1 or (prev_ref is not None and abs(ref - prev_ref) > 1e-6)):
            changes.append({"km": km(t), "dw": round(dwv), "cda": None if c is None else round(float(c), 3),
                            "ref": round(float(ref), 3), "pewny": s == 2})
        prev_dw = dwv if s in (1, 2) else 0.0
        prev_ref = ref if on else None
    lvl = sorted(float(c) for t, s, dw, c, ref in rec if s in (1, 2) and c is not None and 0.1 <= c <= 1.5)
    med = lvl[len(lvl) // 2] if lvl else None
    agree = None
    if win_ts and win_cda is not None and len(win_ts) >= 8:
        tsl = [r[0] for r in rec]
        xs, ys = [], []
        for (t0, t1), qc in zip(win_ts, win_cda):
            i0, i1 = bisect.bisect_left(tsl, t0), bisect.bisect_right(tsl, t1)
            v = sorted(float(r[3]) for r in rec[i0:i1] if r[1] in (1, 2) and r[3] is not None and 0.1 <= r[3] <= 1.5)
            if len(v) >= 10:
                xs.append(float(qc)); ys.append(v[len(v) // 2])
        if len(xs) >= 8:
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
            sxx = sum((a - mx) ** 2 for a in xs) ** 0.5
            syy = sum((b - my) ** 2 for b in ys) ** 0.5
            diffs = sorted(b - a for a, b in zip(xs, ys))
            agree = {"n": len(xs), "r": round(sxy / (sxx * syy), 2) if sxx and syy else None,
                     "diff_med": round(diffs[len(diffs) // 2], 3)}
    return {"seconds": n, "share": share, "changes": changes[:40], "n_changes": len(changes),
            "field_cda_med": None if med is None else round(med, 3),
            "qbot_cda": None if qbot_cda is None else round(float(qbot_cda), 3), "agree": agree}
