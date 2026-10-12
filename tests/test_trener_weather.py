"""TRENER - poranna korekta planu z uwagi na pogode (qbot_trener_weather): czyste funkcje, bez bazy i sieci."""
import os
import sys
import unittest
from datetime import date, time

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_trener_weather as W  # noqa: E402

D = date(2026, 10, 14)  # sroda


def hours(day, rain_hours=(), wind=3.0):
    h = {}
    for hh in range(0, 24):
        h[f"{day.isoformat()}T{hh:02d}"] = {"wind": wind, "gust": 6.0, "feel": 10.0,
                                             "rain": 2.0 if hh in rain_hours else 0.0, "prob": 90 if hh in rain_hours else 5, "snow": 0}
    return h


def ride(st=time(16, 0), dur=120, sid=1, **kw):
    s = {"id": sid, "day": D, "sport": "rower", "name": "Jazda spokojnie", "start_time": st, "dur_min": dur,
         "min_min": 60, "status": "plan", "source": "auto", "is_long": False, "zone": 2}
    s.update(kw)
    return s


class Okno(unittest.TestCase):
    def test_deszcz_w_oknie(self):
        wx = W.window_wx(hours(D, rain_hours=(17,)), D, 16 * 60, 120)
        self.assertEqual(wx["rain_mmh"], 2.0)
        self.assertTrue(W.E.wx_bad(wx, {}, False))

    def test_deszcz_poza_oknem(self):
        wx = W.window_wx(hours(D, rain_hours=(9,)), D, 16 * 60, 120)
        self.assertFalse(W.E.wx_bad(wx, {}, False))

    def test_brak_danych(self):
        self.assertIsNone(W.window_wx({}, D, 600, 60))


class Propozycje(unittest.TestCase):
    def test_przesun_godzine_najblizej(self):
        h = hours(D, rain_hours=(15, 16, 17))
        c = W.candidates(ride(), h, {}, [ride()], {D: [ride()]}, now_min=7 * 60)
        self.assertEqual(c[0]["kind"], "hour")
        self.assertEqual(c[0]["start_time"], "18:00")   # 18-20 sucho, blizej niz 12:30

    def test_kolizja_z_inna_sesja(self):
        h = hours(D, rain_hours=(15, 16, 17))
        sila = {"id": 2, "day": D, "sport": "sila", "start_time": time(18, 0), "dur_min": 60, "status": "plan"}
        c = W.candidates(ride(), h, {}, [ride(), sila], {D: [ride(), sila]}, now_min=7 * 60)
        self.assertEqual(c[0]["kind"], "hour")
        self.assertNotIn(c[0]["start_time"], ("17:30", "18:00", "18:30"))

    def test_kolejnosc_z_kalibracji(self):
        h = hours(D, rain_hours=(15, 16, 17))
        c = W.candidates(ride(), h, {"wx.fallback": 3}, [ride()], {D: [ride()]}, now_min=7 * 60)
        self.assertEqual(c[0]["kind"], "home")
        self.assertEqual(c[0]["dur_min"], 60)

    def test_caly_dzien_deszcz_dom_albo_inny_dzien(self):
        h = hours(D, rain_hours=tuple(range(24)))
        d2 = date(2026, 10, 15)
        h.update(hours(d2))
        c = W.candidates(ride(), h, {}, [ride()], {D: [ride()], d2: []}, now_min=7 * 60)
        kinds = [x["kind"] for x in c]
        self.assertNotIn("hour", kinds)
        self.assertEqual(kinds[0], "day")
        self.assertIn("cz 15.10", c[0]["text"])

    def test_nie_wczesniej_niz_za_30_min(self):
        h = hours(D, rain_hours=(15, 16, 17))
        c = W.candidates(ride(), h, {}, [ride()], {D: [ride()]}, now_min=17 * 60 + 50)
        self.assertNotEqual(c[0]["kind"], "hour")   # 18:30+120 > 20:00

    def test_trenazer_pomijany(self):
        self.assertTrue(W.is_indoor({"name": "Trenażer Z2"}))
        self.assertFalse(W.is_indoor({"name": "Jazda spokojnie"}))

    def test_przyciski(self):
        b = W.buttons({"session_id": 7})
        self.assertEqual(b[0][0]["callback_data"], "tr:wxok:7")
        self.assertEqual(W.buttons(None), [])


if __name__ == "__main__":
    unittest.main()
