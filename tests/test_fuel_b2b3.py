import unittest

from qbot3 import qbot_fuel_tools as f


class TestCarbsB3(unittest.TestCase):
    def test_vector_endurance_3h(self):
        self.assertEqual(f.carbs_g_per_h(0.70, 10800, 1.05, None, 75.0), 65)

    def test_vector_tempo_2_5h(self):
        self.assertEqual(f.carbs_g_per_h(0.85, 9000, 1.10, 28, 80.0), 90)

    def test_min_clamp_20(self):
        self.assertEqual(f.carbs_g_per_h(0.40, 1800, 1.0, None, 60.0), 20)

    def test_max_clamp_110(self):
        self.assertEqual(f.carbs_g_per_h(1.10, 14400, 1.20, 40, 90.0), 110)


class TestFluidB2(unittest.TestCase):
    def test_vector_endurance(self):
        self.assertAlmostEqual(f.fluid_l_per_h(0.70, None, None, 75.0), 0.55, places=9)

    def test_vector_hot(self):
        self.assertAlmostEqual(f.fluid_l_per_h(0.85, 28, 70, 80.0), 1.00, places=9)

    def test_max_clamp_1_5(self):
        self.assertAlmostEqual(f.fluid_l_per_h(0.90, 40, 90, 90.0), 1.50, places=9)

    def test_min_clamp_0_3(self):
        self.assertAlmostEqual(f.fluid_l_per_h(0.50, 0, 30, 55.0), 0.30, places=9)


class TestRegistryWiring(unittest.TestCase):
    def test_tool_registered_and_runs(self):
        from qbot3 import tool_registry as r
        spec = r.lookup("route_fuel_plan")
        self.assertIsNotNone(spec)
        out = spec["callable"]({"if_target": 0.70, "vi": 1.05, "duration_h": 3.0, "body_kg": 75.0})
        self.assertEqual(out.get("status"), "OK")
        analysis = out.get("data", {}).get("analysis", "")
        self.assertIn("B2", analysis)
        self.assertIn("B3", analysis)
        self.assertEqual(out["data"]["data"]["carbs_g_per_h"], 65)
        self.assertAlmostEqual(out["data"]["data"]["fluid_l_per_h"], 0.55, places=9)


if __name__ == "__main__":
    unittest.main()
