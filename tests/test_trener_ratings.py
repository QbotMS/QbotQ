"""Oceny planu w Trenerze: walidacja i wplyw ocen na zestaw silowy (bez bazy)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_trener_ratings as R  # noqa: E402
import qbot_trener_workouts as W  # noqa: E402


class TestClean(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(R.clean_rating({"session_id": "5", "rating": 4, "note": "  fajny układ "}),
                         {"session_id": 5, "rating": 4, "note": "fajny układ"})

    def test_delete_and_empty_note(self):
        self.assertEqual(R.clean_rating({"session_id": 1, "rating": 0, "note": ""})["note"], None)

    def test_bad(self):
        for b in ({"rating": 3}, {"session_id": 1, "rating": 6}, {"session_id": 1, "rating": "x"}, []):
            with self.assertRaises(R.BadRating):
                R.clean_rating(b)


class TestPrefs(unittest.TestCase):
    def test_no_prefs_same_as_before(self):
        a = W.details("sila", "bz", 40, False, 0)
        b = W.details("sila", "bz", 40, False, 0, prefs={})
        self.assertEqual([e["name"] for e in a["exercises"]], [e["name"] for e in b["exercises"]])
        self.assertNotIn("zamiana", a["text"])

    def test_bad_exercise_swapped_to_best_in_group(self):
        base = W.details("sila", "bz", 40, False, 0)["exercises"][0]["name"]  # nogi, wariant 0
        prefs = {base: 1.5, "Przysiad bułgarski (noga na ławce)": 4.5}
        d = W.details("sila", "bz", 40, False, 0, prefs=prefs)
        self.assertEqual(d["exercises"][0]["name"], "Przysiad bułgarski (noga na ławce)")
        self.assertTrue(d["exercises"][0]["swapped"])
        self.assertIn("zamiana wg Twoich ocen", d["text"])

    def test_good_or_neutral_kept(self):
        base = W.details("sila", "bz", 40, False, 0)["exercises"][0]["name"]
        d = W.details("sila", "bz", 40, False, 0, prefs={base: 3.0})
        self.assertEqual(d["exercises"][0]["name"], base)

    def test_all_bad_keeps_rotation(self):
        opts = dict(W.BASE)["brzuch"]
        d0 = W.details("sila", "bz", 40, False, 0)
        d = W.details("sila", "bz", 40, False, 0, prefs={o: 1 for o in opts})
        self.assertEqual(d["exercises"][4]["name"], d0["exercises"][4]["name"])

    def test_extra_pair_swapped(self):
        d0 = W.details("sila", "bz", 40, False, 0)  # akcent klatka + ramiona, para 0
        bad = d0["exercises"][-1]["name"]
        d = W.details("sila", "bz", 40, False, 0, prefs={bad: 1})
        self.assertEqual([e["name"] for e in d["exercises"][-2:]], W.EXTRA["klatka + ramiona"][1])

    def test_text_recent(self):
        t = R.text_recent([{"data": "2026-09-20", "sport": "siła", "ocena": 2, "komentarz": "za dużo nóg"}])
        self.assertIn("2/5 — za dużo nóg", t)


if __name__ == "__main__":
    unittest.main()
