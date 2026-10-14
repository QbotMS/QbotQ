"""Przelom CP z krzywej moc-czas (fitmodel/cp_breakthrough.py) -- czyste funkcje."""
import sys, unittest
sys.path.insert(0, "/opt/qbot/app")
from fitmodel import cp_breakthrough as B


class T(unittest.TestCase):
    def test_no_breakthrough_below_curve(self):
        # TP 240, W' 18 kJ: 2 min = 390 W, 20 min = 255 W
        self.assertIsNone(B.propose(240, 18.0, {120: 370, 300: 290, 600: 265, 1200: 250}))

    def test_margin(self):
        self.assertIsNone(B.propose(240, 18.0, {1200: 255 * 1.005}))   # +0.5 % < 1 % -> szum

    def test_long_effort_raises_tp(self):
        p = B.propose(240, 18.0, {1200: 262})
        self.assertAlmostEqual(p["tp_new"], 247.0, places=1)           # 262 - 18000/1200
        self.assertEqual(p["hie_new_kj"], 18.0)

    def test_short_effort_raises_wprime(self):
        p = B.propose(240, 18.0, {120: 400})
        self.assertAlmostEqual(p["hie_new_kj"], 19.2, places=2)         # (400-240)*120/1000
        self.assertEqual(p["tp_new"], 240.0)

    def test_caps(self):
        p = B.propose(240, 18.0, {1200: 300})
        self.assertEqual(p["tp_new"], round(240 * 1.03, 1))
        self.assertTrue(p["limit"])


if __name__ == "__main__":
    unittest.main()
