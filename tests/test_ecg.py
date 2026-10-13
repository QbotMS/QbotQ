"""qbot_ecg: wykrywanie uderzen, HRV i nieregularnosci na syntetycznym EKG (128 Hz, 30 s) + PDF."""
import os
import sys
import unittest
import warnings

import numpy as np

sys.path.insert(0, "/opt/qbot/app")
warnings.filterwarnings("ignore")
import qbot_ecg as Q  # noqa: E402

FS = 128.0


def synth(rr_ms, noise=0.02, seed=1):
    """Syntetyczne EKG: zalamki P, QRS, T (gaussy) w zadanych odstepach RR."""
    n = int(30 * FS)
    t = np.arange(n) / FS
    x = np.zeros(n)
    rng = np.random.default_rng(seed)
    tr, times = 0.6, []
    for rr in rr_ms:
        if tr > 29.5:
            break
        times.append(tr)
        x += 0.15 * np.exp(-((t - (tr - 0.16)) / 0.025) ** 2)      # P
        x += 1.2 * np.exp(-((t - tr) / 0.012) ** 2)                # R
        x -= 0.25 * np.exp(-((t - (tr + 0.03)) / 0.01) ** 2)       # S
        x += 0.3 * np.exp(-((t - (tr + 0.28)) / 0.06) ** 2)        # T
        tr += rr / 1000.0
    x += noise * rng.standard_normal(n) + 0.1 * np.sin(2 * np.pi * 0.25 * t)   # szum + oddech
    return x.tolist(), times


class Uderzenia(unittest.TestCase):
    def test_rowny_rytm(self):
        x, times = synth([1000] * 40)
        a = Q.analyze(x, FS)
        self.assertTrue(a["ok"])
        self.assertLessEqual(abs(a["n_beats"] - len(times)), 1)
        self.assertAlmostEqual(a["hr_mean"], 60, delta=1.5)
        self.assertEqual(a["n_irregular"], 0)
        self.assertLess(a["rmssd"], 15)

    def test_zmiennosc_rmssd(self):
        rr = [1000 + (60 if i % 2 else -60) for i in range(40)]   # naprzemiennie 940/1060 -> RMSSD ok. 120
        x, _ = synth(rr)
        a = Q.analyze(x, FS)
        self.assertAlmostEqual(a["rmssd"], 120, delta=12)

    def test_przedwczesne_z_pauza(self):
        rr = [1000] * 12 + [650, 1350] + [1000] * 20
        x, times = synth(rr)
        a = Q.analyze(x, FS)
        kinds = [i["kind"] for i in a["irregular"]]
        self.assertIn("przedwczesne_pauza", kinds)
        self.assertEqual(a["n_irregular"], 1)
        hit = [i for i in a["irregular"] if i["kind"] == "przedwczesne_pauza"][0]
        self.assertAlmostEqual(hit["t_s"], times[13], delta=0.05)
        self.assertLess(a["rmssd"], 20)   # odstepy wokol pobudzenia nie psuja HRV

    def test_za_malo(self):
        a = Q.analyze([0.0] * 3840, FS)
        self.assertFalse(a["ok"])


class Interpretacja(unittest.TestCase):
    def rec(self, rr, code="SINUS_NORMAL", hour=7):
        from datetime import datetime
        x, _ = synth(rr)
        return {"samples": x, "sample_rate": FS, "analysis": Q.analyze(x, FS), "classification": code,
                "started_local": datetime(2026, 10, 14, hour, 30)}

    def test_prawidlowy(self):
        out = Q.interpret(self.rec([1000] * 40))
        self.assertEqual(out[0]["status"], "good")
        self.assertIn("bez dodatkowych", out[0]["text"])

    def test_pobudzenie(self):
        out = Q.interpret(self.rec([1000] * 12 + [650, 1350] + [1000] * 20))
        self.assertEqual(out[0]["status"], "warn")
        self.assertIn("przedwczesne", out[0]["text"])

    def test_nie_zatokowy(self):
        self.assertEqual(Q.interpret(self.rec([1000] * 40, code="ATRIAL_FIBRILLATION"))[0]["status"], "bad")

    def test_cisnienie_kategorie(self):
        from datetime import datetime
        t = datetime(2026, 10, 14, 7, 25)
        def bp(s, d):
            return [x for x in Q.interpret(self.rec([1000] * 40), {"bp": [{"local": t, "sys": s, "dia": d}]}) if "Ciśnienie" in x["text"]][0]
        self.assertEqual(bp(120, 75)["status"], "good")
        self.assertEqual(bp(126, 84)["status"], "info")
        self.assertEqual(bp(150, 95)["status"], "warn")

    def test_hrv_trend_rano(self):
        from datetime import datetime
        others = [{"local": datetime(2026, 10, d, 7, 0), "rmssd": 80.0} for d in (10, 11, 12)]
        out = Q.interpret(self.rec([1000] * 40), {"others": others})
        hrv = [x for x in out if x["text"].startswith("HRV")][0]
        self.assertEqual(hrv["status"], "warn")   # rowny rytm = HRV ~0 << 80


class Pdf(unittest.TestCase):
    def test_pdf(self):
        x, _ = synth([900] * 40)
        rec = {"samples": x, "sample_rate": FS, "analysis": Q.analyze(x, FS), "started_local": None,
               "classification": "SINUS_NORMAL", "label": "rytm zatokowy", "hr_avg": 67, "device": "FENIX8", "lead": "Lead I"}
        b = Q.pdf_bytes(rec)
        self.assertTrue(b.startswith(b"%PDF"))
        self.assertGreater(len(b), 20000)


if __name__ == "__main__":
    unittest.main()
