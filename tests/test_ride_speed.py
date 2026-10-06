"""Blok predkosci raportu jazdy (qbot3/rides/ride_speed.py) - liczby na syntetycznej jezdzie."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qbot3.rides.ride_speed import speed_block  # noqa: E402
import qbot_route_time_tools as RT  # noqa: E402


def _ride(scat):
    """Plasko, 20 km/h przez 3600 s, potem 600 s postoju (zapisany), potem 20 km/h przez 1800 s."""
    recs, d, sec = [], 0.0, 0
    v = 20 / 3.6
    for phase, (n, spd) in enumerate(((3600, v), (600, 0.0), (1800, v))):
        for _ in range(n):
            recs.append({"sec": sec, "dist": d, "spd": spd, "alt": 100.0, "scat": scat})
            d += spd
            sec += 1
    return recs


class RideSpeedTest(unittest.TestCase):
    def test_netto_brutto(self):
        v = speed_block(_ride(1))["value"]
        self.assertAlmostEqual(v["netto_kmh"], 20.0, delta=0.2)
        # 30 km w 6000 s -> 18 km/h
        self.assertAlmostEqual(v["brutto_kmh"], 18.0, delta=0.2)
        self.assertEqual(v["stop_s"], v["elapsed_s"] - v["moving_s"])
        self.assertAlmostEqual(v["postoje_min"], 10.0, delta=0.2)

    def test_model_flat_paved(self):
        v = speed_block(_ride(1))["value"]
        tab = RT.SPEED_TABLE["normalny"]["paved"]["-1..1"]
        self.assertAlmostEqual(v["model_kmh"]["normalny"], tab, delta=0.2)
        self.assertEqual(v["vs_model_pct"]["normalny"], round((v["netto_kmh"] / v["model_kmh"]["normalny"] - 1) * 100))
        self.assertEqual(v["by_surface"][0]["klasa"], "asfalt / twarda")
        self.assertEqual(v["nawierzchnia_znana_pct"], 100.0)

    def test_unknown_surface_uses_mean(self):
        v = speed_block(_ride(None))["value"]
        exp = round((RT.SPEED_TABLE["normalny"]["paved"]["-1..1"] + RT.SPEED_TABLE["normalny"]["unpaved"]["-1..1"]) / 2, 1)
        self.assertAlmostEqual(v["model_kmh"]["normalny"], exp, delta=0.2)
        self.assertEqual(v["nawierzchnia_znana_pct"], 0.0)

    def test_too_short(self):
        self.assertIsNone(speed_block(_ride(1)[:10])["value"])


if __name__ == "__main__":
    unittest.main()
