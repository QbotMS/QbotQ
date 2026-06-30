#!/usr/bin/env python3
"""TASK 08/09 - testy orkiestratora route_report (mock 6 narzedzi + LLM stub sekcji C)."""
import re
import unittest
from unittest.mock import patch

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

CANNED_POI_CACHE = {
    "status": "PARTIAL",
    "analysis_status": "PARTIAL",
    "supply_status": "PARTIAL",
    "technical_completeness": "PARTIAL",
    "cache_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
    "generated_at": "2026-06-29T13:08:00+02:00",
    "report_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.md",
    "report_json_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
    "summary": {"hard_resupply": 3, "soft_food_stop": 0, "water": 0, "attractions": 9, "town": 20},
    "buffers": {"avg_speed_kmh": 18.0},
    "hard_resupply": [
        {
            "category": "hard_resupply",
            "name": "Hard resupply 13013337435",
            "lat": 52.627947,
            "lon": 21.586398,
            "route_km": 0.0,
            "distance_to_track_m": 201.5,
            "source_tags": "shop=greengrocer",
            "opening_hours_osm": None,
            "open_at_arrival": True,
            "open_source": "google",
            "eta_iso": "2026-06-29T10:00:00",
        },
        {
            "category": "hard_resupply",
            "name": "abc",
            "lat": 52.627789,
            "lon": 21.5856,
            "route_km": 0.0,
            "distance_to_track_m": 252.0,
            "source_tags": "name=abc; shop=convenience",
            "opening_hours_osm": "Mo-Sa 06:00-21:00; Su 08:00-18:00",
            "open_at_arrival": True,
            "open_source": "osm",
            "eta_iso": "2026-06-29T10:00:00",
        },
        {
            "category": "hard_resupply",
            "name": "Hard resupply 1096084394",
            "lat": 52.637624,
            "lon": 21.683606,
            "route_km": 10.749,
            "distance_to_track_m": 25.9,
            "source_tags": "shop=convenience",
            "opening_hours_osm": "Mo-Fr 07:00-19:00; Sa 07:00-20:00; Su 10:00-17:00",
            "open_at_arrival": True,
            "open_source": "osm",
            "eta_iso": "2026-06-29T10:35:49.800000",
        },
    ],
    "soft_food_stop": [],
    "water": [],
    "attractions": [],
    "town_fallback_check": [
        {
            "category": "town",
            "name": "Rafa",
            "lat": 52.605771,
            "lon": 21.570603,
            "route_km": 1.108,
            "distance_to_track_m": 2801.9,
            "hard_resupply_found": True,
            "hard_resupply_names": "Hard resupply 13013337435, abc",
            "source_tags": "name=Rafa",
        }
    ],
    "missing_chunks_count": 2,
    "missing_chunks": [],
}

ACTIVE_ROUTE_VERSION = {
    "route_id": "55798129",
    "route_artifact_id": 306,
    "created_at": "2026-06-23T22:26:01+02:00",
    "updated_at": "2026-06-29T21:57:49+02:00",
    "sha256": "46c7797c584016ee2278add44652cf8232ee7a1e0e9ae3b84caf6190c060823e",
    "source_artifact_sha256": "46c7797c584016ee2278add44652cf8232ee7a1e0e9ae3b84caf6190c060823e",
    "distance_m": 71137.0,
    "distance_km": 71.137,
    "track_points": 1278,
    "elevation_gain_m": 519.8,
}

LEGACY_COMPATIBLE_ROUTE_VERSION = {
    **ACTIVE_ROUTE_VERSION,
    "route_version_key": None,
}

MISMATCH_LAND_COVER_PROFILE = {
    "id": 20,
    "route_artifact_id": 361,
    "route_id": "55798129",
    "enriched_at": "2026-06-29T12:34:56+02:00",
    "quality_status": "GOOD_INFERRED",
    "coverage_pct": 100.0,
    "tagged_surface_pct": 70.8,
    "inferred_surface_pct": 29.2,
    "unknown_surface_pct": 0.0,
    "sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "source_artifact_sha256": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    "distance_m": 64000.0,
    "distance_km": 64.0,
    "track_points": 900,
    "point_count": 900,
    "elevation_gain_m": 410.0,
    "surface_percentages_raw": {"asphalt": 28.0, "ground": 42.0},
    "surface_percentages_refined": {"asphalt": 28.0, "ground": 42.0},
    "surface_summary_json": {
        "quality_status": "GOOD_INFERRED",
        "coverage_pct": 100.0,
        "tagged_surface_pct": 70.8,
        "inferred_surface_pct": 29.2,
        "unknown_surface_pct": 0.0,
        "route_version_key": None,
    },
    "good_profile": True,
}

rr._fetch_route_version_record = lambda **kwargs: ACTIVE_ROUTE_VERSION

MISMATCH_ROUTE_VERSION = {
    "route_id": "55798129",
    "route_artifact_id": 999,
    "created_at": "2026-06-20T22:26:01+02:00",
    "updated_at": "2026-06-27T21:57:49+02:00",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "source_artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "distance_m": 68000.0,
    "distance_km": 68.0,
    "track_points": 1200,
    "elevation_gain_m": 450.0,
}

VERSIONED_POI_CACHE = {
    **CANNED_POI_CACHE,
    "route_id": "55798129",
    "route_artifact_id": 306,
    "created_at": "2026-06-23T22:26:01+02:00",
    "updated_at": "2026-06-29T21:57:49+02:00",
    "sha256": "46c7797c584016ee2278add44652cf8232ee7a1e0e9ae3b84caf6190c060823e",
    "source_artifact_sha256": "46c7797c584016ee2278add44652cf8232ee7a1e0e9ae3b84caf6190c060823e",
    "distance_m": 71137.0,
    "distance_km": 71.137,
    "track_points": 1278,
    "elevation_gain_m": 519.8,
}

CANONICAL_ROUTE_SOURCE = {
    "route_id": "55798129",
    "route_base_id": 1,
    "route_version_key": "7b11b5b73397923df2a433a285a97d5121b3f0d5e2af824541f742ba0a1d90fe",
    "route_artifact_id": 306,
    "read_path": "canonical",
    "fallback_reason": None,
    "layer_counts": {
        "route_base": 1,
        "route_axis_segments": 1423,
        "route_surface_layer": 76,
        "route_landcover_layer": 890,
        "route_poi_layer": 38,
        "route_shade_layer": 1423,
        "route_elevation_samples": 1424,
        "route_climb_events": 1,
    },
    "route_shade_layer_count": 1423,
    "shade_coverage_pct": 100.0,
    "land_cover_preferred_source": "worldcover_shade",
    "route_elevation_samples": 1424,
    "route_climb_events": 1,
}

