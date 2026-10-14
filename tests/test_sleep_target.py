"""[GARMIN-DANE] Etap 5: wlasny cel snu + analiza pobudek przed budzikiem."""
import sys
import unittest
from datetime import date, datetime, time, timedelta

sys.path.insert(0, "/opt/qbot/app")

from fitmodel.sleep_target import compare, compose, hm, pick_base, wake_button  # noqa: E402


class TestBase(unittest.TestCase):
    def test_threshold_found(self):
        pairs = [(400 + (i % 60), -1.0) for i in range(60)] + [(465 + (i % 30), 3.0) for i in range(40)]
        self.assertEqual(pick_base(pairs), 465)

    def test_default_when_little_data(self):
        self.assertEqual(pick_base([(480, 3.0)] * 10), 465)

    def test_clamped(self):
        pairs = [(380, -2.0)] * 30 + [(410, 2.0)] * 30
        self.assertGreaterEqual(pick_base(pairs), 420)


class TestCompose(unittest.TestCase):
    def test_plain(self):
        t = compose(465, False, False)
        self.assertEqual((t["target"], t["bedtime"], t["alarm"]), (465, "23:10", "07:10"))

    def test_adds_and_cap(self):
        t = compose(465, True, True)
        self.assertEqual(t["add"], 60)
        self.assertEqual(t["bedtime"], "22:10")
        self.assertEqual(t["reasons"], ["ciężki dzień", "organizm pod obciążeniem"])

    def test_hm(self):
        self.assertEqual(hm(465), "7 h 45")


class TestCompare(unittest.TestCase):
    def _row(self, i, label=False, early=False, xss=40):
        d = date(2026, 1, 1) + timedelta(days=i)
        en = datetime.combine(d, time(6, 0) if early else time(7, 10))
        return {"date": d, "dur": 360 if early else 440, "en": en, "st_min": 360, "t": 0.0, "dh": 0.0, "dr": 0.0,
                "stres": 35, "xss": xss, "last_end": time(17, 0), "lokal": True,
                "fs": datetime.combine(d, time(8, 0)), "label": label}

    def test_rule_mode_without_labels(self):
        rows = [self._row(i, early=(i % 4 == 0), xss=(120 if i % 4 == 0 else 40)) for i in range(40)]
        mode, a, b, ne, nr = compare(rows, set())
        self.assertTrue(mode.startswith("reguła"))
        self.assertEqual((ne, nr), (10, 30))
        self.assertGreater(a["xss"], b["xss"])

    def test_label_mode(self):
        rows = [self._row(i, label=(i < 12)) for i in range(40)]
        mode, a, b, ne, nr = compare(rows, {date(2026, 1, 1)})
        self.assertEqual(mode, "oznaczenia")
        self.assertEqual((ne, nr), (12, 28))
        self.assertGreater(a["alk"], b["alk"])   # alkohol 01.01 -> noc konczaca sie 02.01 (oznaczona)

    def test_button(self):
        b = wake_button(date(2026, 10, 15))
        self.assertEqual(b[0][0]["callback_data"], "tr:wake:20261015")


if __name__ == "__main__":
    unittest.main()
