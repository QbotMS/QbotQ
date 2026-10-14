"""Testy zmian zestawu przez uzytkownika (2026-10-09): replace_keys - wymiana wskazanych cwiczen, reszta zostaje."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
sys.path.insert(0, "/opt/qbot/app/tests")

import qbot_trener_sila as S
from test_trener_sila import pool


class ReplaceKeys(unittest.TestCase):
    def base(self, seed="r"):
        return S.choose(pool(), [], n=0, phase="bz", cut=False, dur_min=40, skip=None, seed=seed)["chosen"]

    def test_only_dropped_change_same_group(self):
        for i in range(40):
            ch = self.base(f"r{i}")
            x = ch[i % len(ch)]
            new, pairs, miss = S.replace_keys(pool(), ch, {x["key"]}, {x["key"]}, [], phase="bz", cut=False, seed=f"s{i}")
            self.assertEqual(len(new), len(ch))
            self.assertEqual(miss, [])
            self.assertNotIn(x["key"], {y["key"] for y in new})
            kept = [y["key"] for y in ch if y["key"] != x["key"]]
            self.assertTrue(set(kept) <= {y["key"] for y in new})
            repl = [y for y in new if y["key"] not in kept][0]
            self.assertEqual(repl["grp"], x["grp"])
            self.assertEqual(len({y["key"] for y in new}), len(new))

    def test_max_two_classes_kept(self):
        for i in range(40):
            ch = self.base(f"c{i}")
            drop = {y["key"] for y in ch if y["wclass"] != "0"}
            new, _p, _m = S.replace_keys(pool(), ch, drop, drop, [], phase="bz", cut=False, seed=f"c{i}")
            cls = {y["wclass"] for y in new if y["wclass"] != "0"}
            self.assertLessEqual(len(cls), 2, i)

    def test_never_x_or_banned(self):
        ch = self.base("x")
        x = [y for y in ch if y["grp"] == "plecy"][0]
        others = [p["key"] for p in pool() if p["grp"] == "plecy" and p["key"] != x["key"]]
        over = {k: ("X", 0) for k in others[:-1]}
        new, pairs, miss = S.replace_keys(pool(over), ch, {x["key"]}, {x["key"]}, [], phase="bz", cut=False, seed="x")
        got = [y for y in new if y["grp"] == "plecy" and y["key"] not in {z["key"] for z in ch}]
        self.assertTrue(not got or got[0]["key"] == others[-1] or got[0]["key"] not in over)

    def test_core_stays_bodyweight(self):
        ch = self.base("k")
        cores = {y["key"] for y in ch if y["grp"] == "core"}
        new, _p, _m = S.replace_keys(pool(), ch, cores, cores, [], phase="bz", cut=False, seed="k")
        self.assertTrue(all(y["wclass"] == "0" for y in new if y["grp"] == "core"))


if __name__ == "__main__":
    unittest.main()
