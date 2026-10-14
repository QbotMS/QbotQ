"""Przelom CP (breakthrough) z krzywej moc-czas -- z potwierdzeniem na Telegramie (decyzja Michala 2026-10-08, wariant B).

DLACZEGO: TP/CP w ModelQ to model (kotwice + dryf za CTL); sam nie wykrywa, ze realnie jestes mocniejszy.
METODA: krzywa modelu P(d) = TP + W'/d (W' = HIE). Jesli najlepsza moc jazdy MMP(d) dla d = 2/5/10/20 min
przekracza P(d) o > MARGIN, model jest za nisko => propozycja nowej sygnatury (najmniejsza zgodna z jazda):
  krotkie (2-5 min) podnosza W', dlugie (10-20 min) podnosza TP. Limity: TP +3 %, W' +15 % na zdarzenie.
ODRZUCONE (backtest 08.10): wykrywanie z W'bal bez obcinania -- 10 falszywych "przelomow" na dlugich jazdach
z wieloma zrywami (artefakt regeneracji Skiby), TP dzis 248.8 zamiast 239.5. Krzywa moc-czas: 0 przelomow w 10 mies.
BEZPIECZNIKI: tylko jazdy ze sprawnym miernikiem (bez kwarantanny, poza METER_BAD, meter_phys < 1.15), tylko w gore.
PRZEPLYW (B): daily_job -> kandydat w qbot_v2.cp_breakthrough -> Telegram "#NN ... NN TAK / NN NIE" (48 h)
-> TAK: kotwica w modelq2_anchor (note 'przelom (zatwierdzony)') + przeliczenie sygnatury/publikacja.
TODO [CP-DYNAMICZNE]: po >= 3 przelomach zatwierdzonych bez korekty przejsc na automat (wariant A).
"""
from __future__ import annotations

import datetime as dt
import json

DURS = (120, 300, 600, 1200)
MARGIN = 0.01
MAX_TP_REL, MAX_HIE_REL = 0.03, 0.15
METER_RATIO_MAX = 1.15
TTL_MIN = 48 * 60
ACTION = "confirm_cp_breakthrough"

DDL = [
    """CREATE TABLE IF NOT EXISTS qbot_v2.cp_breakthrough (id bigserial PRIMARY KEY, external_id text, ride_date date,
         tp_old real, hie_old_kj real, pp real, tp_new real, hie_new_kj real, evidence jsonb, status text DEFAULT 'pending',
         pending_action_id integer, created_at timestamptz DEFAULT now(), decided_at timestamptz)""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.cp_bt_checked (external_id text PRIMARY KEY, ride_date date, result text,
         checked_at timestamptz DEFAULT now())""",
]


def _t(rows):
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def curve(tp, hie_kj, d) -> float:
    return float(tp) + float(hie_kj) * 1000.0 / float(d)


def propose(tp, hie_kj, mmp: dict) -> dict | None:
    """mmp: {d_s: W}. Zwraca propozycje (tp_new, hie_new_kj, evidence) albo None gdy brak przelomu."""
    ev = []
    for d in DURS:
        m = mmp.get(d)
        if m and m > curve(tp, hie_kj, d) * (1 + MARGIN):
            ev.append({"d_s": d, "mmp_w": round(float(m), 1), "model_w": round(curve(tp, hie_kj, d), 1)})
    if not ev:
        return None
    t, h = float(tp), float(hie_kj)
    for _ in range(3):                                   # podnies W' dla krotkich, TP dla dlugich; powtorz az zgodne
        for d in DURS:
            m = mmp.get(d)
            if not m or m <= curve(t, h, d):
                continue
            if d <= 300:
                h = max(h, (m - t) * d / 1000.0)
            else:
                t = max(t, m - h * 1000.0 / d)
    cap = t > tp * (1 + MAX_TP_REL) or h > hie_kj * (1 + MAX_HIE_REL)
    t, h = min(t, tp * (1 + MAX_TP_REL)), min(h, hie_kj * (1 + MAX_HIE_REL))
    return {"tp_new": round(t, 1), "hie_new_kj": round(h, 2), "evidence": ev, "limit": cap}


def ensure(conn):
    cur = conn.cursor()
    for q in DDL:
        cur.execute(q)
    conn.commit()


def _clean_rides(conn, since):
    from fitmodel.lthr import _bad
    cur = conn.cursor()
    cur.execute("""SELECT t.external_id, t.date, t.mmp_120_w, t.mmp_300_w, t.mmp_600_w, t.mmp_1200_w
                   FROM qbot_v2.training_sessions t
                   WHERE t.sport_type IN ('cycling','gravel_cycling') AND t.date >= %s AND t.mmp_120_w IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.cp_bt_checked c WHERE c.external_id = t.external_id)
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                                     WHERE q.external_id = t.external_id AND q.released IS NULL)
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.meter_phys m WHERE m.external_id = t.external_id
                                     AND COALESCE(m.ratio, m.ratio_weak) >= %s)
                   ORDER BY t.date""", (since, METER_RATIO_MAX))
    return [r for r in _t(cur.fetchall()) if not _bad(r[1])]


def _sig_before(conn, day):
    cur = conn.cursor()
    cur.execute("SELECT tp_w, hie_kj, pp_w FROM qbot_v2.modelq2_signature WHERE day < %s ORDER BY day DESC LIMIT 1", (day,))
    r = cur.fetchone()
    return tuple(float(x) for x in _t([r])[0]) if r else None


