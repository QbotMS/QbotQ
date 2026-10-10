"""Faworyci ubioru (qbot3/routes/outfit_fav.py) - czesci bez AI. Dok.: docs/OUTFIT_FAVORITES.md"""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from qbot3.routes import outfit_advisor as OA  # noqa: E402
from qbot3.routes import outfit_fav as F  # noqa: E402

WAR = {"na_trasie": {"min": 8, "max": 14}, "prognoza_powietrza": {"min": 9, "max": 15}, "na_rowerze": {"min": 8, "max": 14, "srednia": 11},
       "czas_h": 4.0, "deszcz": {"max_proc": 5, "suma_mm": 0}}


class T(unittest.TestCase):
    def test_gear_list_has_layers(self):
        g = F.gear_list()
        self.assertTrue(g)
        self.assertTrue(all(x["warstwa"] for x in g))
        self.assertTrue(all(x["kategoria"] for x in g))

    def test_with_favs_forces_item(self):
        kand = OA.kandydaci(WAR, set())
        allg = [x for x in F.gear_list() if not x.get("nie_do_jazdy")]
        have = {it["id"] for v in kand.values() for it in v}
        out = [x for x in allg if x["id"] not in have]
        self.assertTrue(out, "brak rzeczy spoza kandydatow do testu")
        fid = out[0]["id"]
        k2 = F._with_favs(kand, [fid])
        by = {it["id"]: it for v in k2.values() for it in v}
        self.assertIn(fid, by)
        self.assertTrue(by[fid]["faworyt"])
        self.assertNotIn(fid, {it["id"] for v in kand.values() for it in v}, "oryginalni kandydaci nie moga sie zmienic")

    def test_valid_one_and_missing(self):
        kand = OA.kandydaci(WAR, set())
        pick = [v[0] for k, v in kand.items() if k in ("koszulka", "spodenki", "buty", "skarpety", "rekawiczki", "glowa")]
        z = {"tempo": "spokojniejsza", "po_co": "x", "rzeczy": [{"id": c["id"], "dlaczego": "ok"} for c in pick], "do_kieszeni": []}
        self.assertIsNone(F._valid_one(z, kand, WAR))
        self.assertIn("tempo", F._valid_one(z, kand, WAR, tempo="szybsza"))
        self.assertEqual(F._missing_favs(z, [pick[0]["id"], 999999]), [999999])

    def test_retag_and_prompt(self):
        self.assertEqual(F._retag(["zestaw A: x", "poprawione automatycznie: A: y"], "B"),
                         ["zestaw B: x", "poprawione automatycznie: B: y"])
        kand = OA.kandydaci(WAR, set())
        p = F._prompt_ai(WAR, kand, [], [], "szybsza")
        self.assertIn("'szybsza'", p)
        self.assertNotIn("DOKLADNIE 2 zestawy", p)


if __name__ == "__main__":
    unittest.main()
