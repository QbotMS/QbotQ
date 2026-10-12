"""Testy czytnika menu Brokula (probka z 12.10.2026, jesli jest w artifacts) i komunikatu."""
import os, sys, unittest
sys.path.insert(0, "/opt/qbot/app")
import qbot_brokul_meals as M

SAMPLE = "/opt/qbot/artifacts/brokul_menu_sample.html"

MINI = """<div class="meals" data-day="2026-10-12"><h2>Menu</h2>
<div class="rounded-lg"><h3> Śniadanie </h3><div><div><div><p> Kotlecik, Papryka </p></div>
<p><strong>Wartości odżywcze na porcję:</strong></p><ul>
<li><div><svg><use href="x.svg#macros-energy_value"></use></svg><span>Wartość energ.</span></div>
<div><strong>389 kcal</strong><strong>1 628 kJ</strong></div></li>
<li><div><svg><use href="x.svg#macros-fat"></use></svg><span>Tłuszcze</span></div><strong>17,8 g</strong></li>
<li><div><svg><use href="x.svg#macros-saturated_acids"></use></svg><span>W tym kwasy tł. nasycone</span></div><strong>6,1 g</strong></li>
<li><div><svg><use href="x.svg#macros-carbohydrates"></use></svg><span>Węglowodany</span></div><strong>32,9 g</strong></li>
<li><div><svg><use href="x.svg#macros-sugar"></use></svg><span>W tym cukry</span></div><strong>9,2 g</strong></li>
<li><div><svg><use href="x.svg#macros-protein"></use></svg><span>Białko</span></div><strong>23,1 g</strong></li>
<li><div><span>Sól</span></div><strong>2,1 g</strong></li></ul>
<p>Składniki:</p><p>brokuł, <strong>jaja</strong> , ser (z <strong>mleka</strong> )</p>
<p>Z uwagi na wykorzystywane w zakładzie surowce, możliwa jest obecność alergenów: soi.</p>
<span>~389kcal</span></div></div></div></div>"""


class TestParser(unittest.TestCase):
    def test_mini(self):
        m = M.parse_menu(MINI, "1")
        self.assertEqual(len(m), 1)
        m = m[0]
        self.assertEqual((m["day"], m["meal_type"], m["name"]), ("2026-10-12", "Śniadanie", "Kotlecik, Papryka"))
        self.assertEqual((m["kcal"], m["kj"], m["fat_g"], m["sat_fat_g"], m["carbs_g"], m["sugars_g"],
                          m["protein_g"], m["salt_g"]), (389, 1628, 17.8, 6.1, 32.9, 9.2, 23.1, 2.1))
        self.assertEqual(m["ingredients"], "brokuł, jaja, ser (z mleka)")
        self.assertTrue(m["allergen_notice"].startswith("Z uwagi na") and m["allergen_notice"].endswith("soi."))
        self.assertTrue(M.meal_ok(m))

    @unittest.skipUnless(os.path.exists(SAMPLE), "brak probki")
    def test_sample(self):
        meals = M.parse_menu(open(SAMPLE, encoding="utf-8").read(), "19957457")
        self.assertEqual(len(meals), 25)
        self.assertTrue(all(M.meal_ok(x) for x in meals))
        self.assertTrue(all(x["salt_g"] is not None and x["sugars_g"] is not None for x in meals))
        f = meals[0]
        self.assertEqual((f["kcal"], f["protein_g"], f["salt_g"]), (389, 23.1, 2.1))
        self.assertIn("mozzarell", f["ingredients"])

    def test_slug(self):
        self.assertEqual(M._slug("II Śniadanie"), "brokul_ii_sniadanie")


if __name__ == "__main__":
    unittest.main()
