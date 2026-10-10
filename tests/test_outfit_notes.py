"""Uwagi do AI (qbot3/routes/outfit_notes.py) - czesci bez AI. Dok.: docs/OUTFIT_FAVORITES.md"""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from qbot3.routes import outfit_fav as F  # noqa: E402
from qbot3.routes import outfit_notes as N  # noqa: E402


def _by():
    return {g["id"]: g for g in F.gear_list()}


def _pick(by, lay, n=2):
    return [g for g in by.values() if g["warstwa"] == lay and not g.get("nie_do_jazdy")][:n]


class T(unittest.TestCase):
    def test_swap_same_layer(self):
        by = _by()
        r1, r2 = _pick(by, "rekawiczki")
        k = _pick(by, "koszulka", 1)[0]
        p = {"zestawy": [{"rzeczy": [dict(r1, dlaczego="x"), dict(k, dlaczego="x")], "do_kieszeni": []},
                         {"rzeczy": [dict(r1, dlaczego="x")], "do_kieszeni": []}]}
        done = N._apply(p, [{"zestaw": "A", "usun_id": r1["id"], "dodaj_id": r2["id"], "gdzie": "na_sobie", "dlaczego": "Zgodnie z Twoja uwaga."}], by)
        ids = [i["id"] for i in p["zestawy"][0]["rzeczy"]]
        self.assertIn(r2["id"], ids)
        self.assertNotIn(r1["id"], ids)
        self.assertEqual([i["id"] for i in p["zestawy"][1]["rzeczy"]], [r1["id"]], "zestaw B bez zmian")
        self.assertTrue(done)
        self.assertTrue(next(i for i in p["zestawy"][0]["rzeczy"] if i["id"] == r2["id"])["z_uwagi"])

    def test_add_replaces_layer_and_ignores_unknown(self):
        by = _by()
        r1, r2 = _pick(by, "rekawiczki")
        p = {"zestawy": [{"rzeczy": [dict(r1, dlaczego="x")], "do_kieszeni": []}]}
        N._apply(p, [{"zestaw": "A", "dodaj_id": r2["id"], "gdzie": "na_sobie"}, {"zestaw": "A", "dodaj_id": 99999999}], by)
        self.assertEqual([i["id"] for i in p["zestawy"][0]["rzeczy"]], [r2["id"]])

    def test_prompt_contains_parts(self):
        by = _by()
        r1 = _pick(by, "rekawiczki", 1)[0]
        s = N._prompt({"zestawy": [{"rzeczy": [dict(r1)], "do_kieszeni": []}]}, by, "zielone rekawiczki", [{"id": 1, "wniosek": "w"}])
        self.assertIn("zielone rekawiczki", s)
        self.assertIn("wnioski_dotad", s)


if __name__ == "__main__":
    unittest.main()
