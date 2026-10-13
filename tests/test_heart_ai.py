"""qbot_heart_ai: kiedy AI dziala, pamiec po hashu faktow, limity slow (bez sieci i bez bazy)."""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")
import qbot_heart_ai as A  # noqa: E402


class Kiedy(unittest.TestCase):
    def test_tylko_gdy_odstaje(self):
        ok = {"interpretation": [{"status": "good", "text": "Rytm zatokowy"}, {"status": "info", "text": "HRV 75 ms"},
                                 {"status": "good", "text": "Ciśnienie w tej samej sesji: 118/76 – prawidłowe."}]}
        self.assertFalse(A.ecg_needs_ai(ok))
        bp = {"interpretation": [{"status": "info", "text": "Ciśnienie w tej samej sesji: 126/84 – wysokie prawidłowe"}]}
        self.assertTrue(A.ecg_needs_ai(bp))
        self.assertTrue(A.ecg_needs_ai({"interpretation": [{"status": "warn", "text": "HRV niżej"}]}))


class Pomocnicze(unittest.TestCase):
    def test_hash_stabilny(self):
        self.assertEqual(A._hash({"a": 1, "b": [1, 2]}), A._hash({"b": [1, 2], "a": 1}))
        self.assertNotEqual(A._hash({"a": 1}), A._hash({"a": 2}))

    def test_limit_slow(self):
        self.assertEqual(A._words("a b c d", 2), "a b…")
        self.assertEqual(A._words(None, 3), "")

    def test_prompty_zakazuja_oceny_wlasnej(self):
        self.assertIn("nie oceniaj sam", A.PROMPT_ECG)
        self.assertIn("nie oceniaj sam", A.PROMPT_REP)


class Laczna(unittest.TestCase):
    def test_fakty_bez_szeregow(self):
        data = {"today": "2026-10-13", "points": [{"status": "bad", "text": "Ciśnienie 140/90"}], "nexus": [{"status": "warn", "text": "x"}],
                "rhr": {"recent": 49, "norm": 46, "delta": 2.8, "series": [1] * 300}, "hrp": {"recent": 125, "norm": 124, "delta": 1, "rides": 10, "series": [1] * 300},
                "bp": {"summary": None, "all": [1] * 50}, "ecg": {"last": None, "list": []}, "sleep": {"spo2": {"text": "t", "below90": 21}}, "body": {"waist_cm": 109}}
        f = A.summary_facts(data)
        self.assertNotIn("series", str(f))
        self.assertEqual(f["saturacja_nocna"], {"below90": 21})
        self.assertIn("DOKŁADNIE 3 zdania", A.PROMPT_SUM)


if __name__ == "__main__":
    unittest.main()