LEGACY_ROUTE_SOURCE = {
    "route_id": "55798129",
    "route_base_id": 1,
    "route_version_key": "7b11b5b73397923df2a433a285a97d5121b3f0d5e2af824541f742ba0a1d90fe",
    "route_artifact_id": 306,
    "read_path": "legacy_fallback",
    "fallback_reason": "route_base_missing",
    "layer_counts": {
        "route_base": 0,
        "route_axis_segments": 0,
        "route_surface_layer": 0,
        "route_landcover_layer": 0,
        "route_poi_layer": 0,
        "route_shade_layer": 0,
        "route_elevation_samples": 0,
        "route_climb_events": 0,
    },
    "route_shade_layer_count": 0,
    "shade_coverage_pct": 0.0,
    "land_cover_preferred_source": "osm_landcover_legacy",
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
        import qbot_route_tools as rt
        self._orig_fetch_surface = rt._fetch_best_route_surface_profile
        self._orig_poi_cache = rr._read_poi_analysis_cache
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4
        rt._fetch_best_route_surface_profile = lambda **kwargs: None
        rr._read_poi_analysis_cache = lambda route_id: CANNED_POI_CACHE

    def tearDown(self):
        import qbot_route_tools as rt
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rt._fetch_best_route_surface_profile = self._orig_fetch_surface
        rr._read_poi_analysis_cache = self._orig_poi_cache

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
        # POI idzie z cache i nie odpala ciężkiego refreshu
        self.assertNotIn("route_poi_analyze_readonly", self._names())
        self.assertIn("POI", a)
        # wszystkie wymagane narzedzia obliczeniowe uzyte
        self.assertEqual(set(self._names()), {
            "route_plan_analysis", "route_profile_detail", "route_time_estimate",
            "tire_pressure", "route_fuel_plan",
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
        self.assertNotIn("route_poi_analyze_readonly", names)

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
        self._orig_poi_cache = rr._read_poi_analysis_cache
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4
        rr._read_poi_analysis_cache = lambda route_id: CANNED_POI_CACHE

    def tearDown(self):
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rr._read_poi_analysis_cache = self._orig_poi_cache

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

    def tearDown(self):
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist

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
        import qbot_route_tools as rt
        self._orig_fetch_surface = rt._fetch_best_route_surface_profile
        self._orig_poi_cache = rr._read_poi_analysis_cache
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 80.0
        rt._fetch_best_route_surface_profile = lambda **kwargs: None
        rr._read_poi_analysis_cache = lambda route_id: CANNED_POI_CACHE

    def tearDown(self):
        import qbot_route_tools as rt
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rt._fetch_best_route_surface_profile = self._orig_fetch_surface
        rr._read_poi_analysis_cache = self._orig_poi_cache

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
        self.assertGreaterEqual(block.count("km "), 3)
        self.assertRegex(block, r"km\s*\d+(?:\.\d+)?")

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
        self.assertIn("z ramek 80 m", a)
        self.assertNotIn("zmiany nawierzchni", a)

    def test_gap_warning(self):
        a = self._doc()
        self.assertIn("PUNKTY UZUPELNIENIA", a)
        self.assertIn("km 20–23", a)


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

class TestRouteReportTask16(unittest.TestCase):
    """TASK 16 — dane zasilajace wzorce: wiatr m/s, POI z km, spojnosc podjazdow, kompletnosc nawierzchni."""

    def setUp(self):
        self.calls = []
        self.canned = {
            "route_plan_analysis": {"status": "OK", "data": {"analysis": (
                "ANALIZA PLANOWANEJ TRASY\n"
                "Dystans: 71.1 km | podjazdy: +800 m / zjazdy: -800 m\n"
                "Stromizny: maks 7%, stromo(>=3.0%) ~2.5 km\n"
                "Nawierzchnia: 60% utwardzona | asfalt 60%, szuter 30%\n"
                "\n"
                "🌤  Pogoda (prognoza): 22-28°C, opady ~0.0 mm na trasie\n"
                "   \U0001f4a8 Pod wiatr (oszczedzaj sie wczesniej): km 40–50 (~6.1 m/s / 22 km/h)\n"
                "   Sila wiatru: sr. 5.0 m/s (18 km/h), maks. 8.9 m/s (32 km/h)\n"
                "\n"
                "\U0001f4aa Forma (FitModel, 2026-06-24): FTP 257 W, 2.55 W/kg"
            )}},
            "route_profile_detail": {"status": "OK", "data": {"analysis": (
                "SZCZEGOLOWY PROFIL TRASY (z ramek 80 m)\n"
                "Dystans 71.1 km | 889 ramek | +800 m / -800 m | max 7% | stromo(>=3.0%) ~2.5 km\n"
                "\n"
                "Nawierzchnia (odcinki >= 0.2 km):\n"
                "  km 0.0-20.0 (20.0): asfalt\n"
                "  km 20.0-30.0 (10.0): szuter luzny\n"
                "  km 30.0-63.3 (33.3): asfalt\n"
                "\n"
                "Podjazdy (>= 3.0%, min 200 m):\n"
                "  km 25.0-27.5 (2.5 km): +180 m, max 7%\n"
            )}},
            "route_time_estimate": {"status": "OK", "data": {"analysis":
                "Szacowany czas trasy\nv 18.0 km/h -> 4:00"}},
            "tire_pressure": {"status": "OK", "data": {"analysis":
                "CISNIENIE OPON\n#1 2.0 bar / 2.2 bar"}},
            "route_fuel_plan": {"status": "OK", "data": {"analysis":
                "- **65 g/h**\n- **0.90 L/h**"}},
            "route_poi_analyze_readonly": {"status": "OK", "data": {
                "analysis": "POI: km 5.0 woda; km 45.0 sklep",
                "counts": {"water": 1, "food": 1, "attractions": 0},
                "report_path": "/opt/qbot/artifacts/poi.md"}},
        }

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return self.canned[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        import qbot_route_tools as rt
        self._orig_fetch_surface = rt._fetch_best_route_surface_profile
        self._orig_poi_cache = rr._read_poi_analysis_cache
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 71.1
        rt._fetch_best_route_surface_profile = lambda **kwargs: None
        rr._read_poi_analysis_cache = lambda route_id: CANNED_POI_CACHE

    def tearDown(self):
        import qbot_route_tools as rt
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rt._fetch_best_route_surface_profile = self._orig_fetch_surface
        rr._read_poi_analysis_cache = self._orig_poi_cache

    def _ctx(self, route_id="55798129"):
        return rr._tool_route_report(
            {"route_id": route_id, "variant": "pelny"}
        )["context_for_section_c"]

    def test_wind_ms_in_context(self):
        """16.d: plan zawiera m/s jako jednostke bazowa, km/h tylko pomocniczo."""
        ctx = self._ctx()
        self.assertIn("POGODA", ctx)
        self.assertIn("m/s", ctx)
        self.assertIn("(18 km/h)", ctx)
        self.assertIn("km 40–50 (~6.1 m/s / 22 km/h)", ctx)
        self.assertNotIn("Sila wiatru: sr. 18 km/h, maks 32 km/h", ctx)
        self.assertNotIn("brak w analizie planu", ctx)

    def test_poi_km_in_context(self):
        """16.f: POI z km 5.0 i 21.0 -> lista + ostrzezenie o luce >20 km."""
        ctx = self._ctx()
        self.assertIn("PUNKTY UZUPELNIENIA", ctx)
        self.assertGreaterEqual(ctx.count("km "), 8)
        self.assertIn("km 0", ctx)
        self.assertIn("km 71", ctx)
        # brak starego komunikatu o luce 40 km
        self.assertNotIn("przerwa 40 km", ctx)

    def test_climb_consistency(self):
        """16.a-fix: build() i build_detail() uzywaja climb_grade=5.0;
        oba raportuja '>=5%'; profil zawiera 'Falistosc' dla odcinkow 3-5%."""
        import io
        from unittest.mock import patch, MagicMock
        from tools.rwgps.route_brief import build, build_detail

        # Ramki build(): (idx, d0_m, d1_m, gain_m, grade_pct, surface, temp, precip, wind_comp, wind_ms)
        def _br():
            r = []
            for i in range(25):   # km 0-2: 2% (plasko)
                r.append((i, i*80, i*80+80, 1.6, 2.0, "asfalt", None, None, None, None))
            for i in range(25):   # km 2-4: 4% (faldy 3-5%)
                r.append((25+i, 2000+i*80, 2000+i*80+80, 3.2, 4.0, "asfalt", None, None, None, None))
            for i in range(7):    # km 4.0-4.56: 6% (podjazd >5%, 560m > climb_min_m=200m)
                r.append((50+i, 4000+i*80, 4000+i*80+80, 4.8, 6.0, "asfalt", None, None, None, None))
            for i in range(55):   # km 4.56-8.96: 1% (plasko)
                r.append((57+i, 4560+i*80, 4560+i*80+80, 0.8, 1.0, "asfalt", None, None, None, None))
            return r

        # Ramki build_detail(): (idx, d0_m, d1_m, ele0, ele1, gain_m, grade_pct, surface)
        def _dr():
            r = []
            for i in range(25):
                r.append((i, i*80, i*80+80, 100.0, 101.6, 1.6, 2.0, "asfalt"))
            for i in range(25):
                r.append((25+i, 2000+i*80, 2000+i*80+80, 100.0, 103.2, 3.2, 4.0, "asfalt"))
            for i in range(7):
                r.append((50+i, 4000+i*80, 4000+i*80+80, 100.0, 104.8, 4.8, 6.0, "asfalt"))
            for i in range(55):
                r.append((57+i, 4560+i*80, 4560+i*80+80, 100.0, 100.8, 0.8, 1.0, "asfalt"))
            return r

        # --- build() ---
        mc = MagicMock()
        mc.cursor.return_value.fetchall.return_value = _br()
        mc.cursor.return_value.fetchone.return_value = None
        with patch("tools.rwgps.route_brief._db_connect", return_value=mc):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                build(route_id="test_r")
        out_b = buf.getvalue()

        # --- build_detail() ---
        mc2 = MagicMock()
        mc2.cursor.return_value.fetchall.return_value = _dr()
        with patch("tools.rwgps.route_brief._db_connect", return_value=mc2):
            with patch("tools.rwgps.route_brief._infer_unknown_frame_surfaces", return_value={}):
                buf2 = io.StringIO()
                with patch("sys.stdout", buf2):
                    build_detail(route_id="test_r")
        out_d = buf2.getvalue()

        # oba progi >=5%
        self.assertIn(">=5%", out_b, "build() brak '>=5%%': " + out_b[:300])
        self.assertIn(">=5%", out_d, "build_detail() brak '>=5%%': " + out_d[:300])
        # brak starego progu 4%
        self.assertNotIn(">=4%", out_b, "build() ma stary prog >=4%")
        self.assertNotIn(">=4%", out_d, "build_detail() ma stary prog >=4%")
        # profil zawiera linie Falistosc (sa odcinki 3-5%)
        self.assertIn("Falistosc", out_d, "build_detail() brak Falistosc: " + out_d[:300])

    def test_surface_table_completeness(self):
        """16.b: ostatni odcinek km 63.3, dystans 71.1 -> UWAGA o brakujacej nawierzchni."""
        ctx = self._ctx()
        self.assertIn("UWAGA: brak danych nawierzchni", ctx)
        # musi podac zakres brakujacych danych
        self.assertRegex(ctx, r"63[,.]3.*71[,.]1|km\s+63")


class TestRouteReportTask17(unittest.TestCase):
    """TASK 17 - bloki, fazy, tabela ryzyk."""

    def test_detect_climb_block(self):
        """Segment >=5%/>=200m daje blok z faktorem 'podjazd'."""
        climbs = [(10.0, 12.0, 8.0)]
        blocks = rr._detect_blocks([], climbs, [], 50.0)
        all_factors = [f for b in blocks for f in b["factors"]]
        self.assertIn("podjazd", all_factors)

    def test_detect_overlap_merge(self):
        """Climb + wind na tym samym km -> ONE blok z oboma faktorami."""
        climbs = [(10.0, 14.0, 7.0)]
        wind = [(12.0, 18.0, 25.0)]
        blocks = rr._detect_blocks([], climbs, wind, 50.0)
        overlap = [b for b in blocks
                   if "podjazd" in b["factors"] and "pod wiatr" in b["factors"]]
        self.assertEqual(len(overlap), 1, f"Oczekiwano 1 scalony blok, mamy: {blocks}")

    def test_phase_has_watts(self):
        """Faza wspinaczki zawiera watty z FTP (format liczba-liczba W)."""
        blocks = [{"km_start": 10.0, "km_end": 14.0,
                   "factors": ["podjazd"],
                   "detail": {"podjazd": "max 8%, 2000 m"}}]
        plan = rr._build_phase_plan(blocks, 250, 50.0)
        self.assertRegex(plan, r"\d+[^\d]\d+ W")

    def test_risk_table_levels(self):
        """>=2 faktory -> 'wysokie'; sam 'start' -> brak 'wysokie'."""
        bloks_hi = [{"km_start": 5.0, "km_end": 10.0,
                     "factors": ["podjazd", "pod wiatr"],
                     "detail": {"podjazd": "8%", "pod wiatr": "~6.9 m/s / 25 km/h"}}]
        table_hi = rr._build_risk_table(bloks_hi)
        self.assertIn("wysokie", table_hi)

        bloks_skip = [{"km_start": 0.0, "km_end": 6.0,
                       "factors": ["start"],
                       "detail": {"start": "km 0-6: rozgrzewka"}}]
        table_skip = rr._build_risk_table(bloks_skip)
        self.assertNotIn("wysokie", table_skip)

    def test_parse_wind_blocks_supports_ms(self):
        """Parse nowego formatu wind -> m/s jako jednostka bazowa, km/h tylko pomocniczo."""
        plan = (
            "🌤  Pogoda (prognoza): 22–28°C, opady ~0.0 mm na trasie\n"
            "   💨 Pod wiatr (oszczedzaj sie wczesniej): km 40–50 (~6.1 m/s / 22 km/h); km 55–59 (~5.0 m/s / 18 km/h)\n"
            "   🍃 Wiatr w plecy: km 10–14 (~3.3 m/s / 12 km/h)\n"
            "   Sila wiatru: sr. 5.0 m/s (18 km/h), maks. 8.9 m/s (32 km/h)\n"
        )
        wind_blocks = rr._parse_wind_blocks_with_kmh(plan)
        self.assertEqual(wind_blocks, [(40.0, 50.0, 6.1, 22.0), (55.0, 59.0, 6.1, 22.0)])
        blocks = rr._detect_blocks([], [], wind_blocks, 80.0)
        phase = rr._build_phase_plan(blocks, 250, 80.0)
        self.assertIn("m/s", phase)
        self.assertIn("km/h", phase)
        self.assertIn("POD WIATR", phase)

    def test_endcap_phase(self):
        """Ostatnie 10% trasy zawsze daje osobny blok 'koncowka'."""
        blocks = rr._detect_blocks([], [], [], 80.0)
        endcap = [b for b in blocks if "koncowka" in b["factors"]]
        self.assertEqual(len(endcap), 1)
        self.assertAlmostEqual(endcap[0]["km_start"], 72.0, delta=1.0)

    def test_rolling_phase_falista(self):
        """has_wavy=True: faza toczna ma tag 'falista'; bez podjazdu brak 'PODJAZD'."""
        blocks = rr._detect_blocks([], [], [], 30.0)
        plan = rr._build_phase_plan(blocks, 250, 30.0, has_wavy=True)
        self.assertIn("falista", plan)
        self.assertNotIn("PODJAZD", plan)

    def test_no_duplicate_headers(self):
        """Bug 1: naglowki PLAN JAZDY i TABELA RYZYK maja wystapic dokladnie raz w ctx."""
        plan_fake = {"status": "OK", "data": {"analysis": (
            "ANALIZA PLANOWANEJ TRASY\n"
            "Dystans: 50.0 km | podjazdy: +500 m\n"
            "Nawierzchnia: 100% utwardzona\n"
            "Pogoda: 20 C, wiatr w plecy\n"
            "\U0001f4aa Forma (FitModel): FTP 250 W, 3.20 W/kg"
        )}}
        prof_fake = {"status": "OK", "data": {"analysis": (
            "PROFIL ODCINKAMI\n"
            "Nawierzchnia (odcinki scalone):\n"
            "  km 0.0-50.0 (50.0): asfalt\n"
            "Podjazdy (>=5%, min 200 m):\n"
            "  km 10.0 - 12.0 (2.0 km) max 8%\n"
            "\n"
        )}}
        t_fake = {"status": "OK", "data": {"analysis": "Szacowany czas\nv 18.0 km/h -> 2:45"}}
        poi_fake = {"status": "OK", "data": {"counts": {}}}
        ctx = rr._build_context_document(
            plan_fake, prof_fake, t_fake, None, None, poi_fake, None, None
        )
        self.assertEqual(ctx.count("### PLAN JAZDY PO FAZACH"), 1,
                         f"Naglowek PLAN JAZDY PO FAZACH zdublowany lub brak:\n{ctx[-800:]}")
        self.assertEqual(ctx.count("### TABELA RYZYK"), 1,
                         f"Naglowek TABELA RYZYK zdublowany lub brak:\n{ctx[-800:]}")

    def test_has_wavy_logic(self):
        """Bug 2: 'Falistosc: brak odcinkow' -> has_wavy False; prawdziwe faldy -> True."""
        # profil z prawdziwymi faldami
        prof_wavy = "PROFIL\nFalistosc: 3 odcinki 3-5% (~2 km lacznie)\n"
        wavy = "Falistosc:" in prof_wavy and "brak odcinkow" not in prof_wavy
        self.assertTrue(wavy, "Profil z falami powinien dawac has_wavy=True")

        # profil plasy (linia istnieje, ale mowi 'brak odcinkow')
        prof_flat = "PROFIL\nFalistosc: brak odcinkow 3-5%\n"
        flat = "Falistosc:" in prof_flat and "brak odcinkow" not in prof_flat
        self.assertFalse(flat, "Profil plaski ('brak odcinkow') powinien dawac has_wavy=False")

        # end-to-end: has_wavy=False -> plan nie zawiera 'falista'
        blocks = rr._detect_blocks([], [], [], 30.0)
        plan = rr._build_phase_plan(blocks, 250, 30.0, has_wavy=flat)
        self.assertNotIn("falista", plan)


class TestRouteReportSurfaceSummaryRegression(unittest.TestCase):
    """Regresja: full route_report bierze surface_summary_json i nie blokuje się na POI refresh."""

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

    def _names(self):
        return [n for n, _ in self.calls]

    def test_full_report_uses_surface_summary_json_and_skips_heavy_poi_refresh(self):
        synthetic_profile = {
            "id": 19,
            "route_artifact_id": 306,
            "route_id": "55798129",
            "enriched_at": "2026-06-29T12:34:56+02:00",
            "quality_status": "GOOD_INFERRED",
            "coverage_pct": 100.0,
            "tagged_surface_pct": 70.8,
            "inferred_surface_pct": 29.2,
            "unknown_surface_pct": 0.0,
            "surface_percentages_raw": {
                "asphalt": 34.9,
                "ground": 32.7,
                "gravel_fine": 10.4,
                "gravel": 7.7,
                "grass": 7.3,
                "unknown": 0.0,
            },
            "surface_percentages_refined": {
                "asphalt": 34.9,
                "ground": 32.7,
                "gravel_fine": 10.4,
                "gravel": 7.7,
                "grass": 7.3,
                "unknown": 0.0,
            },
            "surface_summary_json": {
                "quality_status": "GOOD_INFERRED",
                "coverage_pct": 100.0,
                "tagged_surface_pct": 70.8,
                "inferred_surface_pct": 29.2,
                "unknown_surface_pct": 0.0,
                "geology_context": {
                    "provider": "heuristic_region_v1",
                    "status": "OK",
                    "confidence": "medium",
                    "dominant_region": "mazowsze_sandy_lowland",
                    "dominant_unit": "Mazowsze / niziny piaszczyste",
                    "material_hint": "sand_loose_ground_possible",
                    "risk_flags": [],
                    "warnings": [],
                    "explanation": "Kontekst geologiczny sugeruje większe ryzyko piachu na odcinkach inferred.",
                },
                "problem_segments": {
                    "top_unknown": [],
                    "top_inferred": [],
                },
            },
            "good_profile": True,
        }

        with patch("qbot_route_tools._fetch_best_route_surface_profile", return_value=synthetic_profile), \
                patch.object(rr, "_read_poi_analysis_cache", return_value=None):
            out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})

        analysis = out["analysis"]
        self.assertIn("surface_summary_json", analysis)
        self.assertIn("GOOD_INFERRED", analysis)
        self.assertRegex(analysis, r"unknown\s+0[,.]0%|Unknown:\s*0[,.]0%")
        self.assertIn("Geologia / podłoże", analysis)
        self.assertIn("provider=heuristic_region_v1", analysis)
        self.assertNotIn("nieznana 33%", analysis)
        self.assertNotIn("utwardzona 33%", analysis)
        self.assertIn("Status zaopatrzenia: UNAVAILABLE", analysis)
        self.assertIn("Kompletność techniczna POI: UNAVAILABLE", analysis)
        self.assertNotIn("route_poi_analyze_readonly", self._names())


class TestRouteReportCanonicalReadPath(unittest.TestCase):
    """Regresja: route_report pokazuje canonical read-path bez ruszania sekcji A/B."""

    def setUp(self):
        self.calls = []

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return CANNED[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        self._orig_poi_cache = rr._read_poi_analysis_cache
        self._orig_version_record = rr._fetch_route_version_record
        self._orig_fetch_surface = None
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 99.4
        rr._read_poi_analysis_cache = lambda route_id: CANNED_POI_CACHE
        rr._fetch_route_version_record = lambda **kwargs: ACTIVE_ROUTE_VERSION
        import qbot_route_tools as rt
        self._rt = rt
        self._orig_fetch_surface = rt._fetch_best_route_surface_profile
        rt._fetch_best_route_surface_profile = lambda **kwargs: None

    def tearDown(self):
        import qbot_route_tools as rt
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rr._read_poi_analysis_cache = self._orig_poi_cache
        rr._fetch_route_version_record = self._orig_version_record
        rt._fetch_best_route_surface_profile = self._orig_fetch_surface

    def test_canonical_marker_and_landscape_source_are_rendered(self):
        with patch.object(rr, "read_canonical_route", return_value=CANONICAL_ROUTE_SOURCE):
            out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        analysis = out["analysis"]
        self.assertEqual(out["route_source"]["read_path"], "canonical")
        self.assertEqual(out["route_source"]["land_cover_preferred_source"], "worldcover_shade")
        self.assertEqual(out["route_source"]["route_shade_layer_count"], 1423)
        self.assertIn("## A0 - ŹRÓDŁO DANYCH TRASY", analysis)
        self.assertIn("źródło danych trasy: canonical", analysis)
        self.assertIn("landscape_source: worldcover_shade", analysis)
        self.assertIn("route_shade_layer_count=1423", analysis)
        self.assertIn("shade_coverage_pct=100.0%", analysis)
        self.assertIn("## A0B - OTOCZENIE TRASY (WorldCover / route_shade_layer)", analysis)
        self.assertIn("WorldCover v200", analysis)
        self.assertIn("otoczenie trasy", analysis)
        self.assertIn("lewo / środek / prawo", analysis)
        self.assertIn("## A0C - PROFIL WYSOKOŚCI / PODJAZDY (canonical route_elevation_samples / route_climb_events)", analysis)
        self.assertIn("route_elevation_samples", analysis)
        self.assertIn("route_climb_events", analysis)
        self.assertIn("profil wysokości", analysis)

    def test_legacy_fallback_still_renders_when_canonical_missing(self):
        with patch.object(rr, "read_canonical_route", return_value=LEGACY_ROUTE_SOURCE):
            out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        analysis = out["analysis"]
        self.assertEqual(out["route_source"]["read_path"], "legacy_fallback")
        self.assertEqual(out["route_source"]["fallback_reason"], "route_base_missing")
        self.assertIn("źródło danych trasy: legacy_fallback", analysis)
        self.assertIn("fallback_reason: route_base_missing", analysis)
        self.assertIn("landscape_source: osm_landcover_legacy", analysis)
        self.assertNotIn("## A0B - OTOCZENIE TRASY (WorldCover / route_shade_layer)", analysis)
        self.assertNotIn("## A0C - PROFIL WYSOKOŚCI / PODJAZDY (canonical route_elevation_samples / route_climb_events)", analysis)
        self.assertIn("## A - DANE TRASY", analysis)

    def test_a0_marker_still_present(self):
        with patch.object(rr, "read_canonical_route", return_value=CANONICAL_ROUTE_SOURCE):
            out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        self.assertIn("## A0 - ŹRÓDŁO DANYCH TRASY", out["analysis"])
        self.assertIn("źródło danych trasy: canonical", out["analysis"])
        self.assertIn("## A0B - OTOCZENIE TRASY (WorldCover / route_shade_layer)", out["analysis"])
        self.assertIn("## A0C - PROFIL WYSOKOŚCI / PODJAZDY (canonical route_elevation_samples / route_climb_events)", out["analysis"])


class TestRouteReportPoiSupplyRegression(unittest.TestCase):
    """Regresja POI: cache z listą punktów ma dać status, km_on_route, opening-hours i klastry."""

    def setUp(self):
        self.calls = []

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return CANNED[name]

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        self._orig_poi_cache = rr._read_poi_analysis_cache
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 71.1

        self.poi_cache = {
            "status": "PARTIAL",
            "analysis_status": "PARTIAL",
            "supply_status": "PARTIAL",
            "technical_completeness": "PARTIAL",
            "cache_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_mock.json",
            "generated_at": "2026-06-29T13:08:00+02:00",
            "report_json_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_mock.json",
            "report_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_mock.md",
            "summary": {"hard_resupply": 3, "soft_food_stop": 0, "water": 0, "attractions": 0, "town": 0},
            "buffers": {"avg_speed_kmh": 18.0},
            "hard_resupply": [
                {
                    "category": "hard_resupply",
                    "name": "Żabka",
                    "lat": 52.7000,
                    "lon": 21.7000,
                    "route_km": 10.0,
                    "distance_to_track_m": 120.0,
                    "source_tags": "name=Zabka; shop=convenience",
                    "opening_hours_osm": "Mo-Su 06:00-23:00",
                    "open_at_arrival": True,
                    "open_source": "osm",
                    "eta_iso": "2026-06-29T10:33:20+02:00",
                },
                {
                    "category": "hard_resupply",
                    "name": "Sklep ABC",
                    "lat": 52.7005,
                    "lon": 21.7005,
                    "route_km": 10.2,
                    "distance_to_track_m": 180.0,
                    "source_tags": "name=ABC; shop=convenience",
                    "opening_hours_osm": None,
                    "open_at_arrival": None,
                    "open_source": "unknown",
                    "eta_iso": "2026-06-29T10:36:00+02:00",
                },
                {
                    "category": "hard_resupply",
                    "name": "Biedronka",
                    "lat": 52.7010,
                    "lon": 21.7010,
                    "route_km": 10.8,
                    "distance_to_track_m": 90.0,
                    "source_tags": "name=Biedronka; shop=supermarket",
                    "opening_hours_osm": "Mo-Fr 07:00-21:00; Sa 08:00-20:00; Su 09:00-18:00",
                    "open_at_arrival": False,
                    "open_source": "osm",
                    "eta_iso": "2026-06-29T10:39:00+02:00",
                },
            ],
            "soft_food_stop": [],
            "water": [],
            "attractions": [],
            "town_fallback_check": [],
            "missing_chunks_count": 1,
        }

        rr._read_poi_analysis_cache = lambda route_id: self.poi_cache

    def tearDown(self):
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rr._read_poi_analysis_cache = self._orig_poi_cache

    def test_poi_section_has_status_km_hours_and_clustering(self):
        out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny", "start": "2026-06-29 10:00"})
        analysis = out["analysis"]
        self.assertIn("Status zaopatrzenia:", analysis)
        self.assertIn("Kompletność techniczna POI: PARTIAL", analysis)
        self.assertIn("km 10.0", analysis)
        self.assertIn("distance_from_route_m=", analysis)
        self.assertIn("OPEN_AT_ETA", analysis)
        self.assertIn("UNKNOWN_HOURS", analysis)
        self.assertIn("CLOSED_AT_ETA", analysis)
        self.assertIn("Najważniejsze klastry zaopatrzenia", analysis)
        self.assertIn("+1 innych punktów w pobliżu", analysis)
        self.assertIn("Publiczne drinking_water: 0 (bonus", analysis)
        self.assertIn("Braki techniczne providerów: missing_chunks=1", analysis)
        self.assertNotIn("route_poi_analyze_readonly", [n for n, _ in self.calls])

    def test_poi_section_filters_far_points_and_uses_strategic_fallback(self):
        poi_cache = {
            "status": "PARTIAL",
            "analysis_status": "PARTIAL",
            "supply_status": "PARTIAL",
            "technical_completeness": "PARTIAL",
            "cache_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
            "generated_at": "2026-06-29T14:22:09+02:00",
            "report_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.md",
            "report_json_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
            "summary": {"hard_resupply": 4, "soft_food_stop": 0, "water": 0, "attractions": 0, "town": 0},
            "buffers": {"avg_speed_kmh": 18.0},
            "hard_resupply": [
                {
                    "category": "hard_resupply",
                    "name": "Sklep 25 m",
                    "lat": 52.6001,
                    "lon": 21.6001,
                    "route_km": 10.0,
                    "distance_to_track_m": 25.0,
                    "source_tags": "name=Sklep 25 m; shop=convenience",
                    "opening_hours_osm": "Mo-Su 06:00-23:00",
                    "open_at_arrival": True,
                    "open_source": "google",
                    "eta_iso": "2026-06-29T17:20:00+02:00",
                },
                {
                    "category": "hard_resupply",
                    "name": "Sklep 372 m",
                    "lat": 52.6101,
                    "lon": 21.6101,
                    "route_km": 11.0,
                    "distance_to_track_m": 372.0,
                    "source_tags": "name=Sklep 372 m; shop=supermarket",
                    "opening_hours_osm": "Mo-Su 06:00-23:00",
                    "open_at_arrival": True,
                    "open_source": "google",
                    "eta_iso": "2026-06-29T17:25:00+02:00",
                },
                {
                    "category": "hard_resupply",
                    "name": "Fallback 952 m",
                    "lat": 52.7201,
                    "lon": 21.7201,
                    "route_km": 25.2,
                    "distance_to_track_m": 952.0,
                    "source_tags": "name=Fallback 952 m; shop=convenience",
                    "opening_hours_osm": "Mo-Su 06:00-23:00",
                    "open_at_arrival": True,
                    "open_source": "google",
                    "eta_iso": "2026-06-29T19:20:00+02:00",
                },
                {
                    "category": "hard_resupply",
                    "name": "Zbyt daleko 1508 m",
                    "lat": 52.8201,
                    "lon": 21.8201,
                    "route_km": 75.4,
                    "distance_to_track_m": 1508.0,
                    "source_tags": "name=Zbyt daleko 1508 m; shop=convenience",
                    "opening_hours_osm": "Mo-Su 06:00-23:00",
                    "open_at_arrival": True,
                    "open_source": "google",
                    "eta_iso": "2026-06-29T22:20:00+02:00",
                },
            ],
            "soft_food_stop": [],
            "water": [],
            "attractions": [],
            "town_fallback_check": [],
            "missing_chunks_count": 0,
        }

        analysis = "\n".join(
            rr._render_poi_supply_section(
                poi_cache,
                ride_start="2026-06-29T17:00:00+02:00",
                route_distance_km=99.4,
            )
        )

        self.assertIn("Najważniejsze klastry zaopatrzenia blisko trasy", analysis)
        self.assertIn("Sklep 25 m", analysis)
        self.assertIn("Sklep 372 m", analysis)
        self.assertIn("Awaryjne punkty strategiczne do 1 km", analysis)
        self.assertIn("AWARYJNY_FALLBACK_1KM", analysis)
        self.assertIn("Fallback 952 m", analysis)
        self.assertNotIn("Zbyt daleko 1508 m", analysis)
        self.assertNotIn("distance_from_route_m=1508 m", analysis)
        self.assertNotIn("distance_from_route_m=952 m | opening_hours", analysis.split("Najważniejsze klastry zaopatrzenia blisko trasy")[-1].split("Awaryjne punkty strategiczne do 1 km")[0])

    def test_poi_eta_is_recomputed_per_report_start(self):
        poi_cache = {
            "status": "OK",
            "analysis_status": "OK",
            "supply_status": "OK",
            "technical_completeness": "COMPLETE",
            "cache_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
            "generated_at": "2026-06-29T14:22:09+02:00",
            "report_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.md",
            "report_json_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
            "summary": {"hard_resupply": 1, "soft_food_stop": 0, "water": 0, "attractions": 0, "town": 0},
            "buffers": {"avg_speed_kmh": 20.0},
            "hard_resupply": [
                {
                    "category": "hard_resupply",
                    "name": "Sklep ETA",
                    "lat": 52.6001,
                    "lon": 21.6001,
                    "route_km": 10.0,
                    "distance_to_track_m": 35.0,
                    "source_tags": "name=Sklep ETA; shop=convenience",
                    "opening_hours_osm": "Mo-Su 06:00-16:30",
                    "open_at_arrival": False,
                    "open_source": "google",
                    "eta_iso": "2026-06-29T17:30:00+02:00",
                }
            ],
            "soft_food_stop": [],
            "water": [],
            "attractions": [],
            "town_fallback_check": [],
            "missing_chunks_count": 0,
        }

        a10 = "\n".join(rr._render_poi_supply_section(poi_cache, ride_start="2026-06-29T10:00:00+02:00", route_distance_km=71.1))
        a17 = "\n".join(rr._render_poi_supply_section(poi_cache, ride_start="2026-06-29T17:00:00+02:00", route_distance_km=71.1))

        self.assertIn("eta_at_poi=2026-06-29 10:30:00+02:00", a10)
        self.assertIn("status_hours=OPEN_AT_ETA", a10)
        self.assertIn("eta_at_poi=2026-06-29 17:30:00+02:00", a17)
        self.assertIn("status_hours=CLOSED_AT_ETA", a17)
        self.assertNotIn("eta_at_poi=2026-06-29 17:30:00+02:00", a10)
        self.assertNotIn("eta_at_poi=2026-06-29 10:30:00+02:00", a17)

    def test_poi_section_uses_polish_hours_for_status_and_counts(self):
        poi_cache = {
            "status": "OK",
            "analysis_status": "OK",
            "supply_status": "OK",
            "technical_completeness": "COMPLETE",
            "cache_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
            "generated_at": "2026-06-29T13:08:00+02:00",
            "report_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.md",
            "report_json_path": "/opt/qbot/artifacts/reports/poi_analysis_55798129_00_71.json",
            "summary": {"hard_resupply": 6, "soft_food_stop": 0, "water": 0, "attractions": 0, "town": 0},
            "buffers": {"avg_speed_kmh": 18.0},
            "hard_resupply": [
                {
                    "category": "hard_resupply",
                    "name": "Topaz Express",
                    "route_km": 0.0,
                    "distance_to_track_m": 40.0,
                    "source_tags": "name=Topaz Express; shop=convenience",
                    "opening_hours_osm": "wtorek 5:30–18:00",
                    "open_at_arrival": None,
                    "open_source": "unknown",
                },
                {
                    "category": "hard_resupply",
                    "name": "Wawie sp.j. Piekarnia",
                    "route_km": 0.1,
                    "distance_to_track_m": 45.0,
                    "source_tags": "name=Wawie sp.j. Piekarnia; shop=bakery",
                    "opening_hours_osm": "wtorek 5:30–20:00",
                    "open_at_arrival": None,
                    "open_source": "unknown",
                },
                {
                    "category": "hard_resupply",
                    "name": "Sklep spożywczo-przemysłowy",
                    "route_km": 39.0,
                    "distance_to_track_m": 30.0,
                    "source_tags": "name=Sklep spożywczo-przemysłowy; shop=convenience",
                    "opening_hours_osm": "wtorek 6:00–19:00",
                    "open_at_arrival": None,
                    "open_source": "unknown",
                },
                {
                    "category": "hard_resupply",
                    "name": "Sklep spożywczy GS Samopomoc Chłopska",
                    "route_km": 61.3,
                    "distance_to_track_m": 55.0,
                    "source_tags": "name=Sklep spożywczy GS Samopomoc Chłopska; shop=convenience",
                    "opening_hours_osm": "wtorek 7:30–20:00",
                    "open_at_arrival": None,
                    "open_source": "unknown",
                },
                {
                    "category": "hard_resupply",
                    "name": "Sklep Delikatesy Rodzinne Somianka",
                    "route_km": 71.1,
                    "distance_to_track_m": 60.0,
                    "source_tags": "name=Sklep Delikatesy Rodzinne Somianka; shop=convenience",
                    "opening_hours_osm": "wtorek 6:00–21:00",
                    "open_at_arrival": None,
                    "open_source": "unknown",
                },
                {
                    "category": "hard_resupply",
                    "name": "Sklep spożywczo-przemysłowy Wanda Figat",
                    "route_km": 31.5,
                    "distance_to_track_m": 35.0,
                    "source_tags": "name=Sklep spożywczo-przemysłowy Wanda Figat; shop=convenience",
                    "opening_hours_osm": "wtorek 5:00–13:30 i 16:00–19:30",
                    "open_at_arrival": None,
                    "open_source": "unknown",
                },
            ],
            "soft_food_stop": [],
            "water": [],
            "attractions": [],
            "town_fallback_check": [],
            "missing_chunks_count": 0,
        }

        analysis = "\n".join(
            rr._render_poi_supply_section(
                poi_cache,
                ride_start="2026-06-30T12:00:00+02:00",
                route_distance_km=71.1,
            )
        )

        self.assertIn("Pewne punkty OPEN_AT_ETA do 500 m od trasy: 5", analysis)
        self.assertIn("Punkty blisko okna otwarcia/zamknięcia: 1", analysis)
        self.assertIn("Potencjalne UNKNOWN_HOURS do 500 m od trasy: 0", analysis)
        self.assertIn("Punkty CLOSED_AT_ETA: 0", analysis)
        self.assertIn("Topaz Express", analysis)
        self.assertIn("status_hours=OPEN_AT_ETA", analysis)
        self.assertIn("Wawie sp.j. Piekarnia", analysis)
        self.assertIn("Sklep spożywczo-przemysłowy", analysis)
        self.assertIn("Sklep spożywczy GS Samopomoc Chłopska", analysis)
        self.assertIn("Sklep Delikatesy Rodzinne Somianka", analysis)
        self.assertIn("Sklep spożywczo-przemysłowy Wanda Figat", analysis)
        self.assertIn("status_hours=CLOSED_AT_ETA_MARGIN_RISK", analysis)
        self.assertIn("eta_at_poi=2026-06-30 13:45:00+02:00", analysis)


class TestRouteReportVersionGuard(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_call(name, args):
            self.calls.append((name, dict(args)))
            return CANNED[name]

        def fake_version_record(*, route_id=None, route_artifact_id=None):
            if route_artifact_id is not None:
                try:
                    if int(route_artifact_id) == 999:
                        return MISMATCH_ROUTE_VERSION
                    if int(route_artifact_id) == 306:
                        return ACTIVE_ROUTE_VERSION
                except Exception:
                    return None
            if route_id == "55798129":
                return ACTIVE_ROUTE_VERSION
            return None

        self._orig_call = rr._call_tool
        self._orig_dist = rr._resolve_distance_km
        self._orig_poi_cache = rr._read_poi_analysis_cache
        self._orig_version_record = rr._fetch_route_version_record
        self._orig_fetch_surface = None
        rr._call_tool = fake_call
        rr._resolve_distance_km = lambda route_id: 71.1
        rr._read_poi_analysis_cache = lambda route_id: VERSIONED_POI_CACHE
        rr._fetch_route_version_record = fake_version_record
        import qbot_route_tools as rt
        self._orig_fetch_surface = rt._fetch_best_route_surface_profile
        self._rt = rt

    def tearDown(self):
        rr._call_tool = self._orig_call
        rr._resolve_distance_km = self._orig_dist
        rr._read_poi_analysis_cache = self._orig_poi_cache
        rr._fetch_route_version_record = self._orig_version_record
        self._rt._fetch_best_route_surface_profile = self._orig_fetch_surface

    def _surface_profile(self, route_artifact_id=306):
        return {
            "id": 19 if route_artifact_id == 306 else 88,
            "route_artifact_id": route_artifact_id,
            "route_id": "55798129",
            "enriched_at": "2026-06-29T12:34:56+02:00",
            "quality_status": "GOOD_INFERRED",
            "coverage_pct": 100.0,
            "tagged_surface_pct": 70.8,
            "inferred_surface_pct": 29.2,
            "unknown_surface_pct": 0.0,
            "surface_percentages_raw": {"asphalt": 34.9, "ground": 32.7},
            "surface_percentages_refined": {"asphalt": 34.9, "ground": 32.7},
            "surface_summary_json": {
                "quality_status": "GOOD_INFERRED",
                "coverage_pct": 100.0,
                "tagged_surface_pct": 70.8,
                "inferred_surface_pct": 29.2,
                "unknown_surface_pct": 0.0,
            },
            "good_profile": True,
        }

    def test_matching_surface_profile_passes(self):
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: self._surface_profile(306)
        out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        self.assertEqual(out["status"], "OK")
        analysis = out["analysis"]
        self.assertIn("surface_summary_json", analysis)
        self.assertNotIn("ROUTE_VERSION_MISMATCH", analysis)

    def test_surface_profile_mismatch_blocks_report(self):
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: self._surface_profile(999)
        out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        analysis = out["analysis"]
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("DATA_INTEGRITY_ERROR: ROUTE_VERSION_MISMATCH", analysis)
        self.assertIn("legacy surface path", analysis)
        self.assertNotIn("Źródło profilu: qbot_v2.route_surface_profiles.surface_summary_json", analysis)

    def test_poi_cache_without_version_metadata_warns_legacy(self):
        rr._read_poi_analysis_cache = lambda route_id: CANNED_POI_CACHE
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: None
        out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        analysis = out["analysis"]
        self.assertIn("WARN: SOURCE_VERSION_METADATA_MISSING", analysis)
        self.assertIn("Status zaopatrzenia:", analysis)
        self.assertNotIn("DATA_INTEGRITY_ERROR: ROUTE_VERSION_MISMATCH", analysis)

    def test_poi_cache_version_mismatch_blocks_report(self):
        rr._read_poi_analysis_cache = lambda route_id: {
            **VERSIONED_POI_CACHE,
            "route_artifact_id": 999,
            "sha256": MISMATCH_ROUTE_VERSION["sha256"],
            "source_artifact_sha256": MISMATCH_ROUTE_VERSION["source_artifact_sha256"],
            "distance_m": MISMATCH_ROUTE_VERSION["distance_m"],
            "distance_km": MISMATCH_ROUTE_VERSION["distance_km"],
            "track_points": MISMATCH_ROUTE_VERSION["track_points"],
            "elevation_gain_m": MISMATCH_ROUTE_VERSION["elevation_gain_m"],
            "created_at": MISMATCH_ROUTE_VERSION["created_at"],
            "updated_at": MISMATCH_ROUTE_VERSION["updated_at"],
        }
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: self._surface_profile(306)
        out = rr._tool_route_report({"route_id": "55798129", "variant": "pelny"})
        analysis = out["analysis"]
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("DATA_INTEGRITY_ERROR: ROUTE_VERSION_MISMATCH", analysis)
        self.assertIn("poi_cache", analysis)
        self.assertNotIn("surface_summary_json", analysis.split("## A8 - WODA / SKLEPY / REFILL")[-1])


class TestRouteSurfaceVersionGuard(unittest.TestCase):
    """TASK 1B - version guard dla land-cover / detailed profile bez losowego artefaktu."""

    def setUp(self):
        import qbot_route_tools as rt
        self._rt = rt
        self._orig_resolve = rt._resolve_active_route_artifact_id
        self._orig_fetch_surface = rt._fetch_best_route_surface_profile
        self._orig_build_detail = None

    def tearDown(self):
        import tools.rwgps.route_brief as rb
        self._rt._resolve_active_route_artifact_id = self._orig_resolve
        self._rt._fetch_best_route_surface_profile = self._orig_fetch_surface
        if self._orig_build_detail is not None:
            rb.build_detail = self._orig_build_detail

    def _fake_build_detail(self, *args, **kwargs):
        print(
            "SZCZEGOLOWY PROFIL TRASY (z ramek 80 m)\n"
            "Dystans 71.137 km | 889 ramek | +800 m / -800 m | max 7% | stromo(>=3.0%) ~2.5 km\n"
            "\n"
            "Nawierzchnia (odcinki >= 0.2 km):\n"
            "  km 0.0-20.0 (20.0): asfalt\n"
            "  km 20.0-30.0 (10.0): szuter luzny\n"
            "  km 30.0-63.3 (33.3): asfalt\n"
        )
        return 0

    def test_no_route_id_prompts_for_route_id(self):
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected surface lookup without route_id"))
        import tools.rwgps.route_brief as rb
        self._orig_build_detail = rb.build_detail
        rb.build_detail = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected build_detail without route_id"))
        out = self._rt._tool_qbot_route_profile_detail({})
        self.assertEqual(out["status"], "WARN")
        self.assertIn("Podaj route_id", out["notes"])

    def test_no_route_id_does_not_pick_latest_profile(self):
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected surface lookup without route_id"))
        import tools.rwgps.route_brief as rb
        self._orig_build_detail = rb.build_detail
        rb.build_detail = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected build_detail without route_id"))
        out = self._rt._tool_qbot_route_plan_analysis({})
        self.assertEqual(out["status"], "WARN")
        self.assertIn("Podaj route_id", out["notes"])

    def test_active_route_uses_active_artifact_id(self):
        calls = []
        self._rt._resolve_active_route_artifact_id = lambda route_id: 306 if str(route_id) == "55798129" else None

        def fake_fetch(**kwargs):
            calls.append(dict(kwargs))
            return {
                "id": 19,
                "route_artifact_id": 306,
                "route_id": "55798129",
                "enriched_at": "2026-06-29T12:34:56+02:00",
                "quality_status": "GOOD_INFERRED",
                "coverage_pct": 100.0,
                "tagged_surface_pct": 70.8,
                "inferred_surface_pct": 29.2,
                "unknown_surface_pct": 0.0,
                "surface_percentages_raw": {"asphalt": 34.9, "ground": 32.7},
                "surface_percentages_refined": {"asphalt": 34.9, "ground": 32.7},
                "surface_summary_json": {
                    "quality_status": "GOOD_INFERRED",
                    "coverage_pct": 100.0,
                    "tagged_surface_pct": 70.8,
                    "inferred_surface_pct": 29.2,
                    "unknown_surface_pct": 0.0,
                    "route_version_key": "ok",
                },
                "route_version": ACTIVE_ROUTE_VERSION,
                "good_profile": True,
            }

        self._rt._fetch_best_route_surface_profile = fake_fetch
        import tools.rwgps.route_brief as rb
        self._orig_build_detail = rb.build_detail
        rb.build_detail = self._fake_build_detail
        out = self._rt._tool_qbot_route_profile_detail({"route_id": "55798129"})
        self.assertEqual(out["status"], "OK")
        self.assertTrue(calls)
        self.assertEqual(calls[0].get("route_artifact_id"), 306)
        self.assertNotEqual(calls[0].get("route_artifact_id"), 361)
        self.assertIn("Dystans 71.137 km", out["analysis"])
        self.assertIn("route_artifact_id=306", out["analysis"])
        self.assertNotIn("64.0 km", out["analysis"])

    def test_legacy_compatible_cache_passes(self):
        guard = self._rt._surface_profile_version_guard(
            active_version=ACTIVE_ROUTE_VERSION,
            block_version=LEGACY_COMPATIBLE_ROUTE_VERSION,
            source_name="surface_summary_json",
        )
        self.assertEqual(guard["code"], "LAND_COVER_LEGACY_COMPATIBLE")
        self.assertEqual(guard["status"], "WARN")

    def test_mismatch_cache_blocks(self):
        guard = self._rt._surface_profile_version_guard(
            active_version=ACTIVE_ROUTE_VERSION,
            block_version=MISMATCH_LAND_COVER_PROFILE,
            source_name="surface_summary_json",
        )
        self.assertEqual(guard["code"], "LAND_COVER_VERSION_MISMATCH")
        self.assertEqual(guard["status"], "ERROR")

    def test_mismatched_profile_errors(self):
        self._rt._resolve_active_route_artifact_id = lambda route_id: 306 if str(route_id) == "55798129" else None
        self._rt._fetch_best_route_surface_profile = lambda **kwargs: MISMATCH_LAND_COVER_PROFILE
        import tools.rwgps.route_brief as rb
        self._orig_build_detail = rb.build_detail
        rb.build_detail = self._fake_build_detail
        out = self._rt._tool_qbot_route_profile_detail({"route_id": "55798129"})
        self.assertEqual(out["status"], "ERROR")
        self.assertIn("LAND_COVER_VERSION_MISMATCH", out["analysis"])
        self.assertIn("qbot_route_profile_detail", out["tool"])

if __name__ == "__main__":
    unittest.main()
