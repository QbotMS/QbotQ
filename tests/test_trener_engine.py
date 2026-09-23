"""Testy silnika planu TRENER (bez bazy): qbot_trener_engine.plan_week i pomocnicze."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbot_trener_engine as E

WS = date(2026, 10, 5)  # poniedzialek


def ctx(**kw):
    c = {"week_start": WS, "today": WS, "ov": {}, "goals": [], "rules": [], "calendar": [], "day_state": {},
         "keep": [], "activities_extra": [], "readiness_today": None, "readiness_threshold": None, "weather": {}}
    c.update(kw)
    return c


def by_day(res):
    out = {}
    for s in res["sessions"]:
        out.setdefault(s["day"], []).append(s)
    return out


class TestHelpers(unittest.TestCase):
    def test_rule_period_yearly_wrap(self):
        r = {"period": {"m": "yearly", "f": "01.09", "t": "26.06"}}
        self.assertTrue(E.rule_applies(r, date(2026, 12, 1)))
        self.assertTrue(E.rule_applies(r, date(2027, 3, 1)))
        self.assertFalse(E.rule_applies(r, date(2027, 7, 15)))

    def test_find_slot_skips_busy(self):
        info = {"date": WS, "busy": [(12 * 60, 13 * 60, "x")], "win": {"rower": [(11 * 60, 15 * 60)]}}
        self.assertEqual(E.find_slot(info, "rower", 90, []), ("13:00", 90))

    def test_find_slot_shortens(self):
        info = {"date": WS, "busy": [], "win": {"rower": [(12 * 60, 13 * 60)]}}
        self.assertEqual(E.find_slot(info, "rower", 90, [], 30), ("12:00", 60))
        self.assertIsNone(E.find_slot(info, "rower", 90, [], 75))

    def test_wx_bad(self):
        self.assertIn("wiatr", E.wx_bad({"wind": 9}, {"wx.wind_ms": 7, "wx.forest_bonus_ms": 1}, True))
        self.assertIsNone(E.wx_bad({"wind": 7.5}, {"wx.wind_ms": 7, "wx.forest_bonus_ms": 1}, True))
        self.assertIn("deszcz", E.wx_bad({"rain_mmh": 2, "rain_prob": 90}, {}, False))


class TestPlan(unittest.TestCase):
    def test_empty_week_basic(self):
        r = E.plan_week(ctx())
        d = by_day(r)
        sports = [s["sport"] for s in r["sessions"]]
        self.assertIn("rower", sports)
        longs = [s for s in r["sessions"] if s["is_long"]]
        self.assertEqual(len(longs), 1)
        self.assertGreaterEqual(date.fromisoformat(longs[0]["day"]).weekday(), 5)
        # sila nie dzien po dniu
        sd = sorted(date.fromisoformat(s["day"]) for s in r["sessions"] if s["sport"] == "sila")
        self.assertTrue(all((b - a).days >= 2 for a, b in zip(sd, sd[1:])))
        # min 1 dzien bez treningu (joga sie nie liczy)
        train_days = {s["day"] for s in r["sessions"] if s["sport"] != "joga"}
        self.assertLessEqual(len(train_days), 6)
        self.assertLessEqual(r["planned_h"], r["target_h"] + 1.5)

    def test_busy_respected(self):
        rules = [{"kind": "busy", "name": "syn", "icon": "🚗", "period": {"m": "all"},
                  "windows": [{"d": [1, 1, 1, 1, 1, 1, 1], "k": "h", "a": "07:00", "b": "12:00", "ac": []}]}]
        r = E.plan_week(ctx(rules=rules))
        for s in r["sessions"]:
            self.assertGreaterEqual(E.hm(s["start_time"]), 12 * 60, s)

    def test_pref_window_by_sport(self):
        rules = [{"kind": "pref", "name": "okna", "period": {"m": "all"}, "windows": [
            {"d": [1, 1, 1, 1, 1, 0, 0], "k": "h", "a": "09:00", "b": "12:00", "ac": ["joga"]},
            {"d": [1, 1, 1, 1, 1, 0, 0], "k": "h", "a": "12:00", "b": "15:00", "ac": ["rower"]}]}]
        r = E.plan_week(ctx(rules=rules))
        for s in r["sessions"]:
            if date.fromisoformat(s["day"]).weekday() < 5 and s["sport"] == "rower":
                self.assertTrue(12 * 60 <= E.hm(s["start_time"]) < 15 * 60, s)
            if date.fromisoformat(s["day"]).weekday() < 5 and s["sport"] == "joga":
                self.assertTrue(9 * 60 <= E.hm(s["start_time"]) < 12 * 60, s)

    def test_rest_day_from_calendar(self):
        cal = [{"day": "2026-10-07", "end_day": None, "kind": "event", "event_type": "rest", "title": "", "at_time": None}]
        r = E.plan_week(ctx(calendar=cal))
        self.assertNotIn("2026-10-07", by_day(r))
        self.assertEqual(r["days"]["2026-10-07"]["type"], "rest")

    def test_delegation_only_short_yoga(self):
        cal = [{"day": "2026-10-06", "end_day": "2026-10-07", "kind": "event", "event_type": "delegacja", "title": "", "at_time": None}]
        r = E.plan_week(ctx(calendar=cal))
        for d in ("2026-10-06", "2026-10-07"):
            ss = by_day(r).get(d, [])
            self.assertTrue(all(s["sport"] == "joga" and s["dur_min"] <= 15 for s in ss), ss)

    def test_bad_weather_moves_long_ride(self):
        wx = {"2026-10-10": {"wind": 11}, "2026-10-11": {"wind": 3}}
        r = E.plan_week(ctx(weather=wx, ov={"wx.wind_ms": 7}))
        longs = [s for s in r["sessions"] if s["is_long"]]
        self.assertEqual(longs[0]["day"], "2026-10-11")

    def test_low_readiness_cuts_today(self):
        r = E.plan_week(ctx(readiness_today=-1.0, readiness_threshold=-0.6))
        for s in by_day(r).get("2026-10-05", []):
            if s["sport"] != "joga":
                self.assertTrue(s["cut"])
        self.assertTrue(any("gotowość" in n for n in r["notes"]))

    def test_trip_days_from_goal(self):
        goals = [{"kind": "trip", "name": "Wyprawa", "priority": "B", "date_from": "2026-10-09", "date_to": "2026-10-11", "status": "active"}]
        r = E.plan_week(ctx(goals=goals))
        for d in ("2026-10-09", "2026-10-10", "2026-10-11"):
            self.assertTrue(all(s["sport"] == "joga" for s in by_day(r).get(d, [])))

    def test_keep_manual_consumes_budget(self):
        keep = [{"day": "2026-10-10", "sport": "rower", "name": "Moja jazda", "start_time": "08:00", "dur_min": 240, "status": "plan", "is_long": True}]
        r = E.plan_week(ctx(keep=keep))
        self.assertFalse(any(s["day"] == "2026-10-10" and s["sport"] == "rower" for s in r["sessions"]))

    def test_past_days_not_planned(self):
        r = E.plan_week(ctx(today=date(2026, 10, 8)))
        self.assertTrue(all(s["day"] >= "2026-10-08" for s in r["sessions"]))

    def test_check_rules(self):
        w = E.check_rules([{"day": "2026-10-05", "sport": "sila"}, {"day": "2026-10-06", "sport": "sila"}], {})
        self.assertTrue(any("siła" in x for x in w))

    def test_season_taper_before_A(self):
        goals = [{"kind": "trip", "name": "A", "priority": "A", "date_from": "2027-05-14", "date_to": "2027-05-22", "status": "active"}]
        W = E.season_weeks(goals, {}, date(2026, 9, 28))
        ph = {w["s"].isoformat(): w["ph"] for w in W}
        self.assertEqual(ph["2027-04-26"], "tp")
        self.assertEqual(ph["2027-05-10"], "ev")
        self.assertEqual(ph["2027-05-24"], "rg")


class TestSeasonModel(unittest.TestCase):
    G = [{"kind": "trip", "name": "Badlands", "priority": "A", "date_from": "2027-05-14", "date_to": "2027-05-22", "status": "active"},
         {"kind": "trip", "name": "Wrzesien", "priority": "A", "date_from": "2027-09-04", "date_to": "2027-09-12", "status": "active"}]

    def test_start_first_workday_after_xmas(self):
        self.assertEqual(E.first_workday_after_xmas(2026), date(2026, 12, 28))   # 27.12.2026 = niedziela
        self.assertEqual(E.first_workday_after_xmas(2027), date(2027, 12, 27))   # poniedzialek

    def test_season_of(self):
        self.assertEqual(E.season_of(date(2026, 12, 20), {}), 2026)
        self.assertEqual(E.season_of(date(2026, 12, 28), {}), 2027)

    def test_bounds_auto_and_override(self):
        b = E.season_bounds(2027, {}, self.G)
        self.assertEqual(b["start"], date(2026, 12, 28))
        self.assertEqual(b["luz"], date(2027, 12, 12))
        self.assertEqual(b["roz"], date(2027, 10, 1))                 # 12.09 + 2 tyg. regeneracji < 1.10
        o = E.season_bounds(2027, {"season.2027.luz": "2027-12-15", "season.2027.start": "2027-01-04"}, self.G)
        self.assertEqual((o["start"], o["luz"]), (date(2027, 1, 4), date(2027, 12, 15)))
        self.assertFalse(o["auto"]["luz"])

    def test_timeline_2026_2027(self):
        W = E.season_weeks(self.G, {}, date(2026, 9, 21), 70)
        ph = {w["s"].isoformat(): (w["ph"], w["season"]) for w in W}
        self.assertEqual(ph["2026-09-21"], ("sz", 2026))    # koncowka sezonu 2026 (jazda, bez A)
        self.assertEqual(ph["2026-10-05"], ("rt", 2026))    # roztrenowanie od 1.10
        self.assertEqual(ph["2026-12-14"], ("lz", 2026))    # totalny luz od 12.12
        self.assertEqual(ph["2026-12-28"], ("bz", 2027))    # start sezonu 2027 = baza
        self.assertEqual(ph["2027-05-10"][0], "ev")
        self.assertEqual(ph["2027-10-04"][0], "rt")
        self.assertEqual(ph["2027-12-13"][0], "lz")

    def test_luz_no_plan(self):
        r = E.plan_week(ctx(week_start=date(2026, 12, 14), today=date(2026, 12, 14)))
        self.assertEqual(r["phase"], "lz")
        self.assertEqual(r["sessions"], [])


if __name__ == "__main__":
    unittest.main()
