"""qbot_notif krok 2: jazdy, pogoda, system, demo (2026-10-08)."""
import sys
import unittest
from datetime import date, datetime, time, timezone, timedelta

sys.path.insert(0, "/opt/qbot/app")
import qbot_notif as NF  # noqa: E402

TZ = timezone(timedelta(hours=2))


class NotifStep2Test(unittest.TestCase):
    def test_rides(self):
        rides = [{"key": "111", "started_at": datetime(2026, 10, 8, 14, 25, tzinfo=TZ), "name": "Marki", "km": 42.06},
                 {"key": "222", "started_at": datetime(2026, 10, 7, 9, 0, tzinfo=TZ), "name": None, "km": None}]
        ev, lv = NF.live_rides(rides, {"222"})
        self.assertEqual([e["key"] for e in ev], ["jazda:111", "jazda:222"])
        self.assertEqual(ev[0]["body"], "08.10 14:25 · 42.1 km — raport z jazdy")
        self.assertEqual([x["key"] for x in lv], ["live:ubior:111"])
        self.assertEqual(lv[0]["url"], "/raport-jazdy.html?ride=111")
        self.assertEqual(NF.live_rides(rides, None)[1], [])

    def test_weather(self):
        ses = [{"id": 5, "day": date(2026, 10, 10), "start_time": time(9, 0), "name": "Dłuższa jazda"},
               {"id": 6, "day": date(2026, 10, 11), "start_time": None, "name": "Spokojnie"}]
        wx = {"2026-10-10": {"wind": 9.2, "gust": 15.0, "feel_min": -1.5, "rain_mmh": 1.2, "rain_prob": 70, "snow_cm": 0, "storm": False},
              "2026-10-11": {"wind": 3.0, "gust": 6.0, "feel_min": 8.0, "rain_mmh": 0, "rain_prob": 10, "snow_cm": 0, "storm": False}}
        out = NF.live_weather(ses, wx)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Pogoda przed jazdą: sb 10.10 09:00")
        self.assertIn("deszcz do 1.2 mm/h (70%)", out[0]["body"])
        self.assertIn("wiatr 9.2 m/s (porywy 15.0)", out[0]["body"])
        self.assertIn("przymrozek", out[0]["body"])

    def test_system(self):
        st = [{"name": "qbot-api", "state": "active", "result": "success", "restarts": 0, "since": "x"},
              {"name": "qbot-web", "state": "inactive", "result": "success", "restarts": 0, "since": ""},
              {"name": "qbot-backup", "state": "failed", "result": "exit-code", "restarts": 0, "since": ""},
              {"name": "qbot-komoot-watch", "state": "inactive", "result": "success", "restarts": 0, "since": ""},
              {"name": "qbot-mcp-bridge", "state": "active", "result": "success", "restarts": 2, "since": "Thu 2026-10-08 10:00:00 CEST"}]
        keys = [o["key"] for o in NF.live_system(st, 50.0)]
        self.assertEqual(keys, ["live:system:svc:qbot-web", "live:system:svc:qbot-backup", "system:restart:qbot-mcp-bridge:2"])
        self.assertEqual(NF.live_system([], 93.4)[0]["title"], "Mało miejsca na dysku: zajęte 93%")

    def test_demo(self):
        now = datetime(2026, 10, 8, 12, 0, tzinfo=TZ)
        reqs = [{"id": "A", "status": "PENDING", "user_code": "MM7-4BS", "expires_at": now + timedelta(minutes=1), "device_info": "Mozilla (iPhone)"},
                {"id": "B", "status": "PENDING", "user_code": "X", "expires_at": now - timedelta(minutes=1), "device_info": ""},
                {"id": "C", "status": "CONSUMED", "consumed_at": datetime(2026, 10, 8, 8, 37, tzinfo=TZ), "session_ttl_s": 3600,
                 "device_info": "Mozilla/5.0 (X11; Linux x86_64)"}]
        out = NF.live_demo(reqs, now)
        self.assertEqual([o["key"] for o in out], ["live:demo:A", "system:demo:C"])
        self.assertIn("iPhone", out[0]["body"])
        self.assertEqual(out[1]["body"], "08.10 08:37 · Linux · dostęp 60 min")


if __name__ == "__main__":
    unittest.main()
