"""Garaz > Zakupy (2026-10-13): lista planowanych zakupow (rower + zdrowie), lista kupionych, zapas i przypomnienia.

Baza: garage.db, tabela shop_items (tworzona/uzupelniana tu: DDL + brakujace kolumny).
Dane z linku: front wola istniejace /api/garage/scrape (qbot_gear_scrape) z kategoriami CATEGORIES.
Miniatura: przy zapisie, gdy jest image_url a brak thumb - pobieramy obrazek i robimy JPEG 320 px (data URI).

ETAP 2 (2026-10-13) - zapas rzeczy zuzywalnych (suple, zatyczki...):
- opakowanie: pack_units (np. 90) x qty, jednostka pack_unit (kaps./szt./...), otwarte od opened_at
  (domyslnie data zakupu; dla dokupionego opakowania = przewidywany koniec poprzedniego).
- zuzycie: per_day (recznie) ALBO powiazanie z Zdrowie > Suplementy (supplement_id + per_intake = ile jednostek
  na jedno przyjecie). Dla suplementu liczymy dni wg harmonogramu (dni tygodnia) od otwarcia do wczoraj, MINUS dni
  oznaczone 'pominiete' - dzien niepotwierdzony liczymy jako wziety (przypomnienie raczej za wczesnie niz za pozno).
- przypomnienie, gdy zapasu zostalo na <= lead_days dni (domyslnie 10): Dzwonek (live:zakupy:<id>, notif_items)
  + linia i przyciski w PORANNEJ wiadomosci Telegram (morning) - bez osobnej wiadomosci.
  Przyciski: 'Kup ponownie' (kopia na liste Do kupienia, priorytet Pilne) i 'Odloz 7 dni'. Telegram: zk:r:<id>, zk:z:<id>.

GET  /api/zakupy/list      -> {items (z forecast/due), categories, priorities, bikes, supplements}
POST /api/zakupy/save      <- {id?, name, brand, url, category, priority, qty, price, currency, bike_id, notes, image_url,
                               pack_units, pack_unit, per_day, supplement_id, per_intake, lead_days, opened_at}
POST /api/zakupy/bought    <- {id, paid_price?, bought_at?}      -> do listy Kupione
POST /api/zakupy/unbought  <- {id}                               -> z powrotem do planu
POST /api/zakupy/delete    <- {id}                               (miekko: deleted=1)
POST /api/zakupy/rebuy     <- {id}                               -> nowa pozycja Do kupienia (kopia), idempotentnie
POST /api/zakupy/snooze    <- {id, days=7}                       -> przypomnienie odlozone
POST /api/zakupy/price-search <- {id}                            -> szukanie najnizszej ceny w tle (etap 3)
POST /api/zakupy/use-offer <- {id, url, price, currency, shop}   -> oferta z wyniku jako link i cena pozycji
Zapisy tylko dla wlasciciela (sesja demo = odczyt). Dok.: docs/ZAKUPY.md
"""
from __future__ import annotations

import datetime as _dt
import math
import re
import sqlite3
from typing import Any, Callable
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request

GARAGE_DB = "/opt/qbot/app/data/garage.db"

# Kategorie = dwie grupy (Rower / Zdrowie). Wartosci przekazywane tez do AI przy zaciaganiu z linku.
CATEGORIES = [
    "Rower / części",
    "Rower / odzież",
    "Rower / wyposażenie",
    "Zdrowie / suplementy",
    "Zdrowie / sprzęt",
    "Inne",
]
# Dokad proponujemy dodac rzecz po zakupie (zakladka Garazu).
GARAGE_TARGET = {
    "Rower / części": "bike",
    "Rower / odzież": "gear",
    "Rower / wyposażenie": "equip",
}
PRIORITIES = {1: "Pilne", 2: "Wkrótce", 3: "Kiedyś"}
LEAD_DAYS = 10
SNOOZE_DAYS = 7
MORNING_MAX = 3          # ile pozycji z przyciskami w porannej wiadomosci
DNI = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]

