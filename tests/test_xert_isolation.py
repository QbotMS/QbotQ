"""Bezpiecznik 2026-10-07: Xert = tylko benchmark, NIE wplywa na parametry ModelQ.

Sprawdza statycznie, ze kod liczacy ModelQ (fitmodel/modelq2/*, readiness, daily publish)
nie czyta tabel Xerta, a mq2_backfill czyta benchmark tylko z zamrozonego importu CSV.
"""
import re
import unittest
from pathlib import Path

APP = Path("/opt/qbot/app")
XERT_TABLES = re.compile(r"(modelq2_xert_bench|xert_profile_snapshots|xert_metrics)")


def _code_lines(path: Path):
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s.startswith("#"):
            continue
        yield i, line


class XertIsolationTest(unittest.TestCase):
    def test_modelq2_package_does_not_read_xert(self):
        bad = []
        for p in sorted((APP / "fitmodel" / "modelq2").glob("*.py")):
            for i, line in _code_lines(p):
                if XERT_TABLES.search(line):
                    bad.append(f"{p.name}:{i}: {line.strip()}")
        self.assertEqual(bad, [], "ModelQ v2 czyta tabele Xerta:\n" + "\n".join(bad))

    def test_readiness_does_not_read_xert(self):
        p = APP / "fitmodel" / "readiness.py"
        bad = [f"{i}: {l.strip()}" for i, l in _code_lines(p) if XERT_TABLES.search(l)]
        self.assertEqual(bad, [])

    def test_backfill_reads_only_frozen_csv(self):
        p = APP / "scripts" / "mq2_backfill.py"
        hits = [l for _, l in _code_lines(p) if "modelq2_xert_bench" in l]
        self.assertTrue(hits, "mq2_backfill nie czyta juz benchmarku - zaktualizuj test")
        for l in hits:
            self.assertIn("day <= '2026-07-06'", l, "mq2_backfill czyta nowe wiersze Xerta: " + l.strip())

    def test_daily_bench_writes_only_bench_table(self):
        p = APP / "fitmodel" / "xert_daily_bench.py"
        txt = p.read_text(encoding="utf-8")
        writes = re.findall(r"(?:INSERT INTO|UPDATE)\s+([\w\.]+)", txt)
        self.assertEqual(set(writes), {"qbot_v2.modelq2_xert_bench"})
        self.assertIn("ON CONFLICT (day) DO NOTHING", txt)


if __name__ == "__main__":
    unittest.main()
