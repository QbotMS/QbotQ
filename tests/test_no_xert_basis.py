"""Bezpiecznik (15.10.2026, zasada Michala): Xert NIE jest podstawa liczb QBota -- tylko punkt odniesienia przy kalibracji ModelQ.
Tabele Xerta moga czytac wylacznie moduly porownawcze/importu. Nowe miejsce czytajace Xerta = ten test pada.
Jesli to swiadome porownanie (benchmark), dopisz modul do ALLOW z uzasadnieniem."""
import os
import re
import unittest

APP = "/opt/qbot/app"
SKIP = {".venv", ".git", "archive", "_bak_archive", "tests", "scripts", "__pycache__", "web_public", "web_landing", ".ms-playwright"}
XERT = re.compile(r"xert_profile_snapshots|modelq2_xert_bench|xert_activities")
ALLOW = {
    "qbot3/connectors/import_xert_profile_snapshot.py",  # import danych Xerta (do porownan)
    "fitmodel/xert_bench.py", "fitmodel/xert_daily_bench.py",  # porownanie ModelQ vs Xert
    "fitmodel/tp_recheck.py", "fitmodel/modelq_guard.py",  # straznicy kalibracji ModelQ (Xert jako sprawdzian)
    "fitmodel/modelq2/publish.py", "fitmodel/modelq2/progression.py",  # zapis benchmarku obok sygnatury
    "fitmodel/daily_job.py",  # krok 6b: dzienny dopis Xerta do modelq2_xert_bench (benchmark)
    "qbot_web.py",  # strona ModelQ: kropki Xerta jako benchmark (modelq2_data)
    "qbot3/rides/ride_report_builder.py",  # blok benchmark_xert (porownanie, nie podstawa)
    "qbot_query_handler.py",  # intencje xert_status/xert_snapshot_range = pytania WPROST o Xerta
    "mcp_server.py",  # stary serwer narzedzi (porownania)
    # stara warstwa sprzed Alberta -- do wyciecia 22.10.2026 (docs/LEGACY_USAGE.md):
    "qbot_dashboard.py", "qbot_report_data_provider.py", "qbot_legacy_parity_tools.py",
    "qbot_query_router.py", "qbot_tool_registry.py", "qbot_api.py",
}


class NoXertAsBasis(unittest.TestCase):
    def test_only_allowed_modules_read_xert(self):
        bad = []
        for dp, dns, fns in os.walk(APP):
            dns[:] = [d for d in dns if d not in SKIP]
            for fn in fns:
                if not fn.endswith(".py") or ".bak" in fn:
                    continue
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, APP)
                if rel in ALLOW:
                    continue
                with open(p, encoding="utf-8", errors="ignore") as f:
                    if XERT.search(f.read()):
                        bad.append(rel)
        self.assertEqual(bad, [], "Xert jako podstawa liczb (zasada 15.10.2026): %s" % bad)


if __name__ == "__main__":
    unittest.main()