DDL = """
CREATE TABLE IF NOT EXISTS shop_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    brand      TEXT,
    url        TEXT,
    shop       TEXT,
    category   TEXT NOT NULL,
    priority   INTEGER NOT NULL DEFAULT 2,
    qty        INTEGER NOT NULL DEFAULT 1,
    price      REAL,
    currency   TEXT,
    price_at   TEXT,
    image_url  TEXT,
    thumb      TEXT,
    bike_id    INTEGER,
    notes      TEXT,
    status     TEXT NOT NULL DEFAULT 'planned',
    bought_at  TEXT,
    paid_price REAL,
    deleted    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_shop_items_status ON shop_items(status, deleted);
"""
# etap 2: kolumny dokladane do istniejacej tabeli
EXTRA_COLS = [("pack_units", "REAL"), ("pack_unit", "TEXT"), ("per_day", "REAL"), ("supplement_id", "INTEGER"),
              ("per_intake", "REAL"), ("lead_days", "INTEGER"), ("opened_at", "TEXT"), ("snooze_until", "TEXT"),
              ("refill_id", "INTEGER"), ("refill_of", "INTEGER"),
              # etap 3: szukanie najnizszej ceny (qbot_zakupy_ceny.py, scripts/zakupy_ceny_worker.py)
              ("price_search_at", "TEXT"), ("price_search_status", "TEXT"), ("price_search_note", "TEXT")]

COLS = ("id", "name", "brand", "url", "shop", "category", "priority", "qty", "price", "currency",
        "price_at", "image_url", "thumb", "bike_id", "notes", "status", "bought_at", "paid_price",
        "created_at", "updated_at") + tuple(c for c, _ in EXTRA_COLS)
PACK_FIELDS = ("pack_units", "pack_unit", "per_day", "supplement_id", "per_intake", "lead_days")
COPY_FIELDS = ("name", "brand", "url", "shop", "category", "qty", "price", "currency", "price_at", "image_url",
               "thumb", "bike_id", "notes") + PACK_FIELDS


def _conn(path=None):
    c = sqlite3.connect(path or GARAGE_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(DDL)
    have = {r[1] for r in c.execute("PRAGMA table_info(shop_items)")}
    for col, typ in EXTRA_COLS:
        if col not in have:
            c.execute("ALTER TABLE shop_items ADD COLUMN %s %s" % (col, typ))
    import qbot_zakupy_ceny as _C
    _C.ensure(c)
    return c


def shop_from_url(url):
    host = (urlparse(url or "").hostname or "").lower()
    host = re.sub(r"^(www|m|sklep|shop)\.", "", host)
    return host or None


def _txt(v, n):
    if v is None:
        return None
    s = str(v).strip()
    return s[:n] if s else None


def _num(v):
    if v in (None, ""):
        return None
    try:
        x = float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="zla liczba: %s" % v)
    if x < 0 or math.isnan(x) or math.isinf(x):
        raise HTTPException(status_code=400, detail="zla liczba: %s" % v)
    return round(x, 2)


def _date(v, default_today=True):
    if v in (None, ""):
        return _dt.date.today().isoformat() if default_today else None
    s = str(v).strip()[:10]
    try:
        _dt.date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="zla data: %s" % v)
    return s


def _int(v):
    try:
        return int(v) if v not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return None


