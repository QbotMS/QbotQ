"""bike_tasks: zadania przy rowerze po jezdzie + tekst przypomnienia (2026-10-08)."""
import sqlite3
import subprocess
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")
from qbot3.rides import bike_tasks as BT  # noqa: E402


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE bikes (id INTEGER PRIMARY KEY, name TEXT)")
    c.execute("INSERT INTO bikes VALUES (1,'Grizl'),(2,'Endurace')")
    BT.ensure(c)
    return c


class BikeTasksTest(unittest.TestCase):
    def test_save_and_read(self):
        c = db()
        BT.save(c, "R1", 1, ["lancuch", "smar", "xxx"], "skrzypi")
        d = BT.for_ride(c, "R1")
        self.assertEqual(set(d["mine"]), {"lancuch", "smar"})
        self.assertEqual(d["note"], "skrzypi")
        self.assertEqual(len(d["tasks"]), 7)

    def test_uncheck_removes_todo_keeps_done(self):
        c = db()
        BT.save(c, "R1", 1, ["lancuch", "smar"], None)
        BT.mark_done(c, ids=[d["id"] for d in BT.open_tasks(c) if d["task"] == "smar"])
        BT.save(c, "R1", 1, [], None)
        self.assertEqual({k: v["status"] for k, v in BT.for_ride(c, "R1")["mine"].items()}, {"smar": "done"})

    def test_open_other_and_done_max_id(self):
        c = db()
        BT.save(c, "R1", 1, ["hamulce"], None)
        BT.save(c, "R2", 2, ["swiatla"], None)
        self.assertEqual([o["task"] for o in BT.for_ride(c, "R2")["open_other"]], ["hamulce"])
        mx = max(t["id"] for t in BT.open_tasks(c))
        BT.save(c, "R3", 1, ["kola"], None)
        self.assertEqual(BT.mark_done(c, max_id=mx), 2)
        self.assertEqual([t["task"] for t in BT.open_tasks(c)], ["kola"])

    def test_reminder_text(self):
        self.assertIsNone(BT.reminder_text("Z2", "17:00", []))
        t = BT.reminder_text("Z2 90 min", "17:00", [
            {"label": "wymień łańcuch", "bike": "Grizl", "created_at": "2026-10-07 18:00:00", "note": "skrzypi"},
            {"label": "nasmaruj", "bike": "Grizl", "created_at": "2026-10-07 18:00:00", "note": "skrzypi"}])
        self.assertIn("o 17:00", t)
        self.assertIn("• Grizl: wymień łańcuch, nasmaruj (po jeździe 07.10)", t)
        self.assertEqual(t.count("skrzypi"), 1)
        self.assertIn("dziś", BT.reminder_text("Z2", None, [{"label": "x", "bike": None}]))

    def test_front_js_syntax(self):
        for f in ("raport-jazdy2-gear.js", "raport-jazdy3-rail.js", "raport-jazdy-m.js"):
            r = subprocess.run(["node", "--check", "/opt/qbot/web/public/" + f], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + r.stderr)


if __name__ == "__main__":
    unittest.main()
