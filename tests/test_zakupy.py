"""Testy Garaz > Zakupy (qbot_zakupy_api) na tymczasowej bazie (bez dotykania garage.db)."""
import datetime as dt
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, "/opt/qbot/app")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import qbot_zakupy_api as Z

D = dt.date


class ZakupyTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE bikes (id INTEGER PRIMARY KEY, name TEXT, nickname TEXT, active INTEGER)")
        c.execute("INSERT INTO bikes VALUES (1,'Canyon Grizl','Grizl',1)")
        c.commit(); c.close()
        self._old = (Z.GARAGE_DB, Z.load_supplements)
        Z.GARAGE_DB = self.db
        self.supl = {7: {"id": 7, "name": "Magnez", "days": None, "active": True, "skipped": set()}}
        Z.load_supplements = lambda: self.supl
        self.owner = True
        app = FastAPI()
        app.include_router(Z.build_router(lambda r: "u", lambda r: self.owner))
        self.cl = TestClient(app)

    def tearDown(self):
        Z.GARAGE_DB, Z.load_supplements = self._old
        os.remove(self.db)

    def add(self, **kw):
        b = {"name": "Łańcuch", "category": "Rower / części", "priority": 1,
             "url": "https://www.bike-discount.de/x", "price": "129,90"}
        b.update(kw)
        r = self.cl.post("/api/zakupy/save", json=b)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    # ---------- etap 1 ----------
    def test_add_list_priority_order(self):
        self.add(name="B", priority=3)
        self.add(name="A", priority=1)
        d = self.cl.get("/api/zakupy/list").json()
        self.assertEqual([x["name"] for x in d["items"]], ["A", "B"])
        a = d["items"][0]
        self.assertEqual(a["shop"], "bike-discount.de")
        self.assertEqual(a["price"], 129.9)
        self.assertEqual(a["currency"], "PLN")
        self.assertEqual(a["garage_target"], "bike")
        self.assertEqual(d["bikes"][0]["nickname"], "Grizl")
        self.assertEqual(d["supplements"][0]["name"], "Magnez")

    def test_bought_and_back(self):
        i = self.add()
        r = self.cl.post("/api/zakupy/bought", json={"id": i, "paid_price": "119", "bought_at": "2026-10-13"})
        it = r.json()["item"]
        self.assertEqual((it["status"], it["paid_price"], it["bought_at"]), ("bought", 119.0, "2026-10-13"))
        r = self.cl.post("/api/zakupy/bought", json={"id": self.add(name="X")})
        self.assertEqual(r.json()["item"]["paid_price"], 129.9)
        self.cl.post("/api/zakupy/unbought", json={"id": i})
        st = {x["id"]: x["status"] for x in self.cl.get("/api/zakupy/list").json()["items"]}
        self.assertEqual(st[i], "planned")

    def test_validation_and_delete(self):
        self.assertEqual(self.cl.post("/api/zakupy/save", json={"name": "", "category": "Inne"}).status_code, 400)
        self.assertEqual(self.cl.post("/api/zakupy/save", json={"name": "x", "category": "zla"}).status_code, 400)
        self.assertEqual(self.cl.post("/api/zakupy/save",
                                      json={"name": "x", "category": "Inne", "url": "ftp://a"}).status_code, 400)
        i = self.add()
        self.cl.post("/api/zakupy/delete", json={"id": i})
        self.assertEqual(self.cl.get("/api/zakupy/list").json()["items"], [])

    def test_demo_read_only(self):
        self.owner = False
        self.assertEqual(self.cl.post("/api/zakupy/save", json={"name": "x", "category": "Inne"}).status_code, 403)
        self.assertEqual(self.cl.post("/api/zakupy/rebuy", json={"id": 1}).status_code, 403)
        self.assertEqual(self.cl.get("/api/zakupy/list").status_code, 200)

    # ---------- etap 2: zapas ----------
    def test_forecast_manual(self):
        it = {"status": "bought", "pack_units": 90, "qty": 1, "per_day": 2, "bought_at": "2026-10-01", "pack_unit": "kaps."}
        f = Z.forecast(it, D(2026, 10, 11))
        self.assertEqual((f["used"], f["remaining"], f["days_left"], f["end"]), (20, 70, 35, "2026-11-15"))
        self.assertIsNone(Z.forecast(dict(it, status="planned"), D(2026, 10, 11)))
        self.assertIsNone(Z.forecast(dict(it, per_day=None), D(2026, 10, 11)))
        it2 = dict(it, qty=2)                       # 2 opakowania
        self.assertEqual(Z.forecast(it2, D(2026, 10, 11))["remaining"], 160)

    def test_forecast_supplement_schedule_and_skips(self):
        # pn/sr/pt, 1 kaps.; od pn 05.10 do wczoraj (nd 11.10): pn sr pt = 3, minus pominiete sr 07.10 = 2
        supl = {7: {"days": [0, 2, 4], "active": True, "skipped": {D(2026, 10, 7)}}}
        it = {"status": "bought", "pack_units": 30, "qty": 1, "supplement_id": 7, "per_intake": 1,
              "opened_at": "2026-10-05", "bought_at": "2026-10-03"}
        f = Z.forecast(it, D(2026, 10, 12), supl)
        self.assertEqual(f["used"], 2)
        self.assertEqual(f["remaining"], 28)
        self.assertEqual(f["days_left"], int(28 // (3 / 7)))   # 65
        supl[7]["active"] = False
        self.assertIsNone(Z.forecast(it, D(2026, 10, 12), supl)["days_left"])   # nieaktywny: brak prognozy konca

    def test_due_snooze_rebuy_flow(self):
        i = self.add(name="Zatyczki", category="Zdrowie / sprzęt", pack_units=10, pack_unit="par", per_day=1, lead_days=5)
        today = dt.date.today()
        self.cl.post("/api/zakupy/bought", json={"id": i, "bought_at": (today - dt.timedelta(days=7)).isoformat()})
        it = [x for x in self.cl.get("/api/zakupy/list").json()["items"] if x["id"] == i][0]
        self.assertEqual(it["forecast"]["days_left"], 3)
        self.assertTrue(it["due"])
        n = Z.notif_items()
        self.assertEqual(n[0]["key"], "live:zakupy:%d" % i)
        self.assertEqual(n[0]["action"]["post"], "/api/zakupy/rebuy")
        line, kb = Z.morning()
        self.assertIn("Zatyczki", line)
        self.assertEqual(kb[0][0]["callback_data"], "zk:r:%d" % i)
        # odlozenie -> nie przypomina
        self.cl.post("/api/zakupy/snooze", json={"id": i})
        self.assertEqual(Z.notif_items(), [])
        # kup ponownie (idempotentnie) -> kopia na liscie, oryginal juz nie przypomina
        Z.snooze(i, 1, today=today - dt.timedelta(days=5))
        self.assertEqual(len(Z.notif_items()), 1)
        r1 = self.cl.post("/api/zakupy/rebuy", json={"id": i}).json()
        r2 = self.cl.post("/api/zakupy/rebuy", json={"id": i}).json()
        self.assertTrue(r1["new"]); self.assertFalse(r2["new"]); self.assertEqual(r1["id"], r2["id"])
        new = [x for x in self.cl.get("/api/zakupy/list").json()["items"] if x["id"] == r1["id"]][0]
        self.assertEqual((new["status"], new["priority"], new["pack_units"], new["refill_of"]), ("planned", 1, 10, i))
        self.assertEqual(Z.notif_items(), [])
        # zakup kopii -> otwarcie = koniec poprzedniego opakowania (pozniej niz zakup)
        it2 = self.cl.post("/api/zakupy/bought", json={"id": r1["id"], "bought_at": today.isoformat()}).json()["item"]
        self.assertEqual(it2["opened_at"], (today + dt.timedelta(days=3)).isoformat())
        # usuniecie kopii -> oryginal znow przypomina
        self.cl.post("/api/zakupy/delete", json={"id": r1["id"]})
        self.assertEqual(len(Z.notif_items()), 1)

    def test_supplement_link_saved(self):
        i = self.add(name="Magnez 90", category="Zdrowie / suplementy", pack_units=90, supplement_id=7, per_intake="",
                     per_day=5)
        it = [x for x in self.cl.get("/api/zakupy/list").json()["items"] if x["id"] == i][0]
        self.assertEqual((it["supplement_id"], it["per_intake"], it["per_day"]), (7, 1.0, None))

    def test_callback(self):
        i = self.add(name="Zatyczki", category="Zdrowie / sprzęt", pack_units=10, per_day=1)
        ans = []
        cq = {"id": "q", "data": "zk:r:%d" % i, "message": {"chat": {"id": 5}, "message_id": 1}}
        Z.handle_callback(cq, lambda _id, t="": ans.append(t), lambda t: None, None, 5)
        self.assertIn("Dodane do listy", ans[-1])
        Z.handle_callback(dict(cq, data="zk:z:%d" % i), lambda _id, t="": ans.append(t), lambda t: None, None, 5)
        self.assertIn("Przypomnę od", ans[-1])
        Z.handle_callback(dict(cq, message={"chat": {"id": 9}}), lambda _id, t="": ans.append(t), lambda t: None, None, 5)
        self.assertEqual(ans[-1], "Brak dostepu")


if __name__ == "__main__":
    unittest.main()
