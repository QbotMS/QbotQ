"""[GARMIN-DANE] extract_extra: pola z pelnych odpowiedzi Garmina (snu/HRV)."""
import sys
import unittest

sys.path.insert(0, "/opt/qbot/app")

from qbot_garmin_extra import EXTRA_COLUMNS, extract_extra  # noqa: E402

SLEEP = {
    "dailySleepDTO": {
        "sleepNeed": {"baseline": 450, "actual": 450, "feedback": "NO_CHANGE_NO_ADJUSTMENTS"},
        "nextSleepNeed": {"baseline": 450, "actual": 510, "feedback": "HIGHLY_INCREASED"},
    },
    "skinTempDataExists": True,
    "avgSkinTempDeviationC": -0.1,
    "hrvStatus": "BALANCED",
}
HRV = {"hrvSummary": {"weeklyAvg": 79, "status": "BALANCED",
                      "baseline": {"lowUpper": 73, "balancedLow": 76, "balancedUpper": 89}}}


class TestExtractExtra(unittest.TestCase):
    def test_full(self):
        e = extract_extra(SLEEP, HRV)
        self.assertEqual(e["skin_temp_dev_c"], -0.1)
        self.assertEqual(e["sleep_need_min"], 450)
        self.assertEqual(e["next_sleep_need_min"], 510)
        self.assertEqual(e["next_sleep_need_feedback"], "HIGHLY_INCREASED")
        self.assertEqual(e["garmin_hrv_status"], "BALANCED")
        self.assertEqual(e["hrv_weekly_avg"], 79.0)
        self.assertEqual((e["hrv_balanced_low"], e["hrv_balanced_high"]), (76.0, 89.0))
        self.assertEqual(set(e), set(EXTRA_COLUMNS))

    def test_empty_and_errors(self):
        for s, h in ((None, None), ({}, {}), ("x", [1]), ({"dailySleepDTO": None}, {"hrvSummary": None})):
            e = extract_extra(s, h)
            self.assertTrue(all(v is None for v in e.values()), e)

    def test_skin_flag_false_ignored(self):
        e = extract_extra({"skinTempDataExists": False, "avgSkinTempDeviationC": 0.0}, None)
        self.assertIsNone(e["skin_temp_dev_c"])

    def test_zero_skin_kept(self):
        e = extract_extra({"skinTempDataExists": True, "avgSkinTempDeviationC": 0.0}, None)
        self.assertEqual(e["skin_temp_dev_c"], 0.0)

    def test_hrv_status_fallback_from_sleep(self):
        e = extract_extra({"hrvStatus": "UNBALANCED"}, {})
        self.assertEqual(e["garmin_hrv_status"], "UNBALANCED")


if __name__ == "__main__":
    unittest.main()
