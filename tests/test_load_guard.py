"""Straznik obciazenia (fitmodel/load_guard.py): klasyfikacja, tresc pytania, decyzja 'moc',
odrzucenie obcego czatu. Bez Telegrama; wpis testowy w load_guard sprzatany."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import load_guard as LG  # noqa: E402


class Classify(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(LG.classify(4 * 3600, 336, 242, "power")[0], "OK")          # x1.39
        self.assertEqual(LG.classify(4 * 3600, 360, 242, "power")[0], "SPRAWDZ")     # x1.49
        self.assertEqual(LG.classify(4 * 3600, 160, 242, "power")[0], "SPRAWDZ")     # x0.66
        self.assertEqual(LG.classify(1 * 3600, 150, 60, "power")[0], "KROTKA")       # krotka: bez pytania
        self.assertEqual(LG.classify(4 * 3600, 200, 200, "hr")[0], "KWARANTANNA")
        self.assertEqual(LG.classify(4 * 3600, 200, 2, "power")[0], "BRAK_TETNA")

    def test_question_mentions_cold(self):
        t = LG.question_text(date(2026, 7, 4), 3.5 * 3600, 256, 175, 256 / 175, 12)
        self.assertIn("×1,46", t)
        self.assertIn("chłodno", t)
        t2 = LG.question_text(date(2026, 7, 4), 3.5 * 3600, 256, 175, 256 / 175, 22)
        self.assertNotIn("chłodno", t2)


class Decision(unittest.TestCase):
    def test_moc_decision_and_idempotent(self):
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect(); cur = c.cursor()
        LG.ensure_table(c)
        eid = "TEST-LG-0001"
        cur.execute("DELETE FROM qbot_v2.load_guard WHERE external_id=%s", (eid,))
        cur.execute("INSERT INTO qbot_v2.load_guard (external_id, ride_date, duration_s, xss_power, xss_hr, ratio, verdict) "
                    "VALUES (%s,'2026-07-04',12600,256,175,1.46,'SPRAWDZ')", (eid,))
        c.commit()
        try:
            self.assertIn("z mocy", LG.apply_decision(c, eid, "moc"))
            self.assertIn("już decyzję", LG.apply_decision(c, eid, "tetno"))   # drugi klik nic nie zmienia
        finally:
            cur.execute("DELETE FROM qbot_v2.load_guard WHERE external_id=%s", (eid,))
            c.commit(); c.close()

    def test_foreign_chat_rejected(self):
        said = []
        LG.handle_callback({"id": "1", "data": "lg:hr:X", "message": {"chat": {"id": 999}, "message_id": 5}},
                           lambda i, t="": said.append(t), lambda t: said.append(t), lambda a, b: None, "123")
        self.assertEqual(said, ["Brak dostępu"])


if __name__ == "__main__":
    unittest.main()