def clean(b: dict) -> dict:
    """Walidacja pol z formularza. Rzuca HTTPException 400."""
    v = {}
    v["name"] = _txt(b.get("name"), 200)
    if not v["name"]:
        raise HTTPException(status_code=400, detail="podaj nazwę")
    v["category"] = b.get("category") or ""
    if v["category"] not in CATEGORIES:
        raise HTTPException(status_code=400, detail="wybierz kategorię")
    try:
        v["priority"] = int(b.get("priority") or 2)
    except (TypeError, ValueError):
        v["priority"] = 2
    if v["priority"] not in PRIORITIES:
        raise HTTPException(status_code=400, detail="zly priorytet")
    try:
        v["qty"] = max(1, min(999, int(b.get("qty") or 1)))
    except (TypeError, ValueError):
        v["qty"] = 1
    url = _txt(b.get("url"), 1000)
    if url and not re.match(r"^https?://", url, re.I):
        raise HTTPException(status_code=400, detail="link musi zaczynać się od http(s)://")
    v["url"] = url
    v["shop"] = shop_from_url(url)
    v["brand"] = _txt(b.get("brand"), 120)
    v["price"] = _num(b.get("price"))
    v["currency"] = (_txt(b.get("currency"), 8) or ("PLN" if v["price"] is not None else None))
    if v["currency"]:
        v["currency"] = v["currency"].upper().replace("ZŁ", "PLN")
    img = _txt(b.get("image_url"), 1000)
    v["image_url"] = img if (img and re.match(r"^https?://", img, re.I)) else None
    v["bike_id"] = _int(b.get("bike_id"))
    v["notes"] = _txt(b.get("notes"), 2000)
    # etap 2: opakowanie i zuzycie (wszystko opcjonalne)
    v["pack_units"] = _num(b.get("pack_units"))
    v["pack_unit"] = _txt(b.get("pack_unit"), 16)
    v["supplement_id"] = _int(b.get("supplement_id"))
    v["per_intake"] = _num(b.get("per_intake")) if v["supplement_id"] else None
    v["per_day"] = None if v["supplement_id"] else _num(b.get("per_day"))
    if v["supplement_id"] and not v["per_intake"]:
        v["per_intake"] = 1.0
    ld = _int(b.get("lead_days"))
    v["lead_days"] = max(1, min(90, ld)) if ld else None
    if "opened_at" in b:
        v["opened_at"] = _date(b.get("opened_at"), default_today=False)
    return v


def _make_thumb(image_url):
    try:
        import qbot_gear_scrape as scr
        raw = scr._fetch_image(image_url)
        b64, _ = scr._thumb_b64(raw)
        return ("data:image/jpeg;base64," + b64) if b64 else None
    except Exception:
        return None


# ---------------- zapas: czyste funkcje (testowane) ----------------

def _d(s):
    return _dt.date.fromisoformat(str(s)[:10]) if s else None


