import sys
import unittest
from collections import Counter

sys.path.insert(0, "/opt/qbot/app")

import qbot_trener_exercises as X
import qbot_trener_workouts as W


class Catalog(unittest.TestCase):
    def test_count_and_unique(self):
        keys = [r[0] for r in X.CATALOG]
        self.assertEqual(len(keys), 100)
        self.assertEqual(len(set(keys)), 100)

    def test_groups(self):
        c = Counter(r[2] for r in X.CATALOG)
        self.assertEqual(c, Counter({"nogi": 16, "tyl": 14, "plecy": 14, "klatka": 10, "barki": 10, "ramiona": 8, "core": 18, "rozgrzewka": 10}))

    def test_fields_valid(self):
        for (k, name, grp, lvl, wc, eq, uni, dose, mus, warm, desc) in X.CATALOG:
            self.assertTrue(k.replace("_", "").isalnum(), k)
            self.assertIn(grp, X.GROUPS); self.assertIn(lvl, (1, 2, 3)); self.assertIn(wc, X.WCLS)
            for e in eq.split():
                self.assertIn(e, X.EQUIP, k)
            self.assertTrue(name and dose and mus and desc, k)
            if wc != "0":
                self.assertTrue("h1" in eq or "h2" in eq, k + ": klasa ciezaru bez hantli")
            if "h1" in eq or "h2" in eq:
                self.assertNotEqual(wc, "0", k + ": hantle bez klasy ciezaru")

    def test_batch1_has_texts(self):
        self.assertEqual(len(X.BATCH1), 12)
        for k in X.BATCH1:
            self.assertIn(k, [r[0] for r in X.CATALOG])
            steps, ok, bad = X.TEXTS[k]
            self.assertEqual(len(steps), 3); self.assertTrue(ok and bad)

    def test_batches(self):
        self.assertEqual(X.batches(), 9)
        sizes = Counter(r["batch"] for r in X.rows())
        self.assertEqual(sizes[1], 12)
        self.assertEqual(sum(sizes[b] for b in range(2, 10)), 88)
        self.assertTrue(all(sizes[b] <= X.BATCH_SIZE for b in range(2, 10)))

    def test_prompt(self):
        p = X.prompt(2)
        self.assertIn("ZERO TEKSTU", p); self.assertIn("ilustracje_paczka_2.zip", p)
        self.assertEqual(p.count("\n1. "), 1)
        self.assertEqual(X.prompt(99), "")

    def test_proposal(self):
        keys = {r[0]: r for r in X.CATALOG}
        self.assertEqual(len(X.PROPOSAL), 27)
        for k, p in X.PROPOSAL.items():
            self.assertIn(k, keys); self.assertIn(p, (1, 2, 3))
        # kazda partia ma co najmniej jedno podstawowe, a silowe partie dokladnie jedno ★★★
        from collections import Counter
        grp = Counter(keys[k][2] for k in X.PROPOSAL)
        for g in X.GROUPS:
            self.assertGreaterEqual(grp[g], 1, g)
        top = Counter(keys[k][2] for k, p in X.PROPOSAL.items() if p == 3)
        for g in ("nogi", "tyl", "plecy", "klatka", "barki", "core"):
            self.assertEqual(top[g], 1, g)
        self.assertEqual(X.PROPOSAL["bench_press_db"], 3)

    def test_current_pool_covered(self):
        """Cwiczenia z obecnej rotacji Trenera (nazwy) maja odpowiednik w bazie - przynajmniej 15 z nich po nazwie."""
        names = {r[1].lower() for r in X.CATALOG}
        pool = [o for _, opts in W.BASE for o in opts] + [e for v in W.EXTRA.values() for pair in v for e in pair]
        hits = sum(1 for p in pool if any(n.split(" (")[0] in p.lower() or p.lower().split(" (")[0] in n for n in names))
        self.assertGreaterEqual(hits, 15)


if __name__ == "__main__":
    unittest.main()
