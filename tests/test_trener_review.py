"""Testy weryfikacji planu (bez LLM i bez bazy)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_engine as E
import qbot_trener_review as R

WS = date(2026, 9, 21)


class TestRules(unittest.TestCase):
    def test_sila_on_long_day_and_day_before(self):
        ses = [{"day": "2026-09-27", "sport": "sila", "name": "Siła", "dur_min": 40, "status": "plan"},
               {"day": "2026-09-27", "sport": "rower", "name": "Trasa", "dur_min": 317, "status": "plan", "is_long": True, "xss": 263},
               {"day": "2026-09-26", "sport": "sila", "name": "Siła", "dur_min": 40, "status": "plan"}]
        w = E.check_rules(ses, {})
        self.assertTrue(any("w dniu długiej jazdy" in x for x in w))
        self.assertTrue(any("przeddzień" in x for x in w))
        self.assertTrue(any("dzień po dniu" in x for x in w))

    def test_busy_and_rest(self):
        ses = [{"day": "2026-09-23", "sport": "rower", "name": "Rower", "dur_min": 90, "status": "plan", "start_time": "16:30"}]
        meta = {"2026-09-23": {"type": "rest", "busy": [{"a": "17:00", "b": "21:00", "label": "⚽ Trening Jaśka"}]}}
        w = E.check_rules(ses, {}, meta)
        self.assertTrue(any("REST" in x for x in w))
        self.assertTrue(any("koliduje" in x for x in w))


class TestValidate(unittest.TestCase):
    def test_filters_and_sorts(self):
        raw = {"summary": "ok", "issues": [
            {"day": "2026-09-27", "severity": "niska", "problem": "a"},
            {"day": "2026-10-05", "severity": "wysoka", "problem": "poza tygodniem"},
            {"day": "2026-09-26", "severity": "WYSOKA", "problem": "b", "why": "x", "suggestion": "y"},
            {"day": "2026-09-25", "severity": "dziwna", "problem": "c"},
            {"day": "2026-09-24", "severity": "niska", "problem": ""}]}
        v = R.validate(raw, WS)
        self.assertEqual([i["problem"] for i in v["issues"]], ["b", "c", "a"])
        self.assertEqual(v["issues"][1]["severity"], "średnia")

    def test_garbage(self):
        self.assertEqual(R.validate("nie json", WS)["issues"], [])


class TestInput(unittest.TestCase):
    def test_build_input_shape(self):
        ctx = {"week_start": WS, "today": date(2026, 9, 23), "ov": {}, "goals": [], "rules": [], "day_state": {}, "weather": {},
               "calendar": [{"id": 34, "day": "2026-09-27", "end_day": None, "kind": "event", "event_type": None, "title": "[Q] trasa", "at_time": "09:15", "note": "104,7 km"}],
               "route_entry_ids": {34}}
        ses = [{"day": date(2026, 9, 27), "sport": "rower", "name": "trasa", "start_time": "09:15", "dur_min": 317, "status": "plan", "source": "auto", "is_long": True, "xss": 263}]
        inp = R.build_input(ctx, ses, [], ["x"], {"phase_name": "Sezon — jazda", "target_h": 7, "season": 2026})
        self.assertEqual(len(inp["dni"]), 7)
        nd = inp["dni"][6]
        self.assertEqual(nd["plan"][0]["nazwa"], "trasa")
        self.assertEqual(nd["kalendarz"][0]["notatka"], "104,7 km")
        self.assertEqual(nd["zajetosci"], [])          # trasa z Kalendarza nie jest zajetoscia
        self.assertTrue(inp["dni"][0]["minal"])


if __name__ == "__main__":
    unittest.main()
