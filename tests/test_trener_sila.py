import sys
import unittest
from collections import Counter

sys.path.insert(0, "/opt/qbot/app")

import qbot_trener_exercises as X
import qbot_trener_sila as S


def pool(over=None):
    over = over or {}
    out = []
    for (k, name, grp, lvl, wc, eq, uni, dose, mus, warm, desc) in X.CATALOG:
        t = "P" if k in X.PROPOSAL else "R"
        p = X.PROPOSAL.get(k, 0)
        if k in over:
            t, p = over[k]
        out.append({"key": k, "name": name, "grp": grp, "level": lvl, "wclass": wc, "tier": t, "prio": p, "img": True, "dose": dose, "warmup": warm})
    return out


def run(seed="s", hist=None, **kw):
    a = dict(n=0, phase="bz", cut=False, dur_min=40, skip=None)
    a.update(kw)
    return S.choose(pool(kw.pop("over", None) if "over" in kw else None), hist or [], seed=seed, **{k: v for k, v in a.items() if k != "over"})


class Choose(unittest.TestCase):
    def test_all_groups_and_accent(self):
        ch = run()
        groups = Counter(x["grp"] for x in ch["chosen"])
        for g in S.BASE_GROUPS:
            self.assertGreaterEqual(groups[g], 1, g)
        self.assertEqual(ch["accent"], "klatka + ramiona")
        self.assertEqual(len(ch["chosen"]), 8)

    def test_max_two_weight_classes(self):
        for i in range(60):
            ch = run(seed=f"x{i}", n=i)
            cls = {x["wclass"] for x in ch["chosen"] if x["wclass"] != "0"}
            self.assertLessEqual(len(cls), 2, (i, [(x["key"], x["wclass"]) for x in ch["chosen"]]))

    def test_no_repeat_from_last_and_unique(self):
        for i in range(30):
            a = run(seed=f"a{i}", n=i)
            keys = [x["key"] for x in a["chosen"]]
            self.assertEqual(len(keys), len(set(keys)))
            b = run(seed=f"b{i}", n=i + 1, hist=[keys])
            self.assertFalse(set(keys) & {x["key"] for x in b["chosen"]}, i)

    def test_basic_share_and_bench_often(self):
        tiers, bench, chest = Counter(), 0, 0
        for i in range(300):
            ch = run(seed=f"p{i}", n=i)
            for x in ch["chosen"]:
                if not x["accent"]:
                    tiers[x["tier"]] += 1
                if x["grp"] == "klatka" and not x["accent"]:
                    chest += 1; bench += x["key"] == "bench_press_db"
        share = tiers["P"] / (tiers["P"] + tiers["R"])
        self.assertTrue(0.6 < share < 0.8, share)
        self.assertGreater(bench / chest, 0.25, bench / chest)

    def test_skip_and_excluded(self):
        over = {k: ("X", 0) for k in ("goblet_squat_db",)}
        for i in range(20):
            ch = S.choose(pool(over), [], n=i, phase="bz", cut=False, dur_min=40, skip=["nogi"], seed=f"k{i}")
            g = {x["grp"] for x in ch["chosen"]}
            self.assertFalse(g & {"nogi", "tyl"})
            self.assertNotIn("goblet_squat_db", [x["key"] for x in ch["chosen"]])
            self.assertNotEqual(ch["accent"], "nogi")

    def test_cut_level1_and_core_bodyweight(self):
        for i in range(20):
            ch = run(seed=f"c{i}", n=i, cut=True)
            self.assertTrue(all(x["level"] == 1 for x in ch["chosen"]))
            self.assertTrue(all(x["wclass"] == "0" for x in ch["chosen"] if x["grp"] == "core"))

    def test_deterministic(self):
        self.assertEqual([x["key"] for x in run(seed="same")["chosen"]], [x["key"] for x in run(seed="same")["chosen"]])


class Blocks(unittest.TestCase):
    def test_blocks_order_and_render(self):
        for i in range(30):
            ch = run(seed=f"r{i}", n=i)
            bl = S.build_blocks(ch["chosen"], {"bench_press_db": 12})
            cls = [b["wclass"] for b in bl]
            w = [c for c in cls if c != "0"]
            self.assertEqual(w, sorted(w, key=S.CLS_ORDER.index))
            self.assertLessEqual(len(w), 2)
            self.assertEqual(sum(len(b["items"]) for b in bl), len(ch["chosen"]))
            if cls[-1] == "0":
                self.assertTrue(all(x["grp"] == "core" for x in bl[-1]["items"]))
            d = S.render(ch, bl, [{"key": "cat_cow", "name": "Koci grzbiet", "dose": "8"}], "bz", False)
            self.assertEqual(len(d["exercises"]), len(ch["chosen"]))
            self.assertIn("BLOK A", d["text"]); self.assertNotIn("None", d["text"])
            self.assertTrue(all(e["img"].startswith("/cwiczenia/") for e in d["exercises"]))


if __name__ == "__main__":
    unittest.main()
