"""qbot_notif.py - Centrum powiadomien (dzwonek w menu, 2026-10-08).

Jedno wspolne miejsce: tabela qbot_v2.notif (sql/notif_v1.sql). Dwa rodzaje pozycji:
- ZDARZENIA (klucz bez prefiksu live:) - dopisywane przez moduly przez push(), np. Trener
  (plan tygodnia, rozliczenie, zmiana planu z Kalendarza / po wykonaniu). Widoczne 14 dni.
- STAN NA ZYWO (klucz live:...) - liczony przy kazdym odczycie przez sync_live(): zadania przy
  rowerze (garage.db bike_task), trasy czekajace na potwierdzenie w Telegramie, brak swiezych danych
  (sen, waga > 3 dni). Gdy warunek znika, pozycja sama sie zamyka (resolved_at).
KROK 2 (2026-10-08): jazdy (Nowa jazda - zdarzenie; Uzupelnij, w czym jechales - stan), pogoda przed
zaplanowana jazda Trenera (dzis/jutro, co 30 min), system (uslugi qbot*, samoczynne restarty, dysk,
prosby/wejscia demo QR, nieudane logowania - login_failed() wolane z qbot_web).
Telegram dziala jak dotad - dzwonek go nie zastepuje.
Zmiana tresci pozycji => znow nieprzeczytana. Daty w tekstach DD.MM.
"""
from __future__ import annotations

from datetime import date, datetime

