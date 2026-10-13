"""qbot_webpush.py - powiadomienia systemowe (Web Push) z centrum powiadomien (dzwonka), 2026-10-13.

Etap 1: komputer (Safari / Chrome na Macu). iPhone pozniej (wymaga dodania strony do ekranu poczatkowego).
- Przegladarka zapisuje subskrypcje (SETUP > Powiadomienia > "Powiadomienia na tym komputerze") -> qbot_v2.push_sub.
- Petla w tle w qbot-web (co PUSH_EVERY_S) robi tick(): sync_live (stan na zywo liczony NIEZALEZNIE od otwarcia strony)
  + send_pending(): kazda NOWA albo ZMIENIONA pozycja dzwonka (nieprzeczytana, niezamknieta, nieusunieta), dla rodzaju
  wlaczonego w SETUP > Powiadomienia, idzie raz na wszystkie zapisane urzadzenia. Znacznik notif.pushed_at.
- Zdarzenia z innych procesow (np. Trener z crona) tez trafiaja, bo petla czyta tabele qbot_v2.notif.
- Klucz VAPID: plik PEM poza repo (QBOT_VAPID_PEM, domyslnie /opt/qbot/app/.env.webpush.pem), tworzony przy pierwszym uzyciu.
- Pierwsze uruchomienie oznacza wszystkie istniejace pozycje jako juz wyslane (bez zalewu starymi).
Dok.: docs/NOTIF_CENTER.md (sekcja Powiadomienia na komputerze).
"""
from __future__ import annotations

import base64
import json
import os
import threading

