"""Autotest Karoo dla QExt2 (21.10.2026, sesja karoo-autotest-2110).

QExt2 (od 0.4.19) raz na start uslugi sprawdza kruche, nieoficjalne punkty na Karoo (tlo ekranu startowego, ciemne menu,
usluga zatwierdzajaca okno debugowania, sterowanie lampa) i wysyla raport: POST /ride-readiness {"karooHealth": {...}}
(mcp_server.py, usluga q-bot). Tu: zapis raportu, wykrycie aktualizacji Karoo i zepsutych funkcji (dzwonek QBota),
wylacznik zdalny (lista qext2Disable podawana w ride-readiness) i widok SETUP > QExt2 > Autotest Karoo.

Tabela: qbot_v2.qext2_karoo_health (tworzona tu, CREATE IF NOT EXISTS). Wylacznik: qbot_v2.app_settings, klucz KEY_DISABLE.
Opis: docs/wiki/qext2/autotest-karoo.md
"""
from __future__ import annotations

import hashlib
import json

KEY_DISABLE = "qext2.disable"

# id -> (nazwa po polsku, czy mozna wylaczyc zdalnie)
TESTS = {
    "sdk": ("Połączenie z Karoo (oficjalne)", None),
    "qbot": ("Dane z QBota", None),
    "perm": ("Uprawnienie do ustawień systemu", None),
    "homebg": ("Tło ekranu startowego", "homebg"),
    "darkmenu": ("Ciemne menu", "darkmenu"),
    "clicker": ("Zatwierdzanie okna debugowania", "darkmenu"),
    "light": ("Przełączanie trybu lampy", "light"),
}
FEATURES = {
    "darkmenu": "Ciemne menu (i zatwierdzanie okna)",
    "homebg": "Tło ekranu startowego",
    "light": "Przełączanie trybu lampy",
    "hotspot": "Budzenie hotspotu iPhone'a",
}
# 21.10.2026 (ciemny-2110): przelacznik "Tryb ciemny Karoo" w SETUP > QExt2 = darkmenu + hotspot w liscie wylaczonych
# (hotspot budzony tylko dla ciemnego menu). QExt2 0.4.20 przy darkmenu wylaczonym zdalnie zdejmuje tez usluge
# zatwierdzajaca okno debugowania z ustawien systemu i trzyma debugowanie Wi-Fi wylaczone.
DARK_SET = ("darkmenu", "hotspot")
GUARD_PL = {"zdalnie": "wyłączone zdalnie", "bledy": "wyłączone po 3 błędach", "petla": "wyłączone — pętla padania"}
NOTIF_FAIL = "qext2:karoo:awaria"


def _ensure(cur) -> None:
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.qext2_karoo_health (id BIGSERIAL PRIMARY KEY, "
                "received_at TIMESTAMPTZ NOT NULL DEFAULT now(), boot INT, build INT, build_name TEXT, "
                "karoo_sig TEXT, karoo JSONB, results JSONB, guard JSONB, crash_loop BOOLEAN, n_fail INT)")
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.app_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")


def _one(cur):
    r = cur.fetchone()
    if r is None:
        return None
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _all(cur):
    rs = cur.fetchall()
    if rs and not isinstance(rs[0], dict):
        cols = [d[0] for d in cur.description]
        rs = [dict(zip(cols, r)) for r in rs]
    return rs


def karoo_label(k: dict | None) -> str:
    """Krotki opis wersji Karoo: system + ekran startowy."""
    k = k or {}
    pk = k.get("pkgs") or {}
    sys_ = str(k.get("display") or k.get("incremental") or "?")
    la = str(pk.get("io.hammerhead.launcherapp") or "?").split(" ")[0]
    return f"{sys_} · ekran startowy {la}"


def karoo_sig(k: dict | None) -> str:
    k = k or {}
    base = json.dumps({"d": k.get("display"), "i": k.get("incremental"), "p": k.get("pkgs")}, sort_keys=True)
    return hashlib.sha1(base.encode()).hexdigest()[:12]


def disabled(cur) -> list[str]:
    _ensure(cur)
    cur.execute("SELECT value FROM qbot_v2.app_settings WHERE key=%s", (KEY_DISABLE,))
    r = _one(cur)
    v = (r or {}).get("value")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = []
    return [x for x in (v or []) if x in FEATURES]


def set_disabled(cur, items) -> list[str]:
    _ensure(cur)
    v = sorted({x for x in (items or []) if x in FEATURES})
    cur.execute("INSERT INTO qbot_v2.app_settings (key, value, updated_at) VALUES (%s, %s::jsonb, now()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()", (KEY_DISABLE, json.dumps(v)))
    return v


def _fails(results: dict | None) -> list[str]:
    return [t for t, v in (results or {}).items() if isinstance(v, dict) and v.get("s") == "FAIL"]


