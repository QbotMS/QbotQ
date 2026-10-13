"""Garaz > Zakupy (2026-10-13): lista planowanych zakupow (rower + zdrowie) i lista kupionych.

Baza: garage.db, tabela shop_items (tworzona tu, IF NOT EXISTS).
Dane z linku: front wola istniejace /api/garage/scrape (qbot_gear_scrape) z kategoriami CATEGORIES.
Miniatura: przy zapisie, gdy jest image_url a brak thumb - pobieramy obrazek i robimy JPEG 320 px (data URI),
zeby lista nie zalezala od hotlinkow sklepu.

GET  /api/zakupy/list                 -> {items, categories, priorities, bikes}
POST /api/zakupy/save                 <- {id?, name, brand, url, category, priority, qty, price, currency,
                                            bike_id, notes, image_url}
POST /api/zakupy/bought               <- {id, paid_price?, bought_at? (RRRR-MM-DD)}   -> do listy Kupione
POST /api/zakupy/unbought             <- {id}                                         -> z powrotem do planu
POST /api/zakupy/delete               <- {id}                                         (miekko: deleted=1)
Zapisy tylko dla wlasciciela (sesja demo = odczyt). Dok.: docs/ZAKUPY.md
"""
from __future__ import annotations

import datetime as _dt
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

COLS = ("id", "name", "brand", "url", "shop", "category", "priority", "qty", "price", "currency",
        "price_at", "image_url", "thumb", "bike_id", "notes", "status", "bought_at", "paid_price",
        "created_at", "updated_at")


def _conn():
    c = sqlite3.connect(GARAGE_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(DDL)
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
    if x < 0:
        raise HTTPException(status_code=400, detail="liczba ujemna: %s" % v)
    return round(x, 2)


def _date(v):
    if v in (None, ""):
        return _dt.date.today().isoformat()
    s = str(v).strip()[:10]
    try:
        _dt.date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="zla data: %s" % v)
    return s


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
    bid = b.get("bike_id")
    try:
        v["bike_id"] = int(bid) if bid not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        v["bike_id"] = None
    v["notes"] = _txt(b.get("notes"), 2000)
    return v


def _make_thumb(image_url):
    try:
        import qbot_gear_scrape as scr
        raw = scr._fetch_image(image_url)
        b64, _ = scr._thumb_b64(raw)
        return ("data:image/jpeg;base64," + b64) if b64 else None
    except Exception:
        return None


def _row(r):
    d = {k: r[k] for k in COLS}
    d["garage_target"] = GARAGE_TARGET.get(d["category"])
    d["priority_label"] = PRIORITIES.get(d["priority"])
    return d


def list_items(c):
    rows = c.execute(
        "SELECT * FROM shop_items WHERE deleted=0 "
        "ORDER BY CASE status WHEN 'planned' THEN 0 ELSE 1 END, "
        "CASE WHEN status='planned' THEN priority END, "
        "CASE WHEN status='bought' THEN bought_at END DESC, created_at DESC").fetchall()
    return [_row(r) for r in rows]


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
        c = _conn()
        try:
            items = list_items(c)
            bikes = [dict(x) for x in c.execute(
                "SELECT id, name, nickname FROM bikes WHERE active=1 ORDER BY id").fetchall()]
        finally:
            c.close()
        return {"items": items, "categories": CATEGORIES,
                "priorities": [{"v": k, "label": v} for k, v in PRIORITIES.items()],
                "bikes": bikes}

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
        c = _conn()
        try:
            row = c.execute("SELECT * FROM shop_items WHERE id=? AND deleted=0", (iid,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="brak pozycji")
            if paid is None:
                paid = row["price"]
            c.execute("UPDATE shop_items SET status='bought', bought_at=?, paid_price=?, "
                      "updated_at=datetime('now') WHERE id=?", (day, paid, iid))
            c.commit()
            out = _row(c.execute("SELECT * FROM shop_items WHERE id=?", (iid,)).fetchone())
        finally:
            c.close()
        return {"ok": True, "item": out}

    @r.post("/unbought")
    async def zk_unbought(request: Request) -> Any:
        _auth(request, write=True)
        iid = _id(await _body(request))
        c = _conn()
        try:
            n = c.execute("UPDATE shop_items SET status='planned', bought_at=NULL, paid_price=NULL, "
                          "updated_at=datetime('now') WHERE id=? AND deleted=0", (iid,)).rowcount
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
            c.commit()
        finally:
            c.close()
        if not n:
            raise HTTPException(status_code=404, detail="brak pozycji")
        return {"ok": True}

    return r