def _ask(conn, bt_id, ride_date, tp, hie, tp_new, hie_new, ev) -> int | None:
    import qbot_config as cfg
    import qbot_qcal_telegram as tg
    chat = str(cfg.TELEGRAM_CHAT_ID)
    dd = ride_date.strftime("%d.%m")
    pv = "Przełom %s: CP %.0f -> %.0f W, W' %.1f -> %.1f kJ" % (dd, tp, tp_new, hie, hie_new)
    res = tg.upsert_pending_action(chat_id=chat, action_type=ACTION, payload={"bt_id": bt_id}, preview=pv,
                                   idem_key="cpbt:%d" % bt_id, expires_minutes=TTL_MIN)
    pid = res.get("pending_action_id")
    if not pid:
        return None
    lines = "; ".join("%d min: %.0f W (model %.0f W)" % (e["d_s"] // 60, e["mmp_w"], e["model_w"]) for e in ev)
    tg.send_message(chat, "#%d 💥 Przełom na jeździe %s — pojechałeś mocniej niż model uznaje za Twoje maksimum: %s.\n"
                          "Propozycja: CP %.0f → %.0f W, zapas W′ %.1f → %.1f kJ.\n"
                          "Odpowiedz: %d TAK (zapisz nowy próg) albo %d NIE. Ważne 48 h."
                    % (pid, dd, lines, tp, tp_new, hie, hie_new, pid, pid))
    return pid


def run_daily(conn, since=None, ask=True) -> dict:
    """Krok daily_job: sprawdz nowe czyste jazdy, kandydata zapisz i zapytaj na Telegramie."""
    ensure(conn)
    since = since or (dt.date.today() - dt.timedelta(days=14))
    cur = conn.cursor()
    out = {"sprawdzone": 0, "przelomy": []}
    for eid, d, m2, m5, m10, m20 in _clean_rides(conn, since):
        sig = _sig_before(conn, d)
        if not sig:
            continue
        tp, hie, pp = sig
        p = propose(tp, hie, {120: m2, 300: m5, 600: m10, 1200: m20})
        out["sprawdzone"] += 1
        cur.execute("INSERT INTO qbot_v2.cp_bt_checked (external_id, ride_date, result) VALUES (%s,%s,%s) "
                    "ON CONFLICT (external_id) DO NOTHING", (eid, d, "przelom" if p else "brak"))
        if not p:
            continue
        cur.execute("""INSERT INTO qbot_v2.cp_breakthrough (external_id, ride_date, tp_old, hie_old_kj, pp, tp_new, hie_new_kj, evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (eid, d, tp, hie, pp, p["tp_new"], p["hie_new_kj"], json.dumps(p)))
        bt_id = int(_t([cur.fetchone()])[0][0])
        conn.commit()
        pid = None
        if ask:
            try:
                pid = _ask(conn, bt_id, d, tp, hie, p["tp_new"], p["hie_new_kj"], p["evidence"])
            except Exception as e:  # noqa: BLE001
                out.setdefault("bledy", []).append(str(e)[:160])
            cur.execute("UPDATE qbot_v2.cp_breakthrough SET pending_action_id=%s WHERE id=%s", (pid, bt_id))
        out["przelomy"].append({"id": bt_id, "dzien": str(d), **p, "pytanie": pid})
    conn.commit()
    return out


def approve(bt_id: int) -> dict:
    """Wywolywane z Telegrama (NN TAK): kotwica + przeliczenie sygnatury i publikacja."""
    from fitmodel.ftp_resolver import _db_connect
    from fitmodel.modelq2.progression import build_and_store
    from fitmodel.modelq2.publish import publish_to_daily
    conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ride_date, tp_old, hie_old_kj, pp, tp_new, hie_new_kj, status FROM qbot_v2.cp_breakthrough WHERE id=%s", (bt_id,))
        r = cur.fetchone()
        if not r:
            return {"status": "error", "error": "brak przelomu #%s" % bt_id}
        d, tp0, h0, pp, tp1, h1, st = _t([r])[0]
        if st != "pending":
            return {"status": "error", "error": "przelom #%s ma status %s" % (bt_id, st)}
        note = "przelom (zatwierdzony Telegram): TP %.1f->%.1f W, HIE %.2f->%.2f kJ, cp_breakthrough #%s" % (tp0, tp1, h0, h1, bt_id)
        cur.execute("SELECT 1 FROM qbot_v2.modelq2_anchor WHERE day=%s", (d,))
        if cur.fetchone():
            cur.execute("UPDATE qbot_v2.modelq2_anchor SET tp_w=%s, hie_kj=%s, pp_w=%s, note=%s, frozen_at=now() WHERE day=%s",
                        (tp1, h1, pp, note, d))
        else:
            cur.execute("SELECT ctl FROM qbot_v2.modelq2_signature WHERE day=%s", (d,))
            ctl = cur.fetchone()
            cur.execute("INSERT INTO qbot_v2.modelq2_anchor (day, tp_w, hie_kj, pp_w, ctl_anchor, note, frozen_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,now())", (d, tp1, h1, pp, _t([ctl])[0][0] if ctl else None, note))
        cur.execute("UPDATE qbot_v2.cp_breakthrough SET status='approved', decided_at=now() WHERE id=%s", (bt_id,))
        conn.commit()
        build_and_store(conn)
        publish_to_daily(conn)
        cur.execute("SELECT tp_w FROM qbot_v2.modelq2_signature ORDER BY day DESC LIMIT 1")
        tp_now = float(_t([cur.fetchone()])[0][0])
        return {"status": "OK", "tp_dzis": round(tp_now, 1), "kotwica": str(d)}
    finally:
        conn.close()


def decline(bt_id: int) -> None:
    from fitmodel.ftp_resolver import _db_connect
    conn = _db_connect()
    try:
        conn.cursor().execute("UPDATE qbot_v2.cp_breakthrough SET status='declined', decided_at=now() WHERE id=%s AND status='pending'", (bt_id,))
        conn.commit()
    finally:
        conn.close()
