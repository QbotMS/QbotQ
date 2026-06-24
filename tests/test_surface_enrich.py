import importlib.util
import json
import os
import unittest

_SCRIPT_PATH = "/opt/qbot/app/scripts/surface_enrich_route.py"
_spec = importlib.util.spec_from_file_location("surface_enrich_route", _SCRIPT_PATH)
se = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(se)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.updates = []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "UPDATE" in sql:
            self.updates.append(params)

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.autocommit = True
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


class TestFazaB(unittest.TestCase):
    def setUp(self):
        import tools.rwgps.surface_landcover as sl
        self._sl = sl
        self._orig_fetch = sl._fetch_highway_for_point
        self._orig_db = se._db_connect

    def tearDown(self):
        self._sl._fetch_highway_for_point = self._orig_fetch
        se._db_connect = self._orig_db

    def test_faza_b_updates_unknown(self):
        rows = [(0, 50.0, 19.0), (1, 50.1, 19.1)]
        cur = _FakeCursor(rows)
        conn = _FakeConn(cur)
        se._db_connect = lambda: conn
        self._sl._fetch_highway_for_point = lambda lat, lon, radius=30: "asfalt"
        se._infer_and_save_highway("R1")
        self.assertEqual(len(cur.updates), 2)
        self.assertEqual(cur.updates[0], ("asfalt", "R1", 0))
        self.assertEqual(cur.updates[1], ("asfalt", "R1", 1))
        self.assertTrue(conn.committed)

    def test_faza_b_skips_none(self):
        rows = [(0, 50.0, 19.0), (1, 50.1, 19.1)]
        cur = _FakeCursor(rows)
        conn = _FakeConn(cur)
        se._db_connect = lambda: conn
        self._sl._fetch_highway_for_point = lambda lat, lon, radius=30: None
        se._infer_and_save_highway("R1")
        self.assertEqual(len(cur.updates), 0)

    def test_faza_b_failsafe(self):
        se._db_connect = _boom
        # nie moze rzucic wyjatku
        se._infer_and_save_highway("R1")


class TestFazaC(unittest.TestCase):
    def setUp(self):
        import qbot_route_report_tool as rr
        self._rr = rr
        self._orig_call = rr._call_tool
        self._route_id = "test_faza_c_unit"
        self._path = "/opt/qbot/artifacts/reports/poi_positions_" + self._route_id + ".json"
        if os.path.exists(self._path):
            os.remove(self._path)

    def tearDown(self):
        self._rr._call_tool = self._orig_call
        if os.path.exists(self._path):
            os.remove(self._path)

    def test_faza_c_saves_json(self):
        canned = {"status": "OK", "data": {"analysis": {
            "water": [{"route_km": 5.0, "name": "Studnia A"}],
            "hard_resupply": [{"route_km": 12.0, "name": "Sklep B", "category": "hard_resupply"}],
        }}}
        self._rr._call_tool = lambda name, args: canned
        se._precompute_poi(self._route_id)
        self.assertTrue(os.path.exists(self._path))
        with open(self._path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["route_id"], self._route_id)
        self.assertIn("computed_at", data)
        self.assertEqual(len(data["points"]), 2)
        kms = sorted(p["km"] for p in data["points"])
        self.assertEqual(kms, [5.0, 12.0])
        names = {p["name"] for p in data["points"]}
        self.assertEqual(names, {"Studnia A", "Sklep B"})

    def test_faza_c_failsafe(self):
        self._rr._call_tool = _boom
        # nie moze rzucic wyjatku
        se._precompute_poi(self._route_id)


if __name__ == "__main__":
    unittest.main()
