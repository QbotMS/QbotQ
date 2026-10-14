"""Jazda z Karoo -> ostrzezenie o deszczu (qbot_pogoda_alert.decide dla jazdy otwartej, qbot_karoo_live.short)."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_karoo_live as KL
import qbot_pogoda_alert as RA

TZ = RA.TZ
NOW = dt.datetime(2026, 10, 14, 14, 30, tzinfo=TZ)


def nowcast(rain_from_min=None, rain_to_min=None, mmh=3.0):
    out = []
    for m in range(0, 65, 5):
        r = rain_from_min is not None and rain_from_min <= m <= rain_to_min
        out.append({"t": NOW + dt.timedelta(minutes=m), "udzial": 0.8 if r else 0.0, "mmh": mmh if r else 0.0})
    return out


LIVE = {"id": 7, "nazwa": "jazda (Karoo)", "start": NOW - dt.timedelta(minutes=20), "koniec": NOW + dt.timedelta(minutes=60),
        "src": "karoo", "otwarta": True}


class KarooLive(unittest.TestCase):
    def test_radar_dla_jazdy_otwartej(self):
        d = RA.decide(LIVE, NOW, nowcast(20, 45), {}, [])
        self.assertEqual(d["kind"], "radar")
        self.assertEqual(d["dur"], 30)
        self.assertIn("trwająca od 14:10", d["text"])
        self.assertIn("za 20 min", d["text"])

    def test_jazda_otwarta_bez_prognozy_z_zespolu(self):
        prob = {(NOW + dt.timedelta(hours=h)).strftime("%Y-%m-%dT%H"): 0.9 for h in range(0, 4)}
        self.assertIsNone(RA.decide(LIVE, NOW, nowcast(), prob, []))

    def test_ten_sam_epizod_nie_powtarza(self):
        prev = [{"kind": "radar", "eta": NOW + dt.timedelta(minutes=20)}]
        self.assertIsNone(RA.decide(LIVE, NOW, nowcast(25, 45), {}, prev))

    def test_short_przed_deszczem(self):
        a = {"eta": NOW + dt.timedelta(minutes=12), "data": {"mmh": 2.5, "dur": 30, "otwarte": False}}
        s = KL.short(a, NOW)
        self.assertEqual(s["za_min"], 12)
        self.assertFalse(s["pada"])
        self.assertEqual(s["short"], "deszcz za 12 min · umiarkowany · ~30 min")

    def test_short_gdy_pada(self):
        a = {"eta": NOW - dt.timedelta(minutes=10), "data": {"mmh": 12, "dur": 30}}
        s = KL.short(a, NOW)
        self.assertTrue(s["pada"])
        self.assertEqual(s["short"], "pada · ulewa · jeszcze ~20 min")

    def test_short_po_epizodzie_none(self):
        a = {"eta": NOW - dt.timedelta(minutes=60), "data": {"mmh": 2, "dur": 30}}
        self.assertIsNone(KL.short(a, NOW))


if __name__ == "__main__":
    unittest.main()
