import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

import qbot_trener_exercises as X
import qbot_trener_sheet as SH
import qbot_trener_sila as S


def data(keys_override=None):
    pool = [{"key": k, "name": name, "grp": grp, "level": lvl, "wclass": wc, "tier": "P" if k in X.PROPOSAL else "R",
             "prio": X.PROPOSAL.get(k, 0), "img": True, "dose": dose} for (k, name, grp, lvl, wc, eq, uni, dose, mus, warm, desc) in X.CATALOG]
    ch = S.choose(pool, [], n=0, phase="bz", cut=False, dur_min=40, skip=None, seed="t")
    if keys_override:
        ch["chosen"][0] = dict(ch["chosen"][0], key=keys_override, name="Ćwiczenie bez grafiki")
    d = S.render(ch, S.build_blocks(ch["chosen"]), [{"key": "cat_cow", "name": "Koci grzbiet", "dose": "8"}], "bz", False)
    info = {k: {"steps": t[0], "ok": t[1], "bad": t[2]} for k, t in X.TEXTS.items()}
    return {"details": d, "info": info, "session": {"id": 1, "day": "2026-10-15", "dow": "czwartek", "name": "Siła", "start": "09:00",
                                                     "dur_min": 40, "status": "plan", "phase": "bz", "editable": True}}


class Pdf(unittest.TestCase):
    def test_pdf_with_all_images(self):
        pdf, rep = SH.build_pdf(data())
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(rep["images"], rep["exercises"])
        self.assertGreaterEqual(rep["pages"], 1)
        self.assertGreaterEqual(pdf.count(b"/Subtype /Image"), rep["pages"])

    def test_one_page_for_normal_workout(self):
        pdf, rep = SH.build_pdf(data())
        self.assertEqual(rep["pages"], 1)
        self.assertEqual(rep["layout"], "1 strona")

    def test_very_long_falls_back_to_multi_page(self):
        dd = data()
        ex = dd["details"]["exercises"]
        many = [dict(e, n=i + 1) for i, e in enumerate(ex * 4)]
        dd["details"]["exercises"] = many
        dd["details"]["blocks"] = [{"letter": "A", "wclass": "C", "kg": 10, "head": "BLOK A", "items": [e["n"] for e in many]}]
        pdf, rep = SH.build_pdf(dd)
        self.assertEqual(rep["layout"], "multi")
        self.assertGreater(rep["pages"], 1)
        self.assertEqual(rep["images"], len(many))

    def test_missing_image_is_error_not_file(self):
        with self.assertRaises(SH.SheetError) as cm:
            SH.build_pdf(data("nie_ma_takiej_grafiki"))
        self.assertIn("brak grafik", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
