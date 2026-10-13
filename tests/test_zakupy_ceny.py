"""Testy etapu 3 Zakupow: dopasowanie produktu, ceny, wybor ofert, zapis/odczyt, API (bez sieci)."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "/opt/qbot/app")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import qbot_zakupy_api as Z
import qbot_zakupy_ceny as C


class CzysteTest(unittest.TestCase):
    def test_match(self):
        n = "Łańcuch Shimano XT CN-M8100 12 rz. 126 ogniw"
        self.assertGreaterEqual(C.match_score(n, "Shimano", "Shimano Xt Cn-M8100 Srebrny 12 Ogniw 126"), 0.6)
        self.assertEqual(C.match_score(n, "Shimano", "Shimano Xt Cn M8100 Łańcuch 12 Rz. Srebrny 116 Lin"), 0.0)  # 116 != 126
        self.assertLess(C.match_score("Magnez 90 kaps.", "Olimp", "Olimp Witamina C 90 kaps."), 0.6)
        self.assertGreaterEqual(C.match_score(n, "Shimano", "Łańcuch Rowerowy Shimano 12Rz CN-M8100 126 Ogniw"), 0.6)
        ok, why = C.same_product({"name": "x", "ean": "5901234567890"}, {"name": "y", "ean": "590-1234567890"})
        self.assertTrue(ok)
        ok, why = C.same_product({"name": "x", "ean": "5901234567890"}, {"name": "x", "ean": "4000000000000"})
        self.assertFalse(ok)

    def test_zgloszenie_1310(self):
        # Ceneo pokazalo miernik BBB i Park Tool przy Bitul CH012 -> kod modelu obowiazkowy
        b = "Przymiar trzypunktowy zużycia łańcucha Bitul CH012"
        self.assertGreaterEqual(C.match_score(b, "Bitul", "MIERNIK TRZYPUNKTOWY ZUŻYCIA ŁAŃCUCHA CH012"), 0.6)
        self.assertEqual(C.match_score(b, "Bitul", "Bbb Miernik Zużycia Łańcucha Btl-125 Silver"), 0.0)
        self.assertEqual(C.match_score(b, "Bitul", "PARK TOOL Przyrząd do sprawdzania zużycia łańcucha"), 0.0)
        # wariant z notatki (160mm) obowiazkowy: 165 mm odpada, '160 mm' i '160mm' przechodza
        k, req = "Ramiona korby SRAM Force XPLR E1 DUB Wide", C.variant_tokens("160mm")
        self.assertEqual(C.match_score(k, "Sram", "SRAM Ramiona korby SRAM FORCE XPLR DUB WIDE E1 165 mm", req), 0.0)
        self.assertGreaterEqual(C.match_score(k, "Sram", "Ramiona korby SRAM Force XPLR E1 DUB Wide 160 mm", req), 0.6)
        self.assertGreaterEqual(C.match_score(k, "Sram", "Sram Ramię Korby Quarq Force Xplr E1 160mm Dub Wid", req), 0.6)
        ok, _ = C.same_product({"name": k, "brand": "Sram", "notes": "160mm"},
                               {"name": "SRAM Ramiona korby SRAM FORCE XPLR DUB WIDE E1 165 mm"})
        self.assertFalse(ok)

    def test_parse_price(self):
        for v, want in [("1 299,99 zł", 1299.99), ("129.90", 129.9), ("1.299,00", 1299.0), ("1,299.00", 1299.0),
                        (95, 95.0), ("2.289", 2289.0), ("od 45 zł", 45.0), ("", None), ("0", None)]:
            self.assertEqual(C.parse_price(v), want, v)

    def test_ai_text(self):
        t = 'Oto:\n```json\n[{"shop":"A","url":"https://a.pl/p","price":"122,99","currency":"zł"},{"shop":"B","url":"x"}]\n```'
        o = C.ai_offers_from_text(t)
        self.assertEqual(len(o), 1)
        self.assertEqual((o[0]["price"], o[0]["currency"]), (122.99, "PLN"))
        self.assertEqual(C.ai_offers_from_text("brak"), [])

    def test_pick(self):
        offers = [
            {"shop": "Sprint", "url": "https://sprint-rowery.pl/a", "price_pln": 123, "status": "ok", "source": "ai"},
            {"shop": "sprint-rowery.pl", "url": "https://www.ceneo.pl/1", "price_pln": 119, "status": "ok", "source": "ceneo"},
            {"shop": "Mroz", "url": "https://www.mrozbike.pl/b", "price_pln": 140, "status": "ok", "source": "ai"},
            {"shop": "Allegro", "url": "https://allegro.pl/c", "price_pln": 99, "status": "blocked", "source": "ai"},
            {"shop": "Mroz", "url": "https://mrozbike.pl/x", "price_pln": 99, "status": "blocked", "source": "ai"},
            {"shop": "Zly", "url": "https://zly.pl/c", "price_pln": None, "status": "drop", "source": "ai"},
        ]
        ok, bl = C.pick(offers)
        self.assertEqual([(o["shop"], o["price_pln"]) for o in ok], [("sprint-rowery.pl", 119), ("Mroz", 140)])
        self.assertEqual([o["shop"] for o in bl], ["Allegro"])   # mrozbike jest juz sprawdzony -> nie dubluj


class BazaApiTest(unittest.TestCase):
    def setUp(self):
        fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE bikes (id INTEGER PRIMARY KEY, name TEXT, nickname TEXT, active INTEGER)")
        c.commit(); c.close()
        self._old = (Z.GARAGE_DB, Z.load_supplements, subprocess.Popen)
        Z.GARAGE_DB = self.db
        Z.load_supplements = lambda: {}
        self.spawned = []
        subprocess.Popen = lambda *a, **k: self.spawned.append(a[0])
        app = FastAPI()
        app.include_router(Z.build_router(lambda r: "u", lambda r: True))
        self.cl = TestClient(app)
        self.iid = self.cl.post("/api/zakupy/save", json={"name": "Łańcuch XT", "category": "Rower / części"}).json()["id"]

    def tearDown(self):
        Z.GARAGE_DB, Z.load_supplements, subprocess.Popen = self._old
        os.remove(self.db)

    def test_search_start_and_guard(self):
        r = self.cl.post("/api/zakupy/price-search", json={"id": self.iid})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.spawned and self.spawned[0][-1] == str(self.iid))
        self.assertEqual(self.cl.post("/api/zakupy/price-search", json={"id": self.iid}).status_code, 409)
        it = self.cl.get("/api/zakupy/list").json()["items"][0]
        self.assertEqual(it["price_search_status"], "running")

    def test_save_run_latest_and_use(self):
        c = Z._conn()
        res = {"ok": [{"shop": "a.pl", "url": "https://a.pl/p", "price": 100, "currency": "PLN", "price_pln": 100,
                       "source": "ai", "status": "ok", "note": "x"}],
               "blocked": [{"shop": "allegro.pl", "url": "https://allegro.pl/p", "price": 90, "currency": "PLN",
                            "price_pln": 90, "source": "ai", "status": "blocked", "note": "y"}]}
        C.save_run(c, self.iid, res, "2026-10-13 10:00")
        res["ok"][0]["price_pln"] = 95
        C.save_run(c, self.iid, res, "2026-10-14 10:00")
        c.execute("UPDATE shop_items SET price_search_at='2026-10-14 10:00', price_search_status='done' WHERE id=?", (self.iid,))
        c.commit(); c.close()
        it = self.cl.get("/api/zakupy/list").json()["items"][0]
        o = it["offers"]
        self.assertEqual((o["run_at"], o["ok"][0]["price_pln"], o["blocked"][0]["shop"]), ("2026-10-14 10:00", 95, "allegro.pl"))
        self.assertEqual([h["min_pln"] for h in o["history"]], [100, 95])
        r = self.cl.post("/api/zakupy/use-offer", json={"id": self.iid, "url": "https://a.pl/p", "price": 95, "shop": "a.pl"})
        self.assertEqual(r.status_code, 200)
        it = self.cl.get("/api/zakupy/list").json()["items"][0]
        self.assertEqual((it["url"], it["price"], it["shop"]), ("https://a.pl/p", 95, "a.pl"))


if __name__ == "__main__":
    unittest.main()
