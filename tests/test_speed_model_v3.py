"""Model czasu v3 (2026-10-08): konfiguracja, postoje wg czasu ruchu, bikepacking, zapas v2."""
import importlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_route_time_tools as RT  # noqa: E402

SEGS = [{"len_m": 20000, "grade_pct": 0, "surface": "asfalt"},
        {"len_m": 20000, "grade_pct": 0, "surface": "szuter"},
        {"len_m": 10000, "grade_pct": 3, "surface": "asfalt"}]


class SpeedModelV3Test(unittest.TestCase):
    def test_config_loaded(self):
        self.assertTrue(RT.SPEED_MODEL, "config/speed_model.json nie wczytany")
        self.assertTrue(RT.SPEED_MODEL_VERSION.startswith("v3_"))
        self.assertEqual(RT.SPEED_TABLE["normalny"]["paved"]["-1..1"],
                         RT.SPEED_MODEL["table"]["normalny"]["paved"]["-1..1"])

    def test_short_stops_follow_moving_time(self):
        p = RT.SPEED_MODEL["stops"]["normal"]
        s1 = RT.stops_minutes(20, moving_h=0.9)
        self.assertEqual(s1["krotkie_min"], 0.0)  # pierwsza godzina bez krotkich postojow
        s4 = RT.stops_minutes(90, moving_h=4.0)
        self.assertAlmostEqual(s4["krotkie_min"], round(p["short_min_per_h"] * (4.0 - p["free_h"]), 1), places=1)
        self.assertAlmostEqual(s4["mikro_min"], round(p["micro_min_per_km"] * 90, 1), places=1)

    def test_bikepacking_slower_and_more_stops(self):
        n = RT.estimate_route_time_v2(segments=SEGS)
        b = RT.estimate_route_time_v2(segments=SEGS, bikepacking=True)
        self.assertEqual(n["status"], "OK"); self.assertEqual(b["status"], "OK")
        f = RT.SPEED_MODEL["bikepacking_speed_factor"]
        self.assertAlmostEqual(b["moving_h"], round(n["moving_h"] / f, 2), delta=0.02)
        self.assertGreater(b["stops"]["krotkie_min"], n["stops"]["krotkie_min"])
        self.assertTrue(b["bikepacking"]); self.assertFalse(n["bikepacking"])

    def test_unknown_bike_has_no_effect(self):
        self.assertEqual(RT.speed_factor(False, "rower-ktorego-nie-ma"), 1.0)

    def test_bad_config_falls_back(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"table": {}}, fh)
        try:
            self.assertFalse(RT._load_speed_model(fh.name))
            self.assertEqual(RT.SPEED_MODEL, {})
        finally:
            os.unlink(fh.name)
            RT._load_speed_model()  # przywroc kanon
        self.assertTrue(RT.SPEED_MODEL)

    def test_tool_wrapper_accepts_bikepacking(self):
        out = RT._tool_route_time_estimate({"segments": SEGS, "bikepacking": "true"})
        self.assertTrue(out["bikepacking"])


if __name__ == "__main__":
    unittest.main()
