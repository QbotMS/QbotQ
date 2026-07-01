"""Testy UTCI — wielomian Broede (punkty odniesienia), cisnienie pary (fizyka),
kategorie, granice waznosci. Wartosci odniesienia policzone z zwalidowanej wersji
(wielomian bit-w-bit z pythermalcomfort; cisnienie pary sprawdzone fizyka es(20C)=23.39)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot3.routes import route_utci as R


class TestUTCI(unittest.TestCase):
    REF = [((30, 60, 1.0, 50), 37.924), ((15, 40, 2.0, 50), 20.861),
           ((5, 5, 5.0, 80), -6.884), ((-10, -10, 8.0, 70), -35.679),
           ((25, 25, 0.5, 40), 24.231), ((0, -5, 12, 90), -30.32),
           ((35, 70, 0.5, 60), 46.386), ((-20, -30, 15, 40), -59.962),
           ((20, 20, 3.0, 50), 16.242), ((10, 30, 6, 30), 3.137),
           ((40, 45, 2, 20), 41.079), ((-5, -5, 10, 95), -32.872)]

    def test_reference_points(self):
        for (tdb, tr, v, rh), exp in self.REF:
            self.assertAlmostEqual(R.utci_c(tdb, tr, v, rh), exp, delta=0.01,
                                   msg=f"UTCI({tdb},{tr},{v},{rh})")

    def test_saturation_physics(self):
        # znane cisnienia pary nasyconej [hPa]
        self.assertAlmostEqual(R.sat_vapour_hpa(0), 6.11, delta=0.02)
        self.assertAlmostEqual(R.sat_vapour_hpa(20), 23.39, delta=0.02)
        self.assertAlmostEqual(R.sat_vapour_hpa(30), 42.47, delta=0.03)

    def test_categories(self):
        self.assertEqual(R.utci_category(50), "ekstremalny stres ciepla")
        self.assertEqual(R.utci_category(40), "bardzo silny stres ciepla")
        self.assertEqual(R.utci_category(20), "brak stresu termicznego")
        self.assertEqual(R.utci_category(-15), "silny stres zimna")
        self.assertEqual(R.utci_category(-50), "ekstremalny stres zimna")

    def test_validity_bounds(self):
        self.assertTrue(R.utci_valid(20, 20, 17.0))
        self.assertFalse(R.utci_valid(20, 20, 17.5))   # wiatr poza zakresem
        self.assertFalse(R.utci_valid(20, 20, 0.4))
        self.assertFalse(R.utci_valid(20, 95, 5))      # tr-tdb > 70


if __name__ == "__main__":
    unittest.main()
