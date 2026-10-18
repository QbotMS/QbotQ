"""Testy czystych funkcji jedzenia (qbot_food_log) i harmonogramu dostaw Brokula."""
import sys, unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, "/opt/qbot/app")
import qbot_food_log as F
import qbot_brokul_meals as M

TZ = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 12, 15, 0, tzinfo=TZ)  # poniedzialek


class TestDay(unittest.TestCase):
    def test_default_today(self):
        self.assertEqual(F.parse_day("2 pączki", NOW), date(2026, 10, 12))

    def test_night(self):
        self.assertEqual(F.parse_day("kebab", datetime(2026, 10, 13, 1, 30, tzinfo=TZ)), date(2026, 10, 12))

    def test_words(self):
        self.assertEqual(F.parse_day("wczoraj pizza", NOW), date(2026, 10, 11))
        self.assertEqual(F.parse_day("przedwczoraj lody", NOW), date(2026, 10, 10))
        self.assertEqual(F.parse_day("w sobotę 2 piwa", NOW), date(2026, 10, 10))
        self.assertEqual(F.parse_day("niedziela obiad u mamy", NOW), date(2026, 10, 11))
        self.assertEqual(F.parse_day("w piątek kebab", NOW), date(2026, 10, 9))

    def test_dates(self):
        self.assertEqual(F.parse_day("10.10 lody", NOW), date(2026, 10, 10))
        self.assertEqual(F.parse_day("cola 0.5 l", NOW), date(2026, 10, 12))
        self.assertEqual(F.parse_day("schab 1.5 porcji", NOW), date(2026, 10, 12))
        self.assertEqual(F.parse_day("20.12 pierniki", NOW), date(2025, 12, 20))  # przyszlosc -> rok wczesniej


class TestPhrase(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(F.norm_phrase("Wczoraj PIZZA z łososiem!"), "pizza z lososiem")
        self.assertEqual(F.norm_phrase("w sobotę 2 piwa"), "2 piwa")
        self.assertEqual(F.norm_phrase("pizza"), F.norm_phrase("wczoraj pizza"))


class TestItems(unittest.TestCase):
    def test_clean(self):
        ok = F.clean_items([{"name": "Pączek", "portion": "1 szt.", "kcal": "290", "protein_g": 5, "carbs_g": 40, "fat_g": 12}])
        self.assertEqual(ok[0]["kcal"], 290.0)
        self.assertIsNone(F.clean_items([{"name": "X", "kcal": 100}]))  # brak makr -> odrzucone
        self.assertIsNone(F.clean_items([]))

    def test_receipt(self):
        e = {"id": 7, "day": date(2026, 10, 11), "scale": 0.75,
             "items": [{"name": "Pizza", "portion": "cała ~30 cm", "kcal": 900, "protein_g": 38, "carbs_g": 105, "fat_g": 35}]}
        t = F.receipt_text(e)
        self.assertIn("#7 · nd 11.10 · 675 kcal", t)
        self.assertIn("<pre> 675  Pizza cała ~30 cm</pre>", t)
        self.assertIn("675 kcal", t)
        self.assertIn("×0.75", t)


class TestDelivery(unittest.TestCase):
    def test_days(self):
        html = "<main><ul><li>05.10.2026</li><li>06.10.2026</li><li>12.10.2026</li></ul><p>31.02.2026</p></main>"
        self.assertEqual(M.parse_delivery_days(html), ["2026-10-05", "2026-10-06", "2026-10-12"])



class TestStreaks(unittest.TestCase):
    def _d(self, i):
        return date(2026, 10, 1) + __import__("datetime").timedelta(days=i)

    def test_run_basic(self):
        import qbot_food_streaks as S
        r = S._run([(self._d(i), "ok") for i in range(5)])
        self.assertEqual((r["n"], r["freezes"]), (5, 0))

    def test_neutral_keeps(self):
        import qbot_food_streaks as S
        r = S._run([(self._d(0), "ok"), (self._d(1), "neutral"), (self._d(2), "ok")])
        self.assertEqual(r["n"], 2)

    def test_fail_resets_without_freeze(self):
        import qbot_food_streaks as S
        r = S._run([(self._d(0), "ok"), (self._d(1), "fail"), (self._d(2), "ok")])
        self.assertEqual((r["n"], r["since"]), (1, self._d(2)))

    def test_freeze_saves(self):
        import qbot_food_streaks as S
        seq = [(self._d(i), "ok") for i in range(7)] + [(self._d(7), "fail"), (self._d(8), "ok")]
        r = S._run(seq)
        self.assertEqual((r["n"], r["freezes"], r["used"]), (8, 0, 1))

    def test_freeze_max(self):
        import qbot_food_streaks as S
        r = S._run([(self._d(i), "ok") for i in range(30)])
        self.assertEqual(r["freezes"], 2)


class TestTime(unittest.TestCase):
    def test_hhmm(self):
        self.assertEqual(F._hhmm("21:30"), "21:30")
        self.assertEqual(F._hhmm("9.05"), "09:05")
        self.assertIsNone(F._hhmm(None))
        self.assertIsNone(F._hhmm("25:00"))

    def test_outside(self):
        import qbot_food_streaks as S
        from datetime import time as t
        self.assertTrue(S._outside(t(9, 59)))
        self.assertFalse(S._outside(t(10, 0)))
        self.assertFalse(S._outside(t(19, 59)))
        self.assertTrue(S._outside(t(20, 0)))
        self.assertFalse(S._outside(None))


class TestAlbum(unittest.TestCase):   # 2026-10-18: album zdjec = jeden wpis
    def test_photo_ids(self):
        import qbot_food_log as F
        self.assertEqual(F.photo_ids({"photo_file_ids": ["a", "b"], "photo_file_id": "a"}), ["a", "b"])
        self.assertEqual(F.photo_ids({"photo_file_ids": None, "photo_file_id": "x"}), ["x"])
        self.assertEqual(F.photo_ids({"photo_file_ids": None, "photo_file_id": None}), [])

    def test_baked(self):
        import qbot_food_log as F
        it = [{"name": "a", "kcal": 100, "protein_g": 10, "carbs_g": 20, "fat_g": 4}]
        b = F._baked({"scale": 1.25, "items": it})
        self.assertEqual((b[0]["kcal"], b[0]["fat_g"]), (125.0, 5.0))

if __name__ == "__main__":
    unittest.main()
