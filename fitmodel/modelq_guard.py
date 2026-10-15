from __future__ import annotations

"""Bezpieczniki ModelQ (MODELQ-PRZEGLAD, decyzja Michala 2026-10-14). TYLKO Telegram, NIC nie zmienia.

Po co: przez 3 miesiace HIE siedzialo na ograniczniku i nikt tego nie widzial; bledy wychodzily dopiero przy jezdzie.
Raz w tygodniu (poniedzialek) sprawdza:
  A. ogranicznik: TP lub HIE na granicy dryfu wzgledem najblizszej kotwicy przez >= CLAMP_DAYS dni z rzedu
  B. stara kotwica: ostatnia kotwica starsza niz ANCHOR_MAX_DAYS
Raz w miesiacu (pierwszy poniedzialek) sprawdzian z Xertem (Xert = niezalezny sprawdzian, nic nie przenosimy):
  C. |TP ModelQ - TP Xert| > TP_DIFF_PCT %  -> propozycja przegladu (decyzja Michala)
     HIE: tylko informacja -- HIE Xerta jest znanie zawyzone przez XSS z wadliwego miernika 07-08.2026 (24,2 vs 20 kJ);
     HIE ModelQ kontroluje pytanie o odczucie (fitmodel/wbal_feel.py).
Ten sam alert najwyzej raz na DEDUP_DAYS dni (tabela qbot_v2.modelq_guard_log).
"""

import sys
import datetime as dt

sys.path.insert(0, "/opt/qbot/app")

