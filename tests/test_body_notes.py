"""Notatki TRENERA -> Kalendarz (fitmodel/body_notes.py): reguly zapasowe + zywy zapis/usuniecie na dniu testowym."""
import os
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel import body_notes as BN  # noqa: E402


class Rules(unittest.TestCase):
    def test_fatigue_and_freshness(self):
        self.assertEqual(BN.rules_signal("Ciężkie nogi, nie mam siły")["feel"], -2)
        self.assertEqual(BN.rules_signal("ciężkie nogi")["feel"], -1)
        self.assertEqual(BN.rules_signal("świetnie, noga podaje")["feel"], 1)
        self.assertEqual(BN.rules_signal("plan ok, trasa ładna")["feel"], 0)
        self.assertEqual(BN.rules_signal("")["feel"], 0)


class Live(unittest.TestCase):
    def test_sync_insert_and_delete(self):
        """Dzien testowy 2020-01-01 (poza historia modelu): wpis powstaje z source='trener' i znika po usunieciu notatki."""
        from fitmodel.ftp_resolver import _db_connect
        c = _db_connect(); cur = c.cursor()
        day, sport = "2020-01-01", "test"
        try:
            orig = BN.extract_signal
            BN.extract_signal = BN.rules_signal          # bez wywolania AI w tescie
            r = BN.sync_trener_note(c, day, sport, "Ciężkie nogi, nie mam siły", "Test")
            cur.execute("SELECT feel, title, source FROM qbot_v2.calendar_entry WHERE source_ref=%s", (r["ref"],))
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], -2)
            self.assertTrue(rows[0][1].startswith(BN.TITLE_MARK))
            self.assertEqual(rows[0][2], "trener")
            BN.sync_trener_note(c, day, sport, None, "Test")   # ponowny zapis bez notatki = usuniecie, bez duplikatow
            cur.execute("SELECT count(*) FROM qbot_v2.calendar_entry WHERE source_ref=%s", (r["ref"],))
            self.assertEqual(cur.fetchone()[0], 0)
        finally:
            BN.extract_signal = orig
            cur.execute("DELETE FROM qbot_v2.calendar_entry WHERE source_ref=%s", ("trener:%s:%s" % (day, sport),))
            c.commit(); c.close()


if __name__ == "__main__":
    unittest.main()
