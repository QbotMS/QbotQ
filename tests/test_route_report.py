#!/usr/bin/env python3
"""TASK 08/09 - testy orkiestratora route_report (mock 6 narzedzi + LLM stub sekcji C)."""
import re
import unittest

import qbot_route_report_tool as rr

# Kanoniczne wyniki 6 narzedzi (format success_result: status + data.analysis)
CANNED = {
    "route_plan_analysis": {"status": "OK", "data": {"analysis": (
        "ANALIZA PLANOWANEJ TRASY\n"
        "Dystans: 99.4 km | podjazdy: +1200 m\n"
        "Nawierzchnia: 60% utwardzona\n"
        "Pogoda: 12-20 C, wiatr w plecy km 10-20\n"
        "\n"
        "\U0001f4aa Forma (FitModel, 2026-06-20): FTP 250 W, 3.20 W/kg"
    )}},
    "route_profile_detail": {"status": "OK", "data": {"analysis": (
        "PROFIL ODCINKAMI\nkm 0-5 asfalt\nkm 5-12 szuter luzny"
    )}},
    "route_time_estimate": {"status": "OK", "data": {"analysis": (
        "Szacowany czas trasy\nv 17.3 km/h -> 5:45"
    )}},
    "tire_pressure": {"status": "OK", "data": {"analysis": (
        "CISNIENIE OPON\n#1 2.0 bar / 2.2 bar"
    )}},
    "route_fuel_plan": {"status": "OK", "data": {"analysis": (
        "B2 plyny 0.6 L/h\nB3 wegle 60 g/h"
    ), "data": {}}},
    "route_poi_analyze_readonly": {"status": "OK", "data": {
        "counts": {"water": 3, "food": 5, "attractions": 2},
        "report_path": "/opt/qbot/artifacts/poi.md",
    }},
}


def _fake_section_c(prompt, **kwargs):
    """Stub LLM dla _generate_section_c: zwraca C1/C2/C4 zawsze, C3 tylko gdy proszono."""
    lines = [
        "- C1 Taktyka (ocena): rownomierne tempo na podjazdach.",
        "- C2 Ryzyko (ocena): luzny szuter i wiatr boczny.",
    ]
    if "C3" in prompt:
        lines.append("- C3 Sprzet (ocena): opony gravel pasuja do nawierzchni.")
    lines.append("- C4 Najwieksze zagrozenie (ocena): zjazd po luznym szutrze.")
    return "\n".join(lines)


