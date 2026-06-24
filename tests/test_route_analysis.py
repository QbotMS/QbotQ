import unittest
from unittest import mock
import qbot_route_analysis_tool as mod

PLAN = ("ANALIZA PLANOWANEJ TRASY\nDystans: 95.0 km, podjazdy +1200 m\n"
        "Nawierzchnia: 70% utwardzona, asfalt 70%, nieznana 24%, szuter 6%\n"
        "Forma (FitModel, 2026-06-20): FTP 250 W, 3.5 W/kg, glikogen 450 g")
PROF = "Profil:\nkm 0-24: asfalt\nkm 24-30: nieznana\nkm 30-95: szuter\nPodjazd km 40-45 6%"
TIME = "Szacowany czas: 4:30 h przy 21 km/h"
FUEL = "Wegle 60 g/h, plyny 0.7 L/h, lacznie ~270 g"
TP = "Zestaw Zipp 303, opona 40 mm, cisnienie 2.8/3.0 bar"
FIXT = {"route_plan_analysis": PLAN, "route_profile_detail": PROF,
        "route_time_estimate": TIME, "route_fuel_plan": FUEL, "tire_pressure": TP}
POIS = [(5.2, "sklep", "Zabka"), (8.7, "sklep", "ABC"), (12.1, "woda", "zrodlo")]


def _run(variant):
    with mock.patch.object(mod, "_call_tool", lambda name, args: {"status": "OK", "analysis": FIXT.get(name, "")}), \
         mock.patch.object(mod, "_poi_points", lambda *a, **k: POIS), \
         mock.patch.object(mod, "_wind_speed_kmh", lambda *a, **k: (18.0, 34.0)), \
         mock.patch.object(mod, "_resolve_distance_km", lambda *a, **k: 95.0):
        import qgpt_client
        with mock.patch.object(qgpt_client, "qgpt_text", lambda prompt, **k: prompt):
            return mod._tool_route_analysis({"variant": variant, "route_id": "55734589"})["analysis"]


class TestRouteAnalysis(unittest.TestCase):
    def test_pelny_sections(self):
        o = _run("pelny")
        for t in ("CHARAKTERYSTYKA TRASY", "NAWIERZCHNIA (analiza", "STRATEGIA MOCY",
                  "ZYWIENIE I NAWODNIENIE", "Zalecane cisnienie startowe", "RYZYKA (ranking)"):
            self.assertIn(t, o)

    def test_pelny_D_km(self):
        self.assertIn("km 5.2", _run("pelny"))

    def test_pelny_B_nieznana(self):
        self.assertIn("nieznana", _run("pelny"))

    def test_pelny_C_waty(self):
        self.assertIn("250 W", _run("pelny"))

    def test_pelny_F_km_x(self):
        self.assertIn("km X", _run("pelny"))

    def test_skrocony_no_D(self):
        o = _run("skrocony")
        self.assertNotIn("ZYWIENIE I NAWODNIENIE", o)
        self.assertNotIn("km 5.2", o)
        self.assertIn("STRATEGIA MOCY", o)
        self.assertIn("250 W", o)

    def test_grupa_no_waty(self):
        o = _run("grupa")
        self.assertNotIn("250 W", o)
        self.assertNotIn("FTP", o)
        self.assertNotIn("STRATEGIA MOCY", o)
        self.assertIn("ZYWIENIE I NAWODNIENIE", o)
        self.assertIn("km 5.2", o)


if __name__ == "__main__":
    unittest.main()
