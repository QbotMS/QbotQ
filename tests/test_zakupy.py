"""Testy Garaz > Zakupy (qbot_zakupy_api) na tymczasowej kopii schematu (bez dotykania garage.db)."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, "/opt/qbot/app")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import qbot_zakupy_api as Z


class ZakupyTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE bikes (id INTEGER PRIMARY KEY, name TEXT, nickname TEXT, active INTEGER)")
        c.execute("INSERT INTO bikes VALUES (1,'Canyon Grizl','Grizl',1)")
        c.commit(); c.close()
        self._old = Z.GARAGE_DB
        Z.GARAGE_DB = self.db
        self.owner = True
        app = FastAPI()
        app.include_router(Z.build_router(lambda r: "u", lambda r: self.owner))
        self.cl = TestClient(app)

    def tearDown(self):
        Z.GARAGE_DB = self._old
        os.remove(self.db)

    def add(self, **kw):
        b = {"name": "Łańcuch", "category": "Rower / części", "priority": 1,
             "url": "https://www.bike-discount.de/x", "price": "129,90"}
        b.update(kw)
        r = self.cl.post("/api/zakupy/save", json=b)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

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

    def test_bought_and_back(self):
        i = self.add()
        r = self.cl.post("/api/zakupy/bought", json={"id": i, "paid_price": "119", "bought_at": "2026-10-13"})
        it = r.json()["item"]
        self.assertEqual((it["status"], it["paid_price"], it["bought_at"]), ("bought", 119.0, "2026-10-13"))
        r = self.cl.post("/api/zakupy/bought", json={"id": self.add(name="X")})
        self.assertEqual(r.json()["item"]["paid_price"], 129.9)   # brak ceny zaplaconej = cena z listy
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
        r = self.cl.post("/api/zakupy/save", json={"name": "x", "category": "Inne"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.cl.get("/api/zakupy/list").status_code, 200)


if __name__ == "__main__":
    unittest.main()