class TestRouteReport(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return CANNED[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4
        import qgpt_client
        self._orig_qgpt = qgpt_client.qgpt_text
        qgpt_client.qgpt_text = _fake_section_c

    def tearDown(self):
        import qgpt_client
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        qgpt_client.qgpt_text = self._orig_qgpt

    def _names(self):
        return [n for n, _ in self.calls]

    # ---- brak wariantu => pytanie (ask-first), bez wywolania narzedzi ----
    def test_missing_variant_asks(self):
        out = rr._tool_route_report({"route_id": "55734589"})
        self.assertEqual(out["status"], "OK")
        self.assertIsNone(out["variant"])
        a = out["analysis"]
        self.assertIn("wariant", a.lower())
        self.assertIn("skrócony", a.lower())
        self.assertIn("pełny", a.lower())
        self.assertIn("grup", a.lower())
        self.assertEqual(self.calls, [])

    # ---- wariant pelny ----
    def test_pelny_all_sections(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        self.assertEqual(out["variant"], "pelny")
        a = out["analysis"]
        for marker in ("## A - DANE TRASY", "## A3", "## A7", "## A8",
                       "### B4", "B2/B3", "### B5", "## C"):
            self.assertIn(marker, a, marker)
        # C pisze Albert — narzedzie zwraca tylko kontekst dla sekcji C
        ctx_c = out["context_for_section_c"]
        self.assertIsNotNone(ctx_c)
        for m in ("C1", "C2", "C3", "C4"):
            self.assertIn(m, ctx_c, m)
        # forma/FTP zachowane w pelnym
        self.assertIn("FTP", a)
        # POI dostalo poprawne argumenty
        poi_args = dict(next(args for n, args in self.calls if n == "route_poi_analyze_readonly"))
        self.assertEqual(poi_args["km_from"], 0.0)
        self.assertEqual(poi_args["km_to"], 99.4)
        self.assertTrue(poi_args["open_window"])
        # wszystkie 6 narzedzi uzyte
        self.assertEqual(set(self._names()), {
            "route_plan_analysis", "route_profile_detail", "route_time_estimate",
            "tire_pressure", "route_fuel_plan", "route_poi_analyze_readonly",
        })

    # ---- wariant grupa: bez danych osobistych ----
    def test_grupa_no_personal(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "grupa"})
        self.assertEqual(out["variant"], "grupa")
        a = out["analysis"]
        for marker in ("## A - DANE TRASY", "## A3", "## A8", "### B4", "## C"):
            self.assertIn(marker, a, marker)
        self.assertIsNotNone(out["context_for_section_c"])
        # BEZ danych osobistych: forma/FTP, cisnienia, zywienie, sprzet, C3
        self.assertNotIn("FTP", a)
        self.assertNotIn("Forma", a)
        self.assertNotIn("### B5", a)
        self.assertNotIn("CISNIENIE", a)
        self.assertNotIn("B2/B3", a)
        self.assertNotIn("## A7", a)
        self.assertNotIn("C3", a)
        # tire_pressure i fuel NIE wywolane w grupie
        names = set(self._names())
        self.assertNotIn("tire_pressure", names)
        self.assertNotIn("route_fuel_plan", names)
        self.assertIn("route_poi_analyze_readonly", names)

    # ---- aliasy wariantow ----
    def test_variant_aliases(self):
        self.assertEqual(rr._tool_route_report({"variant": "pełny"})["variant"], "pelny")
        self.assertEqual(rr._tool_route_report({"variant": "dla grupy"})["variant"], "grupa")
        self.assertEqual(rr._tool_route_report({"variant": "skrócony"})["variant"], "skrocony")
        self.assertIsNone(rr._tool_route_report({"variant": "cokolwiek"})["variant"])

    # ---- route_id przekazywany do narzedzi ----
    def test_route_id_passthrough(self):
        rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        plan_args = next(args for n, args in self.calls if n == "route_plan_analysis")
        self.assertEqual(plan_args.get("route_id"), "55734589")
        time_args = next(args for n, args in self.calls if n == "route_time_estimate")
        self.assertEqual(time_args.get("route_id"), "55734589")

    # ---- wszystkie warianty generuja niepusty raport ----
    def test_all_variants_nonempty(self):
        for v in ("skrocony", "pelny", "grupa"):
            out = rr._tool_route_report({"route_id": "55734589", "variant": v})
            self.assertEqual(out["status"], "OK")
            self.assertGreater(len(out["analysis"]), 50)


class TestRouteReportTask09(unittest.TestCase):
    """TASK 09 - B2/B3 realne wejscia, A8 bidony, sekcja C przez LLM."""

    def setUp(self):
        self.calls = []
        self.canned = {
            "route_plan_analysis": {"status": "OK", "data": {"analysis": (
                "ANALIZA PLANOWANEJ TRASY\n"
                "Dystans: 99.4 km\n"
                "Pogoda: 18–24°C, wiatr w plecy\n"
            )}},
            "route_profile_detail": {"status": "OK", "data": {"analysis":
                "PROFIL ODCINKAMI\nkm 0-5 asfalt"}},
            "route_time_estimate": {"status": "OK", "data": {"analysis":
                "Szacowany czas trasy\nv 17.3 km/h -> 3:30"}},
            "tire_pressure": {"status": "OK", "data": {"analysis":
                "CISNIENIE OPON\n#1 2.0 bar"}},
            "route_fuel_plan": {"status": "OK", "data": {"analysis":
                "B2 plyny 0.6 L/h\nB3 wegle 60 g/h"}},
            "route_poi_analyze_readonly": {"status": "OK", "data": {
                "counts": {"water": 3, "food": 5, "attractions": 2},
                "report_path": "/opt/qbot/artifacts/poi.md"}},
        }

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return self.canned[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4
        import qgpt_client
        self._orig_qgpt = qgpt_client.qgpt_text
        qgpt_client.qgpt_text = _fake_section_c

    def tearDown(self):
        import qgpt_client
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        qgpt_client.qgpt_text = self._orig_qgpt

    def _fuel_args(self):
        return next(args for n, args in self.calls if n == "route_fuel_plan")

    def test_fuel_gets_temp_from_plan(self):
        rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        fa = self._fuel_args()
        self.assertIn("temp_c", fa)
        self.assertAlmostEqual(float(fa["temp_c"]), 21.0, places=1)

    def test_fuel_gets_duration_from_time(self):
        rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        fa = self._fuel_args()
        self.assertIn("duration_h", fa)
        self.assertAlmostEqual(float(fa["duration_h"]), 3.5, places=2)

    def test_a8_bidony_hot(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        a = out["analysis"]
        self.assertIn("💧 Bidony", a)
        self.assertIn("plecak", a.lower())
        self.assertIn("refill", a.lower())

    def test_a8_bidony_default(self):
        self.canned["route_plan_analysis"]["data"]["analysis"] = (
            "ANALIZA\nPogoda: 10–14°C, wiatr w plecy\n")
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        a = out["analysis"]
        self.assertIn("💧 Bidony", a)
        self.assertIn("2 bidony w ramie", a)
        self.assertNotIn("plecak", a.lower())

    def test_section_c_pelny_present(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        a = out["analysis"]
        self.assertIn("## C", a)
        ctx_c = out["context_for_section_c"]
        self.assertIsNotNone(ctx_c)
        for m in ("C1", "C2", "C3", "C4"):
            self.assertIn(m, ctx_c)
        self.assertNotIn("model uzupelnia", a)
        self.assertNotIn("model uzupełnia", a)

    def test_section_c_skrocony_absent(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "skrocony"})
        a = out["analysis"]
        self.assertNotIn("## C", a)
        self.assertIsNone(out["context_for_section_c"])


def _echo_section_c(prompt, **kwargs):
    """TASK10 stub LLM: echo-uje konkretne liczby (waty, km) z briefu do oceny."""
    import re as _re
    watts = _re.findall(r"\d+\s*[–-]\s*\d+\s*W", prompt)
    kms = _re.findall(r"km\s*\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?", prompt)
    w = watts[0] if watts else "moc wg briefu"
    km1 = kms[0] if kms else "km 5-12"
    lines = [
        f"- C1 Moc per segment (ocena): trzymaj {w} na plaskich odcinkach.",
        f"- C2 Ryzyko (ocena): najtrudniejszy odcinek {km1} - luzny zwir, jedz ostroznie.",
    ]
    if "C3" in prompt:
        lines.append("- C3 Sprzet (ocena): TAK, opony gravel pasuja do nawierzchni.")
    lines.append(f"- C4 (ocena): najwieksze zagrozenie to {km1} z luznym zwirem.")
    return "\n".join(lines)


class TestRouteReportTask10(unittest.TestCase):
    """TASK 10 - brief z konkretnymi liczbami + sekcja C bez ogolnikow."""

    def setUp(self):
        self.calls = []
        self.canned = {
            "route_plan_analysis": {"status": "OK", "data": {"analysis": (
                "ANALIZA PLANOWANEJ TRASY\n"
                "Dystans: 99.4 km | podjazdy: +1200 m\n"
                "Pogoda: 16–22°C, wiatr w plecy km 10-20\n"
                "\n"
                "\U0001f4aa Forma (FitModel, 2026-06-20): FTP 257 W, 3.30 W/kg"
            )}},
            "route_profile_detail": {"status": "OK", "data": {"analysis": (
                "SZCZEGOLOWY PROFIL TRASY\n"
                "Nawierzchnia (odcinki >= 0.2 km):\n"
                "  km 0.0-5.0 (5.0): asfalt\n"
                "  km 5.0-12.0 (7.0): szuter luzny\n"
                "  km 20.0-35.0 (15.0): zwir\n"
                "  km 40.0-41.5 (1.5): trawa\n"
            )}},
            "route_time_estimate": {"status": "OK", "data": {"analysis":
                "Szacowany czas trasy\nv 17.3 km/h -> 5:45"}},
            "tire_pressure": {"status": "OK", "data": {"analysis":
                "CISNIENIE OPON\naktywny zestaw: gravel\n#1 2.0 bar / 2.2 bar"}},
            "route_fuel_plan": {"status": "OK", "data": {"analysis":
                "- **60 g/h** (zaokraglone do 5 g)\n- **0.85 L/h** (zaokraglone do 0.05 L)"}},
            "route_poi_analyze_readonly": {"status": "OK", "data": {
                "counts": {"water": 3, "food": 5, "attractions": 2},
                "report_path": "/opt/qbot/artifacts/poi.md"}},
        }

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return self.canned[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4
        import qgpt_client
        self._orig_qgpt = qgpt_client.qgpt_text
        qgpt_client.qgpt_text = _echo_section_c

    def tearDown(self):
        import qgpt_client
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        qgpt_client.qgpt_text = self._orig_qgpt

    def _section_c(self, a):
        idx = a.find("## C")
        return a[idx:] if idx >= 0 else ""

    def test_section_c_has_watts(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        c = out["context_for_section_c"]
        self.assertRegex(c, r"\d+\s*[–-]\s*\d+\s*W")

    def test_section_c_has_km_reference(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        c = out["context_for_section_c"]
        self.assertIn("km", c)

    def test_section_c_no_generic_phrases(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        c = out["context_for_section_c"].lower()
        self.assertNotIn("równe tempo", c)
        self.assertNotIn("rownomierne tempo", c)

    def test_brief_extracts_ftp(self):
        brief = rr._build_section_c_brief({
            "plan": self.canned["route_plan_analysis"],
            "variant": "pelny",
        })
        self.assertIn("257", brief)

    def test_brief_extracts_surface_segments(self):
        brief = rr._build_section_c_brief({
            "prof": self.canned["route_profile_detail"],
            "variant": "pelny",
        })
        self.assertIn("km", brief)


class TestRouteReportTask12(unittest.TestCase):
    """TASK 12 - dokument kontekstowy: kombinacje ryzyk, POI km, wnioskowanie, strefy, gap, sekcja C <=8 zdan."""

    def setUp(self):
        self.calls = []
        self.canned = {
            "route_plan_analysis": {"status": "OK", "data": {"analysis": (
                "\U0001f4cb ANALIZA PLANOWANEJ TRASY\n"
                "Dystans: 80.0 km | podjazdy: +900 m / zjazdy: -900 m\n"
                "Stromizny: maks 8%, stromo (>=4%) na ~3.0 km\n"
                "Nawierzchnia: 55% utwardzona | asfalt 55%, szuter 30%, nieznana 15%\n"
                "\n"
                "\U0001f324  Pogoda (prognoza): 28–30°C, opady ~0.0 mm na trasie\n"
                "   \U0001f4a8 Pod wiatr (oszczedzaj sie wczesniej): km 50–60\n"
                "   \U0001f343 Wiatr w plecy: km 5–10\n"
                "\n"
                "\U0001f4aa Forma (FitModel, 2026-06-20): FTP 260 W, 3.40 W/kg"
            )}},
            "route_profile_detail": {"status": "OK", "data": {"analysis": (
                "SZCZEGOLOWY PROFIL TRASY (z ramek 80 m)\n"
                "Dystans 80.0 km | 1000 ramek | +900 m / -900 m | max 8% | stromo(>=4%) ~3.0 km\n"
                "\n"
                "Nawierzchnia (odcinki >= 0.2 km):\n"
                "  km 0.0-20.0 (20.0): asfalt\n"
                "  km 20.0-23.0 (3.0): nieznana\n"
                "  km 50.0-58.0 (8.0): szuter luzny\n"
                "\n"
                "Podjazdy (>= 3%, min 200 m):\n"
                "  km 30.0-33.0 (3.0 km): +150 m, max 8%\n"
            )}},
            "route_time_estimate": {"status": "OK", "data": {"analysis":
                "Szacowany czas trasy\nv 18.0 km/h -> 4:30"}},
            "tire_pressure": {"status": "OK", "data": {"analysis":
                "CISNIENIE OPON\naktywny zestaw: gravel\n#1 2.0 bar / 2.2 bar"}},
            "route_fuel_plan": {"status": "OK", "data": {"analysis":
                "- **60 g/h**\n- **0.85 L/h**"}},
            "route_poi_analyze_readonly": {"status": "OK", "data": {
                "analysis": "POI: km 5.0 woda; km 12.0 sklep; km 55.0 woda",
                "counts": {"water": 2, "food": 1, "attractions": 0},
                "report_path": "/opt/qbot/artifacts/poi.md"}},
        }

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return self.canned[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 80.0
        import qgpt_client
        self._orig_qgpt = qgpt_client.qgpt_text
        qgpt_client.qgpt_text = _echo_section_c

    def tearDown(self):
        import qgpt_client
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        qgpt_client.qgpt_text = self._orig_qgpt

    def _doc(self):
        # TASK 13: dokument kontekstowy nie jest juz w 'analysis' — trafia do context_for_section_c
        return rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})["context_for_section_c"]

    def test_document_has_risk_combinations(self):
        a = self._doc()
        self.assertIn("KOMBINACJE RYZYK", a)
        idx = a.find("KOMBINACJE RYZYK")
        block = a[idx:idx + 600]
        self.assertRegex(block, r"km\s*\d+(?:\.\d+)?\s*[-–]\s*\d+")

    def test_document_has_poi_km(self):
        a = self._doc()
        self.assertIn("PUNKTY UZUPELNIENIA", a)
        idx = a.find("PUNKTY UZUPELNIENIA")
        block = a[idx:idx + 300]
        self.assertIn("km 5", block)
        self.assertIn("km 12", block)

    def test_document_has_unknown_inference(self):
        a = self._doc()
        self.assertIn("NIEZNANA NAWIERZCHNIA", a)
        self.assertIn("piach", a.lower())

    def test_document_has_zones(self):
        a = self._doc()
        for z in ("Z2", "Z3", "Z4"):
            self.assertIn(z, a)
        self.assertRegexpMatches(a, r"\d+–\d+ W") if hasattr(self, "assertRegexpMatches") else self.assertRegex(a, r"\d+–\d+ W")

    def test_section_c_instruction_caps_length(self):
        # C pisze Albert; narzedzie przekazuje limit dlugosci w prompt_C (context_for_section_c)
        ctx = self._doc()
        self.assertIn("Max 8", ctx)

    def test_a3_merged_surface_default(self):
        a = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})["analysis"]
        self.assertIn("zmiany nawierzchni", a)
        self.assertNotIn("(odcinki", a)

    def test_a3_full_surface_on_flag(self):
        a = rr._tool_route_report(
            {"route_id": "55798129", "variant": "pelny", "surface_detail": True}
        )["analysis"]
        self.assertIn("(odcinki", a)
        self.assertNotIn("zmiany nawierzchni", a)

    def test_gap_warning(self):
        a = self._doc()
        self.assertIn("⚠️ UWAGA: przerwa", a)


class TestRouteReportTask13(unittest.TestCase):
    """TASK 13 - Opcja B: narzedzie zwraca context_for_section_c; sekcje C pisze Albert."""

    def setUp(self):
        self.calls = []

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return CANNED[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4

    def tearDown(self):
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist

    def test_returns_context_for_section_c(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "pelny"})
        self.assertIn("context_for_section_c", out)
        ctx = out["context_for_section_c"]
        self.assertIsNotNone(ctx)
        for m in ("C1", "C2", "C3", "C4"):
            self.assertIn(m, ctx)

    def test_skrocony_no_context_c(self):
        out = rr._tool_route_report({"route_id": "55734589", "variant": "skrocony"})
        self.assertIn("context_for_section_c", out)
        self.assertIsNone(out["context_for_section_c"])

    def test_no_llm_in_tool(self):
        import inspect
        src = inspect.getsource(rr)
        self.assertNotIn("qgpt_text", src)
        self.assertFalse(hasattr(rr, "qgpt_text"))

if __name__ == "__main__":
    unittest.main()
