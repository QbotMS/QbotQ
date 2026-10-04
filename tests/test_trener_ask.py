import sys
import unittest
from datetime import date

sys.path.insert(0, "/opt/qbot/app")

import qbot_trener_ask as A
import qbot_trener_workouts as W

WS = date(2026, 9, 28)
TODAY = date(2026, 10, 2)
SES = [
    {"id": 643, "day": "2026-10-02", "sport": "sila", "name": "Siła obwodowa", "start_time": "09:00", "dur_min": 40, "status": "plan", "source": "auto"},
    {"id": 549, "day": "2026-09-29", "sport": "rower", "name": "Rower spokojnie", "start_time": "09:00", "dur_min": 30, "status": "done", "source": "auto"},
    {"id": 642, "day": "2026-10-04", "sport": "rower", "name": "Dłuższa jazda", "start_time": "09:00", "dur_min": 286, "status": "plan", "source": "auto"},
]


class AskValidate(unittest.TestCase):
    def test_example_request(self):
        r = A.validate({"summary": "ok", "changes": [
            {"op": "edit", "id": 643, "skip_groups": ["nogi"]},
            {"op": "add", "day": "2026-10-02", "sport": "rower", "start": "17:00", "dur_min": 40, "note": "test Graila, 30–45′"}]},
            WS, TODAY, SES)
        self.assertEqual(len(r["changes"]), 2)
        self.assertEqual(r["changes"][0]["skip_groups"], ["nogi"])
        self.assertIn("bez: nogi", r["changes"][0]["name"])
        self.assertEqual(r["changes"][1]["start"], "17:00")
        self.assertEqual(r["rejected"], [])

    def test_rejects(self):
        r = A.validate({"changes": [
            {"op": "edit", "id": 549, "dur_min": 20},                 # zrobiona
            {"op": "add", "day": "2026-09-30", "sport": "rower", "dur_min": 30},  # przeszlosc
            {"op": "add", "day": "2026-10-03", "sport": "bieg", "dur_min": 30},   # sport
            {"op": "edit", "id": 999, "dur_min": 20},                 # obca sesja
            {"op": "edit", "id": 642, "skip_groups": ["nogi"]},       # partie tylko dla sily
            {"op": "kasuj", "id": 642}]}, WS, TODAY, SES)
        self.assertEqual(r["changes"], [])
        self.assertEqual(len(r["rejected"]), 6)

    def test_busy_warning_and_limit(self):
        busy = {"2026-10-03": [(16 * 60, 18 * 60, "zakupy")]}
        r = A.validate({"changes": [{"op": "add", "day": "2026-10-03", "sport": "joga", "start": "17:00", "dur_min": 20}] +
                        [{"op": "add", "day": "2026-10-03", "sport": "joga", "start": "07:00", "dur_min": 10}] * 8},
                       WS, TODAY, SES, busy)
        self.assertIn("zakupy", r["changes"][0]["warn"])
        self.assertEqual(len(r["changes"]), A.MAX_OPS)

    def test_clear_skip(self):
        r = A.validate({"changes": [{"op": "edit", "id": 643, "skip_groups": []}]}, WS, TODAY, SES)
        self.assertEqual(r["changes"][0]["skip_groups"], [])
        self.assertEqual(r["changes"][0]["name"], "Siła obwodowa")


class StrengthSkip(unittest.TestCase):
    def test_no_legs(self):
        for n in range(8):
            d = W.details("sila", "bz", 40, False, n, skip=["nogi"])
            groups = [e["group"] for e in d["exercises"]]
            self.assertNotIn("nogi", groups)
            self.assertNotIn("tył ciała", groups)
            self.assertNotEqual(d["accent"], "nogi")
            self.assertNotIn("przysiad", d["text"].lower().split("rozgrzewka")[1].split("\n")[0])

    def test_unchanged_without_skip(self):
        self.assertEqual(W.details("sila", "bz", 40, False, 2), W.details("sila", "bz", 40, False, 2, skip=None) | {})
        self.assertEqual(W.details("sila", "bz", 40, False, 2)["accent"], "nogi")


if __name__ == "__main__":
    unittest.main()
