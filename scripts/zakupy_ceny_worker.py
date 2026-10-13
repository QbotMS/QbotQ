#!/usr/bin/env python3
"""Worker szukania ceny dla jednej pozycji Zakupow (Garaz). Uruchamiany w tle przez POST /api/zakupy/price-search.
Uzycie: .venv/bin/python3 scripts/zakupy_ceny_worker.py <item_id>
Stan na shop_items.price_search_* (running -> done|error), oferty w shop_offers, na koncu wpis w Dzwonku.
Logika: qbot_zakupy_ceny.py. Dok.: docs/ZAKUPY.md"""
import os
import sys
import time

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_zakupy_api as Z
import qbot_zakupy_ceny as C


def _set(iid, status, note=None, at=None):
    c = Z._conn()
    try:
        C.ensure(c)
        c.execute("UPDATE shop_items SET price_search_status=?, price_search_note=?, "
                  "price_search_at=coalesce(?, price_search_at) WHERE id=?", (status, note, at, iid))
        c.commit()
    finally:
        c.close()


def _notify(iid, name, text, run_at):
    try:
        import qbot_notif as NF
        from fitmodel.api import _db_connect
        con = _db_connect()
        try:
            cur = con.cursor()
            NF.push(cur, "zakupy:ceny:%d:%s" % (iid, run_at.replace(" ", "T")), "zakupy", "Ceny: %s" % name[:80], text,
                    "/garaz.html#zakupy")
            con.commit()
        finally:
            con.close()
    except Exception as e:
        C._log("dzwonek: %s" % e)


def main(iid: int) -> int:
    c = Z._conn()
    try:
        C.ensure(c)
        r = c.execute("SELECT * FROM shop_items WHERE id=? AND deleted=0", (iid,)).fetchone()
    finally:
        c.close()
    if not r:
        C._log("brak pozycji %s" % iid)
        return 1
    item = {"id": iid, "name": r["name"], "brand": r["brand"], "url": r["url"]}
    run_at = time.strftime("%Y-%m-%d %H:%M")
    C._log("start #%d %s" % (iid, item["name"]))
    try:
        res = C.run(item)
    except Exception as e:
        C._log("BLAD #%d: %s: %s" % (iid, type(e).__name__, e))
        _set(iid, "error", "błąd: %s" % type(e).__name__, run_at)
        return 1
    c = Z._conn()
    try:
        C.ensure(c)
        C.save_run(c, iid, res, run_at)
        c.execute("UPDATE shop_items SET price_search_status='done', price_search_note=?, price_search_at=? WHERE id=?",
                  (res["note"] + " · %d s" % res["secs"], run_at, iid))
        c.commit()
    finally:
        c.close()
    txt = C.summary(res)
    C._log("koniec #%d: %s | %s" % (iid, txt, res["note"]))
    _notify(iid, item["name"], txt, run_at)
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1])))
