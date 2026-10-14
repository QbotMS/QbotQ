"""[GARMIN-DANE] Etap 2: VO2max QBota z krzywej ModelQ."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.vo2max import add_vo2max, p5_from_modelq, vo2max_ml_kg  # noqa: E402


class TestVo2max(unittest.TestCase):
    def test_known_day(self):
        # 2026-10-14: CP 238.8, W' 18.16 kJ, 103.65 kg -> P5 299.3 W -> 38.2
        self.assertAlmostEqual(p5_from_modelq(238.8, 18.16), 299.33, places=1)
        self.assertEqual(vo2max_ml_kg(238.8, 18.16, 103.65), 38.2)

    def test_calibration_day(self):
        # 2025-02-13: CP 230.2, W' 16.48, 91.57 kg -> 40.6 (Garmin pokazywal 46)
        self.assertEqual(vo2max_ml_kg(230.2, 16.48, 91.57), 40.6)

    def test_missing_or_absurd(self):
        for args in ((None, 18, 100), (240, None, 100), (240, 18, None),
                     (20, 18, 100), (240, 500, 100), (240, 18, 10)):
            self.assertIsNone(vo2max_ml_kg(*args), args)

    def test_series_forward_fill(self):
        rows = [
            {"day": "a", "cp_modelq_w": 240, "wprime_modelq_kj": 18, "weight_kg": 100},
            {"day": "b", "cp_modelq_w": None, "wprime_modelq_kj": None, "weight_kg": None},
            {"day": "c", "cp_modelq_w": 250, "wprime_modelq_kj": None, "weight_kg": 102},
        ]
        add_vo2max(rows)
        self.assertEqual(rows[0]["vo2max_ml_kg"], rows[1]["vo2max_ml_kg"])
        self.assertEqual(rows[2]["vo2max_ml_kg"], vo2max_ml_kg(250, 18, 102))

    def test_series_starts_empty(self):
        rows = [{"day": "a"}, {"day": "b", "cp_modelq_w": 240, "wprime_modelq_kj": 18, "weight_kg": 100}]
        add_vo2max(rows)
        self.assertIsNone(rows[0]["vo2max_ml_kg"])
        self.assertIsNotNone(rows[1]["vo2max_ml_kg"])


if __name__ == "__main__":
    unittest.main()
