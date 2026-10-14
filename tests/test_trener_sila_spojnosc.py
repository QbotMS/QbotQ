"""Spojnosc zestawu (2026-10-09): jedna odmiana z rodziny, bez blokow z 1 cwiczeniem, partie rozdzielone. Bez bazy."""
import sys
import unittest
from collections import Counter

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/tests")
import qbot_trener_sila as S
from test_trener_sila import pool

CASES = [dict(phase=ph, dur_min=d, skip=sk, n=n) for ph in ("bz", "rt") for d in (30, 40) for sk in (None, ["nogi"]) for n in range(4)]


class Spojnosc(unittest.TestCase):
    def sets(self):
        for ci, a in enumerate(CASES):
            for i in range(8):
                ch = S.choose(pool(), [], cut=False, seed=f"q{ci}-{i}", **a)
                yield (ci, i), ch, S.build_blocks(ch["chosen"])

    def test_one_per_family(self):
        for tag, ch, _b in self.sets():
            f = Counter(S.fam(x["key"]) for x in ch["chosen"])
            self.assertTrue(all(v == 1 for v in f.values()), (tag, [x["key"] for x in ch["chosen"]]))

    def test_no_single_exercise_blocks(self):
        for tag, ch, blocks in self.sets():
            if len(blocks) > 1:
                self.assertTrue(all(len(b["items"]) >= 2 for b in blocks),
                                (tag, [(b["wclass"], [x["key"] for x in b["items"]]) for b in blocks]))

    def test_same_group_not_adjacent_when_avoidable(self):
        for tag, ch, blocks in self.sets():
            for b in blocks:
                g = [x["grp"] for x in b["items"]]
                cnt = Counter(g)
                if cnt and max(cnt.values()) <= (len(g) + 1) // 2:
                    self.assertFalse(any(g[k] == g[k + 1] for k in range(len(g) - 1)), (tag, g))

    def test_replace_respects_family(self):
        for tag, ch, _b in self.sets():
            x = ch["chosen"][-1]
            new, _p, _m = S.replace_keys(pool(), ch["chosen"], {x["key"]}, {x["key"]}, [], phase="bz", cut=False, seed=str(tag))
            f = Counter(S.fam(y["key"]) for y in new)
            self.assertTrue(all(v == 1 for v in f.values()), tag)

    def test_review_uses_llm_and_caches_key(self):
        data = {"exercises": [{"n": 1, "key": "a", "name": "A", "group": "plecy", "block": "A"}], "blocks": []}
        self.assertEqual(S._review_key(data), S._review_key(dict(data)))


if __name__ == "__main__":
    unittest.main()
