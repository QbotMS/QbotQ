# -*- coding: utf-8 -*-
"""Profile jazd (2026-10-19): wybor profilu, postoje, miasto na odcinkach. docs/RIDE_PROFILES.md"""
import os, sys, unittest
sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
from qbot3.routes import ride_profiles as RP

CFG = {"stops": {"trening": {"micro_min_per_km": 0.18, "short_min_per_h": 4.8},
                 "krotka_weekend": {"micro_min_per_km": 0.22, "short_min_per_h": 4.4},
                 "dluga": {"micro_min_per_km": 0.19, "short_min_per_h": 8.6},
                 "miasto": {"micro_min_per_km": 0.28, "short_min_per_h": 7.2}},
       "city": {"speed_factor": 0.925, "extra_micro_min_per_km": 0.1, "profile_min_share": 0.5},
       "rules": {"home": [52.345, 21.11], "away_km": 60, "min_h": 2.0,
                 "p75_moving_h_by_month": {str(m): (3.1 if m in (7, 8) else 1.6) for m in range(1, 13)}}}
SM = {"profiles": CFG, "stops": {"normal": {"micro_min_per_km": 0.19, "short_min_per_h": 12.4, "free_h": 1.0},
                                 "bikepacking": {"micro_min_per_km": 0.38, "short_min_per_h": 16.3, "free_h": 0.0}}}


class TestChoose(unittest.TestCase):
    def test_rules(self):
        c = lambda **k: RP.choose_profile(CFG, **k)[0]
        self.assertEqual(c(moving_h=1.0, ride_date="2026-10-21"), "trening")          # sroda
        self.assertEqual(c(moving_h=1.0, ride_date="2026-10-25"), "krotka_weekend")   # niedziela
        self.assertEqual(c(moving_h=2.4, ride_date="2026-10-21"), "dluga")            # pazdziernik: prog 2 h
        self.assertEqual(c(moving_h=2.4, ride_date="2026-07-21"), "trening")          # lipiec: prog 3,1 h
        self.assertEqual(c(moving_h=1.0, ride_date="2026-10-21", start=(43.7, 11.2)), "krotka_weekend")  # wyjazd
        self.assertEqual(c(moving_h=5, ride_date="2026-10-21", city_share=0.66), "miasto")
        self.assertEqual(c(moving_h=5, ride_date="2026-10-21", bikepacking=True), "bikepacking")


class TestStops(unittest.TestCase):
    def test_from_first_km(self):
        s = RP.stops_for(SM, "trening", km=20, moving_h=1.0)
        self.assertAlmostEqual(s["mikro_min"] + s["krotkie_min"], 0.18 * 20 + 4.8, places=3)

    def test_city_extra(self):
        s = RP.stops_for(SM, "dluga", km=100, moving_h=5, city_km=10)
        self.assertAlmostEqual(s["city_extra_min"], 1.0, places=3)
        self.assertEqual(RP.stops_for(SM, "miasto", km=30, moving_h=1.5, city_km=20)["city_extra_min"], 0.0)

    def test_bikepacking_uses_model_stops(self):
        s = RP.stops_for(SM, "bikepacking", km=80, moving_h=4)
        self.assertAlmostEqual(s["mikro_min"] + s["krotkie_min"], 0.38 * 80 + 16.3 * 4, places=3)


class TestClassify(unittest.TestCase):
    def test_bikepacking_sequence_and_city(self):
        H = (52.345, 21.11)
        rides = [dict(id="a", date="2025-07-26", km=103, mov_h=5, start=(54.0, 22.9), end=(54.1, 23.4), city_core=0),
                 dict(id="b", date="2025-07-27", km=112, mov_h=5.8, start=(54.1, 23.4), end=(54.0, 22.9), city_core=0),
                 dict(id="c", date="2025-06-20", km=111, mov_h=6, start=(51.2, 15.5), end=(51.2, 15.5), city_core=0),
                 dict(id="d", date="2026-10-01", km=24, mov_h=1.2, start=H, end=(52.221, 21.023), city_core=0.6)]
        cls = RP.classify_rides(rides, H)
        self.assertEqual((cls["a"], cls["b"]), ("bikepacking", "bikepacking"))
        self.assertNotEqual(cls["c"], "bikepacking")      # petla z bazy, nie ciag A->B
        self.assertEqual(cls["d"], "miasto")


class TestRouteTime(unittest.TestCase):
    def test_city_segments_slower_and_off(self):
        import qbot_route_time_tools as RT
        segs = [{"len_m": 10000, "grade_pct": 0, "surface": "asfalt", "built_up": True, "lat": 52.345, "lon": 21.11},
                {"len_m": 10000, "grade_pct": 0, "surface": "asfalt", "built_up": False}]
        a = RT.estimate_route_time_v2(segments=segs, profile="off")
        b = RT.estimate_route_time_v2(segments=segs, ride_date="2026-10-21")
        self.assertIsNone(a["ride_profile"])
        if RT.SPEED_MODEL.get("profiles"):
            self.assertGreater(b["moving_h"], a["moving_h"])
            self.assertEqual(b["city_km"], 10.0)
            self.assertIn(b["ride_profile"], RP.PROFILES)


if __name__ == "__main__":
    unittest.main()
