"""Raport z jazdy po jezdzie: pytanie na Telegramie (10 min po koncu), worker W1->W2,
skrot na Telegram, mail ze szczegolami. DECISIONS 2026-09-12.

Stan w qbot_v2.ride_report_ask (ride_key, status: asked|yes|no|running|done|error, asked_at, answered_at, note).
"""
from __future__ import annotations
import os, sys, json, html, smtplib, subprocess
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_config as cfg

BASE_URL = "https://albert.cytr.us"
ASK_AFTER_MIN = 10
LOOKBACK_H = 36


def _db():
    from fitmodel.api import _db_connect
    return _db_connect()


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.ride_report_ask(
        ride_key text PRIMARY KEY, status text NOT NULL, asked_at timestamptz DEFAULT now(),
        answered_at timestamptz, note text)""")
    conn.commit()


def _tg(text: str, kb: dict | None = None) -> bool:
    from qbot_telegram_client import _api
    payload = {"chat_id": str(cfg.TELEGRAM_CHAT_ID), "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if kb:
        payload["reply_markup"] = kb
    r = _api("sendMessage", payload)
    return bool(r and r.get("ok"))


def _hm(sec):
    try:
        m = int(round(float(sec) / 60)); return "%d:%02d" % (m // 60, m % 60)
    except Exception:
        return "—"


def _summary_line(ride_key: str, name: str, summ: dict, w1: dict | None) -> str:
    L = (w1 or {}).get("load") or {}
    V = lambda x: (x or {}).get("value") if isinstance(x, dict) else x
    dist = V(L.get("dist_km")) or (float(summ.get("distance") or 0) / 1000.0)
    dur = V(L.get("dur_moving_s")) or summ.get("duration")
    avg = V(L.get("avg_p_w")) or summ.get("averagePower")
    hr = ((w1 or {}).get("physio") or {}).get("hr_avg", {}).get("value") if w1 else summ.get("averageHR")
    xss = V(L.get("xss"))
    wmin = ((w1 or {}).get("wprime") or {}).get("wbal_min_pct", {}).get("value") if w1 else None
    parts = ["%.1f km" % float(dist) if dist else None, _hm(dur) if dur else None,
             "%d W" % round(float(avg)) if avg else None, "tętno %d" % round(float(hr)) if hr else None]
    l2 = [("obciążenie %d" % round(float(xss))) if xss is not None else None,
          ("zapas min. %d%%" % round(float(wmin))) if wmin is not None else None]
    return "🚲 <b>Nowa jazda</b> — %s\n%s\n%s" % (html.escape(name or ride_key),
            " · ".join(p for p in parts if p), " · ".join(p for p in l2 if p))


def _load_w1(conn, ride_key):
    from qbot3.rides import ride_report_builder as rrb
    cur = conn.cursor()
    cur.execute("SELECT w1_json FROM qbot_v2.ride_report_data WHERE ride_key=%s AND schema_version=%s",
                (ride_key, rrb.SCHEMA_VERSION))
    r = cur.fetchone()
    if r and r[0]:
        return r[0] if isinstance(r[0], dict) else json.loads(r[0])
    return None


def pending_rides(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute("""SELECT a.external_id, a.activity_name, a.started_at, a.summary
                   FROM qbot_v2.activity_fit_raw a
                   LEFT JOIN qbot_v2.ride_report_ask k ON k.ride_key = a.external_id
                   WHERE k.ride_key IS NULL AND a.started_at >= now() - interval '%s hours'
                   ORDER BY a.started_at DESC""" % LOOKBACK_H)
    out = []
    now = datetime.now(timezone.utc)
    for ext, name, started, summ in cur.fetchall():
        summ = summ if isinstance(summ, dict) else (json.loads(summ) if summ else {})
        dur = float(summ.get("elapsedDuration") or summ.get("duration") or 0)
        end = started + timedelta(seconds=dur)
        if end + timedelta(minutes=ASK_AFTER_MIN) <= now:
            out.append({"ride_key": ext, "name": name, "summary": summ, "end": end})
    return out


def run_ask() -> int:
    conn = _db(); ensure_table(conn)
    n = 0
    for r in pending_rides(conn):
        w1 = _load_w1(conn, r["ride_key"])
        text = _summary_line(r["ride_key"], r["name"], r["summary"], w1) + "\n\nZrobić raport z analizą AI?"
        kb = {"inline_keyboard": [[
            {"text": "✅ Tak, analizuj", "callback_data": "rr:y:" + r["ride_key"]},
            {"text": "❌ Nie", "callback_data": "rr:n:" + r["ride_key"]}]]}
        ok = _tg(text, kb)
        cur = conn.cursor()
        cur.execute("INSERT INTO qbot_v2.ride_report_ask(ride_key,status,note) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (r["ride_key"], "asked" if ok else "error", None if ok else "telegram sendMessage failed"))
        conn.commit(); n += 1
    conn.close()
    return n


def set_status(ride_key: str, status: str, note: str | None = None):
    conn = _db(); ensure_table(conn); cur = conn.cursor()
    cur.execute("""INSERT INTO qbot_v2.ride_report_ask(ride_key,status,answered_at,note) VALUES(%s,%s,now(),%s)
                   ON CONFLICT (ride_key) DO UPDATE SET status=EXCLUDED.status, answered_at=now(), note=EXCLUDED.note""",
                (ride_key, status, note))
    conn.commit(); conn.close()


def spawn_worker(ride_key: str) -> None:
    logf = open("/opt/qbot/logs/ride_report_worker_%s.log" % ride_key, "ab")
    subprocess.Popen([sys.executable, "/opt/qbot/app/scripts/ride_report_worker.py", str(ride_key)],
                     stdout=logf, stderr=subprocess.STDOUT, cwd="/opt/qbot/app", start_new_session=True)


# ---------------- worker ----------------
def _moments(w1: dict) -> list[dict]:
    """Kotwice km dla W2: postoj, 5 min max, min zapasu, podjazd, najszybszy -- liczone jak we froncie."""
    tr = w1.get("trace") or {}
    km, P, A, wb, t = tr.get("km") or [], tr.get("power") or [], tr.get("alt") or [], tr.get("wbal_pct") or [], tr.get("t") or []
    N = len(km); out = []
    if N < 5: return out
    win = tr.get("window_s") or 10; w5 = max(1, round(300 / win))
    spd = [None] * N
    for i in range(1, N):
        dt = (t[i] - t[i - 1]) or win
        spd[i] = max(0.0, (km[i] - km[i - 1]) / dt * 3600) if km[i] is not None and km[i - 1] is not None else None
    bs, bi = -1, 0
    for i in range(0, N - w5 + 1):
        vals = [P[j] for j in range(i, i + w5) if P[j] is not None]
        if len(vals) == w5 and sum(vals) > bs: bs, bi = sum(vals), i
    if bs > 0: out.append({"co": "najmocniejsze 5 min", "km": [round(km[bi], 1), round(km[min(N - 1, bi + w5)], 1)], "moc_w": round(bs / w5)})
    if any(v is not None for v in wb):
        mi = min((i for i in range(N) if wb[i] is not None), key=lambda i: wb[i])
        out.append({"co": "najglebszy zapas W'bal", "km": [round(km[mi], 1), round(km[mi], 1)], "wbal_pct": wb[mi]})
    bg, bgi, bgj = 0, 0, 0; wC = round(1200 / win)
    for i in range(N):
        for j in range(i + 1, min(N, i + wC)):
            if A[j] is not None and A[i] is not None and A[j] - A[i] > bg: bg, bgi, bgj = A[j] - A[i], i, j
    if bg > 25: out.append({"co": "najwiekszy podjazd", "km": [round(km[bgi], 1), round(km[bgj], 1)], "wzniesienie_m": round(bg)})
    ms = max(range(N), key=lambda i: spd[i] or 0)
    if (spd[ms] or 0) > 25: out.append({"co": "najszybszy moment", "km": [round(km[ms], 1), round(km[ms], 1)], "kmh": round(spd[ms])})
    run, best = 0, None
    for i in range(N):
        if spd[i] is not None and spd[i] < 1.5: run += 1
        else:
            if run * win >= 60 and (not best or run > best[0]): best = (run, i - run)
            run = 0
    if best: out.append({"co": "najdluzszy postoj", "km": [round(km[best[1]], 1), round(km[best[1]], 1)], "min": round(best[0] * win / 60)})
    return out


def _mail_html(name: str, w1: dict, w2: dict, ride_key: str) -> str:
    V = lambda x: (x or {}).get("value") if isinstance(x, dict) else x
    L = w1.get("load") or {}; ph = w1.get("physio") or {}; wp = w1.get("wprime") or {}; sf = V(w1.get("surface")) or {}; wi = V(w1.get("wind")) or {}
    rows = [("Dystans", "%.1f km" % (V(L.get("dist_km")) or 0)), ("Czas ruchu", _hm(V(L.get("dur_moving_s")))),
            ("Moc średnia / znormalizowana", "%s / %s W" % (V(L.get("avg_p_w")), V(L.get("np_w")))),
            ("Intensywność / równość", "%s / %s" % (V(L.get("if")), V(L.get("vi")))),
            ("Tętno śr. / maks.", "%s / %s" % (V(ph.get("hr_avg")), V(ph.get("hr_max")))),
            ("Obciążenie", "%s" % V(L.get("xss"))), ("Zapas na zrywy min.", "%s%%" % V(wp.get("wbal_min_pct"))),
            ("Wiatr wzdłuż (śr.)", "%s m/s" % wi.get("avg_tail_ms") if isinstance(wi, dict) else "—"),
            ("Nawierzchnia", ", ".join("%s %s%%" % (k, v) for k, v in (sf.get("types_pct") or {}).items()) if isinstance(sf, dict) else "—")]
    tab = "".join("<tr><td style='padding:4px 10px 4px 0;color:#666'>%s</td><td style='padding:4px 0'><b>%s</b></td></tr>" % (html.escape(k), html.escape(str(v))) for k, v in rows)
    sec = "".join("<h3 style='margin:16px 0 4px'>%s%s</h3><p style='margin:0'>%s</p>" % (
        html.escape(s.get("tytul") or ""), (" <span style='color:#b3520f;font-size:12px'>km %s–%s</span>" % tuple(s["km"])) if isinstance(s.get("km"), list) and len(s["km"]) == 2 else "",
        html.escape(s.get("tekst") or "")) for s in (w2.get("synteza") or []))
    hl = "".join("<li>%s</li>" % html.escape(x) for x in (w2.get("highlights") or []))
    nx = "".join("<li>%s</li>" % html.escape(x) for x in (w2.get("next") or []))
    link = "%s/raport-jazdy2.html?ride=%s" % (BASE_URL, ride_key)
    return ("<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.5;color:#222;max-width:680px'>"
            "<h2 style='margin:0 0 6px'>%s</h2><p style='font-size:17px;margin:0 0 12px'><b>%s</b></p><ul>%s</ul>"
            "<table style='border-collapse:collapse;font-size:14px;margin:8px 0 12px'>%s</table>%s"
            "<h3 style='margin:18px 0 4px'>Na następny raz</h3><ul>%s</ul>"
            "<p style='margin-top:18px'><a href='%s'>Otwórz raport w QBot (mapa, wykres, odcinki)</a></p></div>") % (
            html.escape(name), html.escape(w2.get("verdict") or ""), hl, tab, sec, nx, link)


def _send_mail(subject: str, html_body: str) -> str:
    to = getattr(cfg, "EMAIL_TO", None) or cfg.GMAIL_USER
    msg = MIMEMultipart("alternative"); msg["Subject"] = subject; msg["From"] = cfg.GMAIL_USER; msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(cfg.GMAIL_USER, cfg.GMAIL_APP_PASSWORD); s.send_message(msg)
    return to


def run_worker(ride_key: str, send_tg: bool = True, send_mail: bool = True) -> dict:
    from qbot3.rides import ride_report_builder as rrb
    from qbot3.rides.ride_report_w2 import build_w2
    set_status(ride_key, "running")
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT activity_name, fit_path FROM qbot_v2.activity_fit_raw WHERE external_id=%s", (ride_key,))
    r = cur.fetchone(); name, fit = (r[0], r[1]) if r else (ride_key, None)
    if not fit or not os.path.exists(fit):
        cand = "/opt/qbot/artifacts/fit/%s.fit" % ride_key
        fit = cand if os.path.exists(cand) else fit
    try:
        w1 = _load_w1(conn, ride_key)
        if not w1:
            if not fit: raise RuntimeError("brak pliku FIT")
            w1 = rrb.build_w1(fit, ride_key); rrb.save_report(ride_key, fit, {}, w1)
        w1p = dict(w1); w1p["momenty_km"] = _moments(w1)
        w2 = build_w2(w1p)
        cur.execute("UPDATE qbot_v2.ride_report_data SET w2_json=%s WHERE ride_key=%s AND schema_version=%s",
                    (json.dumps(w2, ensure_ascii=False), ride_key, rrb.SCHEMA_VERSION)); conn.commit()
        link = "%s/raport-jazdy2.html?ride=%s" % (BASE_URL, ride_key)
        if send_tg:
            hl = "\n".join("• " + html.escape(x) for x in (w2.get("highlights") or [])[:3])
            nx = (w2.get("next") or [None])[0]
            _tg("📋 <b>Raport gotowy</b> — %s\n\n<b>%s</b>\n\n%s\n\n%s🔗 %s\n✉️ szczegóły w mailu" % (
                html.escape(name or ride_key), html.escape(w2.get("verdict") or ""), hl,
                ("<b>Na następny raz:</b> %s\n\n" % html.escape(nx)) if nx else "", link))
        to = None
        if send_mail:
            to = _send_mail("QBot · Raport z jazdy · %s · %s" % (name or ride_key, (w1.get("ride") or {}).get("date") or ""),
                            _mail_html(name or ride_key, w1, w2, ride_key))
        set_status(ride_key, "done", "mail:%s" % to if to else None)
        return {"ok": True, "ride_key": ride_key, "mail_to": to, "verdict": w2.get("verdict")}
    except Exception as e:
        set_status(ride_key, "error", str(e)[:300])
        if send_tg:
            try: _tg("⚠️ Raport z jazdy %s nie powiódł się: %s" % (html.escape(str(name or ride_key)), html.escape(str(e)[:200])))
            except Exception: pass
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()
