"""Silnik tras -- warunki drogi (E3.2): road_flags + alerty oblodzenie/mgla/bloto (bez sieci)."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_pogoda as PG  # noqa: E402
from qbot3.routes import route_meteo_engine as RM  # noqa: E402


def seg(km, eta, **kw):
    d = {"km": km, "eta": eta, "_dur_min": 10, "lod": 0, "mgla": 0, "nawierzchnia": 0}
    d.update(kw)
    return d


class Reguly(unittest.TestCase):
    def test_road_flags(self):
        self.assertEqual(PG.road_flags(1.0, 0.5, -1.0, 800, True, 3.0)[:3], (3, 2, 2))    # mokro + grunt -1 -> lod 3; mgla; bloto
        self.assertEqual(PG.road_flags(3.0, -2.0, 0.3, 10000, False, 0.0)[:3], (1, 0, 0))  # zimny grunt, sucho, bez szronu
        self.assertEqual(PG.road_flags(3.0, 0.4, 0.3, None, False, 0.0)[0], 2)             # szron: punkt rosy >= grunt
        self.assertIsNone(PG.road_flags(3.0, 0.4, 5.0, None, False, 0.0)[1])               # brak widocznosci -> brak oceny mgly


class Alerty(unittest.TestCase):
    def test_okna(self):
        ps = [seg(0, "06:00"), seg(5, "06:10", lod=2), seg(10, "06:20", lod=3, mgla=2), seg(15, "06:30", mgla=2),
              seg(20, "06:40", nawierzchnia=2), seg(25, "06:50")]
        a = {x["typ"]: x for x in RM._build_road_alerts(ps)}
        self.assertEqual(a["oblodzenie"]["severity"], "ALARM")
        self.assertEqual((a["oblodzenie"]["km_od"], a["oblodzenie"]["km_do"]), (5, 10))
        self.assertEqual((a["mgla"]["eta_od"], a["mgla"]["eta_do"]), ("06:20", "06:30"))
        self.assertEqual(a["bloto"]["minuty"], 10)

    def test_brak_danych_widocznosci_nie_daje_mgly(self):
        t0 = dt.datetime(2026, 10, 15, 4, tzinfo=dt.timezone.utc)
        tms = [t0 + dt.timedelta(hours=k) for k in range(4)]
        h = {"dew_point_2m": [1] * 4, "soil_temperature_0cm": [5] * 4, "visibility": [None] * 4, "precipitation": [0] * 4, "snowfall": [0] * 4}
        r = RM._road_at(h, tms, t0 + dt.timedelta(minutes=90), 6.0, {"lat": 52.3, "lon": 21.1})
        self.assertIsNone(r["mgla"])
        self.assertEqual(r["lod"], 0)


if __name__ == "__main__":
    unittest.main()
