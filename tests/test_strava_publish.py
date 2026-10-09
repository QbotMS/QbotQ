# -*- coding: utf-8 -*-
"""Testy czystych funkcji opisu Strava (qbot_strava_publish). 2026-10-09 (v2: bez W'bal w tekscie, MyBiom/do Mamy)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_strava_publish as P  # noqa: E402

PROGI = {"h50": 72.0, "h75": 89.9, "x75": 198.0, "hr50": 119.0, "hr75": 126.0, "pw50": 146.0, "pw75": 164.0}


class T(unittest.TestCase):
    def test_surface_4_10(self):
        s = P.surface_split({"trudna/wolna": 20.2, "twarda szybka": 54.7, "zwykly gravel": 20.1, "ryzyko/niepewne": 5.0})
        self.assertEqual(s, {"asfalt": 55, "szuter": 20, "ujeby": 25})
        self.assertIsNone(P.surface_split({}))

    def test_effort(self):
        # 04.10: dlugo, duze XSS, srednia moc/tetno umiarkowane -> mocno, ale stabilnie
        self.assertEqual(P.effort_class({"xss": 346, "xss_h": 69.5, "min_wbal": 29, "avg_hr": 122, "avg_pw": 144}, PROGI), "mocno")
        # 08.10: krotko, ale tetno 134 (> p75) -> NIE lekko (uwaga Michala)
        self.assertEqual(P.effort_class({"xss": 57, "xss_h": 61.7, "min_wbal": 77, "avg_hr": 134, "avg_pw": 147}, PROGI), "mocno")
        self.assertEqual(P.effort_class({"xss": 250, "xss_h": 110, "min_wbal": 4, "avg_hr": 140, "avg_pw": 190}, PROGI), "wpierdol")
        self.assertEqual(P.effort_class({"xss": 60, "xss_h": 50, "min_wbal": 80, "avg_hr": 110, "avg_pw": 125}, PROGI), "lekko")
        self.assertEqual(P.effort_class({"xss": 120, "xss_h": 80, "min_wbal": 60, "avg_hr": 121, "avg_pw": 150}, PROGI), "rowno")

    def test_no_private_data_in_text(self):
        for cls in ("wpierdol", "mocno", "mocno_akcenty", "lekko", "rowno"):
            s = P.effort_sentence({"cls": cls, "min_wbal": 29}, 3600)
            self.assertNotIn("W′", s); self.assertNotIn("bak", s); self.assertNotIn("29", s)

    def test_kind_decide(self):
        dm = {"domamy": {"core_hit": 0.71, "cov": 0.68}, "mybiom": {"core_hit": 0.06, "cov": 0.11}}
        mb = {"domamy": {"core_hit": 0.04, "cov": 0.19}, "mybiom": {"core_hit": 1.0, "cov": 1.0}}
        szosa = {"domamy": {"core_hit": 0.62, "cov": 0.48}, "mybiom": {"core_hit": 0.06, "cov": 0.17}}
        self.assertEqual(P.kind_decide(24.3, dm), "domamy")
        self.assertEqual(P.kind_decide(21.4, mb), "mybiom")
        self.assertIsNone(P.kind_decide(35.3, szosa))
        self.assertIsNone(P.kind_decide(5.8, mb))
        self.assertIsNone(P.kind_decide(107, mb))

    def test_tiles_plural(self):
        self.assertEqual(P.tiles_phrase(1), "🟩 1 nowy kwadrat")
        self.assertEqual(P.tiles_phrase(12), "🟩 12 nowych kwadratów")
        self.assertEqual(P.tiles_phrase(63), "🟩 63 nowe kwadraty")

    def test_region_guard(self):
        f = {"towns": ["Wyszogród", "Czerwińsk nad Wisłą"], "admin": ["województwo mazowieckie"], "candidates": []}
        v = P.vocab_of(f)
        self.assertTrue(P.region_ok("Mazowsze, między Wyszogrodem a Czerwińskiem nad Wisłą", v))
        self.assertFalse(P.region_ok("Puszcza Kampinoska", v))


if __name__ == "__main__":
    unittest.main()