CLAMP_DAYS = 14
ANCHOR_MAX_DAYS = 90
TP_DIFF_PCT = 5.0
DEDUP_DAYS = 7
EPS = 0.02   # tolerancja trafienia w granice (proporcja)

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.modelq_guard_log (
    id bigserial PRIMARY KEY, check_key text, message text, sent_at timestamptz DEFAULT now())"""


def at_bound(value: float, anchor: float, lo: float, hi: float) -> bool:
    """Czy wartosc lezy na granicy dryfu (anchor*lo lub anchor*hi) z tolerancja EPS (wzgledna do kotwicy)."""
    if not value or not anchor:
        return False
    r = value / anchor
    return abs(r - lo) < EPS * lo or abs(r - hi) < EPS * hi


def clamp_streak(days: list[tuple], lo: float, hi: float) -> int:
    """days: [(wartosc, wartosc_kotwicy)] od najnowszego. Ile kolejnych dni na granicy."""
    n = 0
    for v, a in days:
        if at_bound(v, a, lo, hi):
            n += 1
        else:
            break
    return n


def tp_diff_pct(tp_mq: float | None, tp_x: float | None) -> float | None:
    if not tp_mq or not tp_x:
        return None
    return round(100.0 * (tp_mq - tp_x) / tp_x, 1)


def _pl(x: float, sign: bool = False) -> str:
    return (("%+.1f" if sign else "%.1f") % x).replace(".", ",")


def _send(text: str) -> None:
    from fitmodel.power_meter_guard import _telegram_send
    _telegram_send(text)


def run(conn, today: dt.date | None = None, send=None, force: bool = False, dry: bool = False) -> dict:
    from fitmodel.modelq2 import decay
    today = today or dt.date.today()
    send = send or _send
    weekly = force or today.weekday() == 0
    monthly = force or (today.weekday() == 0 and today.day <= 7)
    if not weekly:
        return {"modelq_guard": "nie dzis (poniedzialki)"}
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("SELECT day, tp_w, hie_kj FROM qbot_v2.modelq2_anchor ORDER BY day")
    anchors = cur.fetchall()
    cur.execute("SELECT day, tp_w, hie_kj FROM qbot_v2.modelq2_signature WHERE day > %s ORDER BY day DESC",
                (today - dt.timedelta(days=60),))
    sig = cur.fetchall()
    alerts = []

    def nearest(d):
        return min(anchors, key=lambda a: abs((d - a[0]).days))

    hie_days = [(float(h), float(nearest(d)[2])) for d, t, h in sig]
    tp_days = [(float(t), float(nearest(d)[1])) for d, t, h in sig]
    s_hie = clamp_streak(hie_days, decay.HIE_DRIFT_MIN, decay.HIE_DRIFT_MAX)
    s_tp = clamp_streak(tp_days, decay.TP_DRIFT_MIN, decay.TP_DRIFT_MAX)
    if s_hie >= CLAMP_DAYS:
        alerts.append(("clamp_hie", "HIE (zapas) od %d dni stoi na granicy bezpiecznika — wartość wyznacza ogranicznik, "
                                    "nie dane. Potrzebna nowa kotwica." % s_hie))
    if s_tp >= CLAMP_DAYS:
        alerts.append(("clamp_tp", "Próg (TP) od %d dni stoi na granicy bezpiecznika — potrzebna nowa kotwica." % s_tp))
    last_anchor = anchors[-1][0] if anchors else None
    if last_anchor and (today - last_anchor).days > ANCHOR_MAX_DAYS:
        alerts.append(("anchor_old", "Ostatnia kotwica ModelQ: %s (%d dni temu). Model jedzie na samym dryfie — "
                                     "warto ją odświeżyć." % (last_anchor.strftime("%d.%m.%Y"), (today - last_anchor).days)))
    info = None
    if monthly:
        cur.execute("SELECT day, tp_w, hie_kj FROM qbot_v2.modelq2_xert_bench WHERE tp_w IS NOT NULL AND valid IS NOT FALSE ORDER BY day DESC LIMIT 1")
        x = cur.fetchone()
        mq_tp = float(sig[0][1]) if sig else None
        mq_hie = float(sig[0][2]) if sig else None
        if x:
            dpct = tp_diff_pct(mq_tp, float(x[1]))
            info = "Sprawdzian z Xertem (%s): próg ModelQ %.0f W vs Xert %.0f W (%s%%), zapas %s vs %s kJ." % (
                x[0].strftime("%d.%m"), mq_tp, float(x[1]), _pl(dpct or 0, True), _pl(mq_hie or 0), _pl(float(x[2] or 0)))
            if dpct is not None and abs(dpct) > TP_DIFF_PCT:
                alerts.append(("xert_tp", info + " Rozjazd progu > %.0f%% — proponuję przegląd (decyzja Twoja)." % TP_DIFF_PCT))
                info = None
    sent = []
    for key, text in alerts:
        cur.execute("SELECT 1 FROM qbot_v2.modelq_guard_log WHERE check_key=%s AND sent_at > now() - interval '%s days'"
                    % ("%s", DEDUP_DAYS), (key,))
        if cur.fetchone():
            continue
        try:
            send("🛡️ ModelQ · bezpiecznik\n" + text)
            if not dry:
                cur.execute("INSERT INTO qbot_v2.modelq_guard_log (check_key, message) VALUES (%s,%s)", (key, text))
            sent.append(key)
        except Exception as exc:
            print("modelq_guard: telegram error: %s" % exc)
    if info:
        try:
            send("🛡️ ModelQ · comiesięczny sprawdzian\n" + info + " W normie.")
            if not dry:
                cur.execute("INSERT INTO qbot_v2.modelq_guard_log (check_key, message) VALUES (%s,%s)", ("xert_info", info))
        except Exception as exc:
            print("modelq_guard: telegram error: %s" % exc)
    if not dry:
        conn.commit()
    return {"hie_streak": s_hie, "tp_streak": s_tp, "last_anchor": str(last_anchor), "alerts": [k for k, _ in alerts],
            "sent": sent, "monthly": monthly}


if __name__ == "__main__":
    # reczny podglad BEZ Telegrama
    from fitmodel.ftp_resolver import _db_connect
    c = _db_connect()
    print(run(c, force=True, dry=True, send=lambda t: print("TG>", t)))
    c.rollback(); c.close()
