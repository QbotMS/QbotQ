"""qbot_notif: Centrum powiadomien - czyste funkcje stanu na zywo (2026-10-08)."""
import subprocess
import sys
import unittest
from datetime import date

sys.path.insert(0, "/opt/qbot/app")
import qbot_notif as NF  # noqa: E402


class NotifTest(unittest.TestCase):
    def test_bike_grouped_per_bike(self):
        out = NF.live_bike([
            {"id": 1, "label": "nasmaruj", "bike_id": 2, "bike": "Grail", "ride_key": "R1", "created_at": "2026-10-07 10:00:00"},
            {"id": 2, "label": "sprawdź hamulce", "bike_id": 2, "bike": "Grail", "ride_key": "R2", "created_at": "2026-10-08 10:00:00"},
            {"id": 3, "label": "naładuj światła", "bike_id": None, "bike": None, "ride_key": "R3", "created_at": "2026-10-08 11:00:00"}])
        self.assertEqual(len(out), 2)
        g = [o for o in out if o["key"] == "live:rower:2"][0]
        self.assertEqual(g["title"], "Grail: do zrobienia (2)")
        self.assertIn("po jeździe 08.10", g["body"])
        self.assertEqual(g["url"], "/raport-jazdy.html?ride=R2")
        self.assertEqual(g["action"]["body"]["ids"], [1, 2])
        self.assertTrue(any(o["key"] == "live:rower:0" and o["title"].startswith("Rower:") for o in out))

    def test_routes(self):
        out = NF.live_routes([{"id": 31, "preview_text": "#31 Znalazłem nową trasę RWGPS: X\nOdpowiedz: 31 TAK"}])
        self.assertEqual(out[0]["key"], "live:trasa:31")
        self.assertIn("#31 Znalazłem", out[0]["body"])

    def test_stale(self):
        t = date(2026, 10, 8)
        self.assertEqual(NF.live_stale({"sen": date(2026, 10, 7), "waga": date(2026, 10, 5)}, t), [])
        out = NF.live_stale({"sen": date(2026, 10, 4), "waga": None}, t)
        self.assertEqual([o["key"] for o in out], ["live:dane:sen", "live:dane:waga"])
        self.assertEqual(out[0]["body"], "ostatnie 04.10 (4 dni temu)")

    def test_nav_js_syntax(self):
        r = subprocess.run(["node", "--check", "/opt/qbot/web/public/nav.js"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