PUSH_EVERY_S = 60
MAX_PER_TICK = 5            # wiecej naraz -> pierwsze 4 osobno + jedno zbiorcze
TTL_S = 12 * 3600
VAPID_SUB = "mailto:qbot@olga181.mikrus.xyz"
INIT_KEY = "webpush.init"
TICK_KEY = "webpush.tick"
_KEY_LOCK = threading.Lock()

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.push_sub (
    id          BIGSERIAL PRIMARY KEY,
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    device      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_ok_at  TIMESTAMPTZ,
    last_err    TEXT
)"""


def _pem_path() -> str:
    return os.getenv("QBOT_VAPID_PEM", "/opt/qbot/app/.env.webpush.pem")


def _rows(cur):
    rs = cur.fetchall()
    if rs and not isinstance(rs[0], dict):
        cols = [d[0] for d in cur.description]
        rs = [dict(zip(cols, r)) for r in rs]
    return rs


def ensure(cur) -> None:
    """Tabela subskrypcji + kolumna notif.pushed_at; jednorazowo: istniejace pozycje = juz wyslane."""
    cur.execute(DDL)
    cur.execute("ALTER TABLE qbot_v2.notif ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMPTZ")
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.app_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    cur.execute("SELECT 1 FROM qbot_v2.app_settings WHERE key=%s", (INIT_KEY,))
    if cur.fetchone() is None:
        cur.execute("UPDATE qbot_v2.notif SET pushed_at=now() WHERE pushed_at IS NULL")
        cur.execute("INSERT INTO qbot_v2.app_settings (key, value) VALUES (%s, '{\"done\": true}'::jsonb) "
                    "ON CONFLICT (key) DO NOTHING", (INIT_KEY,))


# ---------------- klucz VAPID ----------------

def _vapid():
    from py_vapid import Vapid
    p = _pem_path()
    with _KEY_LOCK:
        if not os.path.exists(p):
            v = Vapid()
            v.generate_keys()
            v.save_key(p)
            os.chmod(p, 0o600)
        return Vapid.from_file(p)


def public_key() -> str:
    """Klucz publiczny (applicationServerKey) w base64url bez paddingu."""
    from cryptography.hazmat.primitives import serialization
    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# ---------------- subskrypcje ----------------

def subscribe(cur, sub: dict, device: str | None = None) -> int:
    ep = str((sub or {}).get("endpoint") or "")
    keys = (sub or {}).get("keys") or {}
    if not ep.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("niepelna subskrypcja")
    cur.execute("INSERT INTO qbot_v2.push_sub (endpoint, p256dh, auth, device) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth, device=excluded.device, last_err=NULL "
                "RETURNING id", (ep, keys["p256dh"], keys["auth"], (device or "")[:80]))
    r = cur.fetchone()
    return (r["id"] if isinstance(r, dict) else r[0]) if r else 0


def unsubscribe(cur, endpoint: str) -> int:
    cur.execute("DELETE FROM qbot_v2.push_sub WHERE endpoint=%s", (str(endpoint or ""),))
    return cur.rowcount


def devices(cur) -> list[dict]:
    cur.execute("SELECT id, endpoint, device, created_at, last_ok_at, last_err FROM qbot_v2.push_sub ORDER BY id")
    return _rows(cur)


# ---------------- wysylka ----------------

def _send_one(s: dict, payload: dict) -> str:
    """'ok' | 'gone' (subskrypcja wygasla - usunac) | 'err:<opis>'."""
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info={"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                data=json.dumps(payload, ensure_ascii=False), vapid_private_key=_pem_path(),
                vapid_claims={"sub": VAPID_SUB}, ttl=TTL_S, timeout=10)
        return "ok"
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):
            return "gone"
        return f"err:{code or ''} {str(e)[:150]}"
    except Exception as e:  # siec itp.
        return f"err:{str(e)[:150]}"


def send_to_all(cur, payloads: list[dict]) -> dict:
    cur.execute("SELECT id, endpoint, p256dh, auth FROM qbot_v2.push_sub ORDER BY id")
    subs = _rows(cur)
    st = {"devices": len(subs), "sent": 0, "gone": 0, "err": 0}
    for s in subs:
        last = None
        for p in payloads:
            r = _send_one(s, p)
            if r == "gone":
                cur.execute("DELETE FROM qbot_v2.push_sub WHERE id=%s", (s["id"],))
                st["gone"] += 1
                last = None
                break
            if r == "ok":
                st["sent"] += 1
                last = "ok"
            else:
                st["err"] += 1
                last = r
        if last == "ok":
            cur.execute("UPDATE qbot_v2.push_sub SET last_ok_at=now(), last_err=NULL WHERE id=%s", (s["id"],))
        elif last:
            cur.execute("UPDATE qbot_v2.push_sub SET last_err=%s WHERE id=%s", (last, s["id"]))
    return st


def build_payloads(items: list[dict]) -> list[dict]:
    """items: key, kind, title, body, url (kolejnosc = od najstarszej). Wiecej niz MAX_PER_TICK -> zbiorcze na koncu."""
    out = []
    head = items if len(items) <= MAX_PER_TICK else items[:MAX_PER_TICK - 1]
    for it in head:
        out.append({"title": it["title"], "body": it.get("body") or "",
                    "url": it.get("url") or "/?notif=1", "tag": it["key"]})
    if len(items) > len(head):
        n = len(items) - len(head)
        out.append({"title": f"Jeszcze {n} nowych w dzwonku", "body": "; ".join(i["title"] for i in items[len(head):])[:200],
                    "url": "/?notif=1", "tag": "qbot-zbiorcze"})
    return out


def pending(cur) -> list[dict]:
    """Nowe albo zmienione od ostatniej wysylki, nieprzeczytane, otwarte; zdarzenia nie starsze niz 14 dni."""
    import qbot_notif as NF
    cur.execute("SELECT id, key, kind, title, body, url FROM qbot_v2.notif "
                "WHERE read_at IS NULL AND resolved_at IS NULL AND dismissed_at IS NULL "
                "AND (pushed_at IS NULL OR pushed_at < updated_at) "
                "AND (key LIKE 'live:%%' OR updated_at > now() - make_interval(days => %s)) ORDER BY updated_at, id",
                (NF.EVENT_DAYS,))
    return _rows(cur)


def send_pending(cur) -> dict:
    import qbot_notif as NF
    rows = pending(cur)
    if not rows:
        return {"items": 0}
    en = NF.enabled_map(cur)
    send = [r for r in rows if en.get(NF.source_of(r["key"]) or "", True)]
    st = send_to_all(cur, build_payloads(send)) if send else {"devices": None}
    cur.execute("UPDATE qbot_v2.notif SET pushed_at=now() WHERE id = ANY(%s)", ([r["id"] for r in rows],))
    st.update(items=len(send), skipped=len(rows) - len(send))
    return st


def send_test(cur) -> dict:
    return send_to_all(cur, [{"title": "Test powiadomień", "body": "Działa – tak będą wyglądać powiadomienia z dzwonka QBota.",
                              "url": "/setup.html#powiadomienia", "tag": "qbot-test"}])


def tick(cur, garage_db: str | None = None) -> dict:
    """Jeden obrot petli w tle: przelicz stan na zywo i wyslij nowe pozycje."""
    import qbot_notif as NF
    ensure(cur)
    NF.sync_live(cur, garage_db)
    st = send_pending(cur)
    # slad pracy petli (widoczny w SETUP: "serwer sprawdzal HH:MM") - dowod, ze dziala bez otwartej strony
    from datetime import datetime
    cur.execute("INSERT INTO qbot_v2.app_settings (key, value) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=now()",
                (TICK_KEY, json.dumps({"at": datetime.now().astimezone().isoformat(timespec="seconds"), **st}, default=str)))
    return st


def last_tick(cur) -> dict | None:
    cur.execute("SELECT value FROM qbot_v2.app_settings WHERE key=%s", (TICK_KEY,))
    r = cur.fetchone()
    if not r:
        return None
    return r["value"] if isinstance(r, dict) else r[0]