def record(cur, rep: dict) -> dict:
    """Zapis raportu z Karoo + powiadomienia. Zwraca {ok, qext2Disable} (QExt2 stosuje liste od razu)."""
    import qbot_notif as N
    _ensure(cur)
    karoo = rep.get("karoo") if isinstance(rep.get("karoo"), dict) else {}
    results = rep.get("results") if isinstance(rep.get("results"), dict) else {}
    guard = rep.get("guard") if isinstance(rep.get("guard"), dict) else {}
    sig = karoo_sig(karoo)
    fails = _fails(results)
    cur.execute("SELECT karoo_sig, karoo, results FROM qbot_v2.qext2_karoo_health ORDER BY id DESC LIMIT 1")
    prev = _one(cur)
    cur.execute("INSERT INTO qbot_v2.qext2_karoo_health (boot, build, build_name, karoo_sig, karoo, results, guard, "
                "crash_loop, n_fail) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)",
                (int(rep.get("boot") or -1), int(rep.get("build") or 0) or None, str(rep.get("buildName") or "")[:40] or None,
                 sig, json.dumps(karoo), json.dumps(results), json.dumps(guard), bool(rep.get("crashLoop")), len(fails)))
    names = [TESTS.get(t, (t,))[0] for t in fails]
    if rep.get("crashLoop"):
        names.insert(0, "QExt2 padał w pętli — funkcje nieoficjalne wyłączone do restartu Karoo")
    # 1) aktualizacja Karoo (zmiana wersji wzgledem poprzedniego raportu)
    if prev and prev.get("karoo_sig") and prev["karoo_sig"] != sig:
        old = karoo_label(prev.get("karoo") if isinstance(prev.get("karoo"), dict) else json.loads(prev.get("karoo") or "{}"))
        title = ("Karoo zaktualizowane — QExt2 działa" if not names
                 else f"Karoo zaktualizowane — nie działa: {', '.join(names)}")
        N.push(cur, f"qext2:karoo:wersja:{sig}", "system", title,
               f"Było: {old}. Jest: {karoo_label(karoo)}. Szczegóły: SETUP → QExt2 → Autotest Karoo.", url="/setup.html#qext2")
    # 2) cos nie dziala (stan biezacy; zamyka sie, gdy kolejny autotest jest czysty)
    if names:
        N.push(cur, NOTIF_FAIL, "system", f"QExt2 na Karoo: nie działa {', '.join(names)}",
               "; ".join(f"{TESTS.get(t, (t,))[0]}: {(results.get(t) or {}).get('d', '')}" for t in fails)
               + ". Można wyłączyć funkcję zdalnie: SETUP → QExt2 → Autotest Karoo.", url="/setup.html#qext2")
    else:
        N.resolve(cur, NOTIF_FAIL)
    return {"ok": True, "saved": "karooHealth", "fails": fails, "qext2Disable": disabled(cur)}


def view(cur) -> dict:
    """SETUP > QExt2 > Autotest Karoo: ostatni wynik, historia wersji Karoo, wylacznik zdalny."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Warsaw")
    _ensure(cur)
    cur.execute("SELECT received_at, boot, build, build_name, karoo_sig, karoo, results, guard, crash_loop, n_fail "
                "FROM qbot_v2.qext2_karoo_health ORDER BY id DESC LIMIT 200")
    rows = _all(cur)

    def j(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}

    def t(ts):
        return ts.astimezone(tz).strftime("%d.%m.%Y %H:%M") if ts else ""

    last = None
    if rows:
        r = rows[0]
        res, g = j(r["results"]), j(r["guard"])
        last = {"at": t(r["received_at"]), "build": r["build"], "buildName": r["build_name"],
                "karoo": karoo_label(j(r["karoo"])), "crashLoop": bool(r["crash_loop"]),
                "tests": [{"id": k, "name": TESTS[k][0], "s": (res.get(k) or {}).get("s", "—"),
                           "d": (res.get(k) or {}).get("d", "")} for k in TESTS if k in res],
                "guard": {k: GUARD_PL.get(v, v) for k, v in g.items()}}
    # historia wersji Karoo: kolejne odcinki tej samej wersji (od najstarszego do najnowszego, wynik wg ostatniego testu)
    hist = []
    for r in reversed(rows):
        if hist and hist[-1]["sig"] == r["karoo_sig"]:
            h = hist[-1]
            h["to"] = t(r["received_at"])
            h["builds"].add(r["build"])
            h["fails"] = r["n_fail"]
        else:
            hist.append({"sig": r["karoo_sig"], "karoo": karoo_label(j(r["karoo"])), "from": t(r["received_at"]),
                         "to": t(r["received_at"]), "builds": {r["build"]}, "fails": r["n_fail"]})
    for h in hist:
        h["builds"] = sorted(b for b in h["builds"] if b)
    dis = disabled(cur)
    return {"last": last, "history": list(reversed(hist))[:20], "darkMode": {"on": "darkmenu" not in dis, "set": list(DARK_SET)},
            "features": [{"id": k, "name": v, "off": k in dis} for k, v in FEATURES.items()]}
