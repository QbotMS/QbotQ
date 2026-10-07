"""gear_weather: pogoda jazdy w ride_gear_log (2026-10-07)."""
import sqlite3
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
from qbot3.rides import gear_weather as gw  # noqa: E402

WE = {"apparent_c": {"tier": "B", "value": {"avg": 14.46, "max": 14.7}},
      "temp_c": {"tier": "A", "value": {"avg": 12.7}},
      "precip_mm": {"tier": "B", "value": {"sum": 1.1, "hours": 2}}}


def _db():
    g = sqlite3.connect(":memory:")
    g.execute("CREATE TABLE ride_gear_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ride_key TEXT, slot TEXT, "
              "gear_id INTEGER, value TEXT, updated_at TEXT, UNIQUE(ride_key, slot))")
    g.execute("INSERT INTO ride_gear_log (ride_key, slot, gear_id, value, updated_at) "
              "VALUES ('A','Kurtka',5,NULL,'2026-09-22 10:00:00'), ('A','_odczucie',NULL,'ok','2026-09-22 10:00:01')")
    return g


class GearWeatherTest(unittest.TestCase):
    def test_values_format(self):
        self.assertEqual(gw.values_from_weather(WE), {"_temp_app": "14.5", "_temp_fit": "12.7", "_precip": "1.1"})

    def test_values_partial(self):
        self.assertEqual(gw.values_from_weather({"apparent_c": {"value": {"avg": 0}}}), {"_temp_app": "0.0"})

    def test_write_keeps_ride_time(self):
        g = _db()
        res = gw.write_slots(g, "A", gw.values_from_weather(WE))
        self.assertTrue(res["ok"])
        rows = dict(g.execute("SELECT slot, updated_at FROM ride_gear_log WHERE slot LIKE '\\_t%' ESCAPE '\\' "
                              "OR slot='_precip'").fetchall())
        self.assertEqual(set(rows), {"_temp_app", "_temp_fit", "_precip"})
        self.assertTrue(all(v == "2026-09-22 10:00:01" for v in rows.values()))

    def test_idempotent_update(self):
        g = _db()
        gw.write_slots(g, "A", gw.values_from_weather(WE))
        gw.write_slots(g, "A", {"_temp_app": "9.0"})
        d = dict(g.execute("SELECT slot, value FROM ride_gear_log WHERE ride_key='A'").fetchall())
        self.assertEqual(d["_temp_app"], "9.0")
        self.assertNotIn("_temp_fit", d)
        self.assertEqual(g.execute("SELECT count(*) FROM ride_gear_log").fetchone()[0], 3)

    def test_no_report_no_change(self):
        g = _db()
        res = gw.write_slots(g, "A", None)
        self.assertFalse(res["ok"])
        self.assertEqual(g.execute("SELECT count(*) FROM ride_gear_log").fetchone()[0], 2)

    def test_no_outfit_removes_orphans(self):
        g = _db()
        gw.write_slots(g, "A", gw.values_from_weather(WE))
        g.execute("DELETE FROM ride_gear_log WHERE slot IN ('Kurtka','_odczucie')")
        res = gw.write_slots(g, "A", gw.values_from_weather(WE))
        self.assertEqual(res["why"], "brak stroju")
        self.assertEqual(g.execute("SELECT count(*) FROM ride_gear_log").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