EVENT_DAYS = 14
STALE_DAYS = 3

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.notif (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT,
    url         TEXT,
    action      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ
)"""

KIND_ICON = {"rower": "🔧", "trasa": "🗺️", "trener": "🏋️", "dane": "📡", "system": "⚙️",
             "jazda": "🚴", "ubior": "👕", "pogoda": "🌦️"}

# krok 2 (2026-10-08)
RIDE_DAYS = 3              # jazdy z ostatnich N dni -> "Nowa jazda" + "Uzupelnij, w czym jechales"
DISK_PCT = 90              # zajetosc dysku / od ktorej alarm
WX_EVERY_S = 30 * 60       # pogoda przed jazda: przeliczanie najwyzej co 30 min
WX_RAIN_MMH, WX_RAIN_PROB, WX_WIND, WX_GUST, WX_FROST = 0.5, 60, 8.0, 14.0, 0.0
LONG_RUNNING = ("qbot-api", "qbot-web", "qbot-mcp-bridge", "qbot-dev-mcp", "qbot-qlab-server")
GEAR_AUTO_SLOTS = ("_temp_app", "_temp_fit", "_precip")   # wpisywane automatycznie (pogoda), nie przez czlowieka
_WX_TS = [0.0]
_DOW = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]


def _row(cur):
    r = cur.fetchone()
    if r is None:
        return None
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _rows(cur):
    rs = cur.fetchall()
    if rs and not isinstance(rs[0], dict):
        cols = [d[0] for d in cur.description]
        rs = [dict(zip(cols, r)) for r in rs]
    return rs


def push(cur, key: str, kind: str, title: str, body: str | None = None, url: str | None = None,
         action: dict | None = None, at=None) -> None:
    """Dodaj albo odswiez pozycje. Nowa tresc albo ponowne otwarcie => nieprzeczytana."""
    import json
    aj = json.dumps(action, ensure_ascii=False) if action else None
    cur.execute("SELECT title, body, resolved_at, dismissed_at FROM qbot_v2.notif WHERE key=%s", (key,))
    old = _row(cur)
    if old is None:
        # at = czas samego zdarzenia (np. start jazdy) - wtedy lista pokazuje i sortuje po nim, nie po czasie wykrycia
        cur.execute("INSERT INTO qbot_v2.notif (key, kind, title, body, url, action, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s::jsonb, coalesce(%s, now()), coalesce(%s, now()))",
                    (key, kind, title, body, url, aj, at, at))
    elif old["dismissed_at"] is not None and (old["title"], old["body"]) == (title, body):
        return  # usuniete krzyzykiem - nie wraca, dopoki tresc sie nie zmieni (np. nowe zadanie przy rowerze)
    elif old["resolved_at"] is not None:
        cur.execute("UPDATE qbot_v2.notif SET kind=%s, title=%s, body=%s, url=%s, action=%s::jsonb, created_at=now(), "
                    "updated_at=now(), read_at=NULL, resolved_at=NULL, dismissed_at=NULL WHERE key=%s", (kind, title, body, url, aj, key))
    elif (old["title"], old["body"]) != (title, body):
        cur.execute("UPDATE qbot_v2.notif SET kind=%s, title=%s, body=%s, url=%s, action=%s::jsonb, updated_at=now(), "
                    "read_at=NULL WHERE key=%s", (kind, title, body, url, aj, key))
    else:
        cur.execute("UPDATE qbot_v2.notif SET url=%s, action=%s::jsonb WHERE key=%s", (url, aj, key))


def resolve(cur, key: str) -> None:
    cur.execute("UPDATE qbot_v2.notif SET resolved_at=now() WHERE key=%s AND resolved_at IS NULL", (key,))


def _ddmm(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%d.%m")
    s = str(d or "")
    return f"{s[8:10]}.{s[5:7]}" if len(s) >= 10 else s


# ---------------- stan na zywo (czyste funkcje -> lista pozycji) ----------------

def live_bike(tasks: list[dict]) -> list[dict]:
    """Otwarte zadania przy rowerze -> jedna pozycja na rower."""
    by: dict = {}
    for t in tasks:
        by.setdefault(t.get("bike_id") or 0, []).append(t)
    out = []
    for bid, ts in by.items():
        labs = ", ".join(dict.fromkeys(t["label"] for t in ts))
        last = ts[-1]
        out.append({"key": f"live:rower:{bid}", "kind": "rower",
                    "title": f"{ts[0].get('bike') or 'Rower'}: do zrobienia ({len(ts)})",
                    "body": labs + f" — po jeździe {_ddmm(last.get('created_at'))}",
                    "url": "/raport-jazdy.html?ride=" + str(last.get("ride_key") or ""),
                    "action": {"label": "Zrobione", "post": "/api/bike-tasks/done", "body": {"ids": [t["id"] for t in ts]}}})
    return out


def live_routes(pending: list[dict]) -> list[dict]:
    out = []
    for p in pending:
        prev = (p.get("preview_text") or "").strip().splitlines()
        out.append({"key": f"live:trasa:{p['id']}", "kind": "trasa",
                    "title": "Trasa czeka na potwierdzenie",
                    "body": (prev[0][:160] if prev else f"akcja #{p['id']}") + " — odpowiedz w Telegramie",
                    "url": None, "action": None})
    return out


def live_stale(latest: dict, today: date) -> list[dict]:
    """latest = {'sen': date|None, 'waga': date|None}."""
    out = []
    for name, d in latest.items():
        age = (today - d).days if d else None
        if age is None or age > STALE_DAYS:
            out.append({"key": f"live:dane:{name}", "kind": "dane",
                        "title": f"Brak świeżych danych: {name}",
                        "body": f"ostatnie {_ddmm(d)} ({age} dni temu)" if d else "brak danych",
                        "url": "/forma.html", "action": None})
    return out


def _when(ts) -> str:
    if isinstance(ts, datetime):
        return ts.strftime("%d.%m %H:%M")
    return _ddmm(ts)


def live_rides(rides: list[dict], entered: set | None) -> tuple[list[dict], list[dict]]:
    """rides: key, started_at, name, km. entered = ride_key z wpisanym ubiorem (None = nie sprawdzono).
    Zwraca (zdarzenia 'Nowa jazda', stan na zywo 'Uzupelnij, w czym jechales')."""
    ev, lv = [], []
    for r in rides:
        k = str(r["key"]); url = "/raport-jazdy.html?ride=" + k
        km = f" · {float(r['km']):.1f} km" if r.get("km") else ""
        nm = r.get("name") or "jazda"
        ev.append({"key": f"jazda:{k}", "kind": "jazda", "title": f"Nowa jazda: {nm}",
                   "body": f"{_when(r.get('started_at'))}{km} — raport z jazdy", "url": url, "action": None,
                   "at": r.get("started_at")})
        if entered is not None and k not in entered:
            lv.append({"key": f"live:ubior:{k}", "kind": "ubior", "title": "Uzupełnij, w czym jechałeś",
                       "body": f"{nm} {_when(r.get('started_at'))} — ubiór i rower po jeździe (przycisk Ubiór / rower)",
                       "url": url, "action": None})
    return ev, lv


def live_weather(sessions: list[dict], wx: dict) -> list[dict]:
    """Zaplanowane jazdy rowerowe (dzis/jutro) + prognoza Trenera (forecast: wind, gust, feel_min, rain_mmh,
    rain_prob, snow_cm, storm) -> ostrzezenie gdy deszcz / wiatr / przymrozek / burza / snieg."""
    out = []
    for s in sessions:
        d = s["day"]; w = wx.get(d.isoformat() if hasattr(d, "isoformat") else str(d))
        if not w:
            continue
        why = []
        if w.get("storm"):
            why.append("burza")
        if (w.get("rain_mmh") or 0) > WX_RAIN_MMH or (w.get("rain_prob") or 0) >= WX_RAIN_PROB:
            why.append(f"deszcz do {w.get('rain_mmh') or 0} mm/h ({w.get('rain_prob') or 0}%)")
        if (w.get("wind") or 0) > WX_WIND or (w.get("gust") or 0) > WX_GUST:
            why.append(f"wiatr {w.get('wind')} m/s (porywy {w.get('gust')})")
        if w.get("feel_min") is not None and w["feel_min"] <= WX_FROST:
            why.append(f"przymrozek, odczuwalna {w['feel_min']} °C")
        if (w.get("snow_cm") or 0) > 0:
            why.append(f"śnieg {w['snow_cm']} cm")
        if not why:
            continue
        st = s.get("start_time")
        when = f"{_DOW[d.weekday()]} {d.strftime('%d.%m')}" + (f" {st.strftime('%H:%M')}" if st else "")
        out.append({"key": f"live:pogoda:{s['id']}", "kind": "pogoda", "title": f"Pogoda przed jazdą: {when}",
                    "body": f"{s.get('name') or 'jazda'} — " + ", ".join(why), "url": "/trener.html", "action": None})
    return out


def service_states() -> list[dict]:
    import subprocess
    r = subprocess.run(["systemctl", "list-units", "qbot*.service", "--all", "--no-legend", "--plain"],
                       capture_output=True, text=True, timeout=5)
    names = [ln.split()[0].replace(".service", "") for ln in r.stdout.splitlines() if ln.strip()]
    out = []
    for n in names:
        q = subprocess.run(["systemctl", "show", n, "-p", "ActiveState,Result,NRestarts,ActiveEnterTimestamp"],
                           capture_output=True, text=True, timeout=5).stdout
        kv = dict(x.split("=", 1) for x in q.splitlines() if "=" in x)
        out.append({"name": n, "state": kv.get("ActiveState"), "result": kv.get("Result"),
                    "restarts": int(kv.get("NRestarts") or 0), "since": kv.get("ActiveEnterTimestamp") or ""})
    return out


def disk_pct(path: str = "/") -> float:
    import shutil
    du = shutil.disk_usage(path)
    return round(du.used / du.total * 100, 1)


def live_system(states: list[dict], disk: float | None) -> list[dict]:
    """Uslugi: dlugo dzialajace musza byc active; kazda w stanie failed (tez zadania z timera, np. backup) -> alarm.
    Samoczynny restart (NRestarts > 0) -> zdarzenie. Dysk >= DISK_PCT -> alarm."""
    out = []
    for s in states:
        n = s["name"]
        if s.get("state") == "failed" or (n in LONG_RUNNING and s.get("state") not in ("active", "reloading", "activating")):
            out.append({"key": f"live:system:svc:{n}", "kind": "system", "title": f"Usługa nie działa: {n}",
                        "body": f"stan {s.get('state')}, wynik {s.get('result')}", "url": None, "action": None})
        if s.get("restarts"):
            out.append({"key": f"system:restart:{n}:{s['restarts']}", "kind": "system",
                        "title": f"Usługa {n} zrestartowała się sama",
                        "body": f"automatyczny restart nr {s['restarts']}; działa od {s.get('since') or '?'}", "url": None, "action": None})
    if disk is not None and disk >= DISK_PCT:
        out.append({"key": "live:system:dysk", "kind": "system", "title": f"Mało miejsca na dysku: zajęte {disk:.0f}%",
                    "body": "serwer QBot (Mikrus) — warto posprzątać kopie i logi", "url": None, "action": None})
    return out


def _ua(ua: str | None) -> str:
    u = str(ua or "")
    for k, v in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Mac OS", "Mac"), ("Windows", "Windows"), ("Linux", "Linux")):
        if k in u:
            return v
    return "nieznane urządzenie"


def live_demo(reqs: list[dict], now: datetime) -> list[dict]:
    """Prosby o dostep demo przez QR: czekajaca (PENDING, nieprzeterminowana) = stan na zywo; wykorzystana = zdarzenie."""
    out = []
    for r in reqs:
        if r.get("status") == "PENDING" and r.get("expires_at") and r["expires_at"] > now:
            out.append({"key": f"live:demo:{r['id']}", "kind": "system", "title": "Ktoś prosi o dostęp demo (QR)",
                        "body": f"kod {r.get('user_code')} · {_ua(r.get('device_info'))} — zatwierdź w Telegramie albo na stronie dostępów",
                        "url": None, "action": None})
        elif r.get("consumed_at"):
            ttl = int(r.get("session_ttl_s") or 0) // 60
            out.append({"key": f"system:demo:{r['id']}", "kind": "system", "title": "Wejście demo przez QR",
                        "body": f"{_when(r['consumed_at'])} · {_ua(r.get('device_info'))}" + (f" · dostęp {ttl} min" if ttl else ""),
                        "url": None, "action": None, "at": r["consumed_at"]})
    return out


def login_failed(cur, username: str | None, n_today: int, when: datetime) -> None:
    """Wolane z qbot_web._login_record_failure. Jedna pozycja na dzien, licznik w tytule."""
    push(cur, f"system:login:{when.date().isoformat()}", "system", f"Nieudane logowania dziś: {n_today}",
         f"ostatnia próba {when.strftime('%H:%M')}, login: {str(username or '?')[:40]}")


def sync_live(cur, garage_db: str | None = None, today: date | None = None) -> int:
    """Przelicz pozycje live:*. Kazde zrodlo osobno - blad jednego nie blokuje reszty."""
    today = today or date.today()
    items: list[dict] = []
    ok_prefixes: list[str] = []
    try:
        from qbot3.rides import bike_tasks as BT
        gc = BT.conn(garage_db)
        try:
            items += live_bike(BT.open_tasks(gc))
        finally:
            gc.close()
        ok_prefixes.append("live:rower:")
    except Exception:
        pass
    try:
        cur.execute("SELECT id, preview_text FROM public.telegram_pending_actions "
                    "WHERE status='pending' AND (expires_at IS NULL OR expires_at > now()) "
                    "AND action_type IN ('confirm_route_analysis','confirm_komoot_analysis') ORDER BY id")
        items += live_routes(_rows(cur))
        ok_prefixes.append("live:trasa:")
    except Exception:
        cur.connection.rollback()
    try:
        cur.execute("SELECT (SELECT max(date) FROM qbot_v2.qbot_wellness_daily WHERE sleep_score IS NOT NULL) AS sen, "
                    "(SELECT max(day) FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL) AS waga")
        items += live_stale(dict(_row(cur)), today)
        ok_prefixes.append("live:dane:")
    except Exception:
        cur.connection.rollback()
    # --- krok 2: jazdy (nowa jazda = zdarzenie; brak ubioru = stan na zywo) ---
    try:
        cur.execute("SELECT ts.external_id AS key, ts.started_at, ts.activity_name AS name, "
                    "(afr.summary->>'distance')::numeric/1000 AS km FROM qbot_v2.training_sessions ts "
                    "LEFT JOIN qbot_v2.activity_fit_raw afr ON afr.external_id = ts.external_id "
                    "WHERE ts.sport_type IN ('cycling','gravel_cycling') AND ts.started_at > now() - make_interval(days => %s) "
                    "ORDER BY ts.started_at", (RIDE_DAYS,))
        rides = _rows(cur)
        entered = set()
        try:
            import sqlite3
            g = sqlite3.connect(garage_db or "/opt/qbot/app/data/garage.db")
            try:
                q = ",".join("?" * len(GEAR_AUTO_SLOTS))
                entered = {str(r[0]) for r in g.execute(f"SELECT DISTINCT ride_key FROM ride_gear_log WHERE slot NOT IN ({q})", GEAR_AUTO_SLOTS)}
            finally:
                g.close()
            ok_prefixes.append("live:ubior:")
        except Exception:
            entered = None
        ev, lv = live_rides(rides, entered)
        items += ev + lv
    except Exception:
        cur.connection.rollback()
    # --- krok 2: pogoda przed zaplanowana jazda (Trener), najwyzej co 30 min ---
    try:
        import time as _t
        if _t.time() - _WX_TS[0] > WX_EVERY_S:
            cur.execute("SELECT id, day, start_time, name FROM qbot_v2.trainer_session WHERE sport='rower' AND status='plan' "
                        "AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST", (today, date.fromordinal(today.toordinal() + 1)))
            ses = _rows(cur)
            wx = {}
            if ses:
                import qbot_trener_engine as E
                hp = E.home_point(cur)
                wx = E.forecast(*hp) if hp else {}
            if not ses or wx:
                items += live_weather(ses, wx)
                ok_prefixes.append("live:pogoda:")
                _WX_TS[0] = _t.time()
            else:  # prognoza niedostepna - sprobuj znow za ok. 5 min
                _WX_TS[0] = _t.time() - WX_EVERY_S + 300
        else:
            cur.execute("SELECT key, kind, title, body, url, action FROM qbot_v2.notif WHERE key LIKE 'live:pogoda:%%' AND resolved_at IS NULL")
            keep_wx = _rows(cur)
            items += [dict(r) for r in keep_wx]
            ok_prefixes.append("live:pogoda:")
    except Exception:
        cur.connection.rollback()
    # --- krok 2: system (uslugi, dysk, wejscia demo) ---
    try:
        items += live_system(service_states(), disk_pct())
        ok_prefixes.append("live:system:")
    except Exception:
        pass
    try:
        cur.execute("SELECT id, status, user_code, consumed_at, expires_at, session_ttl_s, device_info "
                    "FROM qbot_v2.web_device_auth_requests WHERE created_at > now() - interval '3 days' ORDER BY created_at")
        items += live_demo(_rows(cur), datetime.now().astimezone())
        ok_prefixes.append("live:demo:")
    except Exception:
        cur.connection.rollback()
    keep = set()
    for it in items:
        push(cur, it["key"], it["kind"], it["title"], it["body"], it["url"], it["action"], it.get("at"))
        keep.add(it["key"])
    cur.execute("SELECT key FROM qbot_v2.notif WHERE key LIKE 'live:%%' AND resolved_at IS NULL")
    for r in _rows(cur):
        if r["key"] not in keep and any(r["key"].startswith(p) for p in ok_prefixes):
            resolve(cur, r["key"])
    return len(items)


# ---------------- SETUP > Powiadomienia (2026-10-08): ktore rodzaje pokazuje dzwonek ----------------
# (id, grupa, nazwa, opis, prefiksy kluczy). Wylaczone nie sa pokazywane ani liczone w plakietce;
# w bazie dalej sie zapisuja (po wlaczeniu od razu widac stan biezacy). Historia pokazuje wszystko.
SOURCES = [
    ("jazda", "Jazdy", "Nowa jazda", "jazda rowerowa z ostatnich 3 dni, link do raportu", ("jazda:",)),
    ("ubior", "Jazdy", "Uzupełnij, w czym jechałeś", "jazda bez wpisanego ubioru i roweru", ("live:ubior:",)),
    ("rower", "Jazdy", "Rower po jeździe — do zrobienia", "zadania zaznaczone w oknie Ubiór / rower", ("live:rower:",)),
    ("pogoda", "Pogoda", "Pogoda przed zaplanowaną jazdą", "deszcz, wiatr, przymrozek, burza, śnieg — dziś i jutro", ("live:pogoda:",)),
    ("trasa", "Trasy", "Trasa czeka na potwierdzenie", "nowa trasa RWGPS / Komoot — odpowiedź w Telegramie", ("live:trasa:",)),
    ("trener_plan", "Trener", "Plan tygodnia", "kopia wiadomości z Telegrama", ("trener:plan:",)),
    ("trener_rozl", "Trener", "Rozliczenie tygodnia", "niedziela wieczorem", ("trener:review:",)),
    ("trener_zmiany", "Trener", "Zmiany planu", "po zmianie w Kalendarzu i po odchyłce wykonania", ("trener:chg:", "trener:adapt:")),
    ("dane_sen", "Dane", "Brak świeżych danych: sen", "nic nowego dłużej niż 3 dni", ("live:dane:sen",)),
    ("dane_waga", "Dane", "Brak świeżych danych: waga", "nic nowego dłużej niż 3 dni", ("live:dane:waga",)),
    ("sys_uslugi", "System", "Usługi QBota", "usługa nie działa, zadanie w tle się wysypało, samoczynny restart", ("live:system:svc:", "system:restart:")),
    ("sys_dysk", "System", "Mało miejsca na dysku", "zajęte 90% i więcej", ("live:system:dysk",)),
    ("sys_demo", "System", "Dostęp demo przez QR", "prośba o dostęp i wejścia", ("live:demo:", "system:demo:")),
    ("sys_login", "System", "Nieudane logowania", "licznik dzienny z godziną ostatniej próby", ("system:login:",)),
]
PREF_KEY = "notif.enabled"


def source_of(key: str) -> str | None:
    for sid, _g, _n, _d, prefs in SOURCES:
        if any(key.startswith(p) for p in prefs):
            return sid
    return None


def _settings_ensure(cur) -> None:
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.app_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")


def enabled_map(cur) -> dict:
    """{id: bool}; brak wpisu = wlaczone."""
    _settings_ensure(cur)
    cur.execute("SELECT value FROM qbot_v2.app_settings WHERE key=%s", (PREF_KEY,))
    r = _row(cur)
    v = (r or {}).get("value") or {}
    return {sid: bool(v.get(sid, True)) for sid, *_ in SOURCES}


def settings_view(cur) -> dict:
    en = enabled_map(cur)
    return {"sources": [{"id": sid, "group": g, "label": n, "desc": d, "enabled": en[sid]} for sid, g, n, d, _p in SOURCES]}


def settings_save(cur, values: dict) -> dict:
    import json
    en = enabled_map(cur)
    for sid in en:
        if sid in (values or {}):
            en[sid] = bool(values[sid])
    cur.execute("INSERT INTO qbot_v2.app_settings (key, value) VALUES (%s, %s::jsonb) "
                "ON CONFLICT (key) DO UPDATE SET value=excluded.value, updated_at=now()", (PREF_KEY, json.dumps(en)))
    return en


def listing(cur, limit: int = 60) -> dict:
    cur.execute("SELECT id, key, kind, title, body, url, action, created_at, updated_at, read_at FROM qbot_v2.notif "
                "WHERE resolved_at IS NULL AND (key LIKE 'live:%%' OR updated_at > now() - make_interval(days => %s)) "
                "ORDER BY (read_at IS NULL) DESC, updated_at DESC LIMIT %s", (EVENT_DAYS, limit))
    items = []
    rows = _rows(cur)
    try:
        en = enabled_map(cur)
    except Exception:
        cur.connection.rollback(); en = {}
    for r in rows:
        sid = source_of(r["key"])
        if sid and not en.get(sid, True):
            continue
        items.append({"id": r["id"], "kind": r["kind"], "icon": KIND_ICON.get(r["kind"], "🔔"), "title": r["title"],
                      "body": r["body"], "url": r["url"], "action": r["action"], "unread": r["read_at"] is None,
                      "when": r["updated_at"].strftime("%d.%m %H:%M") if r["updated_at"] else "",
                      "live": r["key"].startswith("live:")})
    return {"unread": sum(1 for i in items if i["unread"]), "items": items}


def mark_read(cur, ids: list | None = None) -> int:
    if ids:
        cur.execute("UPDATE qbot_v2.notif SET read_at=now() WHERE read_at IS NULL AND id = ANY(%s)", ([int(i) for i in ids],))
    else:
        cur.execute("UPDATE qbot_v2.notif SET read_at=now() WHERE read_at IS NULL AND resolved_at IS NULL")
    return cur.rowcount


def dismiss(cur, nid: int) -> int:
    """Krzyzyk = usun z listy. Wiersz zostaje w bazie (Historia). Wraca tylko, gdy zmieni sie tresc."""
    cur.execute("UPDATE qbot_v2.notif SET resolved_at=coalesce(resolved_at, now()), dismissed_at=now(), "
                "read_at=coalesce(read_at, now()) WHERE id=%s", (int(nid),))
    return cur.rowcount


HISTORY_DAYS = 90


def history(cur, days: int = HISTORY_DAYS, limit: int = 300) -> dict:
    """Log wszystkich powiadomien (tez usunietych i zamknietych samoczynnie) z ostatnich N dni."""
    cur.execute("SELECT id, key, kind, title, body, url, created_at, updated_at, read_at, resolved_at, dismissed_at "
                "FROM qbot_v2.notif WHERE greatest(updated_at, coalesce(resolved_at, updated_at)) > now() - make_interval(days => %s) "
                "ORDER BY updated_at DESC LIMIT %s", (days, limit))
    out = []
    for r in _rows(cur):
        if r["dismissed_at"]:
            st = "usunięte " + r["dismissed_at"].strftime("%d.%m %H:%M")
        elif r["resolved_at"]:
            st = "załatwione samo " + r["resolved_at"].strftime("%d.%m %H:%M")
        elif not r["key"].startswith("live:") and r["updated_at"] and (datetime.now(r["updated_at"].tzinfo) - r["updated_at"]).days >= EVENT_DAYS:
            st = "wygasło (starsze niż %d dni)" % EVENT_DAYS
        else:
            st = "aktywne" + ("" if r["read_at"] else ", nowe")
        out.append({"id": r["id"], "kind": r["kind"], "icon": KIND_ICON.get(r["kind"], "🔔"), "title": r["title"],
                    "body": r["body"], "url": r["url"], "when": r["updated_at"].strftime("%d.%m %H:%M") if r["updated_at"] else "",
                    "status": st})
    return {"days": days, "items": out}