def forecast(it: dict, today: _dt.date, supl: dict | None = None) -> dict | None:
    """Ile zostalo i do kiedy starczy. supl = {id: {"days": [..]|None, "active": bool, "skipped": set(date)}}.
    None = nie liczymy (nie kupione, brak opakowania albo brak zuzycia)."""
    if it.get("status") != "bought" or not it.get("pack_units"):
        return None
    opened = _d(it.get("opened_at")) or _d(it.get("bought_at"))
    if not opened:
        return None
    pack = float(it["pack_units"]) * int(it.get("qty") or 1)
    sid = it.get("supplement_id")
    if sid:
        s = (supl or {}).get(sid)
        if not s:
            return None
        per = float(it.get("per_intake") or 1)
        sched = s.get("days") or None
        n = 0
        d = opened
        while d < today:
            if (not sched or d.weekday() in sched) and d not in s.get("skipped", ()):
                n += 1
            d += _dt.timedelta(days=1)
        used = n * per
        rate = per * (len(sched) / 7.0 if sched else 1.0) if s.get("active") else 0.0
    else:
        per_day = float(it.get("per_day") or 0)
        if per_day <= 0:
            return None
        used = max(0, (today - opened).days) * per_day
        rate = per_day
    remaining = max(0.0, pack - used)
    days_left = int(remaining // rate) if rate > 0 else None
    return {"pack": pack, "used": round(used, 1), "remaining": round(remaining, 1), "rate": round(rate, 3),
            "unit": it.get("pack_unit") or "szt.", "opened": opened.isoformat(), "days_left": days_left,
            "end": (today + _dt.timedelta(days=days_left)).isoformat() if days_left is not None else None,
            "pct": round(remaining / pack, 3) if pack else 0}


def is_due(it: dict, f: dict | None, today: _dt.date) -> bool:
    if not f or f.get("days_left") is None or it.get("refill_id"):
        return False
    sn = _d(it.get("snooze_until"))
    if sn and sn > today:
        return False
    return f["days_left"] <= int(it.get("lead_days") or LEAD_DAYS)


def _fmt_n(x) -> str:
    return ("%g" % round(float(x), 1)).replace(".", ",")


def due_text(it: dict, f: dict) -> str:
    end = _d(f["end"])
    return "zostało ok. %s %s — starczy do %s %s (%d dni)" % (
        _fmt_n(f["remaining"]), f["unit"], DNI[end.weekday()], end.strftime("%d.%m"), f["days_left"])


# ---------------- suplementy (Zdrowie) - tylko odczyt ----------------

def load_supplements() -> dict:
    """{id: {name, days, active, skipped:set}} z qbot_v2 (modul qbot_supplements). Blad -> {}."""
    try:
        from fitmodel.api import _db_connect
        con = _db_connect()
    except Exception:
        return {}
    try:
        cur = con.cursor()
        cur.execute("SELECT id, name, days, active FROM qbot_v2.supplement WHERE NOT deleted ORDER BY sort, id")
        out = {r[0]: {"id": r[0], "name": r[1], "days": list(r[2]) if r[2] else None, "active": bool(r[3]),
                      "skipped": set()} for r in cur.fetchall()}
        cur.execute("SELECT supplement_id, day FROM qbot_v2.supplement_log WHERE status='skipped'")
        for sid, day in cur.fetchall():
            if sid in out:
                out[sid]["skipped"].add(day)
        return out
    except Exception:
        return {}
    finally:
        con.close()


# ---------------- odczyt / akcje (wspolne dla API, Dzwonka i Telegrama) ----------------

def _row(r, today=None, supl=None):
    d = {k: r[k] for k in COLS}
    d["garage_target"] = GARAGE_TARGET.get(d["category"])
    d["priority_label"] = PRIORITIES.get(d["priority"])
    today = today or _dt.date.today()
    f = forecast(d, today, supl)
    d["forecast"] = f
    d["due"] = is_due(d, f, today)
    return d


def list_items(c, today=None, supl=None):
    rows = c.execute(
        "SELECT * FROM shop_items WHERE deleted=0 "
        "ORDER BY CASE status WHEN 'planned' THEN 0 ELSE 1 END, "
        "CASE WHEN status='planned' THEN priority END, "
        "CASE WHEN status='bought' THEN bought_at END DESC, created_at DESC").fetchall()
    out = [_row(r, today, supl) for r in rows]
    import qbot_zakupy_ceny as _C
    for d in out:
        d["offers"] = _C.latest_offers(c, d["id"]) if d.get("price_search_at") else None
    return out


def due_items(today=None, path=None, supl=None) -> list[dict]:
    today = today or _dt.date.today()
    if supl is None:
        supl = load_supplements()
    c = _conn(path)
    try:
        rows = c.execute("SELECT * FROM shop_items WHERE deleted=0 AND status='bought' AND pack_units IS NOT NULL").fetchall()
        items = [_row(r, today, supl) for r in rows]
    finally:
        c.close()
    out = [x for x in items if x["due"]]
    out.sort(key=lambda x: (x["forecast"]["days_left"], x["name"]))
    return out


def rebuy(iid: int, path=None) -> dict:
    """Kopia kupionej pozycji na liste Do kupienia (priorytet Pilne). Idempotentnie: druga proba zwraca te sama."""
    c = _conn(path)
    try:
        src = c.execute("SELECT * FROM shop_items WHERE id=? AND deleted=0", (iid,)).fetchone()
        if not src:
            raise KeyError("brak pozycji %s" % iid)
        if src["refill_id"]:
            ex = c.execute("SELECT id FROM shop_items WHERE id=? AND deleted=0", (src["refill_id"],)).fetchone()
            if ex:
                return {"id": ex["id"], "name": src["name"], "new": False}
        vals = {k: src[k] for k in COPY_FIELDS}
        vals.update(priority=1, status="planned", refill_of=iid)
        keys = list(vals)
        nid = c.execute("INSERT INTO shop_items (%s) VALUES (%s)" % (", ".join(keys), ", ".join(":" + k for k in keys)),
                        vals).lastrowid
        c.execute("UPDATE shop_items SET refill_id=?, updated_at=datetime('now') WHERE id=?", (nid, iid))
        c.commit()
        return {"id": nid, "name": src["name"], "new": True}
    finally:
        c.close()


def snooze(iid: int, days: int = SNOOZE_DAYS, path=None, today=None) -> str:
    until = ((today or _dt.date.today()) + _dt.timedelta(days=max(1, min(60, int(days))))).isoformat()
    c = _conn(path)
    try:
        n = c.execute("UPDATE shop_items SET snooze_until=?, updated_at=datetime('now') WHERE id=? AND deleted=0",
                      (until, iid)).rowcount
        c.commit()
    finally:
        c.close()
    if not n:
        raise KeyError("brak pozycji %s" % iid)
    return until


# ---------------- Dzwonek (qbot_notif.sync_live) ----------------

def notif_items(today=None) -> list[dict]:
    out = []
    for it in due_items(today):
        out.append({"key": "live:zakupy:%d" % it["id"], "kind": "zakupy",
                    "title": "Kończy się: %s" % it["name"], "body": due_text(it, it["forecast"]),
                    "url": "/garaz.html#zakupy",
                    "action": {"label": "Kup ponownie", "post": "/api/zakupy/rebuy", "body": {"id": it["id"]}}})
    return out


# ---------------- Telegram: poranna wiadomosc + przyciski ----------------

def morning(today=None) -> tuple[str | None, list]:
    """(linia do porannej wiadomosci, wiersze przyciskow) - jak qbot_supplements.morning."""
    items = due_items(today)
    if not items:
        return None, []
    parts = ["%s (do %s)" % (it["name"], _d(it["forecast"]["end"]).strftime("%d.%m")) for it in items]
    kb = [[{"text": "🛒 Kup ponownie: %s" % it["name"][:28], "callback_data": "zk:r:%d" % it["id"]},
           {"text": "⏰ +%d dni" % SNOOZE_DAYS, "callback_data": "zk:z:%d" % it["id"]}] for it in items[:MORNING_MAX]]
    return "🛒 Kończy się: " + ", ".join(parts), kb


def _drop_buttons(msg: dict, iid: int) -> None:
    """Usun z wiadomosci tylko wiersz przyciskow tej pozycji (reszta porannych przyciskow zostaje)."""
    try:
        kb = ((msg.get("reply_markup") or {}).get("inline_keyboard")) or []
        keep = [row for row in kb if not any(str(b.get("callback_data", "")).startswith("zk:") and
                                             str(b.get("callback_data", "")).endswith(":%d" % iid) for b in row)]
        if len(keep) != len(kb):
            from qbot_telegram_client import _api
            _api("editMessageReplyMarkup", {"chat_id": (msg.get("chat") or {}).get("id"), "message_id": msg.get("message_id"),
                                            "reply_markup": {"inline_keyboard": keep}})
    except Exception:
        pass


def handle_callback(cq, tg_answer_callback, tg_send_plain, tg_edit_markup, chat_id_allowed):
    """zk:r:<id> kup ponownie / zk:z:<id> odloz 7 dni."""
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    if str((msg.get("chat") or {}).get("id", "")) != str(chat_id_allowed):
        tg_answer_callback(cq.get("id"), "Brak dostepu")
        return
    parts = data.split(":")
    act = parts[1] if len(parts) > 1 else ""
    try:
        iid = int(parts[2])
    except (IndexError, ValueError):
        tg_answer_callback(cq.get("id"))
        return
    try:
        if act == "r":
            r = rebuy(iid)
            tg_answer_callback(cq.get("id"), ("Dodane do listy zakupów: %s" if r["new"] else "Już jest na liście: %s") % r["name"][:40])
        elif act == "z":
            until = snooze(iid)
            tg_answer_callback(cq.get("id"), "Przypomnę od %s" % _d(until).strftime("%d.%m"))
        else:
            tg_answer_callback(cq.get("id"))
            return
    except Exception as e:
        tg_answer_callback(cq.get("id"), "Błąd zapisu")
        tg_send_plain("⚠️ Zakupy: nie udało się zapisać (%s)." % type(e).__name__)
        raise
    _drop_buttons(msg, iid)


# ---------------- API ----------------

def build_router(current_user: Callable, owner_user: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/zakupy")

    def _auth(request, write=False):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        if write and not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")

    async def _body(request):
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Bledny JSON")
        if not isinstance(b, dict):
            raise HTTPException(status_code=400, detail="Bledny JSON")
        return b

    def _id(b):
        try:
            return int(b.get("id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="brak id")

    @r.get("/list")
    def zk_list(request: Request) -> Any:
        _auth(request)
        supl = load_supplements()
        c = _conn()
        try:
            items = list_items(c, supl=supl)
            bikes = [dict(x) for x in c.execute(
                "SELECT id, name, nickname FROM bikes WHERE active=1 ORDER BY id").fetchall()]
        finally:
            c.close()
        return {"items": items, "categories": CATEGORIES,
                "priorities": [{"v": k, "label": v} for k, v in PRIORITIES.items()],
                "bikes": bikes, "lead_days": LEAD_DAYS,
                "supplements": [{"id": s["id"], "name": s["name"], "active": s["active"]} for s in supl.values()]}

    @r.post("/save")
    async def zk_save(request: Request) -> Any:
        _auth(request, write=True)
        b = await _body(request)
        v = clean(b)
        c = _conn()
        try:
            iid = b.get("id")
            old = None
            if iid not in (None, ""):
                iid = _id(b)
                old = c.execute("SELECT * FROM shop_items WHERE id=? AND deleted=0", (iid,)).fetchone()
                if not old:
                    raise HTTPException(status_code=404, detail="brak pozycji")
            thumb = old["thumb"] if old else None
            if v["image_url"] and (not old or old["image_url"] != v["image_url"] or not thumb):
                thumb = _make_thumb(v["image_url"]) or thumb
            if not v["image_url"] and old and old["image_url"]:
                thumb = None
            price_changed = (not old) or old["price"] != v["price"]
            price_at = (_dt.datetime.now().strftime("%Y-%m-%d %H:%M") if v["price"] is not None and price_changed
                        else (old["price_at"] if old else None))
            vals = dict(v, thumb=thumb, price_at=price_at)
            if old:
                sets = ", ".join("%s=:%s" % (k, k) for k in vals)
                c.execute("UPDATE shop_items SET %s, updated_at=datetime('now') WHERE id=:id" % sets,
                          dict(vals, id=iid))
            else:
                keys = list(vals)
                cur = c.execute("INSERT INTO shop_items (%s) VALUES (%s)" % (
                    ", ".join(keys), ", ".join(":" + k for k in keys)), vals)
                iid = cur.lastrowid
            c.commit()
        finally:
            c.close()
        return {"ok": True, "id": iid, "thumb": bool(thumb)}

    @r.post("/bought")
    async def zk_bought(request: Request) -> Any:
        _auth(request, write=True)
        b = await _body(request)
        iid = _id(b)
        paid = _num(b.get("paid_price"))
        day = _date(b.get("bought_at"))
        supl = None
        c = _conn()
        try:
            row = c.execute("SELECT * FROM shop_items WHERE id=? AND deleted=0", (iid,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="brak pozycji")
            if paid is None:
                paid = row["price"]
            opened = row["opened_at"] or day
            if row["refill_of"] and not row["opened_at"]:
                # dokupione opakowanie zaczyna sie, gdy skonczy sie poprzednie (jesli pozniej niz zakup)
                prev = c.execute("SELECT * FROM shop_items WHERE id=?", (row["refill_of"],)).fetchone()
                if prev:
                    supl = load_supplements() if prev["supplement_id"] else {}
                    pf = forecast({k: prev[k] for k in COLS}, _dt.date.today(), supl)
                    if pf and pf.get("end") and pf["end"] > day:
                        opened = pf["end"]
            c.execute("UPDATE shop_items SET status='bought', bought_at=?, paid_price=?, opened_at=?, "
                      "updated_at=datetime('now') WHERE id=?", (day, paid, opened if row["pack_units"] else row["opened_at"], iid))
            c.commit()
            out = _row(c.execute("SELECT * FROM shop_items WHERE id=?", (iid,)).fetchone(),
                       supl=supl if supl is not None else (load_supplements() if row["supplement_id"] else {}))
        finally:
            c.close()
        return {"ok": True, "item": out}

    @r.post("/unbought")
    async def zk_unbought(request: Request) -> Any:
        _auth(request, write=True)
        iid = _id(await _body(request))
        c = _conn()
        try:
            n = c.execute("UPDATE shop_items SET status='planned', bought_at=NULL, paid_price=NULL, opened_at=NULL, "
                          "snooze_until=NULL, updated_at=datetime('now') WHERE id=? AND deleted=0", (iid,)).rowcount
            c.commit()
        finally:
            c.close()
        if not n:
            raise HTTPException(status_code=404, detail="brak pozycji")
        return {"ok": True}

    @r.post("/delete")
    async def zk_delete(request: Request) -> Any:
        _auth(request, write=True)
        iid = _id(await _body(request))
        c = _conn()
        try:
            n = c.execute("UPDATE shop_items SET deleted=1, updated_at=datetime('now') WHERE id=?",
                          (iid,)).rowcount
            # usunieta kopia 'Kup ponownie' -> oryginal znow przypomina
            c.execute("UPDATE shop_items SET refill_id=NULL WHERE refill_id=?", (iid,))
            c.commit()
        finally:
            c.close()
        if not n:
            raise HTTPException(status_code=404, detail="brak pozycji")
        return {"ok": True}

    @r.post("/rebuy")
    async def zk_rebuy(request: Request) -> Any:
        _auth(request, write=True)
        iid = _id(await _body(request))
        try:
            res = rebuy(iid)
        except KeyError:
            raise HTTPException(status_code=404, detail="brak pozycji")
        return dict(res, ok=True)

    @r.post("/price-search")
    async def zk_price_search(request: Request) -> Any:
        """Start szukania ceny w tle (ok. 30-90 s). Wynik: price_search_* + shop_offers + Dzwonek."""
        _auth(request, write=True)
        iid = _id(await _body(request))
        c = _conn()
        try:
            row = c.execute("SELECT price_search_status, price_search_at FROM shop_items WHERE id=? AND deleted=0",
                            (iid,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="brak pozycji")
            now = _dt.datetime.now()
            if row["price_search_status"] == "running" and row["price_search_at"]:
                try:
                    age = (now - _dt.datetime.strptime(row["price_search_at"], "%Y-%m-%d %H:%M")).total_seconds()
                except ValueError:
                    age = 1e9
                if age < 300:
                    raise HTTPException(status_code=409, detail="szukanie już trwa")
            c.execute("UPDATE shop_items SET price_search_status='running', price_search_note=NULL, price_search_at=? "
                      "WHERE id=?", (now.strftime("%Y-%m-%d %H:%M"), iid))
            c.commit()
        finally:
            c.close()
        import subprocess
        import sys as _sys
        log = open("/opt/qbot/artifacts/zakupy_ceny.log", "ab")
        subprocess.Popen([_sys.executable, "/opt/qbot/app/scripts/zakupy_ceny_worker.py", str(iid)],
                         stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         cwd="/opt/qbot/app", start_new_session=True)
        log.close()   # dziecko ma wlasna kopie uchwytu
        return {"ok": True, "status": "running"}

    @r.post("/use-offer")
    async def zk_use_offer(request: Request) -> Any:
        """Ustaw znaleziona oferte jako link i cene pozycji."""
        _auth(request, write=True)
        b = await _body(request)
        iid = _id(b)
        url = _txt(b.get("url"), 1000)
        if not url or not re.match(r"^https?://", url, re.I):
            raise HTTPException(status_code=400, detail="zly link")
        price = _num(b.get("price"))
        cur_ = (_txt(b.get("currency"), 8) or "PLN").upper()
        shop = _txt(b.get("shop"), 120) or shop_from_url(url)
        c = _conn()
        try:
            n = c.execute("UPDATE shop_items SET url=?, shop=?, price=?, currency=?, price_at=?, updated_at=datetime('now') "
                          "WHERE id=? AND deleted=0", (url, shop, price, cur_,
                                                     _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), iid)).rowcount
            c.commit()
        finally:
            c.close()
        if not n:
            raise HTTPException(status_code=404, detail="brak pozycji")
        return {"ok": True}

    @r.post("/snooze")
    async def zk_snooze(request: Request) -> Any:
        _auth(request, write=True)
        b = await _body(request)
        iid = _id(b)
        try:
            until = snooze(iid, int(b.get("days") or SNOOZE_DAYS))
        except KeyError:
            raise HTTPException(status_code=404, detail="brak pozycji")
        return {"ok": True, "snooze_until": until}

    return r
