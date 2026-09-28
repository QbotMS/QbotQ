"""Sezon (fitmodel/season.py): typy tygodni + struktura build() na zywej bazie (tylko odczyt)."""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import season as S  # noqa: E402


class WeekType(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(S.week_type(3, 3, 0, 8.6), "infekcja")
        self.assertEqual(S.week_type(16, 0, 4, 8.6), "wyjazd")
        self.assertEqual(S.week_type(12, 0, 1, 8.6), "mocny")
        self.assertEqual(S.week_type(4.9, 0, 0, 8.6), "lzejszy")
        self.assertEqual(S.week_type(8.0, 0, 1, 8.6), "budowa")
        self.assertEqual(S.week_type(1.0, 0, 0, 8.6, partial=True), "biezacy")


class BuildLive(unittest.TestCase):
    def test_structure(self):
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect()
        try:
            z = S.build(c)
        finally:
            c.close()
        self.assertIn("where", z); self.assertIn("weeks", z); self.assertIsInstance(z["status"], list)
        self.assertGreater(len(z["weeks"]), 4)
        types = {w["type"] for w in z["weeks"]}
        self.assertTrue(types <= {"budowa", "mocny", "lzejszy", "wyjazd", "infekcja", "biezacy"})
        self.assertEqual(sum(1 for w in z["weeks"] if w["partial"]), 1)
        v = z["view"]
        self.assertNotIn("error", v)
        self.assertTrue(v["headline"])
        self.assertGreater(len(v["form"]), 30)
        self.assertTrue(v["plan"])
        self.assertTrue(v["plan"][0]["current"])
        for a, b in zip(v["plan"], v["plan"][1:]):          # plan nie rosnie szybciej niz +15%/tydz. po okresie ochronnym
            if not a["rule"].startswith("po infekcji"):
                self.assertLessEqual(b["hours"], max(a["hours"], round(a["hours"] * 1.15 * 2) / 2.0) + 1e-9)
            self.assertLessEqual(b["long_h"], a["long_h"] + 1.0 + 1e-9)
        ids = [t["id"] for t in z["tiles"]]
        self.assertNotIn("err", ids)
        for t in z["tiles"]:
            self.assertIn(t["level"], ("good", "warn", "bad"))
            self.assertTrue(t["title"] and t["status"] and t["line"])
        self.assertIn("regen", ids)
        st = z["story"]
        self.assertNotIn("error", st)
        for k in ("przebieg", "gdzie", "plan", "obserwacje", "wnioski"):
            self.assertIsInstance(st[k], list)
        self.assertTrue(st["przebieg"] and st["gdzie"])
        # wniosek tylko przy powtorzeniu: kazdy wniosek 'Powtorzylo sie N razy' ma N >= 2
        for w in st["wnioski"]:
            if w.startswith("Powtórzyło się"):
                self.assertGreaterEqual(int(w.split()[2]), 2)


if __name__ == "__main__":
    unittest.main()
