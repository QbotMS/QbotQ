"""Joga w Down Dog - czesci czyste (qbot_trener_joga)."""
import unittest

import qbot_trener_joga as J

ROOT = {
    "categoryFilters": [{"id": "-2", "label": "Ostatnie", "categoryIds": [108]},
                        {"id": "1", "label": "Joga", "categoryIds": [108, 111, 120]},
                        {"id": "2", "label": "Medytacja", "categoryIds": [50]}],
    "categoryOptions": [
        {"id": "108", "label": "Vinyasa", "helpText": "Płynne", "boostSetting": {"options": [{"label": "Biodra"}, {"label": "Tył uda"}, {"label": "Klatka piersiowa i barki"}]},
         "otherSettings": [{"label": "Czas trzymania pozycji", "options": [{"label": "Krótki"}, {"label": "Domyślne"}, {"label": "Długi"}]},
                           {"label": "Savasana", "options": [{"label": "Brak"}, {"label": "3 min"}]}, {"label": "Osoba na wideo", "options": [{"label": "Alexa"}]}]},
        {"id": "111", "label": "Yin", "helpText": "Głębokie", "boostSetting": {"options": [{"label": "Zginacze bioder"}, {"label": "Tył uda"}]},
         "otherSettings": [{"label": "Czas trzymania pozycji", "options": [{"label": "Domyślne"}, {"label": "Długi"}]}]},
        {"id": "120", "label": "Rozciąganie w staniu", "helpText": "Na stojąco", "boostSetting": {"options": [{"label": "Uda"}]}, "otherSettings": []},
        {"id": "50", "label": "Medytacja prowadzona", "boostSetting": {"options": []}},
    ]}


class TestExtract(unittest.TestCase):
    def test_tylko_joga_i_wybrane_ustawienia(self):
        d = J.extract(ROOT)
        self.assertEqual([t["label"] for t in d["types"]], ["Vinyasa", "Yin", "Rozciąganie w staniu"])
        self.assertEqual(set(d["types"][0]["settings"]), {"Czas trzymania pozycji", "Savasana"})   # bez 'Osoba na wideo'

    def test_diff(self):
        old = J.extract(ROOT)
        new = J.extract(ROOT)
        new["types"].append({"label": "Nowa joga", "boosts": [], "settings": {}, "id": "9", "help": ""})
        new["types"][1]["boosts"].append("Szyja")
        d = J.diff(old, new)
        self.assertIn("nowy typ: Nowa joga", d)
        self.assertTrue(any("Szyja" in x for x in d))
        self.assertEqual(J.diff({}, new), [])     # pierwszy import nie jest "nowoscia"


class TestVersions(unittest.TestCase):
    def test_kolejne(self):
        v = J.next_versions("8.2.2")
        self.assertEqual(v[0], "8.2.3")
        self.assertIn("8.3.0", v)
        self.assertIn("9.0.0", v)


class TestRecipe(unittest.TestCase):
    def setUp(self):
        self.types = J.extract(ROOT)["types"]

    def test_walidacja(self):
        r, _ = J.validate_recipe({"typ": "Yin", "boost1": "Zginacze bioder", "boost2": "Tył uda",
                                  "ustawienia": {"Czas trzymania pozycji": "Długi", "Savasana": "3 min"}}, self.types)
        self.assertEqual((r["typ"], r["boost1"], r["boost2"]), ("Yin", "Zginacze bioder", "Tył uda"))
        self.assertEqual(r["ustawienia"], {"Czas trzymania pozycji": "Długi"})          # Yin nie ma Savasany
        self.assertIsNone(J.validate_recipe({"typ": "Hot 26"}, self.types)[0])
        self.assertIsNone(J.validate_recipe({"typ": "Yin", "boost1": "Core"}, self.types)[0])
        r2, n2 = J.validate_recipe({"typ": "Yin", "boost1": "Tył uda", "boost2": "Tył uda"}, self.types)
        self.assertEqual(r2["boost2"], "")

    def test_regula_po_dlugiej_jezdzie(self):
        wk = [{"sport": "rower", "rel": -1, "min": 180, "dluga": True}]
        r = J.rule_recipe({}, wk, self.types)
        self.assertEqual((r["typ"], r["boost1"], r["boost2"]), ("Yin", "Zginacze bioder", "Tył uda"))
        r2 = J.rule_recipe({}, [], self.types)
        self.assertEqual(r2["typ"], "Vinyasa")


class TestRefresh(unittest.TestCase):
    def test_podbicie_wersji(self):
        class C:
            def __init__(self): self.q = []
            def execute(self, sql, args=None): self.q.append((sql, args))
            def fetchone(self): return None
        seen = []
        def getter(v):
            seen.append(v)
            return {"sequenceSettingsRoot": ROOT} if v == "8.2.4" else {"requiredUpdateAnnouncement": {}}
        st = J.refresh(C(), force=True, getter=getter)
        self.assertEqual(st["status"], "ok"); self.assertEqual(st["version"], "8.2.4")
        self.assertEqual(seen[:3], ["8.2.2", "8.2.3", "8.2.4"])


if __name__ == "__main__":
    unittest.main()
