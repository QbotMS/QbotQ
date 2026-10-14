"""Uklad 3 rund (2026-10-09): ciezkie 2-3 -> lzejsze 2-3 -> bez hantli 2-3, miesci sie w czasie. Bez bazy."""
import sys
import unittest
from collections import Counter

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/tests")
import qbot_trener_sila as S
from test_trener_sila import pool

CASES = [dict(phase=ph, dur_min=d, skip=sk, n=n) for ph in ("bz", "rt", "sz") for d in (30, 40, 60)
         for sk in (None, ["nogi"]) for n in range(4)]


def run(a, seed):
    ch = S.choose(pool(), [], cut=False, seed=seed, **a)
    return ch, S.build_blocks(ch["chosen"])


class Uklad(unittest.TestCase):
    def test_three_rounds_heavy_light_bodyweight(self):
        for ci, a in enumerate(CASES):
            for i in range(5):
                ch, bl = run(a, f"u{ci}-{i}")
                cls = [b["wclass"] for b in bl]
                self.assertEqual(len(bl), 3, (a, cls))
                self.assertIn(cls[0], ("C", "S")); self.assertIn(cls[1], ("L", "S")); self.assertEqual(cls[2], "0")
                self.assertNotEqual(cls[0], cls[1])
                for b in bl:
                    self.assertTrue(2 <= len(b["items"]) <= 3, (a, [(b["wclass"], len(b["items"])) for b in bl]))
                    self.assertTrue(all(x["wclass"] == b["wclass"] for x in b["items"]))

    def test_fits_time(self):
        for ci, a in enumerate(CASES):
            for i in range(5):
                ch, bl = run(a, f"t{ci}-{i}")
                self.assertLessEqual(ch["est_min"], a["dur_min"], (a, ch["est_min"], ch["rounds"]))
                self.assertGreaterEqual(ch["rounds"], 1)

    def test_more_time_more_work(self):
        a40 = dict(phase="bz", dur_min=40, skip=None, n=0); a60 = dict(a40, dur_min=60)
        w = lambda ch: ch["rounds"] * len(ch["chosen"])
        self.assertGreater(w(run(a60, "m")[0]), w(run(a40, "m")[0]))

    def test_groups_covered_and_skip(self):
        for ci, a in enumerate(CASES):
            ch, _ = run(a, f"g{ci}")
            got = {x["grp"] for x in ch["chosen"]}
            if a["skip"]:
                self.assertFalse(got & {"nogi", "tyl"})
            if a["dur_min"] >= 40:
                need = set(S.BASE_GROUPS) - (S.SKIP_MAP["nogi"] if a["skip"] else set())
                self.assertGreaterEqual(len(got & need), len(need) - 1, (a, got))

    def test_accent_present(self):
        for n in range(4):
            ch, _ = run(dict(phase="bz", dur_min=40, skip=None, n=n), f"a{n}")
            self.assertTrue(any(x["accent"] for x in ch["chosen"]), n)

    def test_render_rounds_and_time(self):
        ch, bl = run(dict(phase="bz", dur_min=40, skip=None, n=0), "r")
        d = S.render(ch, bl, [], "bz", False)
        self.assertEqual(d["rounds"], ch["rounds"])
        self.assertIn("razem ok.", d["text"])
        self.assertIn("BLOK C · bez hantli", d["text"])


if __name__ == "__main__":
    unittest.main()
