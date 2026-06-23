import datetime
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_route_time_tools as rtt


class TestRouteTimeEstimate(unittest.TestCase):
    def test_weighted_speed_vector(self):
        rides = [
            {"distance_km": 20.0, "duration_sec": 3600.0},
            {"distance_km": 40.0, "duration_sec": 14400.0},
        ]
        v, used = rtt._weighted_speed_kmh(rides)
        self.assertEqual(len(used), 2)
        self.assertAlmostEqual(v, 12.0, places=6)

    def test_not_simple_average(self):
        rides = [
            {"distance_km": 20.0, "duration_sec": 3600.0},
            {"distance_km": 40.0, "duration_sec": 14400.0},
        ]
        v, _ = rtt._weighted_speed_kmh(rides)
        self.assertNotAlmostEqual(v, 15.0, places=3)
        self.assertAlmostEqual(v, 12.0, places=6)

    def test_guard_zero_excluded(self):
        rides = [
            {"distance_km": 20.0, "duration_sec": 3600.0},
            {"distance_km": 0.0, "duration_sec": 3600.0},
            {"distance_km": 30.0, "duration_sec": 0.0},
        ]
        v, used = rtt._weighted_speed_kmh(rides)
        self.assertEqual(len(used), 1)
        self.assertAlmostEqual(v, 20.0, places=6)

    def test_guard_all_zero_none(self):
        rides = [
            {"distance_km": 0.0, "duration_sec": 0.0},
            {"distance_km": 10.0, "duration_sec": 0.0},
        ]
        v, used = rtt._weighted_speed_kmh(rides)
        self.assertIsNone(v)
        self.assertEqual(used, [])

    def test_filter_excludes_virtual_and_yoga(self):
        types = set(rtt._OUTDOOR_CYCLING_TYPES)
        self.assertNotIn("virtual_ride", types)
        self.assertNotIn("yoga", types)
        self.assertEqual(
            types,
            {"cycling", "biking", "mountain_biking", "road_biking", "gravel_cycling"},
        )

    def test_hmm_format(self):
        self.assertEqual(rtt._fmt_hmm(5.0 + 44 / 60.0), "5:44")
        self.assertEqual(rtt._fmt_hmm(1.0), "1:00")
        self.assertEqual(rtt._fmt_hmm(0.5), "0:30")

    def test_flag_below_10(self):
        rides = [
            {"date": datetime.date(2026, 6, 20), "sport_type": "cycling",
             "distance_km": 60.0, "duration_sec": 18000.0},
            {"date": datetime.date(2026, 6, 18), "sport_type": "gravel_cycling",
             "distance_km": 20.0, "duration_sec": 3600.0},
        ]
        orig = rtt._recent_outdoor_rides
        rtt._recent_outdoor_rides = lambda limit=10: rides
        try:
            out = rtt._tool_route_time_estimate({"distance_km": 100.0})
        finally:
            rtt._recent_outdoor_rides = orig
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["data"]["n_rides"], 2)
        self.assertTrue(out["data"]["n_below_target"])
        self.assertIn("< 10", out["analysis"])

    def test_full_estimate_value(self):
        rides = [
            {"date": datetime.date(2026, 6, 20), "sport_type": "cycling",
             "distance_km": 20.0, "duration_sec": 3600.0},
            {"date": datetime.date(2026, 6, 19), "sport_type": "cycling",
             "distance_km": 40.0, "duration_sec": 14400.0},
        ]
        orig = rtt._recent_outdoor_rides
        rtt._recent_outdoor_rides = lambda limit=10: rides
        try:
            out = rtt._tool_route_time_estimate({"distance_km": 24.0})
        finally:
            rtt._recent_outdoor_rides = orig
        self.assertEqual(out["status"], "OK")
        self.assertAlmostEqual(out["data"]["v_kmh"], 12.0, places=3)
        self.assertEqual(out["data"]["est_time_hmm"], "2:00")


if __name__ == "__main__":
    unittest.main()
