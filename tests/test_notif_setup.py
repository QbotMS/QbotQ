"""qbot_notif: SETUP > Powiadomienia - mapowanie kluczy na rodzaje (2026-10-08)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
import qbot_notif as NF  # noqa: E402


class NotifSetupTest(unittest.TestCase):
    def test_source_of(self):
        cases = {"jazda:123": "jazda", "live:ubior:1": "ubior", "live:rower:0": "rower", "live:pogoda:5": "pogoda",
                 "live:trasa:3": "trasa", "trener:plan:2026-W41": "trener_plan", "trener:review:2026-W41": "trener_rozl",
                 "trener:chg:9": "trener_zmiany", "trener:adapt:9": "trener_zmiany", "live:dane:sen": "dane_sen",
                 "live:dane:waga": "dane_waga", "live:system:svc:qbot-api": "sys_uslugi", "system:restart:qbot-web:1": "sys_uslugi",
                 "live:system:dysk": "sys_dysk", "live:demo:A": "sys_demo", "system:demo:B": "sys_demo",
                 "system:login:2026-10-08": "sys_login", "cos:innego": None}
        for k, v in cases.items():
            self.assertEqual(NF.source_of(k), v, k)

    def test_ids_unique(self):
        ids = [s[0] for s in NF.SOURCES]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
