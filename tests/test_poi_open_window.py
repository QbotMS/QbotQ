#!/usr/bin/env python3
from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta

from tools.rwgps.poi_open_window import osm_open_at, parse_osm_opening_hours


WARSAW = timezone(timedelta(hours=2))


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(WARSAW)


class TestPoiOpenWindowParsing(unittest.TestCase):
    def test_polish_weekday_and_single_window(self):
        parsed = parse_osm_opening_hours("wtorek 5:30–18:00")
        self.assertIsNotNone(parsed)
        self.assertTrue(osm_open_at(parsed, _dt("2026-06-30T12:00:00+02:00")))

    def test_polish_weekday_and_multi_window(self):
        parsed = parse_osm_opening_hours("wtorek 5:00–13:30 i 16:00–19:30")
        self.assertIsNotNone(parsed)
        self.assertFalse(osm_open_at(parsed, _dt("2026-06-30T13:45:00+02:00")))

    def test_midnight_close_is_open_until_end_of_day(self):
        parsed = parse_osm_opening_hours("wtorek 6:00–00:00")
        self.assertIsNotNone(parsed)
        self.assertTrue(osm_open_at(parsed, _dt("2026-06-30T14:19:00+02:00")))

    def test_english_abbreviation_still_works(self):
        parsed = parse_osm_opening_hours("Mo-Fr 07:00-19:00; Sa 07:00-20:00; Su 10:00-17:00")
        self.assertIsNotNone(parsed)
        self.assertTrue(osm_open_at(parsed, _dt("2026-06-30T14:10:00+02:00")))

    def test_google_style_weekday_text_with_ampm(self):
        parsed = parse_osm_opening_hours(
            "Monday: 5:30 AM – 6:00 PM; Tuesday: 5:30 AM – 6:00 PM; Sunday: Closed"
        )
        self.assertIsNotNone(parsed)
        self.assertTrue(osm_open_at(parsed, _dt("2026-06-30T12:00:00+02:00")))
        self.assertFalse(osm_open_at(parsed, _dt("2026-06-30T19:30:00+02:00")))


if __name__ == "__main__":
    unittest.main()
